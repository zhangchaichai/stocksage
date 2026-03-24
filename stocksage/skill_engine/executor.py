"""SkillExecutor: 执行 Skill（数据获取 / LLM 调用 / MCP 工具）。

v3.0 重构：统一化执行路径。
- data: 调用 DataFetcher（无 LLM）
- LLM 类 (agent/decision/debate/expert/coordinator): 渲染 prompt → 可选调用 tools → 调用 LLM
- researcher: 提取盲点 → Web 搜索 → LLM 分析

输出路由由 skill.interface.outputs[].target 声明驱动，不再硬编码。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from jinja2 import Template

from stocksage.data.fetcher import DataFetcher
from stocksage.llm.base import BaseLLM
from stocksage.skill_engine.models import SkillDef

# Type alias for streaming callback
OnChunkCallback = Callable[[str], Any]  # async (chunk: str) -> None

logger = logging.getLogger(__name__)

# data Skill 名称到 DataFetcher 方法的映射
_DATA_SKILL_MAP = {
    "fetch_stock_info": "fetch_stock_info",
    "fetch_price_data": "fetch_price_data",
    "fetch_financial": "fetch_financial",
    "fetch_quarterly": "fetch_quarterly",
    "fetch_news": "fetch_news",
    "fetch_fund_flow": "fetch_fund_flow",
    "fetch_sentiment": "fetch_sentiment",
    "fetch_margin_data": "fetch_margin_data",
    "fetch_northbound_flow": "fetch_northbound_flow",
    "fetch_balance_sheet": "fetch_balance_sheet",
}

# LLM 类 Skill 类型 → 默认系统提示词
_SYSTEM_PROMPTS: dict[str, str] = {
    "agent": "你是一位专业的股票分析师。请以JSON格式输出分析结果。",
    "decision": "你是一位专业的股票分析师。请以JSON格式输出分析结果。",
    "debate": "你是一位专业的股票辩论分析师。请以JSON格式输出分析结果。",
    "expert": "你是一位专家评审团成员。请以JSON格式输出审议意见。",
    "coordinator": "你是专家评审团协调者。请以JSON格式输出汇总意见和Round 3决策。",
    "researcher": "你是一位严谨的投资研究员。请基于搜索到的真实数据分析盲点，以JSON格式输出。",
}

# LLM 类 Skill 类型集合
_LLM_SKILL_TYPES = frozenset({"agent", "decision", "debate", "expert", "coordinator"})


# ============================================================
# 工具函数
# ============================================================


def deep_set(d: dict, path: str, value: Any) -> dict:
    """将 value 写入 dict 的嵌套路径。

    路径格式为 ``state.analysis.technical`` ——以点分隔，首段 ``state`` 会被跳过
    （因为返回的就是增量状态字典本身）。

    Args:
        d: 目标字典（会被原地修改并返回）。
        path: 点分隔路径，如 ``"state.decision"`` 或 ``"state.data.price_data"``。
        value: 要写入的值。

    Returns:
        修改后的字典 *d*。

    Examples::

        >>> deep_set({}, "state.analysis.technical", {"ma5": 100})
        {'analysis': {'technical': {'ma5': 100}}}
        >>> deep_set({}, "state.decision", {"action": "buy"})
        {'decision': {'action': 'buy'}}
    """
    parts = path.split(".")
    # 跳过 "state" 前缀
    if parts and parts[0] == "state":
        parts = parts[1:]
    if not parts:
        return d

    # 只有一层路径时直接赋值（如 "state.decision" → parts=["decision"]）
    if len(parts) == 1:
        d[parts[0]] = value
        return d

    # 多层路径时嵌套写入
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    return d


class SkillExecutor:
    """Skill 执行引擎（v3.0 统一化）。"""

    def __init__(self, llm: BaseLLM, data_fetcher: DataFetcher, tool_bridge=None):
        self._llm = llm
        self._fetcher = data_fetcher
        self._tools = tool_bridge

    def with_llm(self, llm: BaseLLM) -> SkillExecutor:
        """返回使用不同 LLM 实例的浅拷贝（共享 fetcher / tools）。"""
        return SkillExecutor(llm, self._fetcher, tool_bridge=self._tools)

    # ============================================================
    # 公共入口
    # ============================================================

    def execute(self, skill: SkillDef, state: dict) -> dict:
        """执行 Skill，返回增量状态更新。

        路由逻辑：
        1. ``data`` → _execute_data_skill（调用 DataFetcher，无 LLM）
        2. ``researcher`` → _execute_researcher_skill（搜索 + LLM）
        3. 其他 LLM 类 (agent/decision/debate/expert/coordinator) → _execute_llm_skill
        """
        logger.info("执行 Skill: %s (type=%s)", skill.name, skill.type)

        # A2A 远程 Skill 路由
        if skill.remote and skill.remote.enabled:
            return self._execute_remote_skill(skill, state)

        if skill.type == "data":
            return self._execute_data_skill(skill, state)
        if skill.type == "researcher":
            return self._execute_researcher_skill(skill, state)
        if skill.type in _LLM_SKILL_TYPES:
            return self._execute_llm_skill(skill, state)

        logger.warning("未知 Skill 类型: %s", skill.type)
        return {}

    async def execute_streaming(
        self,
        skill: SkillDef,
        state: dict,
        on_chunk: OnChunkCallback | None = None,
    ) -> dict:
        """流式执行 Skill，LLM 输出逐 token 通过 on_chunk 回调推送。

        对于 data skill 和 researcher skill 的数据采集部分，不做流式处理。
        仅 LLM 调用部分使用 ``self._llm.stream()``。

        Args:
            skill: Skill 定义。
            state: 当前工作流状态。
            on_chunk: 流式回调，每收到一个 token chunk 时调用。

        Returns:
            增量状态更新字典（与 ``execute()`` 一致）。
        """
        logger.info("流式执行 Skill: %s (type=%s)", skill.name, skill.type)

        # A2A 远程 Skill 路由
        if skill.remote and skill.remote.enabled:
            return self._execute_remote_skill(skill, state)

        if skill.type == "data":
            return self._execute_data_skill(skill, state)
        if skill.type == "researcher":
            return await self._execute_researcher_skill_streaming(skill, state, on_chunk)
        if skill.type in _LLM_SKILL_TYPES:
            return await self._execute_llm_skill_streaming(skill, state, on_chunk)

        logger.warning("未知 Skill 类型: %s", skill.type)
        return {}

    # ============================================================
    # 数据 Skill
    # ============================================================

    def _execute_remote_skill(self, skill: SkillDef, state: dict) -> dict:
        """执行远程 Skill (A2A Protocol)。

        当前为 stub 实现，未来将通过 A2A 协议调用远程 Agent 服务。

        Raises:
            NotImplementedError: 远程 Skill 执行尚未实现。
        """
        raise NotImplementedError(
            f"远程 Skill '{skill.name}' 执行尚未实现。"
            f" endpoint={skill.remote.endpoint if skill.remote else 'N/A'},"
            f" protocol={skill.remote.protocol if skill.remote else 'N/A'}"
        )

    def _execute_data_skill(self, skill: SkillDef, state: dict) -> dict:
        """执行数据 Skill，调用 DataFetcher。"""
        symbol = state.get("meta", {}).get("symbol", "")
        method_name = _DATA_SKILL_MAP.get(skill.name)
        if not method_name:
            return {"errors": [f"未知数据 Skill: {skill.name}"]}

        method = getattr(self._fetcher, method_name)
        data = method(symbol)

        return self._route_outputs(skill, data)

    # ============================================================
    # 通用 LLM Skill（agent / decision / debate / expert / coordinator）
    # ============================================================

    def _execute_llm_skill(self, skill: SkillDef, state: dict) -> dict:
        """通用 LLM Skill 执行，输出路由由 interface.outputs[].target 驱动。"""
        context = self._extract_inputs(skill, state)

        # Tier 2: judge / reflection_module 额外记忆增强
        if skill.name == "judge":
            self._enrich_memory_for_judge(context, state)
        elif skill.name == "reflection_module":
            self._enrich_memory_for_reflection(context, state)

        # 如果 Skill 声明了 tools 且 ToolBridge 可用，先调用工具
        if self._tools and skill.tools:
            context["tool_results"] = self._call_skill_tools(skill, state)

        prompt = Template(skill.prompt_template).render(**context)
        system_prompt = _SYSTEM_PROMPTS.get(skill.type, _SYSTEM_PROMPTS["agent"])
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        # Token estimation for monitoring context size
        input_chars = sum(len(m["content"]) for m in messages)
        est_tokens = input_chars // 4  # rough estimate: 1 token ≈ 4 chars (Chinese ~2 chars)
        logger.info(
            "[Token] %s: input ~%d chars (~%d tokens), max_output=%d",
            skill.name, input_chars, est_tokens, skill.execution.max_tokens,
        )
        if est_tokens > 10000:
            logger.warning(
                "[Token] %s input exceeds 10k tokens (~%d), quality may degrade",
                skill.name, est_tokens,
            )

        response = self._llm.call(
            messages,
            model=skill.execution.model,
            temperature=skill.execution.temperature,
            max_tokens=skill.execution.max_tokens,
        )
        result = self._parse_response(response)

        update = self._route_outputs(skill, result, raw_response=response)

        # 特殊处理：coordinator 额外提取 round3_decision
        if skill.type == "coordinator":
            r3_decision = result.get("round3_decision", {"need_round3": False})
            update["round3_decision"] = r3_decision

        return update

    async def _execute_llm_skill_streaming(
        self,
        skill: SkillDef,
        state: dict,
        on_chunk: OnChunkCallback | None = None,
    ) -> dict:
        """流式 LLM Skill 执行，通过 on_chunk 逐 token 推送。"""
        context = self._extract_inputs(skill, state)

        if skill.name == "judge":
            self._enrich_memory_for_judge(context, state)
        elif skill.name == "reflection_module":
            self._enrich_memory_for_reflection(context, state)

        if self._tools and skill.tools:
            context["tool_results"] = self._call_skill_tools(skill, state)

        prompt = Template(skill.prompt_template).render(**context)
        system_prompt = _SYSTEM_PROMPTS.get(skill.type, _SYSTEM_PROMPTS["agent"])
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        input_chars = sum(len(m["content"]) for m in messages)
        est_tokens = input_chars // 4
        logger.info(
            "[Token] %s: input ~%d chars (~%d tokens), max_output=%d",
            skill.name, input_chars, est_tokens, skill.execution.max_tokens,
        )

        # 流式调用 LLM
        full_response_parts: list[str] = []
        async for chunk in self._llm.stream(
            messages,
            model=skill.execution.model,
            temperature=skill.execution.temperature,
            max_tokens=skill.execution.max_tokens,
        ):
            full_response_parts.append(chunk)
            if on_chunk:
                await on_chunk(chunk)

        response = "".join(full_response_parts)
        result = self._parse_response(response)

        update = self._route_outputs(skill, result, raw_response=response)

        if skill.type == "coordinator":
            r3_decision = result.get("round3_decision", {"need_round3": False})
            update["round3_decision"] = r3_decision

        return update

    # ============================================================
    # 研究员 Skill（盲点搜索 + LLM 分析）
    # ============================================================

    def _execute_researcher_skill(self, skill: SkillDef, state: dict) -> dict:
        """执行研究员 Skill：提取盲点 → Web 搜索 → LLM 分析。"""
        from stocksage.tools.search import search_blind_spots

        stock_name = state.get("meta", {}).get("stock_name", "")
        expert_panel = state.get("expert_panel", {})

        blind_spots = self._collect_blind_spots(expert_panel)
        if not blind_spots:
            logger.info("  未发现需要研究的盲点，跳过 researcher")
            empty_result = {"researched_blind_spots": [], "overall_assessment": "无需研究"}
            return self._route_outputs(skill, empty_result)

        _MAX_BLIND_SPOTS = 10
        if len(blind_spots) > _MAX_BLIND_SPOTS:
            logger.info("  盲点数量 %d 超过上限 %d，仅研究前 %d 个", len(blind_spots), _MAX_BLIND_SPOTS, _MAX_BLIND_SPOTS)
            blind_spots = blind_spots[:_MAX_BLIND_SPOTS]

        logger.info("  开始搜索 %d 个盲点的相关信息...", len(blind_spots))
        print(f"    搜索 {len(blind_spots)} 个盲点相关数据...")

        search_results = search_blind_spots(blind_spots, stock_name=stock_name)

        total_results = sum(len(v) for v in search_results.values())
        print(f"    搜索完成: 共获取 {total_results} 条相关信息")

        context = self._extract_inputs(skill, state)
        context["blind_spots_list"] = "\n".join(f"- {bs}" for bs in blind_spots)
        context["search_results"] = search_results
        context["expert_panel"] = expert_panel

        prompt = Template(skill.prompt_template).render(**context)
        system_prompt = _SYSTEM_PROMPTS.get("researcher", _SYSTEM_PROMPTS["agent"])
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        response = self._llm.call(
            messages,
            model=skill.execution.model,
            temperature=skill.execution.temperature,
            max_tokens=skill.execution.max_tokens,
        )
        result = self._parse_response(response)
        return self._route_outputs(skill, result, raw_response=response)

    async def _execute_researcher_skill_streaming(
        self,
        skill: SkillDef,
        state: dict,
        on_chunk: OnChunkCallback | None = None,
    ) -> dict:
        """流式研究员 Skill：数据采集不流式，LLM 分析部分流式。"""
        from stocksage.tools.search import search_blind_spots

        stock_name = state.get("meta", {}).get("stock_name", "")
        expert_panel = state.get("expert_panel", {})

        blind_spots = self._collect_blind_spots(expert_panel)
        if not blind_spots:
            logger.info("  未发现需要研究的盲点，跳过 researcher")
            empty_result = {"researched_blind_spots": [], "overall_assessment": "无需研究"}
            return self._route_outputs(skill, empty_result)

        _MAX_BLIND_SPOTS = 10
        if len(blind_spots) > _MAX_BLIND_SPOTS:
            blind_spots = blind_spots[:_MAX_BLIND_SPOTS]

        logger.info("  开始搜索 %d 个盲点的相关信息...", len(blind_spots))
        search_results = search_blind_spots(blind_spots, stock_name=stock_name)

        context = self._extract_inputs(skill, state)
        context["blind_spots_list"] = "\n".join(f"- {bs}" for bs in blind_spots)
        context["search_results"] = search_results
        context["expert_panel"] = expert_panel

        prompt = Template(skill.prompt_template).render(**context)
        system_prompt = _SYSTEM_PROMPTS.get("researcher", _SYSTEM_PROMPTS["agent"])
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        # 流式 LLM 调用
        full_response_parts: list[str] = []
        async for chunk in self._llm.stream(
            messages,
            model=skill.execution.model,
            temperature=skill.execution.temperature,
            max_tokens=skill.execution.max_tokens,
        ):
            full_response_parts.append(chunk)
            if on_chunk:
                await on_chunk(chunk)

        response = "".join(full_response_parts)
        result = self._parse_response(response)
        return self._route_outputs(skill, result, raw_response=response)

    # ============================================================
    # 输出路由（v3.0 核心）
    # ============================================================

    def _route_outputs(
        self, skill: SkillDef, result: Any, *, raw_response: str | None = None
    ) -> dict:
        """根据 skill.interface.outputs[].target 将结果路由到正确的状态路径。

        如果 skill 没有声明 outputs 或 target，则回退到按 skill.type 的硬编码逻辑
        以保持向后兼容。

        Args:
            skill: Skill 定义。
            result: 执行结果（data skill 为原始数据，LLM skill 为解析后的 dict）。
            raw_response: LLM 原始响应文本（用于 llm_traces）。

        Returns:
            增量状态更新字典。
        """
        update: dict = {}

        # 尝试声明式路由
        declared = [out for out in skill.interface.outputs if out.target]
        if declared:
            for out in declared:
                deep_set(update, out.target, result)
        else:
            # 回退：按 type 硬编码（向后兼容无 target 的旧 skill）
            update = self._fallback_route(skill, result)

        # LLM traces
        if raw_response is not None:
            update["llm_traces"] = {skill.name: self._strip_code_fences(raw_response)}

        return update

    def _fallback_route(self, skill: SkillDef, result: Any) -> dict:
        """向后兼容的硬编码路由（当 skill 未声明 output target 时使用）。"""
        match skill.type:
            case "data":
                output_key = skill.name.replace("fetch_", "")
                return {"data": {output_key: result}}
            case "agent":
                return {"analysis": {skill.name: result}}
            case "decision":
                return {"decision": result}
            case "debate":
                return {"debate": {skill.name: result}}
            case "expert":
                return {"expert_panel": {skill.name: result}}
            case "coordinator":
                return {"expert_panel": {"coordinator": result}}
            case "researcher":
                return {"expert_panel": {skill.name: result}}
            case _:
                return {}

    # ============================================================
    # 输入提取
    # ============================================================

    def _extract_inputs(self, skill: SkillDef, state: dict) -> dict:
        """从 state 中提取 Skill 所需的输入数据。

        优先使用 skill.interface.inputs[].source 声明的路径，
        同时保持 meta/symbol/stock_name/data/analysis 等常用 context 的自动注入。
        """
        context: dict = {}
        context["meta"] = state.get("meta", {})
        context["symbol"] = state.get("meta", {}).get("symbol", "")
        context["stock_name"] = state.get("meta", {}).get("stock_name", "")

        for inp in skill.interface.inputs:
            if inp.source:
                value = self._resolve_path(state, inp.source)
                context[inp.name] = value
            elif inp.name in state:
                context[inp.name] = state[inp.name]

        context["data"] = state.get("data", {})
        context["analysis"] = state.get("analysis", {})
        return context

    # ============================================================
    # Tier 2: 记忆增强（judge / reflection_module）
    # ============================================================

    @staticmethod
    def _enrich_memory_for_judge(context: dict, state: dict) -> None:
        """为 judge 注入记忆统计摘要（~30 tokens）。"""
        memory = state.get("memory", {})
        reviews_stat = memory.get("review_stats", "")
        position = memory.get("portfolio_position")

        stats: dict[str, Any] = {}
        if reviews_stat:
            stats["review_stats"] = reviews_stat
        if position:
            stats["portfolio_position"] = position

        context["memory_stats"] = stats if stats else None

    @staticmethod
    def _enrich_memory_for_reflection(context: dict, state: dict) -> None:
        """为 reflection_module 注入跨股票策略摘要。"""
        memory = state.get("memory", {})
        context["memory_review_stats"] = memory.get("review_stats", "")
        context["memory_recent_directions"] = memory.get("recent_directions", "")

    # ============================================================
    # 内部工具方法
    # ============================================================

    @staticmethod
    def _collect_blind_spots(expert_panel: dict) -> list[str]:
        """从 expert_panel 中提取所有盲点描述。"""
        spots = []

        bsd = expert_panel.get("blind_spot_detector", {})
        if isinstance(bsd, dict):
            for key in ("risk_blind_spots", "opportunity_blind_spots", "industry_factors"):
                items = bsd.get(key, [])
                if isinstance(items, list):
                    spots.extend(str(s) for s in items if s)

            sys_spots = bsd.get("system_blind_spots", [])
            if isinstance(sys_spots, list):
                for s in sys_spots:
                    if isinstance(s, dict):
                        desc = s.get("blind_spot") or s.get("description", "")
                        if desc:
                            spots.append(str(desc))
                    elif s:
                        spots.append(str(s))

        coord = expert_panel.get("coordinator", {})
        if isinstance(coord, dict):
            summary = coord.get("expert_panel_summary", {})
            if isinstance(summary, dict):
                coord_spots = summary.get("system_blind_spots", [])
                if isinstance(coord_spots, list):
                    for s in coord_spots:
                        s_str = str(s) if not isinstance(s, str) else s
                        if s_str and s_str not in spots:
                            spots.append(s_str)

        return spots

    def _call_skill_tools(self, skill: SkillDef, state: dict) -> dict:
        """调用 Skill 声明的所有工具，返回结果字典。"""
        results = {}
        symbol = state.get("meta", {}).get("symbol", "")

        for tool_uri in skill.tools:
            try:
                tool_key = tool_uri.split("/")[-1] if "/" in tool_uri else tool_uri
                result = self._tools.call(tool_uri, {"symbol": symbol})
                if result is not None:
                    results[tool_key] = result
            except Exception as e:
                logger.warning("工具 %s 调用失败: %s", tool_uri, e)

        return results

    def _resolve_path(self, state: dict, path: str) -> object:
        """解析状态路径，如 'state.data.price_data' → state['data']['price_data']。"""
        parts = path.split(".")
        if parts[0] == "state":
            parts = parts[1:]
        current: object = state
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, {})
            else:
                return {}
        return current

    def _parse_response(self, response: str) -> dict:
        """尝试从 LLM 响应中解析 JSON。"""
        text = self._strip_code_fences(response)

        if not text or not text.strip():
            logger.error("LLM 返回空响应，prompt 可能过长或 max_tokens 不足")
            return {"error": "empty_response", "raw_response": response}

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("JSON 解析失败: %s — 响应前 200 字符: %s", e, text[:200])
            return {"error": "json_decode_error", "raw_response": response}

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """移除 LLM 响应中的 ```json / ``` 代码围栏。"""
        text = text.strip()
        while text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline == -1:
                break
            text = text[first_newline + 1:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3].rstrip()
        return text
