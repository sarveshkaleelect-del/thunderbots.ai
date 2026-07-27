"""
ThunderBots Smart Shop Assistant — Reservation Expiry Scheduler (NEW)

Mirrors the exact shape of services/campaign_dispatch_service.run_scheduler_loop:
polls on a fixed interval, its own loop body never raises (a single tick's
failure is logged and the loop keeps going), and it is wired into
app/main.py's lifespan the same way every other background task is.

Each tick:
  1. Finds every `pending` reservation whose expires_at has passed.
  2. For each, restores stock for every item (row-locked, same as a manual
     cancel) and marks it `expired`.
  3. Runs process_waitlist_for_product() for every product whose stock just
     increased, so a waiting customer is auto-reserved the moment a hold
     lapses — not just when the owner manually restocks.
  4. Broadcasts inventory_update / reservation_update / booking_update over
     the existing shop_assistant_ws_manager so both the shop admin and any
     open customer tab reflect the expiry in real time, with no page reload.
"""
import asyncio
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.shop_assistant import Shop, ShopProduct
from app.services import shop_assistant_service as svc
from app.services import shop_assistant_ws_manager as ws_manager

logger = logging.getLogger(__name__)

RESERVATION_SCHEDULER_POLL_SECONDS = 30


def _product_to_dict(p: ShopProduct) -> dict:
    return {
        "id": p.id, "name": p.name, "sku": p.sku, "category": p.category,
        "quantity_available": p.quantity_available,
    }


def _reservation_to_admin_dict(r, items: list[dict]) -> dict:
    return {
        "id": r.id, "customer_name": r.customer_name, "status": r.status,
        "queue_token": r.queue_token, "queue_number": r.queue_number,
        "is_partial": r.is_partial, "items": items,
        "created_at": r.created_at.isoformat(),
    }


async def run_scheduler_loop() -> None:
    logger.info("Shop Assistant reservation-expiry scheduler loop started")
    while True:
        try:
            await _expire_due_reservations()
        except Exception as e:  # noqa: BLE001 — the loop must never die
            logger.error(f"Shop Assistant reservation-expiry tick failed: {e}", exc_info=True)
        await asyncio.sleep(RESERVATION_SCHEDULER_POLL_SECONDS)


async def _expire_due_reservations() -> None:
    async with AsyncSessionLocal() as db:
        due = await svc.get_due_expirations(db)
        due_ids = [r.id for r in due]

    for reservation_id in due_ids:
        try:
            await _expire_one(reservation_id)
        except Exception as e:  # noqa: BLE001 — one bad reservation must not block the rest
            logger.error(f"Shop Assistant: failed to expire reservation {reservation_id}: {e}", exc_info=True)


async def _expire_one(reservation_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(svc.ShopReservation).where(svc.ShopReservation.id == reservation_id))
        reservation = result.scalar_one_or_none()
        if reservation is None or reservation.status != "pending":
            return  # already handled (raced with a manual confirm/cancel) — no-op

        await db.refresh(reservation, attribute_names=["items"])
        item_snapshot = [{"product_id": it.product_id, "quantity": it.quantity} for it in reservation.items]

        affected_product_ids = await svc.expire_reservation(db, reservation)

        created_from_waitlist = []
        for product_id in set(affected_product_ids):
            created_from_waitlist.extend(await svc.process_waitlist_for_product(db, reservation.shop_id, product_id))

        await db.commit()

        # Broadcast AFTER commit — read back fresh state for the payloads.
        await db.refresh(reservation, attribute_names=["items"])
        await ws_manager.broadcast_booking_update(
            reservation.shop_id,
            _reservation_to_admin_dict(reservation, [
                {"product_id": it.product_id, "quantity": it.quantity, "requested_quantity": it.requested_quantity}
                for it in reservation.items
            ]),
        )
        await ws_manager.broadcast_reservation_status(reservation.shop_id, {
            "lookup_code": reservation.lookup_code, "status": reservation.status,
            "queue_token": reservation.queue_token, "queue_number": reservation.queue_number,
        })

        for product_id in set(affected_product_ids):
            result = await db.execute(select(ShopProduct).where(ShopProduct.id == product_id))
            product = result.scalar_one_or_none()
            if product is not None:
                await ws_manager.broadcast_inventory_update(reservation.shop_id, _product_to_dict(product))

        for new_reservation in created_from_waitlist:
            await ws_manager.broadcast_booking_update(
                new_reservation.shop_id,
                _reservation_to_admin_dict(new_reservation, [
                    {"product_id": it.product_id, "quantity": it.quantity, "requested_quantity": it.requested_quantity}
                    for it in new_reservation.items
                ]),
            )
            await ws_manager.broadcast_waitlist_notification(new_reservation.shop_id, {
                "lookup_code": new_reservation.lookup_code, "queue_token": new_reservation.queue_token,
                "queue_number": new_reservation.queue_number, "status": new_reservation.status,
            })

        logger.info(
            f"Shop Assistant: expired reservation {reservation_id} "
            f"(shop={reservation.shop_id}, items={item_snapshot}, waitlist_fulfilled={len(created_from_waitlist)})"
        )
