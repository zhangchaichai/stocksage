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

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 120

    # Usage quota
    DAILY_TOKEN_QUOTA: int = 1000000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
