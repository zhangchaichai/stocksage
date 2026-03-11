"""Workflows router: CRUD + validate + templates."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.workflows.schemas import (
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowTemplate,
    WorkflowUpdate,
    WorkflowValidationError,
)
from app.workflows.service import (
    create_workflow,
    delete_workflow,
    get_workflow,
    list_workflows,
    update_workflow,
)

router = APIRouter()


# ---- Built-in templates ----

_BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "courtroom_debate_v3",
        "description": "法庭辩论模型 — 6 分析师 + 多空辩论 + 5 专家评审 + 盲点研究 (24 nodes)",
        "definition": {
            "name": "courtroom_debate_v3",
            "version": "3.0.0",
            # Phase 1: 数据采集
            # Phase 2: 6 个分析师 (并行)
            # Phase 2.5: 矛盾汇总
            # Phase 3: 多空观点 (并行)
            # Phase 3.5: 辩论 R1-R2 (串行4步)
            # Phase 4: 5 个专家 (并行)
            # Phase 4.5: 协调者
            # Phase 3.6: [条件] Round 3
            # Phase 4.6: 盲点研究员
            # Phase 5: 法官
            "nodes": [
                # Phase 1
                {"id": "collect_data", "skill": "data_collector"},
                # Phase 2: 6 analysts
                {"id": "technical_analyst", "skill": "technical_analyst"},
                {"id": "fundamental_analyst", "skill": "fundamental_analyst"},
                {"id": "risk_analyst", "skill": "risk_analyst"},
                {"id": "sentiment_analyst", "skill": "sentiment_analyst"},
                {"id": "news_analyst", "skill": "news_analyst"},
                {"id": "fund_flow_analyst", "skill": "fund_flow_analyst"},
                # Phase 2.5
                {"id": "conflict_aggregator", "skill": "conflict_aggregator"},
                # Phase 3: bull/bear
                {"id": "bull_advocate", "skill": "bull_advocate"},
                {"id": "bear_advocate", "skill": "bear_advocate"},
                # Phase 3.5: debate R1-R2
                {"id": "debate_r1_bull_challenge", "skill": "debate_r1_bull_challenge"},
                {"id": "debate_r1_bear_response", "skill": "debate_r1_bear_response"},
                {"id": "debate_r2_bull_revise", "skill": "debate_r2_bull_revise"},
                {"id": "debate_r2_bear_revise", "skill": "debate_r2_bear_revise"},
                # Phase 4: 5 experts
                {"id": "blind_spot_detector", "skill": "blind_spot_detector"},
                {"id": "consensus_analyzer", "skill": "consensus_analyzer"},
                {"id": "decision_tree_builder", "skill": "decision_tree_builder"},
                {"id": "quality_checker", "skill": "quality_checker"},
                {"id": "evidence_validator", "skill": "evidence_validator"},
                # Phase 4.5
                {"id": "panel_coordinator", "skill": "panel_coordinator"},
                # Phase 3.6: Round 3
                {"id": "debate_r3_bull", "skill": "debate_r3_bull"},
                {"id": "debate_r3_bear", "skill": "debate_r3_bear"},
                # Phase 4.6
                {"id": "blind_spot_researcher", "skill": "blind_spot_researcher"},
                # Phase 5
                {"id": "judge", "skill": "judge"},
            ],
            "edges": [
                # START → Phase 1
                {"from": "START", "to": "collect_data"},
                # Phase 1 → Phase 2 (fan-out 6 analysts)
                {"from": "collect_data", "to": "technical_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "fundamental_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "risk_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "sentiment_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "news_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "fund_flow_analyst", "type": "fan_out"},
                # Phase 2 → Phase 2.5 (fan-in → conflict_aggregator)
                {"from": "technical_analyst", "to": "conflict_aggregator", "type": "fan_in"},
                {"from": "fundamental_analyst", "to": "conflict_aggregator", "type": "fan_in"},
                {"from": "risk_analyst", "to": "conflict_aggregator", "type": "fan_in"},
                {"from": "sentiment_analyst", "to": "conflict_aggregator", "type": "fan_in"},
                {"from": "news_analyst", "to": "conflict_aggregator", "type": "fan_in"},
                {"from": "fund_flow_analyst", "to": "conflict_aggregator", "type": "fan_in"},
                # Phase 2.5 → Phase 3 (fan-out bull + bear)
                {"from": "conflict_aggregator", "to": "bull_advocate", "type": "fan_out"},
                {"from": "conflict_aggregator", "to": "bear_advocate", "type": "fan_out"},
                # Phase 3 → Phase 3.5 (fan-in → debate R1)
                {"from": "bull_advocate", "to": "debate_r1_bull_challenge", "type": "fan_in"},
                {"from": "bear_advocate", "to": "debate_r1_bull_challenge", "type": "fan_in"},
                # Phase 3.5: serial debate R1-R2
                {"from": "debate_r1_bull_challenge", "to": "debate_r1_bear_response"},
                {"from": "debate_r1_bear_response", "to": "debate_r2_bull_revise"},
                {"from": "debate_r2_bull_revise", "to": "debate_r2_bear_revise"},
                # Phase 3.5 → Phase 4 (fan-out 5 experts)
                {"from": "debate_r2_bear_revise", "to": "blind_spot_detector", "type": "fan_out"},
                {"from": "debate_r2_bear_revise", "to": "consensus_analyzer", "type": "fan_out"},
                {"from": "debate_r2_bear_revise", "to": "decision_tree_builder", "type": "fan_out"},
                {"from": "debate_r2_bear_revise", "to": "quality_checker", "type": "fan_out"},
                {"from": "debate_r2_bear_revise", "to": "evidence_validator", "type": "fan_out"},
                # Phase 4 → Phase 4.5 (fan-in → coordinator)
                {"from": "blind_spot_detector", "to": "panel_coordinator", "type": "fan_in"},
                {"from": "consensus_analyzer", "to": "panel_coordinator", "type": "fan_in"},
                {"from": "decision_tree_builder", "to": "panel_coordinator", "type": "fan_in"},
                {"from": "quality_checker", "to": "panel_coordinator", "type": "fan_in"},
                {"from": "evidence_validator", "to": "panel_coordinator", "type": "fan_in"},
                # Phase 4.5 → conditional: Round 3 or blind_spot_researcher
                {"from": "panel_coordinator", "to": "debate_r3_bull", "type": "conditional"},
                # Phase 3.6: Round 3 serial
                {"from": "debate_r3_bull", "to": "debate_r3_bear"},
                {"from": "debate_r3_bear", "to": "blind_spot_researcher"},
                # Phase 4.6 → Phase 5
                {"from": "blind_spot_researcher", "to": "judge"},
                # Phase 5 → END
                {"from": "judge", "to": "END"},
            ],
        },
    },
    {
        "name": "quick_analysis",
        "description": "快速分析模式 — 3 个核心分析师 + 直接决策 (5 nodes)",
        "definition": {
            "name": "quick_analysis",
            "version": "3.0.0",
            "nodes": [
                {"id": "collect_data", "skill": "data_collector"},
                {"id": "technical_analyst", "skill": "technical_analyst"},
                {"id": "fundamental_analyst", "skill": "fundamental_analyst"},
                {"id": "risk_analyst", "skill": "risk_analyst"},
                {"id": "judge", "skill": "judge"},
            ],
            "edges": [
                {"from": "START", "to": "collect_data"},
                {"from": "collect_data", "to": "technical_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "fundamental_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "risk_analyst", "type": "fan_out"},
                {"from": "technical_analyst", "to": "judge", "type": "fan_in"},
                {"from": "fundamental_analyst", "to": "judge", "type": "fan_in"},
                {"from": "risk_analyst", "to": "judge", "type": "fan_in"},
                {"from": "judge", "to": "END"},
            ],
        },
    },
    {
        "name": "deep_fundamental",
        "description": "深度基本面分析 — 基本面 + 估值 + 行业 + 风险 + 研报 + 组合建议 (8 nodes)",
        "definition": {
            "name": "deep_fundamental",
            "version": "3.0.0",
            "nodes": [
                {"id": "collect_data", "skill": "data_collector"},
                {"id": "fundamental_analyst", "skill": "fundamental_analyst"},
                {"id": "valuation_analyst", "skill": "valuation_analyst"},
                {"id": "industry_analyst", "skill": "industry_analyst"},
                {"id": "risk_analyst", "skill": "risk_analyst"},
                {"id": "judge", "skill": "judge"},
                {"id": "report_writer", "skill": "report_writer"},
                {"id": "portfolio_advisor", "skill": "portfolio_advisor"},
            ],
            "edges": [
                {"from": "START", "to": "collect_data"},
                {"from": "collect_data", "to": "fundamental_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "valuation_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "industry_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "risk_analyst", "type": "fan_out"},
                {"from": "fundamental_analyst", "to": "judge", "type": "fan_in"},
                {"from": "valuation_analyst", "to": "judge", "type": "fan_in"},
                {"from": "industry_analyst", "to": "judge", "type": "fan_in"},
                {"from": "risk_analyst", "to": "judge", "type": "fan_in"},
                {"from": "judge", "to": "report_writer", "type": "fan_out"},
                {"from": "judge", "to": "portfolio_advisor", "type": "fan_out"},
                {"from": "report_writer", "to": "END"},
                {"from": "portfolio_advisor", "to": "END"},
            ],
        },
    },
    {
        "name": "macro_sentiment",
        "description": "宏观情绪分析 — 宏观 + 情绪 + 资金流 + 新闻 + 技术面 + 组合建议 (8 nodes)",
        "definition": {
            "name": "macro_sentiment",
            "version": "3.0.0",
            "nodes": [
                {"id": "collect_data", "skill": "data_collector"},
                {"id": "macro_analyst", "skill": "macro_analyst"},
                {"id": "sentiment_analyst", "skill": "sentiment_analyst"},
                {"id": "fund_flow_analyst", "skill": "fund_flow_analyst"},
                {"id": "news_analyst", "skill": "news_analyst"},
                {"id": "technical_analyst", "skill": "technical_analyst"},
                {"id": "judge", "skill": "judge"},
                {"id": "portfolio_advisor", "skill": "portfolio_advisor"},
            ],
            "edges": [
                {"from": "START", "to": "collect_data"},
                {"from": "collect_data", "to": "macro_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "sentiment_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "fund_flow_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "news_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "technical_analyst", "type": "fan_out"},
                {"from": "macro_analyst", "to": "judge", "type": "fan_in"},
                {"from": "sentiment_analyst", "to": "judge", "type": "fan_in"},
                {"from": "fund_flow_analyst", "to": "judge", "type": "fan_in"},
                {"from": "news_analyst", "to": "judge", "type": "fan_in"},
                {"from": "technical_analyst", "to": "judge", "type": "fan_in"},
                {"from": "judge", "to": "portfolio_advisor"},
                {"from": "portfolio_advisor", "to": "END"},
            ],
        },
    },
    {
        "name": "full_spectrum",
        "description": "全维度分析 — 9 个分析师全覆盖 + 决策 + 研报 + 组合建议 (13 nodes)",
        "definition": {
            "name": "full_spectrum",
            "version": "3.0.0",
            "nodes": [
                {"id": "collect_data", "skill": "data_collector"},
                {"id": "technical_analyst", "skill": "technical_analyst"},
                {"id": "fundamental_analyst", "skill": "fundamental_analyst"},
                {"id": "risk_analyst", "skill": "risk_analyst"},
                {"id": "sentiment_analyst", "skill": "sentiment_analyst"},
                {"id": "news_analyst", "skill": "news_analyst"},
                {"id": "fund_flow_analyst", "skill": "fund_flow_analyst"},
                {"id": "valuation_analyst", "skill": "valuation_analyst"},
                {"id": "industry_analyst", "skill": "industry_analyst"},
                {"id": "macro_analyst", "skill": "macro_analyst"},
                {"id": "judge", "skill": "judge"},
                {"id": "report_writer", "skill": "report_writer"},
                {"id": "portfolio_advisor", "skill": "portfolio_advisor"},
            ],
            "edges": [
                {"from": "START", "to": "collect_data"},
                {"from": "collect_data", "to": "technical_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "fundamental_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "risk_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "sentiment_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "news_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "fund_flow_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "valuation_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "industry_analyst", "type": "fan_out"},
                {"from": "collect_data", "to": "macro_analyst", "type": "fan_out"},
                {"from": "technical_analyst", "to": "judge", "type": "fan_in"},
                {"from": "fundamental_analyst", "to": "judge", "type": "fan_in"},
                {"from": "risk_analyst", "to": "judge", "type": "fan_in"},
                {"from": "sentiment_analyst", "to": "judge", "type": "fan_in"},
                {"from": "news_analyst", "to": "judge", "type": "fan_in"},
                {"from": "fund_flow_analyst", "to": "judge", "type": "fan_in"},
                {"from": "valuation_analyst", "to": "judge", "type": "fan_in"},
                {"from": "industry_analyst", "to": "judge", "type": "fan_in"},
                {"from": "macro_analyst", "to": "judge", "type": "fan_in"},
                {"from": "judge", "to": "report_writer", "type": "fan_out"},
                {"from": "judge", "to": "portfolio_advisor", "type": "fan_out"},
                {"from": "report_writer", "to": "END"},
                {"from": "portfolio_advisor", "to": "END"},
            ],
        },
    },
]


def _validate_definition(definition: dict[str, Any]) -> list[str]:
    """Basic structural validation of a workflow definition."""
    errors: list[str] = []
    if "nodes" not in definition:
        errors.append("Missing 'nodes' in definition")
    elif not isinstance(definition["nodes"], list) or len(definition["nodes"]) == 0:
        errors.append("'nodes' must be a non-empty list")

    if "edges" not in definition:
        errors.append("Missing 'edges' in definition")
    elif not isinstance(definition["edges"], list) or len(definition["edges"]) == 0:
        errors.append("'edges' must be a non-empty list")

    if errors:
        return errors

    node_ids = {n.get("id") for n in definition["nodes"]}
    node_ids.add("START")
    node_ids.add("END")

    for edge in definition["edges"]:
        src = edge.get("from")
        tgt = edge.get("to")
        if src not in node_ids:
            errors.append(f"Edge references unknown source node: {src}")
        if tgt not in node_ids:
            errors.append(f"Edge references unknown target node: {tgt}")

    # Check reachability: all nodes should be referenced by at least one edge
    referenced = set()
    for edge in definition["edges"]:
        referenced.add(edge.get("from"))
        referenced.add(edge.get("to"))
    for n in definition["nodes"]:
        if n.get("id") not in referenced:
            errors.append(f"Orphan node: {n.get('id')}")

    return errors


@router.get("", response_model=WorkflowListResponse)
async def list_my_workflows(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_workflows(db, current_user.id, skip, limit)
    return WorkflowListResponse(items=items, total=total)


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_new_workflow(
    body: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await create_workflow(
        db, current_user.id, body.name, body.description,
        body.definition, body.version, body.is_public,
    )
    return wf


@router.get("/templates", response_model=list[WorkflowTemplate])
async def get_templates():
    return _BUILTIN_TEMPLATES


@router.post("/validate")
async def validate_workflow(body: WorkflowCreate):
    errors = _validate_definition(body.definition)
    if errors:
        return WorkflowValidationError(errors=errors)
    return {"valid": True}


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow_detail(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await get_workflow(db, workflow_id)
    if wf is None or (wf.owner_id != current_user.id and not wf.is_public):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_existing_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await get_workflow(db, workflow_id)
    if wf is None or wf.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Workflow not found")
    updates = body.model_dump(exclude_unset=True)
    wf = await update_workflow(db, wf, updates)
    return wf


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await get_workflow(db, workflow_id)
    if wf is None or wf.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await delete_workflow(db, wf)
