"""
ThunderBots AI Business Advisor — Core Service (NEW)

Purely additive, read-only analysis layer built on top of the EXISTING
Smart Shop Assistant tables (Shop, ShopProduct, ShopReservation,
ShopReservationItem, ShopProductMovement) and the EXISTING
shop_inventory_intelligence_service (fast/slow movers, low stock,
reorder suggestions, best sellers, dead stock — all reused verbatim,
never re-implemented here).

No existing reservation/inventory/analytics logic is modified. Every
number below is computed from real rows already written by
shop_assistant_service — nothing is fabricated.

Revenue / profit are estimated from `completed` reservations using each
product's CURRENT price (and cost_price, else the shop's
default_margin_percent) — the ledger does not snapshot price-at-sale, so
this is a best-effort estimate, clearly the same convention already used
by the rest of the Shop Assistant ("never a fabricated number", but a
current-price-based estimate where no per-sale price is stored).

Results are cached in Redis (short TTL) via the existing CacheService —
"background analysis / cached calculations" from the spec — and degrade
gracefully (simply recompute) when Redis is unavailable, exactly like
every other cache usage in this codebase.
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import CacheService
from app.models.shop_assistant import (
    Shop, ShopProduct, ShopReservation, ShopReservationItem, ShopProductMovement,
)
from app.services import shop_inventory_intelligence_service as intel_svc

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 180  # background-analysis cache window
_cache = CacheService()


def _day_bounds(day: "datetime.date") -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _today_utc() -> "datetime.date":
    return datetime.now(timezone.utc).date()


async def _get_shop(db: AsyncSession, shop_id: str) -> Shop:
    result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = result.scalar_one_or_none()
    if shop is None:
        raise ValueError(f"Shop {shop_id} not found")
    return shop


def _effective_margin(shop: Shop) -> float:
    try:
        return float(shop.default_margin_percent)
    except Exception:  # noqa: BLE001
        return 30.0


def _line_revenue_and_profit(product: ShopProduct, quantity: int, margin: float) -> tuple[float, float]:
    price = float(product.price) if product.price is not None else 0.0
    revenue = price * quantity
    if product.cost_price is not None:
        cost = float(product.cost_price) * quantity
    else:
        cost = revenue * (1 - margin / 100)
    profit = revenue - cost
    return revenue, profit


# ─────────────────────────────────────────────────────────────────────────────
# Revenue / Orders / Customers
# ─────────────────────────────────────────────────────────────────────────────

async def _completed_reservations_in_range(
    db: AsyncSession, shop_id: str, start: datetime, end: datetime
) -> list[ShopReservation]:
    result = await db.execute(
        select(ShopReservation)
        .where(
            ShopReservation.shop_id == shop_id,
            ShopReservation.status == "completed",
            ShopReservation.completed_at >= start,
            ShopReservation.completed_at < end,
        )
    )
    return list(result.scalars().all())


async def get_revenue_summary(db: AsyncSession, shop_id: str, day: Optional["datetime.date"] = None) -> dict:
    """Revenue, profit, and order count for one calendar day (default:
    today, UTC), computed from completed reservations only."""
    shop = await _get_shop(db, shop_id)
    day = day or _today_utc()
    start, end = _day_bounds(day)
    reservations = await _completed_reservations_in_range(db, shop_id, start, end)

    if not reservations:
        return {"date": day.isoformat(), "revenue": 0.0, "profit": 0.0, "orders": 0}

    reservation_ids = [r.id for r in reservations]
    items_result = await db.execute(
        select(ShopReservationItem).where(ShopReservationItem.reservation_id.in_(reservation_ids))
    )
    items = list(items_result.scalars().all())
    product_ids = {i.product_id for i in items}
    products_result = await db.execute(select(ShopProduct).where(ShopProduct.id.in_(product_ids)))
    products = {p.id: p for p in products_result.scalars().all()}

    margin = _effective_margin(shop)
    revenue = 0.0
    profit = 0.0
    for item in items:
        product = products.get(item.product_id)
        if product is None:
            continue
        r, p = _line_revenue_and_profit(product, item.quantity, margin)
        revenue += r
        profit += p

    return {
        "date": day.isoformat(),
        "revenue": round(revenue, 2),
        "profit": round(profit, 2),
        "orders": len(reservations),
    }


async def get_customer_breakdown(db: AsyncSession, shop_id: str, day: Optional["datetime.date"] = None) -> dict:
    """New vs returning customers for one day, based on customer_name —
    "new" means this is the first reservation ThunderBots has ever seen
    from that name at this shop; "returning" means they had at least one
    earlier reservation."""
    day = day or _today_utc()
    start, end = _day_bounds(day)

    todays_result = await db.execute(
        select(ShopReservation.customer_name, ShopReservation.created_at)
        .where(ShopReservation.shop_id == shop_id, ShopReservation.created_at >= start, ShopReservation.created_at < end)
    )
    todays_rows = todays_result.all()
    if not todays_rows:
        return {"date": day.isoformat(), "new_customers": 0, "returning_customers": 0, "total_customers": 0}

    names_today = {name.strip().lower() for name, _ in todays_rows if name}

    earlier_result = await db.execute(
        select(func.distinct(func.lower(ShopReservation.customer_name)))
        .where(ShopReservation.shop_id == shop_id, ShopReservation.created_at < start)
    )
    earlier_names = {n.strip() for (n,) in earlier_result.all() if n}

    new_customers = len(names_today - earlier_names)
    returning_customers = len(names_today & earlier_names)

    return {
        "date": day.isoformat(),
        "new_customers": new_customers,
        "returning_customers": returning_customers,
        "total_customers": len(names_today),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Overview — the main dashboard payload
# ─────────────────────────────────────────────────────────────────────────────

async def get_overview(db: AsyncSession, shop_id: str) -> dict:
    cache_key = f"business_advisor:overview:{shop_id}:{_today_utc().isoformat()}"
    cached = await _cache.get(cache_key)
    if cached:
        return cached

    today = _today_utc()
    yesterday = today - timedelta(days=1)

    today_summary = await get_revenue_summary(db, shop_id, today)
    yesterday_summary = await get_revenue_summary(db, shop_id, yesterday)
    customers = await get_customer_breakdown(db, shop_id, today)

    low_stock_alerts = await intel_svc.get_low_stock_alerts(db, shop_id)
    low_stock = [a for a in low_stock_alerts if a["severity"] == "low"]
    out_of_stock = [a for a in low_stock_alerts if a["severity"] == "out_of_stock"]
    fast_moving = await intel_svc.get_fast_moving_products(db, shop_id, limit=5)
    slow_moving = await intel_svc.get_slow_moving_products(db, shop_id, limit=5)
    best_selling = await intel_svc.get_best_selling_products(db, shop_id, limit=5)

    revenue_change_pct = None
    if yesterday_summary["revenue"] > 0:
        revenue_change_pct = round(
            ((today_summary["revenue"] - yesterday_summary["revenue"]) / yesterday_summary["revenue"]) * 100, 1
        )

    payload = {
        "today_revenue": today_summary["revenue"],
        "yesterday_revenue": yesterday_summary["revenue"],
        "revenue_change_pct": revenue_change_pct,
        "profit": today_summary["profit"],
        "orders": today_summary["orders"],
        "new_customers": customers["new_customers"],
        "returning_customers": customers["returning_customers"],
        "low_stock_products": low_stock,
        "out_of_stock_products": out_of_stock,
        "fast_moving_products": fast_moving,
        "slow_moving_products": slow_moving,
        "best_selling_products": best_selling,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await _cache.set(cache_key, payload, ttl=CACHE_TTL_SECONDS)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# AI Recommendations (deterministic, rule-based — no external LLM call, so
# these always work even with no AI provider configured)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Recommendation:
    type: str
    priority: str        # "high" | "medium" | "low"
    confidence: int       # 0-100
    title: str
    reason: str
    suggested_action: str
    product_id: Optional[str] = None
    product_name: Optional[str] = None


def _rec_to_dict(r: Recommendation) -> dict:
    return {
        "type": r.type, "priority": r.priority, "confidence": r.confidence,
        "title": r.title, "reason": r.reason, "suggested_action": r.suggested_action,
        "product_id": r.product_id, "product_name": r.product_name,
    }


async def get_recommendations(db: AsyncSession, shop_id: str) -> list[dict]:
    cache_key = f"business_advisor:recommendations:{shop_id}:{_today_utc().isoformat()}"
    cached = await _cache.get(cache_key)
    if cached:
        return cached

    recs: list[Recommendation] = []

    # 1. Restock — from real reorder suggestions
    reorders = await intel_svc.get_reorder_suggestions(db, shop_id)
    for r in reorders[:3]:
        urgency_high = r["quantity_available"] == 0 or r["avg_daily_demand"] > 0
        recs.append(Recommendation(
            type="restock", priority="high" if r["quantity_available"] == 0 else "medium",
            confidence=90 if r["avg_daily_demand"] > 0 else 65,
            title=f"Restock {r['product_name']}",
            reason=(f"Only {r['quantity_available']} left, selling at "
                    f"{r['avg_daily_demand']}/day on average."),
            suggested_action=f"Reorder {r['suggested_reorder_quantity']} units of {r['product_name']}.",
            product_id=r["product_id"], product_name=r["product_name"],
        ))

    # 2. Reduce price / remove slow movers / better alternatives — from dead stock
    dead_stock = await intel_svc.get_dead_stock(db, shop_id)
    best_sellers = await intel_svc.get_best_selling_products(db, shop_id, limit=3)
    for d in dead_stock[:2]:
        idle = d["days_since_last_sale"]
        if idle is None or idle >= 45:
            recs.append(Recommendation(
                type="remove_slow_moving", priority="medium", confidence=70,
                title=f"Remove or discontinue {d['product_name']}",
                reason=(f"{d['product_name']} has never sold" if idle is None
                        else f"{d['product_name']} hasn't sold in {idle} days"),
                suggested_action="Consider discontinuing this product or clearing remaining stock.",
                product_id=d["product_id"], product_name=d["product_name"],
            ))
        else:
            recs.append(Recommendation(
                type="reduce_price", priority="medium", confidence=60,
                title=f"Reduce price of {d['product_name']}",
                reason=f"{d['product_name']} hasn't moved in {idle} days despite {d['quantity_available']} units in stock.",
                suggested_action="Lower the price 10-15% to clear the stock.",
                product_id=d["product_id"], product_name=d["product_name"],
            ))
        if best_sellers:
            alt = best_sellers[0]
            recs.append(Recommendation(
                type="better_alternative", priority="low", confidence=55,
                title=f"Recommend {alt['product_name']} instead of {d['product_name']}",
                reason=f"{alt['product_name']} is a proven best seller ({alt['units_sold']} units sold) in the same shop.",
                suggested_action=f"Highlight {alt['product_name']} to customers browsing {d['product_name']}.",
                product_id=alt["product_id"], product_name=alt["product_name"],
            ))

    # 3. Combo offer — pair a fast mover with a slow mover
    fast_moving = await intel_svc.get_fast_moving_products(db, shop_id, limit=1)
    slow_moving = await intel_svc.get_slow_moving_products(db, shop_id, limit=1)
    if fast_moving and slow_moving and fast_moving[0]["product_id"] != slow_moving[0]["product_id"]:
        recs.append(Recommendation(
            type="combo_offer", priority="medium", confidence=60,
            title=f"Create a combo: {fast_moving[0]['product_name']} + {slow_moving[0]['product_name']}",
            reason=f"{fast_moving[0]['product_name']} is a fast mover — bundling it can lift sales of the slower {slow_moving[0]['product_name']}.",
            suggested_action="Bundle both products at a small combined discount.",
        ))

    # 4. Weekend discount — Thu/Fri, if slow movers exist
    weekday = datetime.now(timezone.utc).weekday()  # 0=Mon..6=Sun
    if weekday in (3, 4) and slow_moving:
        recs.append(Recommendation(
            type="weekend_discount", priority="low", confidence=55,
            title="Run a weekend discount",
            reason="Weekend footfall is typically higher and several products are moving slowly.",
            suggested_action="Offer a short weekend discount on slow-moving products.",
        ))

    # 5. WhatsApp campaign — if revenue dropped or few new customers
    overview = await get_overview(db, shop_id)
    if (overview["revenue_change_pct"] is not None and overview["revenue_change_pct"] < -10) or overview["new_customers"] == 0:
        recs.append(Recommendation(
            type="whatsapp_campaign", priority="medium", confidence=65,
            title="Start a WhatsApp campaign",
            reason=("Revenue dropped vs yesterday." if (overview["revenue_change_pct"] or 0) < -10
                    else "No new customers today."),
            suggested_action="Send a WhatsApp broadcast with a limited-time offer to re-engage customers.",
        ))

    # 6. Increase inventory before expected demand — rising demand trend
    trend = await intel_svc.get_demand_trend(db, shop_id)
    if len(trend) >= 7:
        recent = sum(p["units"] for p in trend[-3:])
        prior = sum(p["units"] for p in trend[-7:-3]) or 1
        if recent > prior * 1.3 and fast_moving:
            recs.append(Recommendation(
                type="increase_inventory", priority="high", confidence=72,
                title=f"Increase inventory of {fast_moving[0]['product_name']}",
                reason="Demand has risen noticeably over the last 3 days versus the prior period.",
                suggested_action="Increase stock ahead of the expected continued rise in demand.",
                product_id=fast_moving[0]["product_id"], product_name=fast_moving[0]["product_name"],
            ))

    if not recs:
        recs.append(Recommendation(
            type="all_good", priority="low", confidence=80,
            title="No urgent actions right now",
            reason="Inventory, sales, and customer trends all look healthy.",
            suggested_action="Keep monitoring — check back tomorrow for fresh recommendations.",
        ))

    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: (priority_order.get(r.priority, 3), -r.confidence))
    result = [_rec_to_dict(r) for r in recs]
    await _cache.set(cache_key, result, ttl=CACHE_TTL_SECONDS)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Predictions
# ─────────────────────────────────────────────────────────────────────────────

async def _daily_revenue_series(db: AsyncSession, shop_id: str, days: int = 14) -> list[dict]:
    since_day = _today_utc() - timedelta(days=days - 1)
    series = []
    for i in range(days):
        day = since_day + timedelta(days=i)
        summary = await get_revenue_summary(db, shop_id, day)
        series.append({"date": summary["date"], "value": summary["revenue"]})
    return series


async def get_predictions(db: AsyncSession, shop_id: str) -> dict:
    cache_key = f"business_advisor:predictions:{shop_id}:{_today_utc().isoformat()}"
    cached = await _cache.get(cache_key)
    if cached:
        return cached

    revenue_series = await _daily_revenue_series(db, shop_id, days=7)
    values = [p["value"] for p in revenue_series]
    nonzero = [v for v in values if v > 0]
    avg_daily = (sum(values) / len(values)) if values else 0.0

    # Simple trend: compare last 3 days average to the prior 4 days average.
    trend_factor = 1.0
    if len(values) >= 7:
        recent_avg = sum(values[-3:]) / 3
        prior_avg = sum(values[:4]) / 4
        if prior_avg > 0:
            trend_factor = max(0.5, min(2.0, recent_avg / prior_avg))

    tomorrow_sales = round(avg_daily * trend_factor, 2)
    next_week_revenue = round(tomorrow_sales * 7, 2)

    low_stock_risk = await intel_svc.get_out_of_stock_predictions(db, shop_id)
    demand_trend = await intel_svc.get_demand_trend(db, shop_id)
    expected_demand_units = sum(p["units"] for p in demand_trend[-7:]) if demand_trend else 0
    predicted_best_sellers = await intel_svc.get_fast_moving_products(db, shop_id, limit=5)

    payload = {
        "tomorrow_sales_estimate": tomorrow_sales,
        "next_week_revenue_estimate": next_week_revenue,
        "trend_factor": round(trend_factor, 2),
        "revenue_history": revenue_series,
        "low_stock_risk": low_stock_risk[:8],
        "expected_demand_next_7_days_units": expected_demand_units,
        "predicted_best_sellers": predicted_best_sellers,
    }
    await _cache.set(cache_key, payload, ttl=CACHE_TTL_SECONDS)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Alerts
# ─────────────────────────────────────────────────────────────────────────────

async def get_alerts(db: AsyncSession, shop_id: str) -> list[dict]:
    alerts: list[dict] = []
    overview = await get_overview(db, shop_id)

    if overview["out_of_stock_products"]:
        alerts.append({
            "type": "low_stock", "severity": "high",
            "message": f"{len(overview['out_of_stock_products'])} product(s) are completely out of stock.",
        })
    if overview["low_stock_products"]:
        alerts.append({
            "type": "low_stock", "severity": "medium",
            "message": f"{len(overview['low_stock_products'])} product(s) are running low on stock.",
        })
    if overview["revenue_change_pct"] is not None and overview["revenue_change_pct"] <= -20:
        alerts.append({
            "type": "revenue_drop", "severity": "high",
            "message": f"Revenue is down {abs(overview['revenue_change_pct'])}% vs yesterday.",
        })
    if len(overview["slow_moving_products"]) >= 3:
        alerts.append({
            "type": "slow_sales", "severity": "medium",
            "message": f"{len(overview['slow_moving_products'])} products have slowed down recently.",
        })
    if overview["fast_moving_products"] and overview["fast_moving_products"][0]["units_sold"] >= 20:
        top = overview["fast_moving_products"][0]
        alerts.append({
            "type": "high_demand", "severity": "low",
            "message": f"\"{top['product_name']}\" is seeing high demand ({top['units_sold']} units in {top['window_days']} days).",
        })

    dead_stock = await intel_svc.get_dead_stock(db, shop_id)
    if len(dead_stock) >= 3:
        alerts.append({
            "type": "inventory_issues", "severity": "medium",
            "message": f"{len(dead_stock)} products haven't sold recently — review your inventory mix.",
        })

    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────────────────────────────────────

async def get_report(db: AsyncSession, shop_id: str, period: str) -> dict:
    """period: 'daily' | 'weekly' | 'monthly'"""
    today = _today_utc()
    if period == "daily":
        days = 1
    elif period == "weekly":
        days = 7
    elif period == "monthly":
        days = 30
    else:
        raise ValueError("period must be one of: daily, weekly, monthly")

    rows = []
    total_revenue = 0.0
    total_profit = 0.0
    total_orders = 0
    for i in range(days):
        day = today - timedelta(days=days - 1 - i)
        summary = await get_revenue_summary(db, shop_id, day)
        customers = await get_customer_breakdown(db, shop_id, day)
        rows.append({**summary, **{k: v for k, v in customers.items() if k != "date"}})
        total_revenue += summary["revenue"]
        total_profit += summary["profit"]
        total_orders += summary["orders"]

    shop = await _get_shop(db, shop_id)
    return {
        "shop_name": shop.name,
        "period": period,
        "start_date": rows[0]["date"] if rows else today.isoformat(),
        "end_date": rows[-1]["date"] if rows else today.isoformat(),
        "total_revenue": round(total_revenue, 2),
        "total_profit": round(total_profit, 2),
        "total_orders": total_orders,
        "daily_breakdown": rows,
    }
