"""Memory subsystem constants and shared definitions."""

# Importance weights by memory type — single source of truth.
# Used by extractor.py (write path) and forgetting.py (scoring path).
MEMORY_TYPE_WEIGHTS: dict[str, float] = {
    "stock_profile": 0.9,
    "analysis_event": 0.6,
    "market_event": 0.7,
    "price_anchor": 0.5,
    "strategy_review": 0.8,
    "user_preference": 0.9,
    "portfolio_context": 0.4,
    "industry_insight": 0.6,
    "investment_action": 0.7,
}
