"""
Smart Shop Assistant — WebSocket connection registry

In-process dict/set registry, same pattern as live_agent_ws_manager.py.

HORIZONTAL-SCALING FIX (v107): now bridged across worker processes via
Redis pub/sub, same mechanism and same fail-open behavior as
live_agent_ws_manager.py's cross-worker bridge — see that module's
docstring for the full rationale. Every broadcast_* function below still
delivers to any locally-held sockets first (no added latency in the common
single-worker case) and additionally publishes to a shop-scoped Redis
channel so other workers holding sockets for the same shop_id also
deliver it. Call `start_cross_worker_bridge()` once at app startup.

One shop has two kinds of live listeners:

1. Admin sockets   — the shop owner's Shop Admin page. Receives
                     inventory_update, booking_update (full customer_name +
                     items), waitlist_update, and queue_update — everything.
2. Public sockets  — any number of customer devices on the `/shop/<slug>`
                     page. Receive:
                       - inventory_update       quantity changes (unchanged)
                       - reservation_update      minimal-disclosure status
                                                 push keyed by lookup_code
                                                 only (no customer_name) —
                                                 lets a customer's own
                                                 browser react to their own
                                                 reservation's status/queue
                                                 position without polling
                       - waitlist_notification   same idea, for a waitlist
                                                 entry that just got
                                                 auto-reserved
                       - queue_update            shop-wide "N waiting" count
                     Full booking details (customer_name) for OTHER
                     customers are never broadcast to the public channel.
"""
import asyncio
import json
import logging
import uuid
from typing import Any

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_admin_sockets: dict[str, set] = {}
_public_sockets: dict[str, set] = {}

_WORKER_ID = uuid.uuid4().hex
# Separate channels per audience — admin-only payloads (e.g. booking_update
# with full customer_name) must NEVER be replayed to a public socket on
# another worker, so the admin/public disclosure boundary that the local
# _broadcast() calls already enforce is preserved across the bridge too.
_SHOP_ADMIN_CHANNEL_PREFIX = "wsbridge:shop:admin:"
_SHOP_PUBLIC_CHANNEL_PREFIX = "wsbridge:shop:public:"
_listener_task: "asyncio.Task | None" = None


def register_admin(shop_id: str, websocket: Any) -> None:
    _admin_sockets.setdefault(shop_id, set()).add(websocket)


def unregister_admin(shop_id: str, websocket: Any) -> None:
    sockets = _admin_sockets.get(shop_id)
    if sockets:
        sockets.discard(websocket)
        if not sockets:
            _admin_sockets.pop(shop_id, None)


def register_public(shop_id: str, websocket: Any) -> None:
    _public_sockets.setdefault(shop_id, set()).add(websocket)


def unregister_public(shop_id: str, websocket: Any) -> None:
    sockets = _public_sockets.get(shop_id)
    if sockets:
        sockets.discard(websocket)
        if not sockets:
            _public_sockets.pop(shop_id, None)


async def _broadcast(sockets: set, payload: dict) -> None:
    dead = []
    for ws in sockets:
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.debug(f"Shop Assistant WS: dropping dead socket: {e}")
            dead.append(ws)
    for ws in dead:
        sockets.discard(ws)


async def _publish(channel_prefix: str, shop_id: str, payload: dict) -> None:
    """HORIZONTAL-SCALING FIX (v107): fan this payload out to any other
    worker process that holds sockets for this shop_id/audience. Fails
    open — if Redis is unavailable, only this worker's local sockets are
    notified, same as before this fix."""
    redis = get_redis()
    if not redis:
        return
    try:
        envelope = json.dumps({"origin": _WORKER_ID, "payload": payload}, default=str)
        await redis.publish(channel_prefix + shop_id, envelope)
    except Exception as e:
        logger.debug(f"Shop Assistant WS: pubsub publish failed for shop={shop_id}: {e}")


async def start_cross_worker_bridge() -> "asyncio.Task | None":
    """Call once at app startup (see main.py lifespan). No-ops if Redis is
    unavailable — local, same-process delivery keeps working regardless."""
    redis = get_redis()
    if not redis:
        logger.info("Shop Assistant cross-worker WS bridge disabled — Redis unavailable")
        return None

    pubsub = redis.pubsub()
    await pubsub.psubscribe(_SHOP_ADMIN_CHANNEL_PREFIX + "*", _SHOP_PUBLIC_CHANNEL_PREFIX + "*")

    async def _loop():
        try:
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                try:
                    channel = message["channel"]
                    data = json.loads(message["data"])
                except Exception:
                    continue
                if data.get("origin") == _WORKER_ID:
                    continue
                payload = data.get("payload")
                if payload is None:
                    continue
                if channel.startswith(_SHOP_ADMIN_CHANNEL_PREFIX):
                    shop_id = channel[len(_SHOP_ADMIN_CHANNEL_PREFIX):]
                    if shop_id in _admin_sockets:
                        await _broadcast(_admin_sockets[shop_id], payload)
                elif channel.startswith(_SHOP_PUBLIC_CHANNEL_PREFIX):
                    shop_id = channel[len(_SHOP_PUBLIC_CHANNEL_PREFIX):]
                    if shop_id in _public_sockets:
                        await _broadcast(_public_sockets[shop_id], payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Shop Assistant cross-worker WS bridge listener stopped: {e}")

    global _listener_task
    _listener_task = asyncio.create_task(_loop())
    return _listener_task


async def stop_cross_worker_bridge() -> None:
    global _listener_task
    if _listener_task:
        _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass
        _listener_task = None


async def broadcast_inventory_update(shop_id: str, product: dict) -> None:
    """Sent to BOTH admin and public listeners whenever a product's quantity
    or details change (edit, import/sync, reservation created/cancelled)."""
    payload = {"type": "inventory_update", "product": product}
    if shop_id in _admin_sockets:
        await _broadcast(_admin_sockets[shop_id], payload)
    if shop_id in _public_sockets:
        await _broadcast(_public_sockets[shop_id], payload)
    await _publish(_SHOP_ADMIN_CHANNEL_PREFIX, shop_id, payload)
    await _publish(_SHOP_PUBLIC_CHANNEL_PREFIX, shop_id, payload)


async def broadcast_booking_update(shop_id: str, reservation: dict) -> None:
    """Admin-only — Live Customer Bookings feed. Full detail (customer_name,
    every item)."""
    payload = {"type": "booking_update", "reservation": reservation}
    if shop_id in _admin_sockets:
        await _broadcast(_admin_sockets[shop_id], payload)
    await _publish(_SHOP_ADMIN_CHANNEL_PREFIX, shop_id, payload)


async def broadcast_reservation_status(shop_id: str, status: dict) -> None:
    """Public — minimal-disclosure push so the customer's OWN device (which
    already knows its own lookup_code) can react in real time to its own
    reservation's status/queue_number changing, without polling and without
    learning anything about any other customer. Expected keys: lookup_code,
    status, queue_token, queue_number, and optionally expires_at /
    queue_position."""
    payload = {"type": "reservation_update", **status}
    if shop_id in _public_sockets:
        await _broadcast(_public_sockets[shop_id], payload)
    await _publish(_SHOP_PUBLIC_CHANNEL_PREFIX, shop_id, payload)


async def broadcast_waitlist_notification(shop_id: str, waitlist_status: dict) -> None:
    """Public — sent the moment a waiting customer is auto-reserved because
    stock became available. Same minimal-disclosure shape as
    broadcast_reservation_status, keyed by the waitlist entry's own
    lookup_code so only that customer's device recognizes it as theirs."""
    public_payload = {"type": "waitlist_notification", **waitlist_status}
    admin_payload = {"type": "waitlist_update", **waitlist_status}
    if shop_id in _public_sockets:
        await _broadcast(_public_sockets[shop_id], public_payload)
    if shop_id in _admin_sockets:
        await _broadcast(_admin_sockets[shop_id], admin_payload)
    await _publish(_SHOP_PUBLIC_CHANNEL_PREFIX, shop_id, public_payload)
    await _publish(_SHOP_ADMIN_CHANNEL_PREFIX, shop_id, admin_payload)


async def broadcast_queue_update(shop_id: str, queue: dict) -> None:
    """Live queue length / composition — sent to both admin and public
    (public gets just the aggregate count, never other customers' names)."""
    admin_payload = {"type": "queue_update", **queue}
    public_payload = {"type": "queue_update", "total_waiting": queue.get("total_waiting")}
    if shop_id in _admin_sockets:
        await _broadcast(_admin_sockets[shop_id], admin_payload)
    if shop_id in _public_sockets:
        await _broadcast(_public_sockets[shop_id], public_payload)
    await _publish(_SHOP_ADMIN_CHANNEL_PREFIX, shop_id, admin_payload)
    await _publish(_SHOP_PUBLIC_CHANNEL_PREFIX, shop_id, public_payload)


async def broadcast_inventory_alert(shop_id: str, alert: dict) -> None:
    """Admin-only — AI Inventory Intelligence pushing a low-stock / stockout
    alert the moment a mutation crosses a threshold, instead of the admin
    having to poll the analytics endpoints."""
    payload = {"type": "inventory_alert", **alert}
    if shop_id in _admin_sockets:
        await _broadcast(_admin_sockets[shop_id], payload)
    await _publish(_SHOP_ADMIN_CHANNEL_PREFIX, shop_id, payload)
