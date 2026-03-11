"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(256), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workflows = relationship("Workflow", back_populates="owner", cascade="all, delete-orphan")
    custom_skills = relationship("CustomSkill", back_populates="owner", cascade="all, delete-orphan")
    runs = relationship("WorkflowRun", back_populates="owner", cascade="all, delete-orphan")
    investment_actions = relationship("InvestmentAction", back_populates="owner", cascade="all, delete-orphan")
    memory_items = relationship("MemoryItem", back_populates="owner", cascade="all, delete-orphan")


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    definition = Column(JSON, nullable=False)
    version = Column(String(32), default="1.0.0")
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="workflows")
    runs = relationship("WorkflowRun", back_populates="workflow", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_workflows_owner_id", "owner_id"),
    )


class CustomSkill(Base):
    __tablename__ = "custom_skills"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    version = Column(String(32), default="1.0.0")
    type = Column(String(32), nullable=False)  # agent, data, decision, etc.
    tags = Column(JSON, default=list)
    definition_md = Column(Text, nullable=False)  # Raw .md content
    is_published = Column(Boolean, default=False, nullable=False)
    forked_from = Column(Uuid, nullable=True)
    stars_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="custom_skills")

    __table_args__ = (
        Index("ix_custom_skills_owner_id", "owner_id"),
        Index("ix_custom_skills_name_owner", "name", "owner_id", unique=True),
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workflow_id = Column(Uuid, ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String(16), nullable=False)
    stock_name = Column(String(64), default="")
    status = Column(
        String(16),
        default="queued",
        nullable=False,
    )
    config_overrides = Column(JSON, default=dict)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="runs")
    workflow = relationship("Workflow", back_populates="runs")
    events = relationship("RunEvent", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_workflow_runs_owner_id", "owner_id"),
        Index("ix_workflow_runs_status", "status"),
    )


class RunEvent(Base):
    __tablename__ = "run_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id = Column(Uuid, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(32), nullable=False)
    node_name = Column(String(128), nullable=True)
    phase = Column(String(64), nullable=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run = relationship("WorkflowRun", back_populates="events")

    __table_args__ = (
        Index("ix_run_events_run_id", "run_id"),
    )


class SkillStar(Base):
    __tablename__ = "skill_stars"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    skill_id = Column(Uuid, ForeignKey("custom_skills.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_skill_stars_skill_user", "skill_id", "user_id", unique=True),
    )


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(Uuid, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True)
    tokens_input = Column(Integer, default=0, nullable=False)
    tokens_output = Column(Integer, default=0, nullable=False)
    provider = Column(String(32), default="deepseek")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_usage_records_user_id", "user_id"),
        Index("ix_usage_records_created_at", "created_at"),
    )


class MemoryResource(Base):
    """Raw data source for memory extraction."""
    __tablename__ = "memory_resources"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(32), nullable=False)  # workflow_run / user_input / market_feed / news
    source_id = Column(String(128), nullable=True)  # e.g. WorkflowRun.id
    modality = Column(String(32), nullable=False)  # analysis_result / price_data / news_text / user_chat
    snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    items = relationship("MemoryItem", back_populates="resource", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_memory_resources_user_id", "user_id"),
    )


class MemoryItem(Base):
    """Structured memory entry extracted from resources."""
    __tablename__ = "memory_items"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(Uuid, ForeignKey("memory_resources.id", ondelete="SET NULL"), nullable=True)
    memory_type = Column(String(32), nullable=False)
    # stock_profile / analysis_event / market_event / price_anchor
    # strategy_review / user_preference / portfolio_context / industry_insight / investment_action
    content = Column(Text, nullable=False)
    structured_data = Column(JSON, nullable=True)
    importance_weight = Column(Float, default=0.5, nullable=False)
    access_count = Column(Integer, default=0, nullable=False)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    happened_at = Column(DateTime(timezone=True), nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="memory_items")
    resource = relationship("MemoryResource", back_populates="items")
    category_links = relationship("MemoryCategoryItem", back_populates="item", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_memory_items_user_id", "user_id"),
        Index("ix_memory_items_user_type", "user_id", "memory_type"),
    )


class MemoryCategory(Base):
    """Semantic category for organizing memory items."""
    __tablename__ = "memory_categories"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    item_links = relationship("MemoryCategoryItem", back_populates="category", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_memory_categories_user_name", "user_id", "name", unique=True),
    )


class MemoryCategoryItem(Base):
    """Many-to-many link between MemoryItem and MemoryCategory."""
    __tablename__ = "memory_category_items"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    item_id = Column(Uuid, ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Uuid, ForeignKey("memory_categories.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    item = relationship("MemoryItem", back_populates="category_links")
    category = relationship("MemoryCategory", back_populates="item_links")

    __table_args__ = (
        Index("ix_memory_cat_items_unique", "item_id", "category_id", unique=True),
    )


class InvestmentAction(Base):
    """User investment action record."""
    __tablename__ = "investment_actions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(Uuid, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String(16), nullable=False)
    stock_name = Column(String(64), default="")
    action_type = Column(String(16), nullable=False)  # buy / sell / hold / watch
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=True)
    amount = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    analysis_snapshot = Column(JSON, nullable=True)
    action_date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="investment_actions")
    run = relationship("WorkflowRun")
    backtest_results = relationship("BacktestResult", back_populates="action", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_investment_actions_user_id", "user_id"),
        Index("ix_investment_actions_user_symbol", "user_id", "symbol"),
    )


class BacktestResult(Base):
    """Backtest result for an investment action."""
    __tablename__ = "backtest_results"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action_id = Column(Uuid, ForeignKey("investment_actions.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(Uuid, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String(16), nullable=False)
    period_days = Column(Integer, nullable=False)
    backtest_date = Column(DateTime(timezone=True), nullable=True)
    action_price = Column(Float, nullable=True)
    current_price = Column(Float, nullable=True)
    price_change_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    max_gain_pct = Column(Float, nullable=True)
    predicted_direction = Column(String(8), nullable=True)  # up / down / neutral
    actual_direction = Column(String(8), nullable=True)
    direction_correct = Column(Boolean, nullable=True)
    diagnosis = Column(JSON, nullable=True)
    # Phase 4: enhanced risk & dealer metrics
    sharpe_ratio = Column(Float, nullable=True)
    sortino_ratio = Column(Float, nullable=True)
    var_95 = Column(Float, nullable=True)
    wyckoff_phase_at_action = Column(String(32), nullable=True)
    dealer_signals_at_action = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    action = relationship("InvestmentAction", back_populates="backtest_results")
    evolution_suggestions = relationship("EvolutionSuggestion", back_populates="backtest", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_backtest_results_user_id", "user_id"),
        Index("ix_backtest_results_action_period", "action_id", "period_days"),
    )


class ScreenerJob(Base):
    """Stock screener job."""
    __tablename__ = "screener_jobs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filters = Column(JSON, default=list)
    pool = Column(String(32), default="hs300")
    custom_symbols = Column(JSON, nullable=True)
    strategy_id = Column(String(64), nullable=True)   # predefined strategy key
    top_n = Column(Integer, default=20)               # user-configurable result count
    enable_ai_score = Column(Boolean, default=False)   # whether to run AIScorer
    data_date = Column(String(16), nullable=True)       # user-specified trading date for pywencai
    date_from = Column(String(16), nullable=True)        # price data start date (YYYY-MM-DD)
    date_to = Column(String(16), nullable=True)          # price data end date (YYYY-MM-DD)
    market_filters = Column(JSON, nullable=True)         # board/market filter list, e.g. ["sh_main","cyb"]
    status = Column(String(16), default="queued")  # queued / running / completed / failed
    total_scanned = Column(Integer, default=0)
    candidates = Column(JSON, nullable=True)          # Layer 1: full candidate list
    results = Column(JSON, nullable=True)             # Layer 2: top_n AI-scored results
    analyst_reports = Column(JSON, nullable=True)      # AI analyst team reports
    error_message = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_screener_jobs_user_id", "user_id"),
    )


class ChatMessage(Base):
    """Chat message history."""
    __tablename__ = "chat_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    intent = Column(String(64), nullable=True)
    action_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_chat_messages_user_id", "user_id"),
    )


class EvolutionSuggestion(Base):
    """Evolution suggestion generated from backtest diagnosis."""
    __tablename__ = "evolution_suggestions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    backtest_id = Column(Uuid, ForeignKey("backtest_results.id", ondelete="SET NULL"), nullable=True)
    evolution_type = Column(String(32), nullable=False)
    # skill_weight / skill_prompt / workflow_structure / new_skill
    target_type = Column(String(32), nullable=False)  # skill / workflow
    target_name = Column(String(128), nullable=False)
    suggestion_text = Column(Text, nullable=False)
    suggestion_diff = Column(JSON, nullable=True)
    priority = Column(String(8), default="medium")
    confidence = Column(Float, default=0.5)
    status = Column(String(16), default="pending")  # pending / accepted / rejected / applied
    applied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    backtest = relationship("BacktestResult", back_populates="evolution_suggestions")

    __table_args__ = (
        Index("ix_evolution_suggestions_user_status", "user_id", "status"),
    )
