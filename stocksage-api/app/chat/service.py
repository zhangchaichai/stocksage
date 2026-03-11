"""Chat service: execute intents and generate responses."""

from __future__ import annotations

import logging

from app.chat.schemas import ChatMessageResponse

logger = logging.getLogger(__name__)

# Route mapping for navigation intents
_NAV_ROUTES = {
    "open_screener": ("/screener", "Stock Screener"),
    "open_indicators": ("/indicators", "Indicator Dashboard"),
    "open_backtest": ("/backtest", "Backtest Center"),
    "open_portfolio": ("/portfolio", "Portfolio"),
    "open_memory": ("/memory", "Memory"),
    "open_evolution": ("/evolution", "Strategy Evolution"),
    "run_workflow": ("/workflows", "Workflows"),
}


async def handle_intent(
    intent: str,
    metadata: dict | None,
    original_message: str,
    user_id,
    db,
) -> ChatMessageResponse:
    """Process the recognized intent and produce a response."""

    # Navigation intents
    if intent in _NAV_ROUTES:
        route, label = _NAV_ROUTES[intent]
        # If indicators + symbol, route with symbol
        if intent == "open_indicators" and metadata and metadata.get("symbol"):
            symbol = metadata["symbol"]
            return ChatMessageResponse(
                reply=f"Opening indicator dashboard for {symbol}...",
                intent=intent,
                action="navigate",
                data={"route": f"/indicators?symbol={symbol}"},
            )
        return ChatMessageResponse(
            reply=f"Opening {label}...",
            intent=intent,
            action="navigate",
            data={"route": route},
        )

    # Analyze stock → create a workflow run
    if intent == "analyze_stock" and metadata and metadata.get("symbol"):
        symbol = metadata["symbol"]
        run_id = await _auto_create_run(symbol, user_id, db)
        if run_id:
            return ChatMessageResponse(
                reply=f"Analysis started for {symbol}. You can track its progress.",
                intent=intent,
                action="run_analysis",
                data={"run_id": str(run_id), "symbol": symbol, "route": f"/runs/{run_id}"},
            )
        return ChatMessageResponse(
            reply=f"Could not start analysis for {symbol}. Please try running manually from the dashboard.",
            intent=intent,
            action="none",
            data={"symbol": symbol},
        )

    # General question → LLM chat
    if intent == "general_question":
        reply = await _llm_chat(original_message)
        return ChatMessageResponse(
            reply=reply,
            intent=intent,
            action="none",
        )

    return ChatMessageResponse(
        reply="I'm not sure how to help with that. Try asking about a stock or feature.",
        intent="general_question",
        action="none",
    )


async def _auto_create_run(symbol: str, user_id, db) -> str | None:
    """Create a workflow run for the given symbol using the first available workflow."""
    try:
        from sqlalchemy import select
        from app.db.models import Workflow, WorkflowRun
        from app.runs.worker import dispatch_run

        # Find user's first workflow, or any public workflow
        result = await db.execute(
            select(Workflow)
            .where(Workflow.owner_id == user_id)
            .limit(1)
        )
        workflow = result.scalar_one_or_none()

        if workflow is None:
            result = await db.execute(
                select(Workflow)
                .where(Workflow.is_public == True)  # noqa: E712
                .limit(1)
            )
            workflow = result.scalar_one_or_none()

        if workflow is None:
            return None

        run = WorkflowRun(
            owner_id=user_id,
            workflow_id=workflow.id,
            symbol=symbol,
            stock_name=symbol,
            status="queued",
        )
        db.add(run)
        await db.flush()
        await db.commit()
        await db.refresh(run)

        dispatch_run(run.id)
        return str(run.id)

    except Exception as e:
        logger.exception("Auto-create run failed: %s", e)
        return None


async def _llm_chat(message: str) -> str:
    """Generate an LLM response for a general question."""
    try:
        from stocksage.llm.factory import create_llm
        from app.config import settings

        provider = settings.DEFAULT_LLM_PROVIDER or "deepseek"
        llm = create_llm(provider)

        prompt = f"""You are StockSage, an intelligent stock analysis assistant. Answer the following question concisely and helpfully. If it's about stocks, provide relevant financial insight.

User: {message}
Assistant:"""

        response = llm.invoke(prompt)
        return response.content.strip() if hasattr(response, "content") else str(response).strip()

    except Exception as e:
        logger.warning("LLM chat failed: %s", e)
        return "Sorry, I'm unable to process your question right now. Please try again later."
