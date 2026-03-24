"""SkillAgent: ReAct 循环引擎。

替代 SkillExecutor 的「模板渲染 → 单次 LLM 调用 → JSON 解析」模式。
SkillAgent 在 while 循环中让 LLM 自主决定调用哪些工具，何时停止。

关键特性：
- ReAct 循环：思考 → 工具调用 → 观察 → 再思考 → ...
- 约束边界：max_iterations, allowed_tools, budget_tokens, timeout
- 进度回调：每次迭代、工具调用、完成时通知外部
- 用户交互：通过 inject_user_context() 注入用户补充信息
- 向后兼容：max_iterations=1 + 空工具列表 ≈ 旧版 SkillExecutor
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

from stocksage.agent.constraints import AgentConstraints
from stocksage.agent.llm_adapter import AgentLLMResponse
from stocksage.skill_engine.models import SkillDef

logger = logging.getLogger(__name__)

# Type for progress callback: (event_type: str, payload: dict) -> None
ProgressCallback = Callable[[str, dict[str, Any]], None]


class SkillAgent:
    """ReAct 循环 Agent — 在工作流节点内部运行。

    Usage:
        agent = SkillAgent(skill, llm, tool_registry, constraints)
        result = await agent.execute(state)
    """

    def __init__(
        self,
        skill: SkillDef,
        llm: Any,
        tool_registry: Any | None = None,
        constraints: AgentConstraints | None = None,
        on_progress: ProgressCallback | None = None,
        interaction_callback: Callable | None = None,
    ):
        self._skill = skill
        self._llm = llm  # LiteLLMAdapter / NanobotLLMAdapter / BaseLLMToolCallingAdapter
        self._tools = tool_registry
        self._constraints = constraints or AgentConstraints()
        self._on_progress = on_progress
        self._interaction_callback = interaction_callback
        self._injected_context: list[str] = []
        self._total_tokens: int = 0
        self._cancelled: bool = False

    def cancel(self) -> None:
        """取消正在执行的 Agent — 下一轮迭代前会检查。"""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def inject_user_context(self, content: str) -> None:
        """用户在运行中补充信息，下一轮迭代会看到。"""
        self._injected_context.append(content)

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """执行 ReAct 循环，返回增量状态更新。"""
        start_time = time.monotonic()
        symbol = state.get("meta", {}).get("symbol", "unknown")

        # Build system prompt
        system_prompt = self._build_system_prompt(state)
        user_prompt = self._build_user_prompt(state)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Get tool definitions (if tools available and allowed)
        tool_defs = self._get_tool_definitions()

        self._emit("agent_started", {
            "tools": [t["function"]["name"] for t in tool_defs] if tool_defs else [],
            "max_iterations": self._constraints.max_iterations,
            "symbol": symbol,
        })

        iteration = 0
        final_content: str | None = None

        while iteration < self._constraints.max_iterations:
            iteration += 1

            # Check cancellation
            if self._cancelled:
                logger.info("[%s] Agent 已被取消", self._skill.name)
                final_content = json.dumps({
                    "warning": "分析已被用户取消",
                    "iterations_completed": iteration - 1,
                }, ensure_ascii=False)
                break

            self._emit("agent_iteration", {
                "iteration": iteration,
                "max_iterations": self._constraints.max_iterations,
            })

            # Check timeout
            elapsed = time.monotonic() - start_time
            if self._constraints.timeout_seconds > 0 and elapsed > self._constraints.timeout_seconds:
                logger.warning("[%s] Agent 超时 (%.1fs)", self._skill.name, elapsed)
                final_content = self._make_timeout_response(iteration, elapsed)
                break

            # Check token budget
            if self._constraints.budget_tokens > 0 and self._total_tokens > self._constraints.budget_tokens:
                logger.warning("[%s] Token 预算超限 (%d/%d)",
                               self._skill.name, self._total_tokens, self._constraints.budget_tokens)
                final_content = self._make_budget_response(iteration)
                break

            # Inject user context if any
            if self._injected_context:
                for ctx in self._injected_context:
                    messages.append({
                        "role": "user",
                        "content": f"[用户补充信息] {ctx}",
                    })
                    self._emit("user_context_injected", {"content": ctx[:100]})
                self._injected_context.clear()

            # Call LLM
            try:
                response: AgentLLMResponse = await self._llm.chat(
                    messages=messages,
                    tools=tool_defs if tool_defs else None,
                    temperature=self._skill.execution.temperature,
                    max_tokens=self._skill.execution.max_tokens,
                )
            except Exception as e:
                logger.error("[%s] LLM 调用失败: %s", self._skill.name, e)
                final_content = json.dumps({
                    "error": f"LLM 调用失败: {e!s}",
                    "iterations_completed": iteration,
                }, ensure_ascii=False)
                break

            # Track tokens
            self._total_tokens += response.usage.get("total_tokens", 0)

            if response.has_tool_calls:
                # Add assistant message with tool calls
                assistant_msg = self._build_assistant_message(response)
                messages.append(assistant_msg)

                # Execute each tool call
                for tc in response.tool_calls:
                    self._emit("agent_tool_call", {
                        "tool": tc.name,
                        "args": tc.arguments,
                    })

                    result = await self._execute_tool(tc.name, tc.arguments)

                    result_str = str(result)
                    # Truncate tool result if needed
                    max_chars = self._constraints.max_tool_result_chars
                    if max_chars > 0 and len(result_str) > max_chars:
                        result_str = result_str[:max_chars] + "\n...(结果过长已截断)"
                    self._emit("agent_tool_result", {
                        "tool": tc.name,
                        "result_length": len(result_str),
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": result_str,
                    })

                # Emit thinking if present
                if response.content:
                    self._emit("agent_thinking", {"thought": response.content[:200]})
            else:
                # No tool calls — agent is done
                final_content = response.content
                break

        if final_content is None:
            final_content = self._make_max_iter_response(iteration)

        elapsed = time.monotonic() - start_time
        self._emit("agent_completed", {
            "iterations": iteration,
            "elapsed": round(elapsed, 1),
            "tokens_used": self._total_tokens,
        })

        # Parse output and route to state
        return self._route_output(final_content, state)

    # ── Internal methods ──────────────────────────────────────

    def _build_system_prompt(self, state: dict[str, Any]) -> str:
        """构建 Agent 系统提示词。"""
        symbol = state.get("meta", {}).get("symbol", "")
        stock_name = state.get("meta", {}).get("stock_name", "")

        parts = [
            f"# {self._skill.description or self._skill.name}",
            "",
            f"你正在分析股票: {stock_name}({symbol})" if symbol else "",
            "",
            "## 输出要求",
            "请以 JSON 格式输出你的分析结果。",
        ]

        # Add output schema hint if available
        if hasattr(self._skill, "output_schema") and self._skill.output_schema:
            parts.append(f"\n输出字段说明:\n{json.dumps(self._skill.output_schema, ensure_ascii=False, indent=2)}")

        return "\n".join(parts)

    def _build_user_prompt(self, state: dict[str, Any]) -> str:
        """构建初始用户消息（基于 Skill 的 prompt_template 或默认指令）。"""
        if self._skill.prompt_template:
            # Use Jinja2 template rendering with available state data
            try:
                from jinja2 import Template
                context = self._extract_inputs(state)
                return Template(self._skill.prompt_template).render(**context)
            except Exception as e:
                logger.warning("[%s] 模板渲染失败，使用默认指令: %s", self._skill.name, e)

        # Default: instruct agent to use tools
        symbol = state.get("meta", {}).get("symbol", "")
        return f"请使用可用的工具分析股票 {symbol}，然后以 JSON 格式输出分析结论。"

    def _extract_inputs(self, state: dict[str, Any]) -> dict[str, Any]:
        """从 state 中提取 Skill 声明的输入。"""
        context: dict[str, Any] = {}
        for inp in self._skill.interface.inputs:
            if inp.source:
                val = self._resolve_state_path(state, inp.source)
                context[inp.name] = val
            else:
                context[inp.name] = state.get(inp.name)

        # Always include meta
        context["meta"] = state.get("meta", {})
        context["symbol"] = state.get("meta", {}).get("symbol", "")
        context["stock_name"] = state.get("meta", {}).get("stock_name", "")
        return context

    @staticmethod
    def _resolve_state_path(state: dict[str, Any], path: str) -> Any:
        """解析 state 点分路径，如 state.analysis.technical。"""
        parts = path.split(".")
        if parts and parts[0] == "state":
            parts = parts[1:]
        current: Any = state
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取工具定义列表。"""
        if not self._tools:
            return []
        if not self._constraints.allowed_tools and self._constraints.max_iterations <= 1:
            return []
        return self._tools.get_definitions()

    async def _execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """执行工具调用。"""
        if not self._tools:
            return f"错误: 工具 {name} 不可用"

        try:
            result = await self._tools.execute(name, arguments)
            return result
        except Exception as e:
            logger.error("[%s] 工具 %s 执行失败: %s", self._skill.name, name, e)
            return f"工具 {name} 执行失败: {e!s}"

    @staticmethod
    def _build_assistant_message(response: AgentLLMResponse) -> dict[str, Any]:
        """构建包含 tool_calls 的 assistant 消息。"""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }
        if response.has_tool_calls:
            msg["tool_calls"] = [tc.to_openai_tool_call() for tc in response.tool_calls]
        return msg

    def _route_output(self, content: str | None, state: dict[str, Any]) -> dict[str, Any]:
        """将 Agent 输出路由到增量状态更新。"""
        from stocksage.skill_engine.executor import deep_set

        if content is None:
            content = "{}"

        # Try to parse as JSON
        parsed = self._parse_json(content)

        # Route based on skill.interface.outputs
        result: dict[str, Any] = {}
        outputs = self._skill.interface.outputs
        if outputs:
            for out in outputs:
                if out.target:
                    deep_set(result, out.target, parsed)
                else:
                    result[out.name] = parsed
        else:
            # Fallback: use skill name as key under analysis
            result.setdefault("analysis", {})[self._skill.name] = parsed

        return result

    @staticmethod
    def _parse_json(content: str) -> Any:
        """尝试从 LLM 输出中解析 JSON。"""
        text = content.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start) if "```" in text[start:] else len(text)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start) if "```" in text[start:] else len(text)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Try finding JSON object
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

        # Return raw text wrapped in dict
        return {"raw_output": text}

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """发射进度事件。"""
        if self._on_progress:
            try:
                self._on_progress(event_type, payload)
            except Exception as e:
                logger.debug("Progress callback error: %s", e)

    def _make_timeout_response(self, iteration: int, elapsed: float) -> str:
        return json.dumps({
            "warning": "分析因超时而提前终止",
            "iterations_completed": iteration,
            "elapsed_seconds": round(elapsed, 1),
        }, ensure_ascii=False)

    def _make_budget_response(self, iteration: int) -> str:
        return json.dumps({
            "warning": "分析因 token 预算超限而提前终止",
            "iterations_completed": iteration,
            "tokens_used": self._total_tokens,
        }, ensure_ascii=False)

    def _make_max_iter_response(self, iteration: int) -> str:
        return json.dumps({
            "warning": f"已达到最大迭代次数 ({iteration})，自动终止",
            "iterations_completed": iteration,
        }, ensure_ascii=False)
