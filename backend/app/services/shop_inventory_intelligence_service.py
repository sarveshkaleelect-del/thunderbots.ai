"""
ThunderBots Smart Shop Assistant — AI Inventory Intelligence (NEW)

Every figure this module returns is computed directly from two live tables:

  - ShopProduct               current on-hand quantity (source of truth)
  - ShopProductMovement       append-only ledger of every quantity change
                              ever applied, written by shop_assistant_service
                              (see record_movement — one row per event)

Nothing here calls an external AI provider and nothing is estimated from a
prior/synthetic distribution — "AI" refers to the deterministic, rule-based
interpretation layer at the bottom of this file (build_insights) that turns
the real computed numbers into a plain-English sentence. This mirrors the
same "never hallucinate inventory" principle shop_assistant_service.search_products
already follows: if the ledger doesn't show it, this module doesn't say it.

Demand / "units moved" is measured from `reservation_hold` +
`reservation_edit_hold` + `waitlist_fulfilled` movement rows (the moment a
customer actually took stock off the shelf), NOT from `reservation_completed`
alone — a shop that never bothers clicking "Completed" at the counter would
otherwise show zero sales activity forever, which would be actively
misleading. `reservation_completed` rows are surfaced separately as
"confirmed picked-up sales" wherever that distinction matters.
"""
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shop_assistant import Shop, ShopProduct, ShopProductMovement

logger = logging.getLogger(__name__)

# Movement event types that represent real demand (stock actually leaving
# the shelf for a customer), as opposed to administrative corrections.
_DEMAND_EVENT_TYPES = ("reservation_hold", "reservation_edit_hold", "waitlist_fulfilled")
_RESTOCK_EVENT_TYPES = ("adjusted", "import", "sync_pull", "created")

_FAST_SLOW_WINDOW_DAYS = 14
_DEMAND_TREND_WINDOW_DAYS = 28
_DEAD_STOCK_WINDOW_DAYS = 30
_STOCKOUT_PREDICTION_WINDOW_DAYS = 14


def _threshold_for(product: ShopProduct, shop: Shop) -> int:
    return product.low_stock_threshold if product.low_stock_threshold is not None else shop.low_stock_threshold


def _reorder_qty_for(product: ShopProduct, shop: Shop, avg_daily_demand: float) -> int:
    if product.reorder_quantity is not None:
        return product.reorder_quantity
    # No explicit override — suggest two weeks of average demand, floored at
    # the shop's default low-stock threshold so a slow/no-history product
    # still gets a sane, non-zero suggestion.
    suggested = round(avg_daily_demand * 14)
    return max(suggested, shop.low_stock_threshold)


async def _get_shop(db: AsyncSession, shop_id: str) -> Shop:
    result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = result.scalar_one_or_none()
    if shop is None:
        raise ValueError(f"Shop {shop_id} not found")
    return shop


async def _demand_units_by_product(
    db: AsyncSession, shop_id: str, since: datetime
) -> dict[str, int]:
    result = await db.execute(
        select(ShopProductMovement.product_id, func.sum(ShopProductMovement.units))
        .where(
            ShopProductMovement.shop_id == shop_id,
            ShopProductMovement.event_type.in_(_DEMAND_EVENT_TYPES),
            ShopProductMovement.created_at >= since,
        )
        .group_by(ShopProductMovement.product_id)
    )
    return {pid: int(total or 0) for pid, total in result.all()}


async def _last_demand_at_by_product(db: AsyncSession, shop_id: str) -> dict[str, datetime]:
    result = await db.execute(
        select(ShopProductMovement.product_id, func.max(ShopProductMovement.created_at))
        .where(ShopProductMovement.shop_id == shop_id, ShopProductMovement.event_type.in_(_DEMAND_EVENT_TYPES))
        .group_by(ShopProductMovement.product_id)
    )
    return {pid: ts for pid, ts in result.all()}


# ─────────────────────────────────────────────────────────────────────────────
# Low stock / out-of-stock
# ─────────────────────────────────────────────────────────────────────────────

async def get_low_stock_alerts(db: AsyncSession, shop_id: str) -> list[dict]:
    """Products at or below their effective threshold (per-product override,
    else the shop default) — includes fully out-of-stock (0) products too."""
    shop = await _get_shop(db, shop_id)
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id))
    products = list(result.scalars().all())
    alerts = []
    for p in products:
        threshold = _threshold_for(p, shop)
        if p.quantity_available <= threshold:
            alerts.append({
                "product_id": p.id, "product_name": p.name,
                "quantity_available": p.quantity_available, "threshold": threshold,
                "severity": "out_of_stock" if p.quantity_available == 0 else "low",
            })
    alerts.sort(key=lambda a: a["quantity_available"])
    return alerts


async def get_out_of_stock_predictions(db: AsyncSession, shop_id: str) -> list[dict]:
    """Estimated days-until-stockout per product, from REAL trailing demand
    (units held via reservations/waitlist over the last
    _STOCKOUT_PREDICTION_WINDOW_DAYS days) divided into current on-hand
    quantity. Products with zero recent demand are omitted — there is no
    real data to project from, and fabricating a "flat" projection for them
    would violate the live-data-only requirement."""
    since = datetime.now(timezone.utc) - timedelta(days=_STOCKOUT_PREDICTION_WINDOW_DAYS)
    demand = await _demand_units_by_product(db, shop_id, since)
    if not demand:
        return []
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id, ShopProduct.id.in_(demand.keys())))
    products = {p.id: p for p in result.scalars().all()}

    predictions = []
    for product_id, units in demand.items():
        product = products.get(product_id)
        if product is None or units <= 0:
            continue
        avg_daily = units / _STOCKOUT_PREDICTION_WINDOW_DAYS
        if avg_daily <= 0:
            continue
        days_left = product.quantity_available / avg_daily
        predictions.append({
            "product_id": product.id, "product_name": product.name,
            "quantity_available": product.quantity_available,
            "avg_daily_demand": round(avg_daily, 2),
            "estimated_days_to_stockout": round(days_left, 1),
        })
    predictions.sort(key=lambda p: p["estimated_days_to_stockout"])
    return predictions


# ─────────────────────────────────────────────────────────────────────────────
# Fast / slow movers, dead stock, best sellers, demand trend
# ─────────────────────────────────────────────────────────────────────────────

async def get_fast_moving_products(db: AsyncSession, shop_id: str, *, limit: int = 10) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=_FAST_SLOW_WINDOW_DAYS)
    demand = await _demand_units_by_product(db, shop_id, since)
    return await _rank_by_units(db, shop_id, demand, limit=limit, descending=True, window_days=_FAST_SLOW_WINDOW_DAYS)


async def get_slow_moving_products(db: AsyncSession, shop_id: str, *, limit: int = 10) -> list[dict]:
    """Products that HAVE stock but the least (or zero) recent demand —
    distinct from dead stock, which requires a longer, harder zero-activity
    window (see get_dead_stock)."""
    since = datetime.now(timezone.utc) - timedelta(days=_FAST_SLOW_WINDOW_DAYS)
    demand = await _demand_units_by_product(db, shop_id, since)
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id, ShopProduct.quantity_available > 0))
    in_stock = list(result.scalars().all())
    rows = [{"product_id": p.id, "product_name": p.name, "quantity_available": p.quantity_available,
             "units_sold": demand.get(p.id, 0), "window_days": _FAST_SLOW_WINDOW_DAYS} for p in in_stock]
    rows.sort(key=lambda r: r["units_sold"])
    return rows[:limit]


async def _rank_by_units(
    db: AsyncSession, shop_id: str, demand: dict[str, int], *, limit: int, descending: bool, window_days: int
) -> list[dict]:
    if not demand:
        return []
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id, ShopProduct.id.in_(demand.keys())))
    products = {p.id: p for p in result.scalars().all()}
    rows = [
        {"product_id": pid, "product_name": products[pid].name, "quantity_available": products[pid].quantity_available,
         "units_sold": units, "window_days": window_days}
        for pid, units in demand.items() if pid in products and units > 0
    ]
    rows.sort(key=lambda r: r["units_sold"], reverse=descending)
    return rows[:limit]


async def get_best_selling_products(db: AsyncSession, shop_id: str, *, limit: int = 10) -> list[dict]:
    """All-time (unbounded window) units held via reservation/waitlist —
    the definitive "best sellers" list, not time-boxed like fast-movers."""
    result = await db.execute(
        select(ShopProductMovement.product_id, func.sum(ShopProductMovement.units))
        .where(ShopProductMovement.shop_id == shop_id, ShopProductMovement.event_type.in_(_DEMAND_EVENT_TYPES))
        .group_by(ShopProductMovement.product_id)
    )
    demand = {pid: int(total or 0) for pid, total in result.all()}
    return await _rank_by_units(db, shop_id, demand, limit=limit, descending=True, window_days=0)


async def get_dead_stock(db: AsyncSession, shop_id: str) -> list[dict]:
    """In-stock products with NO demand movement at all in the last
    _DEAD_STOCK_WINDOW_DAYS days (or ever, if the product predates the
    ledger and has never once moved)."""
    since = datetime.now(timezone.utc) - timedelta(days=_DEAD_STOCK_WINDOW_DAYS)
    last_demand = await _last_demand_at_by_product(db, shop_id)
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id, ShopProduct.quantity_available > 0))
    products = list(result.scalars().all())

    dead = []
    for p in products:
        last = last_demand.get(p.id)
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or last < since:
            days_idle = None
            if last is not None:
                days_idle = (datetime.now(timezone.utc) - last).days
            dead.append({
                "product_id": p.id, "product_name": p.name,
                "quantity_available": p.quantity_available,
                "days_since_last_sale": days_idle,  # None => never sold at all
            })
    dead.sort(key=lambda d: (d["days_since_last_sale"] is not None, d["days_since_last_sale"] or 0), reverse=True)
    return dead


async def get_demand_trend(db: AsyncSession, shop_id: str, product_id: str | None = None) -> list[dict]:
    """Daily bucketed demand units over the trailing _DEMAND_TREND_WINDOW_DAYS,
    for one product or the whole shop (product_id=None) — real per-day
    totals from the movement ledger, not a smoothed/synthetic curve."""
    since = datetime.now(timezone.utc) - timedelta(days=_DEMAND_TREND_WINDOW_DAYS)
    query = (
        select(ShopProductMovement.created_at, ShopProductMovement.units)
        .where(
            ShopProductMovement.shop_id == shop_id,
            ShopProductMovement.event_type.in_(_DEMAND_EVENT_TYPES),
            ShopProductMovement.created_at >= since,
        )
    )
    if product_id:
        query = query.where(ShopProductMovement.product_id == product_id)
    result = await db.execute(query)
    rows = result.all()

    buckets: dict[str, int] = {}
    day = since.date()
    today = datetime.now(timezone.utc).date()
    while day <= today:
        buckets[day.isoformat()] = 0
        day += timedelta(days=1)
    for created_at, units in rows:
        key = created_at.date().isoformat()
        buckets[key] = buckets.get(key, 0) + int(units or 0)

    return [{"date": d, "units": u} for d, u in sorted(buckets.items())]


# ─────────────────────────────────────────────────────────────────────────────
# Auto reorder suggestions
# ─────────────────────────────────────────────────────────────────────────────

async def get_reorder_suggestions(db: AsyncSession, shop_id: str) -> list[dict]:
    shop = await _get_shop(db, shop_id)
    since = datetime.now(timezone.utc) - timedelta(days=_STOCKOUT_PREDICTION_WINDOW_DAYS)
    demand = await _demand_units_by_product(db, shop_id, since)

    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id))
    products = list(result.scalars().all())

    suggestions = []
    for p in products:
        threshold = _threshold_for(p, shop)
        if p.quantity_available > threshold:
            continue
        avg_daily = demand.get(p.id, 0) / _STOCKOUT_PREDICTION_WINDOW_DAYS
        suggested_qty = _reorder_qty_for(p, shop, avg_daily)
        suggestions.append({
            "product_id": p.id, "product_name": p.name,
            "quantity_available": p.quantity_available, "threshold": threshold,
            "avg_daily_demand": round(avg_daily, 2),
            "suggested_reorder_quantity": int(suggested_qty),
        })
    suggestions.sort(key=lambda s: s["quantity_available"])
    return suggestions


# ─────────────────────────────────────────────────────────────────────────────
# Movement history / timeline
# ─────────────────────────────────────────────────────────────────────────────

async def get_product_movement_history(
    db: AsyncSession, shop_id: str, product_id: str, *, limit: int = 100
) -> list[dict]:
    result = await db.execute(
        select(ShopProductMovement)
        .where(ShopProductMovement.shop_id == shop_id, ShopProductMovement.product_id == product_id)
        .order_by(ShopProductMovement.created_at.desc())
        .limit(limit)
    )
    return [_movement_to_dict(m) for m in result.scalars().all()]


async def get_inventory_timeline(db: AsyncSession, shop_id: str, *, limit: int = 200) -> list[dict]:
    """Chronological (most recent first) feed of every inventory event across
    every product in the shop — the "what happened, in order" view."""
    result = await db.execute(
        select(ShopProductMovement, ShopProduct.name)
        .join(ShopProduct, ShopProduct.id == ShopProductMovement.product_id)
        .where(ShopProductMovement.shop_id == shop_id)
        .order_by(ShopProductMovement.created_at.desc())
        .limit(limit)
    )
    return [{**_movement_to_dict(m), "product_name": name} for m, name in result.all()]


def _movement_to_dict(m: ShopProductMovement) -> dict:
    return {
        "id": m.id, "product_id": m.product_id, "event_type": m.event_type,
        "quantity_delta": m.quantity_delta, "units": m.units,
        "quantity_before": m.quantity_before, "quantity_after": m.quantity_after,
        "reference_id": m.reference_id, "created_at": m.created_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Inventory health + AI insights
# ─────────────────────────────────────────────────────────────────────────────

async def get_inventory_health(db: AsyncSession, shop_id: str) -> dict:
    shop = await _get_shop(db, shop_id)
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id))
    products = list(result.scalars().all())
    total = len(products)
    if total == 0:
        return {
            "total_products": 0, "healthy_count": 0, "low_stock_count": 0,
            "out_of_stock_count": 0, "dead_stock_count": 0, "health_score": 100,
        }

    out_of_stock = sum(1 for p in products if p.quantity_available == 0)
    low_stock = sum(1 for p in products if 0 < p.quantity_available <= _threshold_for(p, shop))
    dead_stock = len(await get_dead_stock(db, shop_id))
    healthy = total - out_of_stock - low_stock

    # Deterministic composite score — 100 minus a real penalty per problem
    # category, weighted by how severe each is; never randomized.
    penalty = (out_of_stock / total) * 50 + (low_stock / total) * 25 + (dead_stock / total) * 25
    health_score = round(max(0, 100 - penalty))

    return {
        "total_products": total, "healthy_count": healthy, "low_stock_count": low_stock,
        "out_of_stock_count": out_of_stock, "dead_stock_count": dead_stock,
        "health_score": health_score,
    }


async def build_insights(db: AsyncSession, shop_id: str, *, max_insights: int = 6) -> list[str]:
    """Deterministic, rule-based natural-language insights generated ONLY
    from the real computed metrics above — no external LLM call, so there is
    no hallucination risk and every sentence traces directly back to a
    number this module actually computed from the live ledger."""
    insights: list[str] = []

    health = await get_inventory_health(db, shop_id)
    if health["out_of_stock_count"] > 0:
        insights.append(
            f"{health['out_of_stock_count']} product(s) are completely out of stock right now — "
            f"customers searching for them will be offered the waiting list."
        )

    predictions = await get_out_of_stock_predictions(db, shop_id)
    for pred in predictions[:2]:
        if pred["estimated_days_to_stockout"] <= 7:
            insights.append(
                f"\"{pred['product_name']}\" is on pace to run out in about "
                f"{pred['estimated_days_to_stockout']:.0f} day(s) at the current rate of "
                f"{pred['avg_daily_demand']:.1f} units/day — consider reordering soon."
            )

    reorders = await get_reorder_suggestions(db, shop_id)
    for r in reorders[:2]:
        insights.append(
            f"\"{r['product_name']}\" is at or below its reorder threshold "
            f"({r['quantity_available']} left) — suggested reorder quantity is {r['suggested_reorder_quantity']}."
        )

    fast = await get_fast_moving_products(db, shop_id, limit=1)
    if fast:
        insights.append(
            f"\"{fast[0]['product_name']}\" is your fastest mover — {fast[0]['units_sold']} units "
            f"in the last {_FAST_SLOW_WINDOW_DAYS} days."
        )

    dead = await get_dead_stock(db, shop_id)
    if dead:
        oldest = dead[0]
        if oldest["days_since_last_sale"] is not None:
            insights.append(
                f"\"{oldest['product_name']}\" hasn't sold in {oldest['days_since_last_sale']} days "
                f"while still holding {oldest['quantity_available']} units — consider a promotion or discontinuing it."
            )
        else:
            insights.append(
                f"\"{oldest['product_name']}\" has never recorded a sale and still holds "
                f"{oldest['quantity_available']} units."
            )

    if not insights:
        insights.append("Inventory looks healthy — no low-stock, stockout-risk, or dead-stock issues detected right now.")

    return insights[:max_insights]
