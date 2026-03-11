"""Screener API router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScreenerJob, User
from app.db.session import get_db
from app.deps import get_current_user
from app.screener.schemas import (
    NLQueryRequest,
    NLQueryResponse,
    ScreenerJobCreate,
    ScreenerJobResponse,
    ScreenerMatch,
    StrategyBacktestRequest,
    StrategyBacktestResponse,
    StrategyDetail,
    StrategyListItem,
)
from app.screener.worker import dispatch_screener_job

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

def _job_to_response(job: ScreenerJob) -> ScreenerJobResponse:
    matches = [
        ScreenerMatch(
            symbol=m.get("symbol", ""),
            name=m.get("name", ""),
            indicators=m.get("indicators", {}),
            ai_score=m.get("ai_score"),
            ai_reason=m.get("ai_reason"),
        )
        for m in (job.results or [])
    ]
    candidates_raw = job.candidates if hasattr(job, "candidates") and job.candidates else []
    candidates = [
        ScreenerMatch(
            symbol=c.get("symbol", ""),
            name=c.get("name", ""),
            indicators=c.get("indicators", {}),
        )
        for c in candidates_raw
    ]
    return ScreenerJobResponse(
        id=str(job.id),
        status=job.status,
        filters=job.filters or [],
        pool=job.pool,
        strategy_id=getattr(job, "strategy_id", None),
        top_n=getattr(job, "top_n", 20) or 20,
        enable_ai_score=getattr(job, "enable_ai_score", False) or False,
        data_date=getattr(job, "data_date", None),
        date_from=getattr(job, "date_from", None),
        date_to=getattr(job, "date_to", None),
        market_filters=getattr(job, "market_filters", None) or [],
        total_scanned=job.total_scanned or 0,
        candidates=candidates,
        candidate_count=len(candidates_raw),
        matches=matches,
        analyst_reports=getattr(job, "analyst_reports", None),
        error=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else "",
    )


def _strat_to_list_item(s) -> StrategyListItem:
    return StrategyListItem(
        id=s.id,
        name=s.name,
        description=s.description,
        icon=s.icon,
        category=s.category,
        risk_level=s.risk_level,
        suitable_for=s.suitable_for,
        pool=s.pool,
        sell_condition_count=len(s.sell_conditions),
    )


def _strat_to_detail(s) -> StrategyDetail:
    return StrategyDetail(
        id=s.id,
        name=s.name,
        description=s.description,
        icon=s.icon,
        category=s.category,
        risk_level=s.risk_level,
        suitable_for=s.suitable_for,
        pool=s.pool,
        sell_condition_count=len(s.sell_conditions),
        pywencai_queries=s.pywencai_queries,
        display_fields=s.display_fields,
        sell_conditions=[
            {"type": c.type, "label": c.label, **c.params}
            for c in s.sell_conditions
        ],
        risk_params=s.risk_params,
    )


# ── strategy endpoints ────────────────────────────────────────────────────────

@router.get("/strategies", response_model=list[StrategyListItem])
async def list_strategies(
    current_user: User = Depends(get_current_user),
):
    """List all available predefined screener strategies."""
    from app.screener.strategies.registry import registry
    return [_strat_to_list_item(s) for s in registry.list_all()]


@router.get("/strategies/{strategy_id}", response_model=StrategyDetail)
async def get_strategy(
    strategy_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get full detail of a predefined strategy."""
    from app.screener.strategies.registry import registry
    strat = registry.get(strategy_id)
    if strat is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return _strat_to_detail(strat)


# ── screener job endpoints ────────────────────────────────────────────────────

@router.post("/run", response_model=ScreenerJobResponse, status_code=201)
async def run_screener(
    body: ScreenerJobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a new stock screening job.

    Pass ``strategy_id`` to use a predefined strategy (pywencai path), or
    ``filters`` for the custom condition path (legacy behaviour).
    """
    # Validate strategy_id if provided
    if body.strategy_id:
        from app.screener.strategies.registry import registry
        if registry.get(body.strategy_id) is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy_id: {body.strategy_id!r}. "
                       f"Valid IDs: {[s.id for s in registry.list_all()]}",
            )

    job = ScreenerJob(
        user_id=current_user.id,
        filters=[f.model_dump() for f in body.filters],
        pool=body.pool,
        custom_symbols=body.custom_symbols,
        strategy_id=body.strategy_id,
        top_n=body.top_n,
        enable_ai_score=body.enable_ai_score,
        data_date=body.data_date,
        date_from=body.date_from,
        date_to=body.date_to,
        market_filters=body.market_filters or [],
        status="queued",
    )
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(job)

    dispatch_screener_job(job.id)
    return _job_to_response(job)


@router.get("/jobs", response_model=list[ScreenerJobResponse])
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's screening jobs."""
    result = await db.execute(
        select(ScreenerJob)
        .where(ScreenerJob.user_id == current_user.id)
        .order_by(ScreenerJob.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return [_job_to_response(j) for j in result.scalars().all()]


@router.get("/jobs/{job_id}", response_model=ScreenerJobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific screening job result."""
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    result = await db.execute(
        select(ScreenerJob).where(
            ScreenerJob.id == uid,
            ScreenerJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Screener job not found")
    return _job_to_response(job)


# ── NL query translation ──────────────────────────────────────────────────────

@router.post("/nl_query", response_model=NLQueryResponse)
async def nl_query(
    body: NLQueryRequest,
    current_user: User = Depends(get_current_user),
):
    """Translate a natural language query into a pywencai query string.

    Uses rule-based matching first (instant), then falls back to DeepSeek LLM.
    """
    from app.screener.nl_translator import (
        find_strategy_hint,
        translate_by_llm,
        translate_by_rules,
    )

    q = body.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Rule layer (fast path)
    pywencai_query = translate_by_rules(q)

    # LLM fallback
    if not pywencai_query:
        pywencai_query = await translate_by_llm(q)

    if not pywencai_query:
        return NLQueryResponse(
            pywencai_query="",
            error="无法解析查询，请尝试更具体的描述，如「低价高成长」「主力资金流入」",
        )

    strategy_hint = find_strategy_hint(q)
    return NLQueryResponse(
        pywencai_query=pywencai_query,
        strategy_hint=strategy_hint,
    )


# ── Strategy backtest ─────────────────────────────────────────────────────────

@router.post("/backtest", response_model=StrategyBacktestResponse)
async def strategy_backtest(
    body: StrategyBacktestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Simulate holding returns for a completed screener job's matches.

    Fetches the current price for each symbol in the screener job results,
    computes the theoretical return over ``period_days`` from the job's
    completion time, and returns aggregate stats.

    Note: This is a lightweight simulation using current prices, not a full
    historical replay.  For accurate backtesting, use the backtest module.
    """
    from concurrent.futures import ThreadPoolExecutor
    import asyncio

    from app.screener.strategies.registry import registry

    # Validate strategy
    strat = registry.get(body.strategy_id)
    if strat is None:
        raise HTTPException(status_code=404, detail=f"Strategy not found: {body.strategy_id!r}")

    # Load the screener job
    try:
        job_uid = uuid.UUID(body.job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id")

    result = await db.execute(
        select(ScreenerJob).where(
            ScreenerJob.id == job_uid,
            ScreenerJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Screener job not found")
    if job.status != "completed" or not job.results:
        raise HTTPException(status_code=400, detail="Screener job is not completed or has no results")

    matches = job.results  # list of {symbol, name, indicators}
    if not matches:
        return StrategyBacktestResponse(
            strategy_id=body.strategy_id,
            strategy_name=strat.name,
            job_id=body.job_id,
            period_days=body.period_days,
            total_stocks=0,
            items=[],
        )

    def _fetch_price_sync(symbol: str) -> float | None:
        """Fetch latest close price for a symbol."""
        try:
            import akshare as ak
            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily",
                adjust="qfq",
            )
            if df is not None and not df.empty:
                return float(df.iloc[-1]["收盘"])
        except Exception:
            pass
        return None

    loop = asyncio.get_event_loop()
    _exec = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bt")

    # Fetch current prices concurrently
    async def _get_price(symbol: str) -> float | None:
        return await loop.run_in_executor(_exec, _fetch_price_sync, symbol)

    price_tasks = [_get_price(m["symbol"]) for m in matches]
    prices = await asyncio.gather(*price_tasks, return_exceptions=True)

    # Build items and compute stats
    from app.screener.schemas import StrategyBacktestItem
    items: list[StrategyBacktestItem] = []
    returns: list[float] = []

    for m, price in zip(matches, prices):
        current = float(price) if isinstance(price, (int, float)) else None
        # Use close from indicators as entry price proxy
        entry = m.get("indicators", {}).get("close")
        if entry is not None:
            try:
                entry = float(entry)
            except (TypeError, ValueError):
                entry = None

        pct = None
        if entry and current and entry > 0:
            pct = round((current - entry) / entry * 100, 2)
            returns.append(pct)

        items.append(StrategyBacktestItem(
            symbol=m["symbol"],
            name=m.get("name", ""),
            entry_price=entry,
            current_price=current,
            price_change_pct=pct,
        ))

    avg_return = round(sum(returns) / len(returns), 2) if returns else None
    win_rate = round(sum(1 for r in returns if r > 0) / len(returns), 3) if returns else None
    max_gain = round(max(returns), 2) if returns else None
    max_loss = round(min(returns), 2) if returns else None

    return StrategyBacktestResponse(
        strategy_id=body.strategy_id,
        strategy_name=strat.name,
        job_id=body.job_id,
        period_days=body.period_days,
        total_stocks=len(items),
        avg_return_pct=avg_return,
        win_rate=win_rate,
        max_gain_pct=max_gain,
        max_loss_pct=max_loss,
        items=items,
    )
