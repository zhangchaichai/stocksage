"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    # Startup — auto-create tables (dev convenience, use alembic in production)
    from app.db.models import Base
    from app.db.session import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Start the scheduler
    from app.scheduler.worker import start_scheduler, stop_scheduler
    await start_scheduler()

    yield

    # Shutdown
    stop_scheduler()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="StockSage Multi-Agent Stock Analysis Platform API",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Routers ----

from app.auth.router import router as auth_router
from app.workflows.router import router as workflows_router
from app.skills.router import router as skills_router
from app.runs.router import router as runs_router
from app.runs.progress import router as progress_router
from app.reports.router import router as reports_router

from app.marketplace.router import router as marketplace_router
from app.sharing.router import router as sharing_router
from app.usage.router import router as usage_router
from app.portfolio.router import router as portfolio_router
from app.memory.router import router as memory_router
from app.backtest.router import router as backtest_router
from app.evolution.router import router as evolution_router
from app.indicators.router import router as indicators_router
from app.screener.router import router as screener_router
from app.chat.router import router as chat_router
from app.scheduler.router import router as scheduler_router
from app.screener_backtest.router import router as screener_backtest_router
from app.middleware import RateLimitMiddleware

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(workflows_router, prefix="/api/workflows", tags=["workflows"])
app.include_router(skills_router, prefix="/api/skills", tags=["skills"])
app.include_router(runs_router, prefix="/api/runs", tags=["runs"])
app.include_router(progress_router, prefix="/api/runs", tags=["progress"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])

app.include_router(marketplace_router, prefix="/api/marketplace", tags=["marketplace"])
app.include_router(sharing_router, prefix="/api/sharing", tags=["sharing"])
app.include_router(usage_router, prefix="/api/usage", tags=["usage"])
app.include_router(portfolio_router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(memory_router, prefix="/api/memory", tags=["memory"])
app.include_router(backtest_router, prefix="/api/backtest", tags=["backtest"])
app.include_router(evolution_router, prefix="/api/evolution", tags=["evolution"])
app.include_router(indicators_router, prefix="/api/indicators", tags=["indicators"])
app.include_router(screener_router, prefix="/api/screener", tags=["screener"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(scheduler_router, prefix="/api/scheduler", tags=["scheduler"])
app.include_router(screener_backtest_router, prefix="/api/screener-backtest", tags=["screener-backtest"])

# Rate limiting
app.add_middleware(RateLimitMiddleware, calls_per_minute=120)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
