"""Background worker for executing workflow runs.

In production this would be an ARQ worker process. For now, we use
asyncio.create_task for simplicity and testability — the ARQ integration
can be layered on top without changing the core logic.

This module integrates with the core stocksage engine:
  - Uses WorkflowCompiler to compile workflow definitions
  - Runs the LangGraph engine in a thread pool (sync → async bridge)
  - Records progress events and stores the full analysis result
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.config import settings
from app.db.models import RunEvent, Workflow, WorkflowRun
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# Load environment variables from parent .env (for DEEPSEEK_API_KEY etc.)
load_dotenv(Path(__file__).resolve().parents[3] / ".env")
load_dotenv()  # Also load local .env

# Thread pool for running synchronous LangGraph engine
_engine_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stocksage-engine")


def _init_engine_components():
    """Lazily initialize the core stocksage engine components.

    Returns (registry, executor, fetcher, skills_dir) or None if unavailable.
    """
    try:
        from stocksage.data.fetcher import DataFetcher
        from stocksage.llm.factory import create_llm
        from stocksage.skill_engine.executor import SkillExecutor
        from stocksage.skill_engine.registry import SkillRegistry

        provider = settings.DEFAULT_LLM_PROVIDER or "deepseek"
        llm = create_llm(provider)

        # MCP initialization (optional, degrades gracefully)
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
            # Try relative to the stocksage package
            import stocksage
            skills_dir = Path(stocksage.__file__).parent / "skills"
        count = registry.load_from_dir(skills_dir)
        logger.info("Loaded %d skills from %s", count, skills_dir)

        return registry, executor, fetcher, skills_dir
    except Exception as e:
        logger.warning("Failed to initialize stocksage engine: %s", e)
        return None


# Lazy singleton
_engine_components = None


def _get_engine():
    global _engine_components
    if _engine_components is None:
        _engine_components = _init_engine_components()
    return _engine_components


def _resolve_workflow_yaml(workflow_name: str) -> Path | None:
    """Try to find a built-in workflow YAML matching the name."""
    import stocksage
    workflows_dir = Path(stocksage.__file__).parent / "workflows"

    for suffix in (".yaml", ".yml"):
        candidate = workflows_dir / f"{workflow_name}{suffix}"
        if candidate.exists():
            return candidate

    return None


def _run_engine_sync(
    workflow_name: str,
    workflow_definition: dict,
    symbol: str,
    stock_name: str,
    progress_callback,
) -> dict:
    """Run the stocksage engine synchronously (called from thread pool).

    Tries the WorkflowCompiler with a built-in YAML first, then falls back
    to the legacy WorkflowEngine.
    """
    components = _get_engine()
    if components is None:
        raise RuntimeError("StockSage engine not available")

    registry, executor, fetcher, skills_dir = components

    from stocksage.workflow.compiler import WorkflowCompiler

    # Try to find a built-in YAML workflow
    yaml_path = _resolve_workflow_yaml(workflow_name)

    if yaml_path:
        logger.info("Using built-in workflow YAML: %s", yaml_path)
        definition = WorkflowCompiler.load(yaml_path)
    else:
        # Convert the API definition format to the compiler format
        logger.info("Compiling workflow from API definition: %s", workflow_name)
        compiler_dict = _api_def_to_compiler_dict(workflow_name, workflow_definition)
        definition = WorkflowCompiler.load(compiler_dict)

    # Provide collect_data custom node
    def collect_data_fn(state: dict) -> dict:
        from stocksage.workflow.engine import WorkflowEngine
        engine_instance = WorkflowEngine.__new__(WorkflowEngine)
        engine_instance._fetcher = fetcher
        return engine_instance._collect_data(state)

    # Validate
    errors = WorkflowCompiler.validate(definition, registry)
    if errors:
        logger.warning("Workflow validation warnings: %s", errors)

    # Compile and run
    compiled = WorkflowCompiler.compile(
        definition, executor, registry,
        collect_data_fn=collect_data_fn,
        progress_callback=progress_callback,
    )

    return compiled.run(symbol, stock_name)


def _api_def_to_compiler_dict(name: str, api_def: dict) -> dict:
    """Convert API workflow definition format to the WorkflowCompiler dict format.

    API format:
      nodes: [{id, skill, config?}]
      edges: [{from, to, type?, condition?}]

    Compiler format:
      nodes: [{name, skill, type?}]
      edges: [{source, target, type?}]
    """
    compiler_nodes = []
    for node in api_def.get("nodes", []):
        node_name = node.get("id") or node.get("name", "")
        compiler_nodes.append({
            "name": node_name,
            "skill": node.get("skill", node_name),
            "type": "custom" if node_name == "collect_data" else "skill",
        })

    compiler_edges = []
    for edge in api_def.get("edges", []):
        source = edge.get("from") or edge.get("source", "")
        target = edge.get("to") or edge.get("target", "")
        edge_type = edge.get("type", "serial")

        compiler_edges.append({
            "source": source,
            "target": target,
            "type": edge_type,
        })

    return {
        "name": name,
        "version": api_def.get("version", "1.0.0"),
        "nodes": compiler_nodes,
        "edges": compiler_edges,
        "custom_nodes": {"collect_data": "engine._collect_data"},
    }


def _serialize_result(raw_result: dict) -> dict:
    """Serialize the LangGraph result state to a JSON-safe dict for storage."""
    result = {}
    # Extract the key sections
    for key in ("meta", "decision", "analysis", "debate", "expert_panel",
                "errors", "current_phase"):
        if key in raw_result:
            val = raw_result[key]
            # Ensure it's JSON-serializable
            try:
                json.dumps(val, ensure_ascii=False)
                result[key] = val
            except (TypeError, ValueError):
                result[key] = str(val)

    # Add summary from decision
    decision = result.get("decision", {})
    if isinstance(decision, dict):
        result["summary"] = decision.get("core_logic", "Analysis completed")
        result["recommendation"] = decision.get("recommendation", "")
        result["confidence"] = decision.get("confidence", "")
    else:
        result["summary"] = "Analysis completed"

    result["symbol"] = raw_result.get("meta", {}).get("symbol", "")
    result["stock_name"] = raw_result.get("meta", {}).get("stock_name", "")
    result["status"] = "completed"

    return result


async def execute_run(run_id: uuid.UUID) -> None:
    """Execute a queued workflow run.

    Tries to use the real stocksage engine. Falls back to simulation
    if the engine is not available.
    """
    async with async_session_factory() as db:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.runs.service import get_run, update_run_status

        run = await get_run(db, run_id)
        if run is None or run.status != "queued":
            return

        # Load workflow definition
        wf_result = await db.execute(
            select(Workflow).where(Workflow.id == run.workflow_id)
        )
        workflow = wf_result.scalar_one_or_none()
        workflow_name = workflow.name if workflow else "quick_analysis"
        workflow_definition = workflow.definition if workflow else {}

        # Mark as running
        run = await update_run_status(db, run, "running", started_at=datetime.now(timezone.utc))
        await db.commit()

        try:
            # Publish start event
            await _record_event(db, run.id, "run_start", payload={"symbol": run.symbol})
            await db.commit()

            # Try the real engine
            engine = _get_engine()
            if engine is not None:
                logger.info("Running real engine for %s (%s)", run.symbol, workflow_name)

                # Collect progress events to record after engine finishes
                progress_events: list[tuple[str, str]] = []

                def progress_callback(node_name: str, status: str) -> None:
                    progress_events.append((node_name, status))
                    logger.info("  [%s] %s: %s", run.symbol, node_name, status)

                # Run engine in thread pool (LangGraph is synchronous)
                loop = asyncio.get_event_loop()
                raw_result = await loop.run_in_executor(
                    _engine_pool,
                    functools.partial(
                        _run_engine_sync,
                        workflow_name,
                        workflow_definition,
                        run.symbol,
                        run.stock_name,
                        progress_callback,
                    ),
                )

                # Record progress events
                for node_name, status in progress_events:
                    event_type = "node_start" if status == "started" else "node_complete"
                    if status == "failed":
                        event_type = "node_error"
                    await _record_event(db, run.id, event_type, node_name=node_name)
                await db.commit()

                result = _serialize_result(raw_result)
            else:
                # Fallback: simulation
                logger.info("Engine not available, simulating run for %s", run.symbol)
                await _simulate_execution(db, run)
                result = {
                    "symbol": run.symbol,
                    "stock_name": run.stock_name,
                    "status": "completed",
                    "summary": f"Analysis completed for {run.symbol} (simulated)",
                }

            await _record_event(db, run.id, "run_complete", payload={
                "summary": result.get("summary", ""),
                "recommendation": result.get("recommendation", ""),
            })
            run = await update_run_status(
                db, run, "completed",
                result=result,
                completed_at=datetime.now(timezone.utc),
            )
            await db.commit()

        except Exception as e:
            logger.exception("Run %s failed: %s", run_id, e)
            await _record_event(db, run.id, "run_error", payload={"error": str(e)})
            run = await update_run_status(
                db, run, "failed",
                error_message=str(e),
                completed_at=datetime.now(timezone.utc),
            )
            await db.commit()


async def _simulate_execution(db, run: WorkflowRun) -> None:
    """Simulate node execution with events. Replace with real engine later."""
    nodes = ["collect_data", "analyst", "judge"]
    for node in nodes:
        await _record_event(db, run.id, "node_start", node_name=node)
        await asyncio.sleep(0.01)
        await _record_event(db, run.id, "node_complete", node_name=node)


async def _record_event(
    db, run_id: uuid.UUID, event_type: str,
    node_name: str | None = None, phase: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    event = RunEvent(
        run_id=run_id,
        event_type=event_type,
        node_name=node_name,
        phase=phase,
        payload=payload or {},
    )
    db.add(event)
    await db.flush()


# ---- Task dispatcher ----

_background_tasks: set[asyncio.Task] = set()


def dispatch_run(run_id: uuid.UUID) -> None:
    """Fire-and-forget a run execution as a background task."""
    task = asyncio.create_task(execute_run(run_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
