"""
ThunderBots AI Business Advisor — AI Chat (NEW)

All AI calls go through the EXISTING AI Engine provider resolution chain
(app.services.ai_engine.resolve_agent_provider / get_provider_for_user /
validate_model_for_provider) — the identical chain already used by
services/personal_email_ai_service.py. No new provider classes, no new
API-key storage.

The model is given the real, already-computed business numbers (overview +
recommendations + predictions, from business_advisor_service) as context
and asked to answer the owner's question grounded in those numbers — it is
never asked to invent figures.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_engine import (
    get_provider_for_user, resolve_agent_provider, validate_model_for_provider, ProviderError,
)
from app.services import business_advisor_service as advisor_svc

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the AI Business Advisor for a small shop owner using ThunderBots. "
    "You will be given the shop's real, already-computed performance data "
    "(today/yesterday revenue, profit, orders, customers, stock levels, "
    "fastest/slowest products, AI recommendations, and predictions). "
    "Answer the owner's question using ONLY this data — never invent numbers "
    "that are not present. If the data doesn't cover the question, say so "
    "plainly. Be concise, practical, and speak like a helpful business "
    "advisor, not a data dump — use plain sentences, not JSON."
)


def _format_context(overview: dict, recommendations: list[dict], predictions: dict, alerts: list[dict]) -> str:
    lines = [
        f"Today's revenue: {overview['today_revenue']}",
        f"Yesterday's revenue: {overview['yesterday_revenue']}",
        f"Revenue change vs yesterday: {overview['revenue_change_pct']}%",
        f"Profit today: {overview['profit']}",
        f"Orders today: {overview['orders']}",
        f"New customers today: {overview['new_customers']}",
        f"Returning customers today: {overview['returning_customers']}",
        f"Out of stock products: {[p['product_name'] for p in overview['out_of_stock_products']]}",
        f"Low stock products: {[p['product_name'] for p in overview['low_stock_products']]}",
        f"Fast moving products: {[p['product_name'] for p in overview['fast_moving_products']]}",
        f"Slow moving products: {[p['product_name'] for p in overview['slow_moving_products']]}",
        f"Best selling products: {[p['product_name'] for p in overview['best_selling_products']]}",
        f"Tomorrow's predicted sales: {predictions['tomorrow_sales_estimate']}",
        f"Next week predicted revenue: {predictions['next_week_revenue_estimate']}",
        "Current AI recommendations: " + "; ".join(
            f"{r['title']} (priority: {r['priority']}, confidence: {r['confidence']}%) — {r['reason']}"
            for r in recommendations[:6]
        ),
        "Active alerts: " + "; ".join(a["message"] for a in alerts) if alerts else "Active alerts: none",
    ]
    return "\n".join(lines)


async def ask(db: AsyncSession, shop_id: str, user_id: str, question: str) -> dict:
    overview = await advisor_svc.get_overview(db, shop_id)
    recommendations = await advisor_svc.get_recommendations(db, shop_id)
    predictions = await advisor_svc.get_predictions(db, shop_id)
    alerts = await advisor_svc.get_alerts(db, shop_id)
    context = _format_context(overview, recommendations, predictions, alerts)

    prompt = f"Business data:\n{context}\n\nOwner's question: {question}"

    try:
        provider_id = await resolve_agent_provider(None, user_id)
        llm = await get_provider_for_user(provider_id, user_id)
        model, _ = validate_model_for_provider(provider_id, None)
        answer = await llm.complete(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4, max_tokens=600, model=model,
        )
        return {"answer": (answer or "").strip(), "grounded": True}
    except ProviderError as e:
        return {
            "answer": (
                "I need an AI provider configured (Settings → AI Providers) to answer free-form "
                f"questions. Here's what the numbers show right now: {context}"
            ),
            "grounded": True,
            "error": str(e),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning(f"business_advisor_ai_service.ask failed: {e}")
        return {
            "answer": "Sorry, I couldn't generate an AI answer right now. Please try again shortly.",
            "grounded": False,
        }


async def generate_daily_summary(db: AsyncSession, shop_id: str, user_id: str) -> dict:
    return await ask(db, shop_id, user_id, "Generate today's business summary in 4-6 sentences.")
