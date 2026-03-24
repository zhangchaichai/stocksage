"""ChatAgent: 对话层 ReAct Agent。

替代现有的 intent.py (regex 意图识别) + service.py (if-else 路由) + _llm_chat (一次性调用)。

核心改变:
- 旧版: regex 分类 → 硬编码路由 → 单次 LLM 调用
- 新版: LLM + 工具 → ReAct 循环 → 流式输出

LLM 通过选择调什么工具来隐式完成意图识别。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from stocksage.agent.tools.registry import ToolRegistry

from stocksage.agent.llm_adapter import AgentLLMResponse

logger = logging.getLogger(__name__)


class ChatAgent:
    """对话层 ReAct Agent。

    与 SkillAgent 的区别:
    - SkillAgent: 分析工作流中的节点，输出 JSON，写入 state
    - ChatAgent:  面向用户的对话入口，输出自然语言，流式推送

    不再需要 intent.py 里的 regex 匹配和 service.py 里的 if-else 路由。
    LLM 通过 tool calling 隐式地完成意图识别。
    """

    def __init__(
        self,
        llm: Any,
        tool_registry: ToolRegistry,
        *,
        max_iterations: int = 10,
        max_context_messages: int = 20,
    ):
        self._llm = llm  # LiteLLMAdapter / NanobotLLMAdapter
        self._tools = tool_registry
        self._max_iterations = max_iterations
        self._max_context = max_context_messages

    async def chat_stream(
        self,
        user_message: str,
        history: list[dict[str, str]],
    ) -> AsyncIterator[dict[str, Any]]:
        """处理用户消息，流式返回响应。

        Yields:
            {"type": "token", "content": "..."}         — LLM 输出的文本 token
            {"type": "thinking", "content": "..."}      — Agent 在思考
            {"type": "tool_call", "tool": "...", ...}    — 工具调用事件
            {"type": "tool_result", "tool": "...", ...}  — 工具返回事件
            {"type": "action", "action": "...", ...}     — 前端动作
            {"type": "done", "full_reply": "..."}        — 完成
        """
        messages = self._build_messages(user_message, history)
        tool_defs = self._tools.get_definitions()

        full_reply_parts: list[str] = []
        actions: list[dict[str, Any]] = []
        iteration = 0

        while iteration < self._max_iterations:
            iteration += 1

            try:
                response: AgentLLMResponse = await self._llm.chat(
                    messages=messages,
                    tools=tool_defs if tool_defs else None,
                )
            except Exception as e:
                logger.error("ChatAgent LLM 调用失败: %s", e)
                yield {"type": "token", "content": "抱歉，服务暂时不可用，请稍后再试。"}
                break

            if response.has_tool_calls:
                # Agent decided to call tools
                if response.content:
                    yield {"type": "thinking", "content": response.content}

                # Build assistant message
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [tc.to_openai_tool_call() for tc in response.tool_calls],
                }
                messages.append(assistant_msg)

                # Execute each tool call
                for tc in response.tool_calls:
                    tool_name = tc.name
                    tool_args = tc.arguments

                    yield {
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args,
                    }

                    # Execute
                    try:
                        result = await self._tools.execute(tool_name, tool_args)
                    except Exception as e:
                        result = f"工具执行失败: {e!s}"

                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "result_preview": result[:200],
                    }

                    # Extract frontend actions
                    action = self._extract_action(tool_name, tool_args, result)
                    if action:
                        actions.append(action)
                        yield {"type": "action", **action}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                # Agent outputs final reply
                if response.content:
                    full_reply_parts.append(response.content)
                    yield {"type": "token", "content": response.content}
                break
        else:
            # Max iterations exhausted without a final reply — use last content
            if not full_reply_parts:
                fallback = "分析完成，但未能生成完整回复。请尝试重新提问。"
                full_reply_parts.append(fallback)
                yield {"type": "token", "content": fallback}

        full_reply = "".join(full_reply_parts)
        yield {
            "type": "done",
            "full_reply": full_reply,
            "actions": actions,
        }

    async def chat_stream_sse(
        self,
        user_message: str,
        history: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        """SSE 格式的流式输出 — 直接用于 StreamingResponse。"""
        async for event in self.chat_stream(user_message, history):
            event_type = event.get("type", "message")
            payload = {k: v for k, v in event.items() if k != "type"}
            data = json.dumps(payload, ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"

    def _build_messages(
        self,
        user_message: str,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """构建 LLM 消息列表: system + history + user。"""
        system_prompt = self._build_system_prompt()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        # Truncate to recent N messages
        recent = history[-self._max_context :] if history else []
        messages.extend(recent)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _build_system_prompt(self) -> str:
        return """# StockSage 智能助手

你是 StockSage 智能股票分析助手。你可以：
1. 启动完整分析工作流（调用 run_analysis 工具，后台异步执行）
2. 根据策略筛选股票（调用 screen_stocks 工具）
3. 快速查询股票基本信息（调用 query_stock 或 fetch_stock_info 工具）
4. 获取历史价格数据（调用 fetch_price_data 工具）
5. 获取财务数据（调用 fetch_financial 工具）
6. 获取新闻资讯（调用 fetch_news 工具）
7. 获取资金流向（调用 fetch_fund_flow 工具）
8. 计算技术指标（调用 calc_indicator 工具，支持 MA/RSI/MACD/BOLL/KDJ/OBV/ATR/CCI）
9. 计算估值指标（调用 calc_valuation 工具，支持 PE/PB/PS/PEG/DCF）
10. 导航到功能页面（调用 navigate 工具）

## 工作方式
- 当用户要求分析股票时，主动调用多个数据和计算工具获取真实数据，基于数据给出分析
- 典型分析流程：先获取基本信息 → 获取价格数据 → 计算技术指标(MA/RSI/MACD等) → 获取财务数据 → 计算估值 → 综合分析
- 可以并行调用多个工具提高效率
- 如果不需要工具（如闲聊、知识问答），直接回答
- 回复要简洁自然，像一个专业的投资顾问
- 用中文回复
- 回复中引用的数据必须来自工具返回的真实数据，不要编造数字

## 约束
- 所有投资建议都需声明"仅供参考，不构成投资建议"
- 数据来源于公开市场数据
- 如果用户没指定股票代码，先询问"""

    @staticmethod
    def _extract_action(
        tool_name: str,
        args: dict[str, Any],
        result: str,
    ) -> dict[str, Any] | None:
        """从工具调用中提取前端动作。"""
        if tool_name == "navigate":
            return {"action": "navigate", "data": {"route": args.get("route", "/")}}
        if tool_name == "run_analysis":
            try:
                data = json.loads(result) if isinstance(result, str) else result
                return {"action": "run_analysis", "data": data}
            except (json.JSONDecodeError, TypeError):
                return {"action": "run_analysis", "data": {"symbol": args.get("symbol")}}
        if tool_name == "screen_stocks":
            return {"action": "navigate", "data": {"route": "/screener"}}
        return None
