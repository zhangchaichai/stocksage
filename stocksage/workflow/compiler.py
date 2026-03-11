"""WorkflowCompiler: 将声明式 YAML 工作流定义编译为 LangGraph StateGraph。

v3.0 核心模块。将工作流定义（YAML/dict）编译为可执行的 LangGraph 图。

编译流程：
    load(path_or_dict) → WorkflowDefinition
    validate(definition, registry) → list[str] (错误列表)
    compile(definition, executor, registry) → CompiledWorkflow
    CompiledWorkflow.run(symbol, stock_name) → dict
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from stocksage.skill_engine.executor import SkillExecutor
from stocksage.skill_engine.models import SkillDef
from stocksage.skill_engine.registry import SkillRegistry
from stocksage.workflow.conditions import evaluate_condition
from stocksage.workflow.nodes import make_skill_node
from stocksage.workflow.state import WorkflowState, create_state_class

logger = logging.getLogger(__name__)


# ============================================================
# 工作流定义数据模型
# ============================================================


@dataclass
class EdgeDef:
    """工作流边定义。"""

    source: str
    target: str | list[str]  # fan_out 时为 list
    type: str = "serial"  # serial | fan_out | fan_in | conditional
    condition: dict | None = None  # conditional 边的条件表达式
    path_map: dict[str, str] | None = None  # conditional 边的路径映射


@dataclass
class NodeDef:
    """工作流节点定义。"""

    name: str
    skill: str  # 对应的 skill 名称
    type: str = "skill"  # skill | custom (预留)


@dataclass
class WorkflowDefinition:
    """完整的工作流定义。"""

    name: str
    version: str = "1.0.0"
    description: str = ""
    state: dict[str, dict] | None = None  # 动态 state schema
    nodes: list[NodeDef] = field(default_factory=list)
    edges: list[EdgeDef] = field(default_factory=list)
    initial_state: dict[str, Any] = field(default_factory=dict)
    # 特殊节点：collect_data 等内置逻辑
    custom_nodes: dict[str, str] = field(default_factory=dict)


# ============================================================
# 编译产物
# ============================================================


@dataclass
class CompiledWorkflow:
    """编译后的工作流，封装 LangGraph 图 + 初始状态模板。"""

    name: str
    graph: Any  # LangGraph compiled graph
    initial_state_template: dict[str, Any]
    _progress_callback: Callable | None = None

    def run(
        self,
        symbol: str,
        stock_name: str = "",
        *,
        progress_callback: Callable | None = None,
    ) -> dict:
        """运行工作流。

        Args:
            symbol: 股票代码。
            stock_name: 股票名称。
            progress_callback: 节点执行回调 ``(node_name, status) -> None``。

        Returns:
            工作流最终状态字典。
        """
        self._progress_callback = progress_callback

        # 构建初始状态
        state = dict(self.initial_state_template)
        state["meta"] = {"symbol": symbol, "stock_name": stock_name, "market": "cn"}

        return self.graph.invoke(state)


# ============================================================
# WorkflowCompiler
# ============================================================


class WorkflowCompiler:
    """将声明式工作流定义编译为 LangGraph StateGraph。"""

    # ----------------------------------------------------------
    # load: YAML/dict → WorkflowDefinition
    # ----------------------------------------------------------

    @staticmethod
    def load(source: str | Path | dict) -> WorkflowDefinition:
        """从 YAML 文件路径或 dict 加载工作流定义。

        Args:
            source: YAML 文件路径、YAML 字符串或已解析的 dict。

        Returns:
            WorkflowDefinition 实例。
        """
        if isinstance(source, dict):
            raw = source
        elif isinstance(source, Path) or (isinstance(source, str) and (
            source.endswith(".yaml") or source.endswith(".yml")
        )):
            path = Path(source)
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            # 尝试作为 YAML 字符串解析
            raw = yaml.safe_load(source)

        if not isinstance(raw, dict):
            raise ValueError("工作流定义必须是字典格式")

        return WorkflowCompiler._parse_definition(raw)

    @staticmethod
    def _parse_definition(raw: dict) -> WorkflowDefinition:
        """将原始 dict 解析为 WorkflowDefinition。"""
        nodes = []
        for n in raw.get("nodes", []):
            nodes.append(NodeDef(
                name=n["name"],
                skill=n.get("skill", n["name"]),
                type=n.get("type", "skill"),
            ))

        edges = []
        for e in raw.get("edges", []):
            target = e["target"]
            # fan_out 的 target 可能是列表
            if isinstance(target, str):
                target_val = target
            else:
                target_val = list(target)

            edges.append(EdgeDef(
                source=e["source"],
                target=target_val,
                type=e.get("type", "serial"),
                condition=e.get("condition"),
                path_map=e.get("path_map"),
            ))

        return WorkflowDefinition(
            name=raw.get("name", "unnamed"),
            version=raw.get("version", "1.0.0"),
            description=raw.get("description", ""),
            state=raw.get("state"),
            nodes=nodes,
            edges=edges,
            initial_state=raw.get("initial_state", {}),
            custom_nodes=raw.get("custom_nodes", {}),
        )

    # ----------------------------------------------------------
    # validate: 验证 DAG
    # ----------------------------------------------------------

    @staticmethod
    def validate(
        definition: WorkflowDefinition,
        registry: SkillRegistry,
    ) -> list[str]:
        """验证工作流定义的合法性。

        检查：
        1. 所有节点引用的 skill 在 registry 中存在
        2. 所有边引用的节点已定义
        3. START 到 END 可达
        4. 无孤立节点

        Args:
            definition: 工作流定义。
            registry: Skill 注册表。

        Returns:
            错误消息列表（空列表表示验证通过）。
        """
        errors: list[str] = []
        node_names = {n.name for n in definition.nodes}

        # 1. Skill 存在性检查
        for node in definition.nodes:
            if node.type == "skill" and registry.get(node.skill) is None:
                errors.append(f"节点 '{node.name}' 引用的 skill '{node.skill}' 不存在")

        # 2. 边引用合法性
        valid_names = node_names | {"START", "END"}
        for edge in definition.edges:
            if edge.source not in valid_names:
                errors.append(f"边的 source '{edge.source}' 不是已定义的节点")
            targets = edge.target if isinstance(edge.target, list) else [edge.target]
            for t in targets:
                if t not in valid_names:
                    errors.append(f"边的 target '{t}' 不是已定义的节点")

        # 3. START 可达性
        reachable = set()
        WorkflowCompiler._dfs_reachable(definition, "START", reachable)
        unreachable = node_names - reachable
        if unreachable:
            errors.append(f"以下节点从 START 不可达: {', '.join(sorted(unreachable))}")

        # 4. END 可达性（反向）
        has_end_edge = any(
            (isinstance(e.target, str) and e.target == "END")
            or (isinstance(e.target, list) and "END" in e.target)
            or (e.path_map and "END" in e.path_map.values())
            for e in definition.edges
        )
        if not has_end_edge:
            errors.append("没有任何边通向 END")

        return errors

    @staticmethod
    def _dfs_reachable(
        definition: WorkflowDefinition,
        start: str,
        visited: set[str],
    ) -> None:
        """从 start 出发，DFS 遍历所有可达节点。"""
        if start in visited:
            return
        visited.add(start)
        for edge in definition.edges:
            if edge.source == start:
                targets = edge.target if isinstance(edge.target, list) else [edge.target]
                for t in targets:
                    WorkflowCompiler._dfs_reachable(definition, t, visited)
                # path_map 中的目标也算可达
                if edge.path_map:
                    for t in edge.path_map.values():
                        WorkflowCompiler._dfs_reachable(definition, t, visited)

    # ----------------------------------------------------------
    # compile: WorkflowDefinition → CompiledWorkflow
    # ----------------------------------------------------------

    @staticmethod
    def compile(
        definition: WorkflowDefinition,
        executor: SkillExecutor,
        registry: SkillRegistry,
        *,
        collect_data_fn: Any | None = None,
        progress_callback: Callable | None = None,
    ) -> CompiledWorkflow:
        """将 WorkflowDefinition 编译为 LangGraph StateGraph。

        Args:
            definition: 工作流定义。
            executor: Skill 执行器。
            registry: Skill 注册表。
            collect_data_fn: 可选的 collect_data 自定义节点函数。
            progress_callback: 节点执行回调。

        Returns:
            CompiledWorkflow 实例。
        """
        # 1. 生成 state class
        if definition.state:
            state_class = create_state_class(definition.state)
        else:
            state_class = WorkflowState

        builder = StateGraph(state_class)

        # 2. 注册节点
        for node_def in definition.nodes:
            if node_def.name in definition.custom_nodes:
                # 自定义节点（如 collect_data）需要外部提供
                continue

            skill = registry.get(node_def.skill)
            if skill is None:
                logger.warning("跳过未注册的 skill: %s", node_def.skill)
                continue

            node_fn = make_skill_node(skill, executor)
            if progress_callback:
                node_fn = _wrap_with_progress(node_fn, node_def.name, progress_callback)

            builder.add_node(node_def.name, node_fn)

        # 注册自定义节点
        if collect_data_fn:
            if any(n.name == "collect_data" for n in definition.nodes):
                builder.add_node("collect_data", collect_data_fn)

        # 3. 注册边
        # 跟踪 fan_in 目标，用于生成汇聚边
        fan_in_targets: dict[str, list[str]] = {}

        for edge in definition.edges:
            source = edge.source if edge.source != "START" else START
            target_raw = edge.target

            if edge.type == "serial":
                target = END if target_raw == "END" else target_raw
                builder.add_edge(source, target)

            elif edge.type == "fan_out":
                # fan_out: 将 target 列表转换为 Send 路由函数
                targets = target_raw if isinstance(target_raw, list) else [target_raw]
                fan_out_fn = _make_fan_out_fn(targets)
                builder.add_conditional_edges(source, fan_out_fn)

            elif edge.type == "fan_in":
                # fan_in: 多个 source → 同一 target（延迟处理）
                target = target_raw if isinstance(target_raw, str) else target_raw[0]
                if target not in fan_in_targets:
                    fan_in_targets[target] = []
                fan_in_targets[target].append(edge.source)

            elif edge.type == "conditional":
                # conditional: 条件表达式 → 路径映射
                if edge.condition and edge.path_map:
                    cond_fn = _make_condition_fn(edge.condition, edge.path_map)
                    builder.add_conditional_edges(source, cond_fn, edge.path_map)
                else:
                    logger.warning("条件边缺少 condition 或 path_map: %s → %s", source, target_raw)

        # 处理 fan_in 汇聚边
        for target, sources in fan_in_targets.items():
            for src in sources:
                target_node = END if target == "END" else target
                builder.add_edge(src, target_node)

        # 4. 编译
        compiled_graph = builder.compile()

        # 5. 构建初始状态模板
        initial_template = _build_initial_state(definition, state_class)

        return CompiledWorkflow(
            name=definition.name,
            graph=compiled_graph,
            initial_state_template=initial_template,
        )


# ============================================================
# 辅助函数
# ============================================================


def _make_fan_out_fn(targets: list[str]) -> Callable:
    """创建 fan-out 路由函数，返回 Send 列表。"""
    def fan_out(state: dict) -> list[Send]:
        return [Send(name, state) for name in targets]
    return fan_out


def _make_condition_fn(condition: dict, path_map: dict[str, str]) -> Callable:
    """创建条件路由函数。

    条件表达式求值后根据 path_map 返回目标节点名。
    """
    def condition_fn(state: dict) -> str:
        if evaluate_condition(condition, state):
            # 条件为真 → path_map 中第一个键
            return list(path_map.keys())[0]
        # 条件为假 → path_map 中第二个键
        keys = list(path_map.keys())
        return keys[1] if len(keys) > 1 else keys[0]
    return condition_fn


def _wrap_with_progress(
    node_fn: Callable,
    node_name: str,
    callback: Callable,
) -> Callable:
    """包装节点函数，在执行前后触发进度回调。"""
    def wrapped(state: dict) -> dict:
        callback(node_name, "started")
        try:
            result = node_fn(state)
            callback(node_name, "completed")
            return result
        except Exception as e:
            callback(node_name, "failed")
            raise
    wrapped.__name__ = node_name
    return wrapped


def _build_initial_state(definition: WorkflowDefinition, state_class: type) -> dict:
    """根据 state schema 构建初始状态模板。"""
    template: dict[str, Any] = {}

    if definition.state:
        for key, spec in definition.state.items():
            type_name = spec.get("type", "dict")
            if type_name == "dict":
                template[key] = {}
            elif type_name == "list":
                template[key] = []
            elif type_name == "str":
                template[key] = ""
            elif type_name in ("int", "float"):
                template[key] = 0
            elif type_name == "bool":
                template[key] = False
            else:
                template[key] = {}
    else:
        # WorkflowState 默认模板
        template = {
            "meta": {},
            "data": {},
            "analysis": {},
            "debate": {},
            "expert_panel": {},
            "round3_decision": {},
            "decision": {},
            "errors": [],
            "current_phase": "init",
            "llm_traces": {},
        }

    # 合并用户自定义初始状态
    if definition.initial_state:
        template.update(definition.initial_state)

    return template
