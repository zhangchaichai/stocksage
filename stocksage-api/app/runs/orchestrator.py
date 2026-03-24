"""RunOrchestrator: 管理工作流执行生命周期，支持流式输出和断线重连。

替代 worker.py 的 ThreadPool 模式，使用 asyncio.Task + Queue 实现
Producer-Consumer 架构。Producer 在后台执行工作流，Consumer 通过
SSE endpoint 推送事件给前端。

Key design:
- Producer 独立于 Consumer 生命周期（断线不停止执行）
- 事件双写: Queue (实时推送) + DB (持久化，用于断线重连回放)
- ResponseBuffer 聚合 LLM token chunk 为段落
- Phase 2: execute_streaming() 逐 token 推送 skill_chunk 事件
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import uuid as uuid_mod
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.db.models import RunEvent, Workflow, WorkflowRun
from app.db.session import async_session_factory
from app.runs.buffer import ResponseBuffer
from app.runs.interaction import InteractionManager

logger = logging.getLogger(__name__)

_engine_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="orchestrator-engine")


@dataclass
class RunContext:
    """单次运行的上下文。"""

    run_id: UUID
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    task: asyncio.Task | None = None
    buffer: ResponseBuffer = field(default_factory=ResponseBuffer)
    current_phase: str = ""
    is_done: bool = False

    async def emit(self, event_type: str, **kwargs: Any) -> None:
        """推送事件到 Queue + 持久化到 DB。"""
        now = datetime.now(timezone.utc)
        data = {
            "event": event_type,
            "run_id": str(self.run_id),
            "timestamp": now.isoformat(),
            **kwargs,
        }

        # 通过 Buffer 处理（聚合 skill_chunk）
        processed_events = self.buffer.process(data)

        for evt in processed_events:
            # 持久化到 DB
            await self._persist_event(evt)
            # 推送给 Consumer
            try:
                self.queue.put_nowait(evt)
            except asyncio.QueueFull:
                pass  # Consumer 断开或太慢，丢弃即可（DB 有完整记录）

    async def _persist_event(self, event: dict) -> None:
        """持久化事件到 DB。"""
        try:
            async with async_session_factory() as db:
                db_event = RunEvent(
                    run_id=self.run_id,
                    event_type=event.get("event", "unknown"),
                    node_name=event.get("skill_name"),
                    phase=event.get("phase", self.current_phase),
                    payload={
                        k: v for k, v in event.items()
                        if k not in ("event", "run_id", "timestamp")
                    },
                    item_id=event.get("item_id"),
                )
                db.add(db_event)
                await db.commit()
        except Exception as e:
            logger.warning("Failed to persist event: %s", e)


class RunOrchestrator:
    """管理工作流执行生命周期，支持流式输出和断线重连。"""

    def __init__(self, config_manager: Any = None, model_factory: Any = None):
        self._active_runs: dict[str, RunContext] = {}
        self._config_manager = config_manager
        self._model_factory = model_factory
        self._interactions = InteractionManager()

    async def start_run(
        self,
        run_id: UUID,
        workflow_name: str,
        workflow_definition: dict,
        symbol: str,
        stock_name: str = "",
        owner_id: UUID | None = None,
    ) -> None:
        """启动后台 Producer Task。"""
        ctx = RunContext(run_id=run_id)
        self._active_runs[str(run_id)] = ctx
        ctx.task = asyncio.create_task(
            self._producer(ctx, workflow_name, workflow_definition,
                           symbol, stock_name, owner_id),
            name=f"run-{run_id}",
        )

    async def stream_events(self, run_id: UUID) -> AsyncGenerator[dict, None]:
        """Consumer: 从 Queue 读取事件，yield 给 SSE endpoint。

        支持断线重连: 客户端断开后 Producer 继续执行;
        客户端重连时，从 DB 读取已持久化的事件回放，然后接续 Queue。
        """
        ctx = self._active_runs.get(str(run_id))

        if ctx is None:
            # 运行已结束或不存在，从 DB 读取历史事件
            async for event in self._replay_from_db(run_id):
                yield event
            return

        while True:
            try:
                event = await asyncio.wait_for(ctx.queue.get(), timeout=20)
            except asyncio.TimeoutError:
                if ctx.is_done:
                    break
                # 心跳保活
                yield {
                    "event": "heartbeat",
                    "data": {"run_id": str(run_id)},
                }
                continue

            yield event
            if event.get("event") in ("run_completed", "run_failed"):
                break

    def is_run_active(self, run_id: UUID) -> bool:
        """检查运行是否正在执行。"""
        return str(run_id) in self._active_runs

    async def respond_to_interaction(self, run_id: UUID, response: str) -> bool:
        """向等待中的交互请求投递用户响应。

        Returns:
            True if response delivered, False if no pending interaction.
        """
        return self._interactions.respond(str(run_id), response)

    @property
    def interactions(self) -> InteractionManager:
        """获取交互管理器。"""
        return self._interactions

    async def _producer(
        self,
        ctx: RunContext,
        workflow_name: str,
        workflow_definition: dict,
        symbol: str,
        stock_name: str,
        owner_id: UUID | None,
    ) -> None:
        """后台任务: 编译 + 执行工作流，推送事件到 Queue。"""
        try:
            await ctx.emit("run_started", skill_name=None,
                           phase="init", payload={"symbol": symbol})

            # 执行工作流
            result = await self._execute_workflow(
                ctx, workflow_name, workflow_definition,
                symbol, stock_name, owner_id,
            )

            # 存储结果
            await self._finalize(ctx, result, owner_id)

            await ctx.emit("run_completed", phase="completed",
                           payload={"summary": result.get("summary", "")})

        except Exception as e:
            logger.exception("Run %s failed: %s", ctx.run_id, e)
            await ctx.emit("run_failed", payload={"error": str(e)})

            # 更新 DB 状态为 failed
            try:
                async with async_session_factory() as db:
                    from app.runs.service import get_run, update_run_status
                    run = await get_run(db, ctx.run_id)
                    if run:
                        await update_run_status(
                            db, run, "failed",
                            error_message=str(e),
                            completed_at=datetime.now(timezone.utc),
                        )
                        await db.commit()
            except Exception as db_err:
                logger.warning("Failed to update run status to failed: %s", db_err)

        finally:
            ctx.is_done = True
            self._interactions.cleanup(str(ctx.run_id))
            self._active_runs.pop(str(ctx.run_id), None)

    async def _execute_workflow(
        self,
        ctx: RunContext,
        workflow_name: str,
        workflow_definition: dict,
        symbol: str,
        stock_name: str,
        owner_id: UUID | None,
    ) -> dict:
        """编译并执行工作流，支持 token 级流式推送。

        使用 LangGraph 编译图但替换节点函数为流式版本，通过
        progress_callback + on_chunk 实时推送事件到 SSE 消费端。
        """
        from stocksage.data.fetcher import DataFetcher
        from stocksage.llm.factory import ModelFactory, create_llm
        from stocksage.skill_engine.executor import SkillExecutor
        from stocksage.skill_engine.registry import SkillRegistry
        from stocksage.workflow.compiler import WorkflowCompiler

        # 初始化组件
        factory = self._model_factory
        if factory:
            llm = factory.create_model()
        else:
            from app.config import settings
            provider = settings.DEFAULT_LLM_PROVIDER or "deepseek"
            llm = create_llm(provider)

        mcp_manager = None
        try:
            from stocksage.mcp.client_manager import MCPClientManager
            mcp_manager = MCPClientManager()
        except Exception:
            pass

        fetcher = DataFetcher(mcp_manager=mcp_manager)

        tool_bridge = None
        if mcp_manager:
            try:
                from stocksage.mcp.tool_bridge import ToolBridge
                tool_bridge = ToolBridge(mcp_manager=mcp_manager)
            except Exception:
                pass

        executor = SkillExecutor(llm, fetcher, tool_bridge=tool_bridge)
        registry = SkillRegistry()

        skills_dir = Path(__file__).resolve().parents[2] / "stocksage" / "skills"
        if not skills_dir.exists():
            import stocksage
            skills_dir = Path(stocksage.__file__).parent / "skills"
        registry.load_from_dir(skills_dir)

        # 加载工作流
        yaml_path = self._resolve_workflow_yaml(workflow_name)
        if yaml_path:
            definition = WorkflowCompiler.load(yaml_path)
        else:
            from app.runs.worker import _api_def_to_compiler_dict
            compiler_dict = _api_def_to_compiler_dict(workflow_name, workflow_definition)
            definition = WorkflowCompiler.load(compiler_dict)

        # collect_data 自定义节点
        def collect_data_fn(state: dict) -> dict:
            from stocksage.workflow.engine import WorkflowEngine
            engine_instance = WorkflowEngine.__new__(WorkflowEngine)
            engine_instance._fetcher = fetcher
            return engine_instance._collect_data(state)

        # 验证
        errors = WorkflowCompiler.validate(definition, registry)
        if errors:
            logger.warning("Workflow validation warnings: %s", errors)

        # 构建流式 progress_callback: 同步回调 → 异步事件推送
        # 用队列桥接同步/异步边界
        progress_queue: asyncio.Queue = asyncio.Queue()
        streaming_chunks_queue: asyncio.Queue = asyncio.Queue()

        def progress_callback(node_name: str, status: str) -> None:
            try:
                progress_queue.put_nowait((node_name, status))
            except Exception:
                pass

        # 为 LLM skills 创建流式节点函数
        from stocksage.workflow.nodes import make_streaming_skill_node

        # 编译（使用流式节点）
        compiled = WorkflowCompiler.compile(
            definition, executor, registry,
            collect_data_fn=collect_data_fn,
            progress_callback=progress_callback,
            node_factory=functools.partial(
                make_streaming_skill_node,
                executor=executor,
                factory=factory,
                streaming_queue=streaming_chunks_queue,
            ),
        )

        # 记忆召回
        ctx.current_phase = "memory_recall"
        await ctx.emit("phase_changed", phase="memory_recall")

        memory_context: dict = {}
        if owner_id:
            try:
                memory_context = await self._recall_memory(owner_id, symbol)
            except Exception as e:
                logger.warning("Memory recall failed: %s", e)

        # 执行工作流
        ctx.current_phase = "execution"
        await ctx.emit("phase_changed", phase="execution")

        loop = asyncio.get_event_loop()

        # 启动后台线程执行同步 LangGraph 图
        run_future = loop.run_in_executor(
            _engine_pool,
            functools.partial(
                compiled.run, symbol, stock_name,
                memory_context=memory_context,
            ),
        )

        # 同时消费 progress 和 streaming chunk 事件
        done = False
        while not done:
            # Drain progress events
            while not progress_queue.empty():
                try:
                    node_name, status = progress_queue.get_nowait()
                    event_type = "skill_started" if status == "started" else "skill_completed"
                    if status == "failed":
                        event_type = "skill_failed"
                    await ctx.emit(event_type, skill_name=node_name)
                except Exception:
                    break

            # Drain streaming chunk events
            while not streaming_chunks_queue.empty():
                try:
                    skill_name, chunk = streaming_chunks_queue.get_nowait()
                    await ctx.emit("skill_chunk", skill_name=skill_name, payload=chunk)
                except Exception:
                    break

            # 检查 LangGraph 执行是否完成
            if run_future.done():
                done = True
            else:
                await asyncio.sleep(0.05)

        # 最终 drain
        while not progress_queue.empty():
            try:
                node_name, status = progress_queue.get_nowait()
                event_type = "skill_started" if status == "started" else "skill_completed"
                if status == "failed":
                    event_type = "skill_failed"
                await ctx.emit(event_type, skill_name=node_name)
            except Exception:
                break

        while not streaming_chunks_queue.empty():
            try:
                skill_name, chunk = streaming_chunks_queue.get_nowait()
                await ctx.emit("skill_chunk", skill_name=skill_name, payload=chunk)
            except Exception:
                break

        raw_result = run_future.result()

        # 序列化结果
        from app.runs.worker import _serialize_result
        return _serialize_result(raw_result)

    async def _recall_memory(self, user_id: UUID, symbol: str) -> dict:
        """异步召回记忆上下文。"""
        from app.memory.recall import recall_memory_compact
        async with async_session_factory() as db:
            return await recall_memory_compact(db, user_id, symbol)

    async def _finalize(
        self,
        ctx: RunContext,
        result: dict,
        owner_id: UUID | None,
    ) -> None:
        """存储结果、提取记忆。"""
        async with async_session_factory() as db:
            from app.runs.service import get_run, update_run_status

            run = await get_run(db, ctx.run_id)
            if run is None:
                return

            await update_run_status(
                db, run, "completed",
                result=result,
                completed_at=datetime.now(timezone.utc),
            )

            # 记忆提取
            if owner_id:
                try:
                    from app.memory.extractor import ingest_from_run
                    await ingest_from_run(
                        db,
                        user_id=owner_id,
                        symbol=run.symbol,
                        stock_name=run.stock_name,
                        run_result=result,
                        run_id=run.id,
                    )
                    logger.info("Memory ingested for run %s (%s)", ctx.run_id, run.symbol)
                except Exception as e:
                    logger.warning("Memory ingestion failed: %s", e)

            await db.commit()

    async def _replay_from_db(self, run_id: UUID) -> AsyncGenerator[dict, None]:
        """从 DB 回放已持久化的事件 (用于断线重连)。"""
        from sqlalchemy import select

        async with async_session_factory() as db:
            q = (
                select(RunEvent)
                .where(RunEvent.run_id == run_id)
                .order_by(RunEvent.created_at.asc())
            )
            result = await db.execute(q)
            events = result.scalars().all()

            for event in events:
                yield {
                    "event": event.event_type,
                    "run_id": str(run_id),
                    "skill_name": event.node_name,
                    "phase": event.phase,
                    "item_id": event.item_id,
                    "timestamp": event.created_at.isoformat() if event.created_at else "",
                    **(event.payload or {}),
                }

    @staticmethod
    def _resolve_workflow_yaml(workflow_name: str) -> Path | None:
        """查找内置工作流 YAML。"""
        import stocksage
        workflows_dir = Path(stocksage.__file__).parent / "workflows"
        for suffix in (".yaml", ".yml"):
            candidate = workflows_dir / f"{workflow_name}{suffix}"
            if candidate.exists():
                return candidate
        return None


# ---- Module-level singleton ----

_orchestrator: RunOrchestrator | None = None


def get_orchestrator() -> RunOrchestrator:
    """获取全局 RunOrchestrator 单例。"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RunOrchestrator()
    return _orchestrator


def init_orchestrator(
    config_manager: Any = None,
    model_factory: Any = None,
) -> RunOrchestrator:
    """初始化全局 RunOrchestrator (在 app lifespan 中调用)。"""
    global _orchestrator
    _orchestrator = RunOrchestrator(
        config_manager=config_manager,
        model_factory=model_factory,
    )
    return _orchestrator
