"""Background worker for screener jobs — v2.1 three-layer architecture.

Layer 1 (Data Acquisition):
  Path A  strategy.pywencai_enabled  → PywencaiEngine.query()  → full candidates
  Path B  strategy.akshare_enrich    → Snapshot + Enrich        → full candidates
  Path C  custom filters             → per-stock scan           → full candidates

Layer 2 (AI Scoring, optional):
  Take top_n from candidates → AIScorer.score() → scored results

Layer 3 (Deep Workflow Analysis):
  User-triggered via POST /runs/batch — not handled here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial

from sqlalchemy import select

from app.db.models import ScreenerJob
from app.db.session import async_session_factory
from app.screener.service import (
    evaluate_filters,
    extract_key_indicators,
    resolve_stock_pool,
)

logger = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="screener")
_background_tasks: set[asyncio.Task] = set()


# ── Date range helpers ────────────────────────────────────────────────────────

def _price_days_from_range(date_from: str | None, date_to: str | None) -> int | None:
    """Convert date_from/date_to to a 'days' count for fetch_price_data.

    Returns None if no range is specified (use DataFetcher default).
    The days value is calendar days * 1.5 to account for weekends.
    """
    if not date_from and not date_to:
        return None
    try:
        from datetime import datetime as _dt
        end = _dt.strptime(date_to, "%Y-%m-%d") if date_to else _dt.now()
        start = _dt.strptime(date_from, "%Y-%m-%d") if date_from else None
        if start is None:
            return None
        delta = (end - start).days
        # Buffer factor so AkShare tail() has enough rows
        return max(int(delta * 1.6), 30)
    except Exception:
        return None


# ── lazy imports so missing deps don't break startup ────────────────────────

def _get_pywencai_engine():
    from app.screener.engines.pywencai_engine import PywencaiEngine
    return PywencaiEngine()


def _get_registry():
    from app.screener.strategies.registry import registry
    return registry


# ── Helper: bypass local proxy for domestic API calls ────────────────────────

@contextlib.contextmanager
def _no_proxy():
    """Temporarily clear proxy env vars so domestic APIs (eastmoney, 10jqka) connect directly.

    macOS system proxy (e.g. Clash on 127.0.0.1:7890) is picked up by urllib/requests
    and breaks AkShare/pywencai calls to Chinese financial data APIs.
    """
    saved = {}
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        yield
    finally:
        os.environ.update(saved)


# ── Candidate slimming (reduce JSON storage size) ────────────────────────────

def _slim_candidates(candidates: list[dict]) -> list[dict]:
    """Keep only symbol/name/indicators per candidate."""
    return [
        {
            "symbol": c.get("symbol", ""),
            "name": c.get("name", ""),
            "indicators": c.get("indicators", {}),
        }
        for c in candidates
    ]


# ── Path C: original per-stock scan (unchanged) ─────────────────────────────

def _scan_stock_sync(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict | None:
    """Fetch data and compute indicators for a single stock (sync)."""
    try:
        from stocksage.data.fetcher import DataFetcher
        from stocksage.data.indicators import compute_all_indicators

        with _no_proxy():
            fetcher = DataFetcher()
            data: dict = {}
            data["price_data"] = fetcher.fetch_price_data(
                symbol, start_date=start_date, end_date=end_date
            )
            data["stock_info"] = fetcher.fetch_stock_info(symbol)
            data["financial"] = fetcher.fetch_financial(symbol, end_date=end_date)
            data["fund_flow"] = fetcher.fetch_fund_flow(
                symbol, start_date=start_date, end_date=end_date
            )
            data["margin"] = fetcher.fetch_margin_data(
                symbol, start_date=start_date, end_date=end_date
            )
            data["quarterly"] = fetcher.fetch_quarterly(symbol, end_date=end_date)
            data["balance_sheet"] = fetcher.fetch_balance_sheet(symbol, end_date=end_date)
            data["northbound"] = fetcher.fetch_northbound_flow(
                symbol, start_date=start_date, end_date=end_date
            )
            data["dragon_tiger"] = fetcher.fetch_dragon_tiger(
                symbol, start_date=start_date, end_date=end_date
            )

        return compute_all_indicators(data)
    except Exception as e:
        logger.warning("Failed to scan %s: %s", symbol, e)
        return None


async def _run_custom_filters(job: ScreenerJob) -> tuple[list[dict], int]:
    """Original path C — iterate pool stock by stock."""
    filters = job.filters or []
    custom = job.custom_symbols or []
    market_filters = getattr(job, "market_filters", None) or []
    stock_pool = resolve_stock_pool(job.pool, custom, market_filters=market_filters)

    date_from = getattr(job, "date_from", None)
    date_to = getattr(job, "date_to", None)

    loop = asyncio.get_event_loop()
    matches: list[dict] = []
    scanned = 0

    for symbol, name in stock_pool:
        scanned += 1
        indicators = await loop.run_in_executor(
            _pool, partial(_scan_stock_sync, symbol, date_from, date_to)
        )
        if indicators is None:
            continue
        if evaluate_filters(indicators, filters):
            snapshot = extract_key_indicators(indicators)
            matches.append({"symbol": symbol, "name": name, "indicators": snapshot})

    return matches, scanned


# ── Path A: pywencai engine ──────────────────────────────────────────────────

def _pywencai_query_sync(queries, top_n, sort_field, sort_ascending, display_fields):
    """Run pywencai query synchronously (called via run_in_executor).

    NOTE: top_n here is the pywencai-level limit (from strategy YAML).
    We pass a large number to get as many candidates as possible,
    then slice to user's top_n later in Layer 2.
    """
    engine = _get_pywencai_engine()
    success, df, msg = engine.query(
        queries=queries,
        top_n=top_n,
        sort_field=sort_field,
        sort_ascending=sort_ascending,
    )
    if not success or df is None:
        return False, [], msg
    matches = engine.df_to_matches(df, display_fields)
    return True, matches, msg


async def _run_pywencai_path(job: ScreenerJob, strategy) -> tuple[list[dict], int]:
    """Path A: pywencai fast query, optional AkShare enrichment.

    Returns ALL candidates (not sliced by top_n yet).
    """
    loop = asyncio.get_event_loop()

    # Request ALL candidates from pywencai (the AI analyst team is designed
    # to handle 1000+ stocks via pre-aggregation — no need to cap here).
    pywencai_limit = 5000

    # Build effective query list: inject date constraint and board filter
    queries = list(strategy.pywencai_queries)
    date_suffix = _build_pywencai_date_suffix(
        getattr(job, "date_from", None),
        getattr(job, "date_to", None),
        getattr(job, "data_date", None),
    )
    board_suffix = _build_pywencai_board_suffix(getattr(job, "market_filters", None) or [])
    if date_suffix or board_suffix:
        extra = (date_suffix + "，" + board_suffix).strip("，")
        queries = [q + "，" + extra for q in queries]

    success, matches, msg = await loop.run_in_executor(
        _pool,
        partial(
            _pywencai_query_sync,
            queries,
            pywencai_limit,
            strategy.pywencai_sort_field,
            strategy.pywencai_sort_ascending,
            strategy.display_fields,
        ),
    )

    if not success:
        logger.warning(
            "Job %s: pywencai failed (%s), falling back to AkShare path", job.id, msg
        )
        return await _run_akshare_two_stage(job, strategy)

    # Post-filter by market_filters on the returned symbol codes
    market_filters = getattr(job, "market_filters", None) or []
    if market_filters and matches:
        matches = _filter_matches_by_market(matches, market_filters)

    logger.info("Job %s: pywencai path OK — %d candidates (%s)", job.id, len(matches), msg)
    return matches, len(matches)


def _build_pywencai_date_suffix(
    date_from: str | None,
    date_to: str | None,
    data_date: str | None,
) -> str:
    """Build a pywencai date constraint clause."""
    if data_date:
        return f"日期{data_date}"
    if date_from and date_to:
        return f"{date_from}至{date_to}"
    if date_to:
        return f"截至{date_to}"
    return ""


_BOARD_LABEL: dict[str, str] = {
    "sh_main": "沪市主板",
    "sz_main": "深市主板",
    "cyb": "创业板",
    "kcb": "科创板",
    "bj": "北交所",
}

# Code prefix sets for post-filter (pywencai may not perfectly honour board clause)
_MARKET_PREFIXES_WORKER: dict[str, tuple[str, ...]] = {
    "sh_main": ("60", "90"),
    "sz_main": ("00",),
    "cyb":     ("30",),
    "kcb":     ("688",),
    "bj":      ("4", "8"),
}
_MARKET_EXCLUDE_WORKER: dict[str, tuple[str, ...]] = {
    "sh_main": ("688",),
}


def _build_pywencai_board_suffix(market_filters: list[str]) -> str:
    """Build a pywencai board constraint clause, e.g. '创业板或科创板'."""
    labels = [_BOARD_LABEL[mf] for mf in market_filters if mf in _BOARD_LABEL]
    if not labels:
        return ""
    return "或".join(labels)


def _filter_matches_by_market(matches: list[dict], market_filters: list[str]) -> list[dict]:
    """Post-filter match dicts by code prefix (safety net after pywencai)."""
    result = []
    for m in matches:
        code = str(m.get("symbol", ""))
        for mf in market_filters:
            prefixes = _MARKET_PREFIXES_WORKER.get(mf, ())
            excl = _MARKET_EXCLUDE_WORKER.get(mf, ())
            if code.startswith(prefixes) and not code.startswith(excl):
                result.append(m)
                break
    return result


# ── Path B: AkShare two-stage scan ──────────────────────────────────────────

def _akshare_snapshot_sync(
    filters: list[dict],
    max_candidates: int = 200,
    market_filters: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Stage 1: fast-filter with AkShare full-market snapshot."""
    try:
        import akshare as ak
        import pandas as pd

        with _no_proxy():
            df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return []

        # Board/market filter
        if market_filters:
            from app.screener.service import _apply_market_filters
            df = _apply_market_filters(df, market_filters)

        # Vectorised filter using pandas
        COLUMN_MAP = {
            "close":         "最新价",
            "market_cap":    "总市值",
            "pe":            "市盈率-动态",
            "turnover_rate": "换手率",
            "vol_ratio":     "量比",
            "change_pct":    "涨跌幅",
            "amplitude":     "振幅",
        }

        mask = pd.Series([True] * len(df), index=df.index)

        for f in filters:
            field = f.get("field", "")
            op = f.get("operator", "")
            value = f.get("value")
            col = COLUMN_MAP.get(field)
            if col is None or col not in df.columns:
                continue
            try:
                series = pd.to_numeric(df[col], errors="coerce")
                if op == "lt":
                    mask = mask & (series < value)
                elif op == "lte":
                    mask = mask & (series <= value)
                elif op == "gt":
                    mask = mask & (series > value)
                elif op == "gte":
                    mask = mask & (series >= value)
                elif op == "eq":
                    mask = mask & (series == value)
                elif op == "ne":
                    mask = mask & (series != value)
            except Exception:
                continue

        filtered = df[mask].head(max_candidates)
        return list(zip(filtered["代码"].astype(str), filtered["名称"].astype(str)))

    except Exception as exc:
        logger.error("AkShare snapshot fast filter failed: %s", exc)
        return []


def _enrich_stock_sync(
    symbol: str,
    required_fields: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Stage 2: deep indicator computation for a single stock within date range."""
    try:
        # Only use cache when no date range specified (cache key doesn't include dates)
        if not start_date and not end_date:
            from app.indicators.router import _cache_get, _cache_set, _compute_indicators_sync
            cached = _cache_get(symbol, 120)
            if cached is not None:
                return cached
            with _no_proxy():
                result = _compute_indicators_sync(symbol, 120)
            _cache_set(symbol, 120, result)
            return result

        # Date-specific fetch — bypass cache, fetch directly
        from stocksage.data.fetcher import DataFetcher
        from stocksage.data.indicators import compute_all_indicators

        with _no_proxy():
            fetcher = DataFetcher()
            data: dict = {}
            data["price_data"] = fetcher.fetch_price_data(
                symbol, start_date=start_date, end_date=end_date
            )
            data["stock_info"] = fetcher.fetch_stock_info(symbol)
            data["financial"] = fetcher.fetch_financial(symbol, end_date=end_date)
            data["fund_flow"] = fetcher.fetch_fund_flow(
                symbol, start_date=start_date, end_date=end_date
            )
            data["margin"] = fetcher.fetch_margin_data(
                symbol, start_date=start_date, end_date=end_date
            )
            data["quarterly"] = fetcher.fetch_quarterly(symbol, end_date=end_date)
            data["balance_sheet"] = fetcher.fetch_balance_sheet(symbol, end_date=end_date)
            data["northbound"] = fetcher.fetch_northbound_flow(
                symbol, start_date=start_date, end_date=end_date
            )
            data["dragon_tiger"] = fetcher.fetch_dragon_tiger(
                symbol, start_date=start_date, end_date=end_date
            )
        return compute_all_indicators(data)
    except Exception as exc:
        logger.warning("Enrich %s failed: %s", symbol, exc)
        return {}


async def _run_akshare_two_stage(job: ScreenerJob, strategy) -> tuple[list[dict], int]:
    """Path B: Stage1 snapshot fast-filter → Stage2 deep indicator enrichment."""
    loop = asyncio.get_event_loop()
    filters = job.filters or []
    market_filters = getattr(job, "market_filters", None) or []
    date_from = getattr(job, "date_from", None)
    date_to = getattr(job, "date_to", None)

    # Stage 1
    candidates: list[tuple[str, str]] = await loop.run_in_executor(
        _pool, partial(_akshare_snapshot_sync, filters, 200, market_filters)
    )
    stage1_count = len(candidates)
    logger.info("Job %s: Stage1 snapshot gave %d candidates", job.id, stage1_count)

    if not candidates:
        return [], 0

    # Stage 2 — enrich in parallel with date range
    matches: list[dict] = []
    required = strategy.akshare_required_fields if strategy else []

    async def _enrich_one(symbol: str, name: str) -> dict | None:
        indicators = await loop.run_in_executor(
            _pool, partial(_enrich_stock_sync, symbol, required, date_from, date_to)
        )
        if not indicators:
            return None
        if evaluate_filters(indicators, filters):
            snapshot = extract_key_indicators(indicators)
            return {"symbol": symbol, "name": name, "indicators": snapshot}
        return None

    tasks = [_enrich_one(sym, name) for sym, name in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, dict):
            matches.append(r)

    logger.info("Job %s: Stage2 enrichment gave %d matches from %d candidates",
                job.id, len(matches), stage1_count)
    return matches, stage1_count


# ── Main dispatcher ──────────────────────────────────────────────────────────

async def execute_screener_job(job_id: uuid.UUID) -> None:
    """Execute a screener job with three-layer architecture.

    Layer 1: Data acquisition → all candidates → stored in job.candidates
    Layer 2: AI scoring (optional) → top_n scored → stored in job.results
    """
    async with async_session_factory() as db:
        result = await db.execute(select(ScreenerJob).where(ScreenerJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None or job.status != "queued":
            return

        job.status = "running"
        await db.commit()

        try:
            strategy = None
            if job.strategy_id:
                reg = _get_registry()
                strategy = reg.get(job.strategy_id)
                if strategy is None:
                    raise ValueError(f"Unknown strategy_id: {job.strategy_id!r}")

            # ══════════════════════════════════════════════════════════════
            # Layer 1: Data Acquisition — get full candidate list
            # ══════════════════════════════════════════════════════════════

            # ── Path A: pywencai strategy ────────────────────────────────
            if strategy and strategy.pywencai_enabled:
                all_candidates, scanned = await _run_pywencai_path(job, strategy)

            # ── Path B: AkShare-only strategy (e.g. dealer_wyckoff) ──────
            elif strategy and strategy.akshare_enrich_enabled:
                all_candidates, scanned = await _run_akshare_two_stage(job, strategy)

            # ── Path C: custom filters (legacy) ──────────────────────────
            else:
                all_candidates, scanned = await _run_custom_filters(job)

            # Store full candidate list (Layer 1 output)
            job.candidates = _slim_candidates(all_candidates)
            job.total_scanned = scanned
            await db.commit()  # Persist early so frontend can show candidates
            logger.info(
                "Job %s Layer 1 done: %d candidates, %d scanned",
                job_id, len(all_candidates), scanned,
            )

            # ══════════════════════════════════════════════════════════════
            # Layer 2: AI Analyst Team (optional) — multi-perspective analysis
            # ══════════════════════════════════════════════════════════════

            top_n = job.top_n or 20
            top_slice = all_candidates[:top_n]

            if job.enable_ai_score and all_candidates:
                try:
                    from app.screener.quant.analyst_team import AnalystTeam

                    strategy_name = (
                        f"{strategy.name}（{strategy.description[:30]}）"
                        if strategy else "自定义条件筛选"
                    )
                    report_result = await AnalystTeam.analyze(
                        all_candidates,
                        strategy_context=strategy_name,
                        top_n=top_n,
                        date_from=getattr(job, "date_from", None),
                        date_to=getattr(job, "date_to", None),
                    )

                    # Store analyst reports
                    job.analyst_reports = report_result

                    # Extract top_picks from synthesis and enrich with indicators
                    top_picks = report_result.get("synthesis", {}).get("top_picks", [])
                    if top_picks:
                        # Build lookup for enriching picks with indicators
                        cand_map = {
                            c.get("symbol", ""): c for c in all_candidates
                        }
                        enriched = []
                        for pick in top_picks:
                            sym = str(pick.get("symbol", "")).strip()
                            cand = cand_map.get(sym)
                            if cand:
                                enriched.append({
                                    **cand,
                                    "ai_score": pick.get("score", 0),
                                    "ai_reason": pick.get("reason", ""),
                                })
                            else:
                                enriched.append({
                                    "symbol": sym,
                                    "name": pick.get("name", ""),
                                    "indicators": {},
                                    "ai_score": pick.get("score", 0),
                                    "ai_reason": pick.get("reason", ""),
                                })
                        job.results = enriched
                    else:
                        # Synthesis produced no picks — fall back to top_slice
                        job.results = top_slice

                    logger.info(
                        "Job %s Layer 2 done: AnalystTeam produced %d picks, %d reports",
                        job_id,
                        len(job.results or []),
                        len(report_result.get("analysts", [])),
                    )
                except Exception as exc:
                    # AnalystTeam failed — fall back to simple AIScorer
                    logger.warning(
                        "Job %s: AnalystTeam failed (%s), falling back to AIScorer",
                        job_id, exc,
                    )
                    try:
                        from app.screener.quant.ai_scorer import AIScorer
                        scorer = AIScorer()
                        strategy_name = (
                            f"{strategy.name}（{strategy.description[:30]}）"
                            if strategy else "自定义条件筛选"
                        )
                        scored = await scorer.score(top_slice, strategy_context=strategy_name)
                        job.results = scored
                    except Exception as exc2:
                        logger.warning("Job %s: AIScorer fallback also failed: %s", job_id, exc2)
                        job.results = top_slice
            else:
                # AI scoring disabled — just take top_n as-is
                job.results = top_slice

            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info(
                "Job %s completed: %d results, %d candidates, %d scanned",
                job_id, len(job.results or []), len(all_candidates), scanned,
            )

        except Exception as e:
            logger.exception("Screener job %s failed: %s", job_id, e)
            job.status = "failed"
            job.error_message = str(e)
            await db.commit()


def dispatch_screener_job(job_id: uuid.UUID) -> None:
    """Fire-and-forget a screener job as a background task."""
    task = asyncio.create_task(execute_screener_job(job_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
