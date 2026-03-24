"""Application configuration via Pydantic Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://stocksage:stocksage@localhost:5432/stocksage"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # App
    APP_NAME: str = "StockSage API"
    DEBUG: bool = False

    # StockSage core
    SKILLS_DIR: str = ""  # defaults to stocksage/skills if empty
    DEFAULT_LLM_PROVIDER: str = "deepseek"
    LLM_FALLBACK_CHAIN: str = ""  # comma-separated, e.g. "deepseek,openai,anthropic"
    LLM_HEALTH_COOLDOWN: int = 300  # seconds to skip a failed provider

    # Orchestrator (v2 streaming architecture)
    USE_ORCHESTRATOR: bool = False  # Set True to use RunOrchestrator instead of ThreadPool worker

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 120

    # Usage quota
    DAILY_TOKEN_QUOTA: int = 1000000

    # Auto-backtest: trigger backtest automatically after workflow/screener completion
    AUTO_BACKTEST_AFTER_WORKFLOW: bool = False
    AUTO_BACKTEST_AFTER_SCREENER: bool = False
    AUTO_BACKTEST_PERIOD_DAYS: int = 30

    # Email notification
    REPORT_EMAIL_ENABLED: bool = True
    REPORT_EMAIL_SMTP_HOST: str = "smtp.163.com"
    REPORT_EMAIL_SMTP_PORT: int = 465
    REPORT_EMAIL_SENDER: str = "18001365209@163.com"
    REPORT_EMAIL_USER: str = "18001365209@163.com"
    REPORT_EMAIL_PASSWORD: str = "DEq5AJtZQ9CyVeGw"
    REPORT_EMAIL_DEFAULT_TO: str = "441158425@qq.com"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
