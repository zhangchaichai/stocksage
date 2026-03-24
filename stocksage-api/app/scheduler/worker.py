"""Scheduler worker: cron-based task execution engine.

Uses asyncio-based scheduling with cron expression parsing. Each enabled
ScheduledTask is registered as a periodic job. When a job fires, it
dispatches the appropriate action (screener run, workflow run, backtest, etc.)
via the existing background task infrastructure.

Startup:
    Called from app lifespan — loads all enabled tasks from DB and registers them.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# ── Cron parser ──────────────────────────────────────────────────────────────

_WEEKDAY_MAP = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7}


def _parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of matching integers."""
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip().lower()
        # Map weekday names
        for name, num in _WEEKDAY_MAP.items():
            part = part.replace(name, str(num))

        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if base == "*":
                start = min_val
            elif "-" in base:
                start = int(base.split("-")[0])
            else:
                start = int(base)
            values.update(range(start, max_val + 1, step))
        elif "-" in part:
            lo, hi = part.split("-", 1)
            values.update(range(int(lo), int(hi) + 1))
        else:
            values.add(int(part))
    return values


def cron_matches(cron_expr: str, dt: datetime) -> bool:
    """Check if a datetime matches a cron expression.

    Supports 5-field cron: minute hour day month weekday
    """
    parts = cron_expr.strip().split()
    if len(parts) < 5:
        return False

    minute_field, hour_field, day_field, month_field, weekday_field = parts[:5]

    minutes = _parse_cron_field(minute_field, 0, 59)
    hours = _parse_cron_field(hour_field, 0, 23)
    days = _parse_cron_field(day_field, 1, 31)
    months = _parse_cron_field(month_field, 1, 12)
    weekdays = _parse_cron_field(weekday_field, 0, 7)
    # Normalize: 0 and 7 both mean Sunday
    if 0 in weekdays:
        weekdays.add(7)
    if 7 in weekdays:
        weekdays.add(0)

    iso_weekday = dt.isoweekday()  # Monday=1 ... Sunday=7

    return (
        dt.minute in minutes
        and dt.hour in hours
        and dt.day in days
        and dt.month in months
        and iso_weekday in weekdays
    )


# ── Task registry ────────────────────────────────────────────────────────────

class _TaskEntry:
    """In-memory state for a registered scheduled task."""
    __slots__ = ("task_id", "user_id", "task_type", "cron_expr", "tz",
                 "config", "enabled", "name")

    def __init__(self, task_id: str, user_id, task_type: str,
                 cron_expr: str, tz: str, config: dict, enabled: bool,
                 name: str = ""):
        self.task_id = task_id
        self.user_id = user_id
        self.task_type = task_type
        self.cron_expr = cron_expr
        self.tz = tz
        self.config = config
        self.enabled = enabled
        self.name = name


_registered: dict[str, _TaskEntry] = {}
_scheduler_task: asyncio.Task | None = None


def register_task(task) -> None:
    """Register (or re-register) a ScheduledTask from the DB model."""
    tid = str(task.id)
    if not task.enabled:
        _registered.pop(tid, None)
        return
    _registered[tid] = _TaskEntry(
        task_id=tid,
        user_id=task.user_id,
        task_type=task.task_type,
        cron_expr=task.cron_expr,
        tz=task.timezone or "Asia/Shanghai",
        config=task.config or {},
        enabled=task.enabled,
        name=getattr(task, "name", "") or "",
    )
    logger.info("Scheduler: registered task %s (%s) cron=%s",
                tid, task.task_type, task.cron_expr)


def unregister_task(task_id: str) -> None:
    """Unregister a task by ID."""
    entry = _registered.pop(task_id, None)
    if entry:
        logger.info("Scheduler: unregistered task %s", task_id)


def trigger_task_now(task_id: str) -> None:
    """Manually trigger a registered task immediately."""
    entry = _registered.get(task_id)
    if entry is None:
        logger.warning("Scheduler: trigger_task_now — task %s not registered", task_id)
        return
    asyncio.create_task(_execute_task(entry))


# ── Task execution dispatcher ────────────────────────────────────────────────

async def _execute_task(entry: _TaskEntry) -> None:
    """Execute a scheduled task based on its type."""
    logger.info("Scheduler: executing task %s (%s)", entry.task_id, entry.task_type)
    task_id = entry.task_id
    user_id = entry.user_id
    config = entry.config

    try:
        result_data: Any = None
        if entry.task_type == "screener":
            result_data = await _run_screener_task(user_id, config)
        elif entry.task_type == "workflow_run":
            result_data = await _run_workflow_task(user_id, config)
        elif entry.task_type == "workflow_backtest":
            result_data = await _run_workflow_backtest_task(user_id, config)
        elif entry.task_type == "screener_backtest":
            result_data = await _run_screener_backtest_task(user_id, config)
        elif entry.task_type == "memory_forgetting":
            result_data = await _run_memory_forgetting_task(user_id, config)
        else:
            logger.warning("Scheduler: unknown task_type '%s'", entry.task_type)
            await _update_task_status(task_id, "failed", error=f"Unknown task_type: {entry.task_type}")
            return

        await _update_task_status(task_id, "completed")
        await _send_task_notification(entry, "completed", result_data)

    except Exception as e:
        logger.exception("Scheduler: task %s failed: %s", task_id, e)
        await _update_task_status(task_id, "failed", error=str(e))
        await _send_task_notification(entry, "failed", None, error=str(e))


async def _update_task_status(
    task_id: str,
    status: str,
    error: str | None = None,
) -> None:
    """Update the last_run fields on the ScheduledTask record."""
    from app.db.models import ScheduledTask
    from sqlalchemy import select

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(ScheduledTask).where(ScheduledTask.id == uuid.UUID(task_id))
            )
            task = result.scalar_one_or_none()
            if task:
                task.last_run_at = datetime.now(timezone.utc)
                task.last_run_status = status
                task.last_run_error = error if status == "failed" else None
                task.run_count = (task.run_count or 0) + 1
                await db.commit()
    except Exception as e:
        logger.warning("Scheduler: failed to update task status %s: %s", task_id, e)


# ── Task type implementations ────────────────────────────────────────────────

async def _run_screener_task(user_id, config: dict) -> dict:
    """Run a screener job for the user. Returns {"job_id": ...}."""
    from app.db.models import ScreenerJob
    from app.screener.worker import dispatch_screener_job

    async with async_session_factory() as db:
        job = ScreenerJob(
            user_id=user_id,
            filters=[],
            pool=config.get("pool", "hs300"),
            custom_symbols=config.get("custom_symbols"),
            strategy_id=config.get("strategy_id"),
            top_n=config.get("top_n", 20),
            enable_ai_score=config.get("enable_ai_score", False),
            data_date=config.get("data_date"),
            date_from=config.get("date_from"),
            date_to=config.get("date_to"),
            market_filters=config.get("market_filters", []),
            status="queued",
        )
        db.add(job)
        await db.flush()
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    dispatch_screener_job(job_id)
    logger.info("Scheduler: dispatched screener job %s", job_id)
    return {"job_id": str(job_id)}


async def _run_workflow_task(user_id, config: dict) -> dict:
    """Run a workflow analysis for a stock. Returns {"run_id": ...}."""
    from app.db.models import Workflow, WorkflowRun
    from app.runs.worker import dispatch_run
    from sqlalchemy import select

    workflow_id = config.get("workflow_id")
    symbol = config.get("symbol", "")
    stock_name = config.get("stock_name", "")

    if not symbol:
        raise ValueError("workflow_run config missing 'symbol'")

    async with async_session_factory() as db:
        # Resolve workflow
        wf_id = None
        if workflow_id:
            wf_id = uuid.UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id

        run = WorkflowRun(
            owner_id=user_id,
            workflow_id=wf_id,
            symbol=symbol,
            stock_name=stock_name,
            status="queued",
            config_overrides=config.get("config_overrides", {}),
        )
        db.add(run)
        await db.flush()
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    dispatch_run(run_id)
    logger.info("Scheduler: dispatched workflow run %s for %s", run_id, symbol)
    return {"run_id": str(run_id)}


async def _run_workflow_backtest_task(user_id, config: dict) -> dict:
    """Run batch backtests for all eligible investment actions. Returns result summaries."""
    from app.backtest.service import run_batch_backtest

    period_days = config.get("period_days", 30)
    symbol = config.get("symbol")

    backtest_summaries: list[dict] = []

    async with async_session_factory() as db:
        if symbol:
            # Backtest specific symbol's actions
            from sqlalchemy import select
            from app.db.models import InvestmentAction, BacktestResult
            actions_q = (
                select(InvestmentAction)
                .where(InvestmentAction.user_id == user_id)
                .where(InvestmentAction.symbol == symbol)
                .where(InvestmentAction.action_type.in_(["buy", "sell"]))
            )
            result = await db.execute(actions_q)
            actions = list(result.scalars().all())
            from app.backtest.service import run_backtest
            for action in actions:
                await run_backtest(db, user_id, action.id, period_days)
        else:
            await run_batch_backtest(db, user_id, period_days)
        await db.commit()

        # Collect recent backtest results for notification
        from sqlalchemy import select
        from app.db.models import BacktestResult
        recent_q = (
            select(BacktestResult)
            .where(BacktestResult.user_id == user_id)
            .order_by(BacktestResult.created_at.desc())
            .limit(50)
        )
        rows = await db.execute(recent_q)
        for bt in rows.scalars().all():
            backtest_summaries.append({
                "symbol": bt.symbol,
                "price_change_pct": bt.price_change_pct,
                "direction_correct": bt.direction_correct,
                "sharpe_ratio": bt.sharpe_ratio,
            })

    logger.info("Scheduler: workflow backtest completed for user %s", user_id)
    return {"backtest_results": backtest_summaries}


async def _run_screener_backtest_task(user_id, config: dict) -> dict:
    """Run screener backtest for a completed screener job. Returns {"result_id": ...}."""
    from app.screener_backtest.service import run_screener_backtest
    from app.db.models import ScreenerJob
    from sqlalchemy import select

    period_days = config.get("period_days", 30)
    job_id = config.get("job_id")
    strategy_id = config.get("strategy_id")

    result_id = None

    async with async_session_factory() as db:
        if job_id:
            # Backtest a specific job
            bt_result = await run_screener_backtest(
                db, user_id, uuid.UUID(job_id), period_days
            )
            if bt_result:
                result_id = str(bt_result.id) if hasattr(bt_result, "id") else None
        elif strategy_id:
            # Find the latest completed job for this strategy
            result = await db.execute(
                select(ScreenerJob)
                .where(ScreenerJob.user_id == user_id)
                .where(ScreenerJob.strategy_id == strategy_id)
                .where(ScreenerJob.status == "completed")
                .order_by(ScreenerJob.created_at.desc())
                .limit(1)
            )
            job = result.scalar_one_or_none()
            if job:
                bt_result = await run_screener_backtest(db, user_id, job.id, period_days)
                if bt_result:
                    result_id = str(bt_result.id) if hasattr(bt_result, "id") else None
            else:
                raise ValueError(f"No completed screener job found for strategy {strategy_id}")
        else:
            # Backtest the most recent completed screener job
            result = await db.execute(
                select(ScreenerJob)
                .where(ScreenerJob.user_id == user_id)
                .where(ScreenerJob.status == "completed")
                .order_by(ScreenerJob.created_at.desc())
                .limit(1)
            )
            job = result.scalar_one_or_none()
            if job:
                bt_result = await run_screener_backtest(db, user_id, job.id, period_days)
                if bt_result:
                    result_id = str(bt_result.id) if hasattr(bt_result, "id") else None
            else:
                raise ValueError("No completed screener jobs to backtest")

        await db.commit()

    logger.info("Scheduler: screener backtest completed for user %s", user_id)
    return {"result_id": result_id}


async def _run_memory_forgetting_task(user_id, config: dict) -> dict:
    """Run memory forgetting cycle for a user.

    Compresses old analysis events and archives expired price anchors.
    Config options:
        max_anchor_age_days: int (default 365)
    """
    from app.memory.forgetting import run_forgetting_cycle

    async with async_session_factory() as db:
        results = await run_forgetting_cycle(db, user_id)
        await db.commit()

    logger.info(
        "Scheduler: memory forgetting completed for user %s — "
        "compressed %d events, archived %d expired anchors",
        user_id, results.get("compressed", 0), results.get("expired_anchors", 0),
    )
    return results


# ── Email notification ────────────────────────────────────────────────────────

async def _send_task_notification(
    entry: _TaskEntry,
    status: str,
    result_data: Any | None,
    error: str | None = None,
) -> None:
    """Send an email notification after task completion/failure.

    Never raises — failures are logged and silently ignored so they
    don't interfere with the main scheduler flow.
    """
    from app.config import settings
    if not settings.REPORT_EMAIL_ENABLED:
        return

    try:
        from app.notification.email_sender import send_email
        from app.notification import formatter

        task_name = entry.name or entry.task_type

        if status == "failed":
            subject, html = formatter.format_task_failed(
                task_name, entry.task_type, error or "Unknown error",
            )
            await send_email(subject, html)
            return

        # Successful — format based on task type
        subject: str | None = None
        html: str | None = None

        if entry.task_type == "screener" and result_data:
            job_id = result_data.get("job_id")
            if job_id:
                subject, html = await _format_screener_notification(job_id)

        elif entry.task_type == "workflow_run" and result_data:
            run_id = result_data.get("run_id")
            if run_id:
                subject, html = await _format_workflow_notification(run_id)

        elif entry.task_type == "workflow_backtest" and result_data:
            bt_results = result_data.get("backtest_results", [])
            if bt_results:
                subject, html = formatter.format_backtest_report(bt_results)

        elif entry.task_type == "screener_backtest" and result_data:
            result_id = result_data.get("result_id")
            if result_id:
                subject, html = await _format_screener_backtest_notification(result_id)

        elif entry.task_type == "memory_forgetting" and result_data:
            subject, html = formatter.format_memory_forgetting_report(result_data)

        if subject and html:
            await send_email(subject, html)

    except Exception as e:
        logger.warning("Scheduler: failed to send notification for task %s: %s", entry.task_id, e)


async def _format_screener_notification(job_id: str) -> tuple[str, str]:
    """Load a ScreenerJob and format it for email."""
    from app.db.models import ScreenerJob
    from app.notification.formatter import format_screener_report
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(ScreenerJob).where(ScreenerJob.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if job:
            return format_screener_report(job)
    return ("选股任务完成", "<p>选股任务已完成，但无法加载结果详情。</p>")


async def _format_workflow_notification(run_id: str) -> tuple[str, str]:
    """Load a WorkflowRun and format it for email."""
    from app.db.models import WorkflowRun
    from app.notification.formatter import format_workflow_report
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(WorkflowRun).where(WorkflowRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if run:
            return format_workflow_report(run)
    return ("分析任务完成", "<p>工作流分析已完成，但无法加载结果详情。</p>")


async def _format_screener_backtest_notification(result_id: str) -> tuple[str, str]:
    """Load a ScreenerBacktestResult and format it for email."""
    from app.db.models import ScreenerBacktestResult
    from app.notification.formatter import format_screener_backtest_report
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(ScreenerBacktestResult).where(
                ScreenerBacktestResult.id == uuid.UUID(result_id)
            )
        )
        bt = result.scalar_one_or_none()
        if bt:
            return format_screener_backtest_report(bt)
    return ("选股回测完成", "<p>选股回测已完成，但无法加载结果详情。</p>")


# ── Scheduler loop ───────────────────────────────────────────────────────────

async def _scheduler_loop() -> None:
    """Main scheduler loop: checks every 30 seconds if any cron jobs should fire."""
    logger.info("Scheduler: loop started with %d registered tasks", len(_registered))
    last_fired: dict[str, datetime] = {}

    while True:
        try:
            now = datetime.now(timezone.utc)

            for tid, entry in list(_registered.items()):
                if not entry.enabled:
                    continue

                # Convert to task timezone for cron matching
                try:
                    import zoneinfo
                    tz = zoneinfo.ZoneInfo(entry.tz)
                    local_now = now.astimezone(tz)
                except Exception:
                    local_now = now

                if cron_matches(entry.cron_expr, local_now):
                    # Avoid firing multiple times in the same minute
                    last = last_fired.get(tid)
                    if last and (now - last).total_seconds() < 60:
                        continue

                    last_fired[tid] = now
                    logger.info("Scheduler: cron match for task %s (%s) at %s",
                                tid, entry.task_type, local_now.strftime("%H:%M"))
                    asyncio.create_task(_execute_task(entry))

        except Exception as e:
            logger.exception("Scheduler: loop error: %s", e)

        await asyncio.sleep(30)


async def start_scheduler() -> None:
    """Start the scheduler and load all enabled tasks from DB."""
    global _scheduler_task

    # Load tasks from DB
    try:
        async with async_session_factory() as db:
            from app.scheduler.service import list_enabled_tasks
            tasks = await list_enabled_tasks(db)
            for task in tasks:
                register_task(task)
            logger.info("Scheduler: loaded %d enabled tasks from DB", len(tasks))
    except Exception as e:
        logger.warning("Scheduler: failed to load tasks from DB: %s", e)

    # Start the loop
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Scheduler: started")


def stop_scheduler() -> None:
    """Stop the scheduler loop."""
    global _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None
        logger.info("Scheduler: stopped")
