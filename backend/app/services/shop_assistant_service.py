"""
ThunderBots Smart Shop Assistant — Core Service (independent product)

v2 — Smart Reservation System + AI Inventory Intelligence groundwork.

Concurrency model (unchanged in spirit from v1, extended to multi-row locks):
every mutation that touches stock takes `SELECT ... FOR UPDATE` row locks —
on the Shop row first (to hand out a gapless queue number), then on every
ShopProduct row involved, always sorted by product_id — before reading or
writing quantity_available. Consistent lock ordering (Shop, then Products
ascending by id) is what prevents deadlocks when two concurrent multi-item
reservations both touch an overlapping set of products.

Every function that changes `quantity_available` also writes exactly one
ShopProductMovement row (see record_movement) — this ledger is the single
source of truth the inventory-intelligence service reads from. Nothing here
ever estimates or fabricates a number.
"""
import io
import logging
import difflib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import qrcode
import qrcode.image.svg
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shop_assistant import (
    Shop, ShopProduct, ShopReservation, ShopReservationItem,
    ShopWaitlistEntry, ShopProductMovement,
    ACTIVE_RESERVATION_STATUSES,
)

logger = logging.getLogger(__name__)

# Below this similarity score we treat a query as "no real match" rather than
# forcing a guess — this is what "never hallucinate inventory" comes down to
# in practice: if nothing in the live table is a plausible match, say so.
_MATCH_CUTOFF = 0.45
_MAX_SUGGESTIONS = 5


@dataclass
class ProductMatch:
    product: ShopProduct
    score: float


class InsufficientStockError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class ReservationNotFoundError(Exception):
    pass


class WaitlistEntryNotFoundError(Exception):
    pass


class InvalidReservationStateError(Exception):
    """Raised when an action (edit/confirm/ready/complete/cancel) is
    attempted on a reservation whose current status doesn't allow it."""
    pass


class DuplicateReservationError(Exception):
    """Raised when the same customer already holds an active (pending /
    confirmed / ready) reservation covering at least one of the requested
    products at this shop."""
    pass


class EmptyReservationError(Exception):
    """Raised when a reservation would end up with zero fulfillable items
    (every requested product is completely out of stock)."""
    pass


@dataclass
class ReservationItemPlan:
    product_id: str
    requested_quantity: int


@dataclass
class ReservationItemPreview:
    product_id: str
    product_name: str
    requested_quantity: int
    fulfillable_quantity: int
    quantity_available: int

    @property
    def is_partial(self) -> bool:
        return 0 < self.fulfillable_quantity < self.requested_quantity

    @property
    def is_unavailable(self) -> bool:
        return self.fulfillable_quantity == 0


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


# ─────────────────────────────────────────────────────────────────────────────
# Search (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

async def search_products(db: AsyncSession, shop_id: str, query: str) -> list[ProductMatch]:
    """
    Typo-tolerant search over a shop's LIVE inventory. Always re-queries the
    database (never a process-local cache) so results reflect the latest
    synchronized quantity, including edits made seconds ago from Excel/Sheets
    or another customer's just-completed reservation.
    """
    result = await db.execute(
        select(ShopProduct).where(ShopProduct.shop_id == shop_id)
        .options(selectinload(ShopProduct.images))
    )
    products = list(result.scalars().all())
    if not products:
        return []

    query_norm = _normalize(query)
    if not query_norm:
        return []

    scored: list[ProductMatch] = []
    for product in products:
        name_norm = _normalize(product.name)
        # Exact / substring match always wins outright (handles "motor" typed
        # for "Stark Motor" cleanly, not just near-miss spelling).
        if query_norm == name_norm or query_norm in name_norm or name_norm in query_norm:
            score = 1.0
        else:
            score = difflib.SequenceMatcher(None, query_norm, name_norm).ratio()
            # Also check the SKU, if present — a customer may type a part number.
            if product.sku:
                sku_score = difflib.SequenceMatcher(
                    None, query_norm, _normalize(product.sku)
                ).ratio()
                score = max(score, sku_score)
        if score >= _MATCH_CUTOFF:
            scored.append(ProductMatch(product=product, score=score))

    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:_MAX_SUGGESTIONS]


# ─────────────────────────────────────────────────────────────────────────────
# Locking helpers
# ─────────────────────────────────────────────────────────────────────────────

async def get_product_locked(db: AsyncSession, shop_id: str, product_id: str) -> ShopProduct:
    """Fetch a product WITH a row lock, for use inside a reservation transaction."""
    result = await db.execute(
        select(ShopProduct)
        .where(ShopProduct.id == product_id, ShopProduct.shop_id == shop_id)
        .with_for_update()
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError(product_id)
    return product


async def _get_products_locked(
    db: AsyncSession, shop_id: str, product_ids: list[str]
) -> dict[str, ShopProduct]:
    """Locks every distinct product row, always in ascending id order, so two
    concurrent multi-item reservations touching an overlapping product set
    can never deadlock against each other."""
    locked: dict[str, ShopProduct] = {}
    for pid in sorted(set(product_ids)):
        locked[pid] = await get_product_locked(db, shop_id, pid)
    return locked


async def _get_shop_locked(db: AsyncSession, shop_id: str) -> Shop:
    """Row-locks the Shop itself — used to atomically hand out the next
    gapless queue number. Always locked BEFORE any product row in the same
    transaction (consistent lock ordering: Shop, then Products ascending)."""
    result = await db.execute(select(Shop).where(Shop.id == shop_id).with_for_update())
    shop = result.scalar_one_or_none()
    if shop is None:
        raise ProductNotFoundError(shop_id)  # shop vanished mid-transaction — treat like not-found
    return shop


def _effective_low_stock_threshold(product: ShopProduct, shop: Shop) -> int:
    return product.low_stock_threshold if product.low_stock_threshold is not None else shop.low_stock_threshold


async def record_movement(
    db: AsyncSession,
    *,
    shop_id: str,
    product_id: str,
    event_type: str,
    quantity_delta: int,
    units: int,
    quantity_before: int,
    quantity_after: int,
    reference_id: str | None = None,
) -> ShopProductMovement:
    """The ONLY place any code in this module should write to the movement
    ledger — every quantity change writes exactly one row here, which is what
    lets shop_inventory_intelligence_service compute every figure from real,
    recorded history instead of guessing."""
    movement = ShopProductMovement(
        shop_id=shop_id, product_id=product_id, event_type=event_type,
        quantity_delta=quantity_delta, units=units,
        quantity_before=quantity_before, quantity_after=quantity_after,
        reference_id=reference_id,
    )
    db.add(movement)
    await db.flush()
    return movement


# ─────────────────────────────────────────────────────────────────────────────
# Reservation preview (read-only — no locks, no writes)
# ─────────────────────────────────────────────────────────────────────────────

async def preview_reservation(
    db: AsyncSession, shop_id: str, items: list[ReservationItemPlan]
) -> list[ReservationItemPreview]:
    """Best-effort, lock-free snapshot of what's fulfillable right now, so the
    customer can see "5 of 7 available" and decide before anything is
    actually held. Stock can still move between this call and the real
    create_reservation() call — that one re-verifies under a row lock and
    caps quantities down further if needed, so this preview is advisory
    only, never authoritative."""
    if not items:
        return []
    product_ids = [i.product_id for i in items]
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id, ShopProduct.id.in_(product_ids)))
    products = {p.id: p for p in result.scalars().all()}

    previews = []
    for item in items:
        product = products.get(item.product_id)
        if product is None:
            raise ProductNotFoundError(item.product_id)
        fulfillable = max(0, min(item.requested_quantity, product.quantity_available))
        previews.append(ReservationItemPreview(
            product_id=product.id, product_name=product.name,
            requested_quantity=item.requested_quantity,
            fulfillable_quantity=fulfillable,
            quantity_available=product.quantity_available,
        ))
    return previews


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate-reservation guard
# ─────────────────────────────────────────────────────────────────────────────

async def _assert_no_duplicate(
    db: AsyncSession, shop_id: str, customer_name: str, product_ids: list[str]
) -> None:
    """A customer with an already-active (pending/confirmed/ready)
    reservation covering at least one of the same products at this shop
    cannot open a second one for that product — prevents accidental
    double-booking from a double-tap or a re-submitted form."""
    name_norm = _normalize(customer_name)
    result = await db.execute(
        select(ShopReservation)
        .where(
            ShopReservation.shop_id == shop_id,
            ShopReservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        )
    )
    active = result.scalars().all()
    for reservation in active:
        if _normalize(reservation.customer_name) != name_norm:
            continue
        await db.refresh(reservation, attribute_names=["items"])
        existing_product_ids = {item.product_id for item in reservation.items}
        if existing_product_ids & set(product_ids):
            raise DuplicateReservationError(
                "You already have an active reservation covering one of these products."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Reservation creation (multi-item, partial-fulfillment safe)
# ─────────────────────────────────────────────────────────────────────────────

async def create_reservation(
    db: AsyncSession,
    *,
    shop_id: str,
    items: list[ReservationItemPlan],
    customer_name: str,
) -> ShopReservation:
    """
    Atomically decrements stock for every fulfillable item and creates one
    reservation header covering all of them.

    - Items with zero available stock are simply skipped (not included in
      the reservation) — the caller (public API) surfaces this to the
      customer so they can join the waiting list instead.
    - Items with partial stock are held at the available quantity and the
      reservation is flagged `is_partial=True`.
    - Raises EmptyReservationError if literally nothing could be fulfilled.
    - Raises DuplicateReservationError if this customer already holds an
      active reservation on one of the requested products.
    """
    if not items:
        raise ValueError("items must be a non-empty list")
    for i in items:
        if i.requested_quantity <= 0:
            raise ValueError("quantity must be a positive integer")

    customer_name = customer_name.strip()[:120]
    if not customer_name:
        raise ValueError("customer_name is required")

    await _assert_no_duplicate(db, shop_id, customer_name, [i.product_id for i in items])

    # Consistent lock order: Shop row (queue number) THEN Products ascending.
    shop = await _get_shop_locked(db, shop_id)
    products = await _get_products_locked(db, shop_id, [i.product_id for i in items])

    reservation = ShopReservation(
        shop_id=shop_id,
        customer_name=customer_name,
        status="pending",
        queue_number=shop.next_queue_number,
    )
    shop.next_queue_number += 1

    if shop.reservation_timeout_minutes > 0:
        reservation.expires_at = datetime.now(timezone.utc) + timedelta(minutes=shop.reservation_timeout_minutes)

    db.add(reservation)
    await db.flush()

    any_fulfilled = False
    any_partial = False
    for plan in items:
        product = products[plan.product_id]
        fulfillable = max(0, min(plan.requested_quantity, product.quantity_available))
        if fulfillable == 0:
            continue  # fully out of stock for this item — caller offers waitlist
        before = product.quantity_available
        product.quantity_available -= fulfillable
        item = ShopReservationItem(
            reservation_id=reservation.id, product_id=product.id,
            requested_quantity=plan.requested_quantity, quantity=fulfillable,
        )
        db.add(item)
        await record_movement(
            db, shop_id=shop_id, product_id=product.id,
            event_type="reservation_hold", quantity_delta=-fulfillable, units=fulfillable,
            quantity_before=before, quantity_after=product.quantity_available,
            reference_id=reservation.id,
        )
        any_fulfilled = True
        if fulfillable < plan.requested_quantity:
            any_partial = True

    if not any_fulfilled:
        raise EmptyReservationError("None of the requested products are currently in stock")

    reservation.is_partial = any_partial
    await db.flush()
    await db.refresh(reservation, attribute_names=["items"])
    return reservation


# ─────────────────────────────────────────────────────────────────────────────
# Editing before confirmation
# ─────────────────────────────────────────────────────────────────────────────

async def edit_reservation(
    db: AsyncSession, shop_id: str, reservation_id: str, items: list[ReservationItemPlan]
) -> ShopReservation:
    """Replaces a still-`pending` reservation's line items. Restores all
    currently-held stock first, then re-applies the new item list using the
    exact same partial-fulfillment-safe logic as create_reservation — all
    inside one transaction, so a mid-edit crash can never leave stock
    double-counted or lost."""
    result = await db.execute(
        select(ShopReservation).where(ShopReservation.id == reservation_id, ShopReservation.shop_id == shop_id)
    )
    reservation = result.scalar_one_or_none()
    if reservation is None:
        raise ReservationNotFoundError(reservation_id)
    if reservation.status != "pending":
        raise InvalidReservationStateError("Only a pending reservation can be edited")
    if not items:
        raise ValueError("items must be a non-empty list")

    await db.refresh(reservation, attribute_names=["items"])
    all_product_ids = {it.product_id for it in reservation.items} | {i.product_id for i in items}
    products = await _get_products_locked(db, shop_id, list(all_product_ids))

    # Restore everything currently held by this reservation.
    for old_item in list(reservation.items):
        product = products[old_item.product_id]
        before = product.quantity_available
        product.quantity_available += old_item.quantity
        await record_movement(
            db, shop_id=shop_id, product_id=product.id,
            event_type="reservation_cancelled", quantity_delta=old_item.quantity, units=old_item.quantity,
            quantity_before=before, quantity_after=product.quantity_available,
            reference_id=reservation.id,
        )
        await db.delete(old_item)
    await db.flush()

    any_fulfilled = False
    any_partial = False
    new_items: list[ShopReservationItem] = []
    for plan in items:
        if plan.requested_quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        product = products[plan.product_id]
        fulfillable = max(0, min(plan.requested_quantity, product.quantity_available))
        if fulfillable == 0:
            continue
        before = product.quantity_available
        product.quantity_available -= fulfillable
        item = ShopReservationItem(
            reservation_id=reservation.id, product_id=product.id,
            requested_quantity=plan.requested_quantity, quantity=fulfillable,
        )
        db.add(item)
        new_items.append(item)
        await record_movement(
            db, shop_id=shop_id, product_id=product.id,
            event_type="reservation_edit_hold", quantity_delta=-fulfillable, units=fulfillable,
            quantity_before=before, quantity_after=product.quantity_available,
            reference_id=reservation.id,
        )
        any_fulfilled = True
        if fulfillable < plan.requested_quantity:
            any_partial = True

    if not any_fulfilled:
        raise EmptyReservationError("None of the requested products are currently in stock")

    reservation.is_partial = any_partial
    # Editing refreshes the hold window — same rule as a brand-new reservation.
    result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = result.scalar_one()
    if shop.reservation_timeout_minutes > 0:
        reservation.expires_at = datetime.now(timezone.utc) + timedelta(minutes=shop.reservation_timeout_minutes)

    await db.flush()
    await db.refresh(reservation, attribute_names=["items"])
    return reservation


# ─────────────────────────────────────────────────────────────────────────────
# Status transitions
# ─────────────────────────────────────────────────────────────────────────────

async def _get_reservation_or_raise(db: AsyncSession, shop_id: str, reservation_id: str) -> ShopReservation:
    result = await db.execute(
        select(ShopReservation).where(ShopReservation.id == reservation_id, ShopReservation.shop_id == shop_id)
    )
    reservation = result.scalar_one_or_none()
    if reservation is None:
        raise ReservationNotFoundError(reservation_id)
    return reservation


async def confirm_reservation(db: AsyncSession, shop_id: str, reservation_id: str) -> ShopReservation:
    """pending -> confirmed. Clears expires_at — a confirmed hold is no
    longer at risk of the automatic expiry loop."""
    reservation = await _get_reservation_or_raise(db, shop_id, reservation_id)
    if reservation.status != "pending":
        raise InvalidReservationStateError(f"Cannot confirm a reservation in status '{reservation.status}'")
    reservation.status = "confirmed"
    reservation.confirmed_at = datetime.now(timezone.utc)
    reservation.expires_at = None
    await db.flush()
    await db.refresh(reservation, attribute_names=["items"])
    return reservation


async def mark_ready(db: AsyncSession, shop_id: str, reservation_id: str) -> ShopReservation:
    """confirmed (or pending, for a shop that skips explicit confirmation) -> ready."""
    reservation = await _get_reservation_or_raise(db, shop_id, reservation_id)
    if reservation.status not in ("pending", "confirmed"):
        raise InvalidReservationStateError(f"Cannot mark ready a reservation in status '{reservation.status}'")
    reservation.status = "ready"
    reservation.ready_at = datetime.now(timezone.utc)
    reservation.expires_at = None
    await db.flush()
    await db.refresh(reservation, attribute_names=["items"])
    return reservation


async def complete_reservation(db: AsyncSession, shop_id: str, reservation_id: str) -> ShopReservation:
    """Marks a reservation completed (picked up at the counter). Stock was
    already decremented at hold time, so completing does NOT touch
    quantity_available again — it DOES write a `reservation_completed`
    movement row per item (units=quantity, delta=0) since that's the moment
    a hold becomes a confirmed sale for AI Inventory Intelligence purposes
    (best sellers, demand trend, fast/slow movers)."""
    reservation = await _get_reservation_or_raise(db, shop_id, reservation_id)
    if reservation.status in ("completed", "cancelled", "expired"):
        return reservation  # idempotent no-op
    await db.refresh(reservation, attribute_names=["items"])
    for item in reservation.items:
        result = await db.execute(select(ShopProduct).where(ShopProduct.id == item.product_id))
        product = result.scalar_one_or_none()
        if product is None:
            continue
        await record_movement(
            db, shop_id=shop_id, product_id=product.id,
            event_type="reservation_completed", quantity_delta=0, units=item.quantity,
            quantity_before=product.quantity_available, quantity_after=product.quantity_available,
            reference_id=reservation.id,
        )
    reservation.status = "completed"
    reservation.completed_at = datetime.now(timezone.utc)
    reservation.expires_at = None
    await db.flush()
    await db.refresh(reservation, attribute_names=["items"])
    return reservation


async def _restore_and_close(
    db: AsyncSession, reservation: ShopReservation, *, new_status: str, reason: str | None,
) -> list[str]:
    """Shared body of cancel/expire: restores stock for every item, marks the
    reservation terminal, and returns the list of affected product_ids so
    the caller can trigger waitlist processing for each."""
    await db.refresh(reservation, attribute_names=["items"])
    affected_product_ids: list[str] = []
    for item in reservation.items:
        product = await get_product_locked(db, reservation.shop_id, item.product_id)
        before = product.quantity_available
        product.quantity_available += item.quantity
        await record_movement(
            db, shop_id=reservation.shop_id, product_id=product.id,
            event_type="reservation_expired" if new_status == "expired" else "reservation_cancelled",
            quantity_delta=item.quantity, units=item.quantity,
            quantity_before=before, quantity_after=product.quantity_available,
            reference_id=reservation.id,
        )
        affected_product_ids.append(product.id)

    reservation.status = new_status
    reservation.expires_at = None
    reservation.cancelled_reason = reason
    now = datetime.now(timezone.utc)
    if new_status == "cancelled":
        reservation.cancelled_at = now
    await db.flush()
    return affected_product_ids


async def cancel_reservation(
    db: AsyncSession, shop_id: str, reservation_id: str, *, reason: str = "cancelled"
) -> tuple[ShopReservation, list[str]]:
    """Restores stock and marks the reservation cancelled. Returns the
    reservation plus the list of product_ids whose stock increased, so the
    caller can run process_waitlist_for_product() on each."""
    reservation = await _get_reservation_or_raise(db, shop_id, reservation_id)
    if reservation.status in ("completed", "cancelled", "expired"):
        return reservation, []  # already terminal — idempotent no-op

    affected = await _restore_and_close(db, reservation, new_status="cancelled", reason=reason)
    await db.refresh(reservation, attribute_names=["items"])
    return reservation, affected


async def expire_reservation(db: AsyncSession, reservation: ShopReservation) -> list[str]:
    """Used only by the background expiry loop — reservation is already
    loaded (and known to be 'pending' and past expires_at) by the caller."""
    return await _restore_and_close(db, reservation, new_status="expired", reason="expired")


async def get_due_expirations(db: AsyncSession, *, limit: int = 200) -> list[ShopReservation]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ShopReservation)
        .where(ShopReservation.status == "pending", ShopReservation.expires_at.isnot(None), ShopReservation.expires_at <= now)
        .limit(limit)
    )
    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Waiting list
# ─────────────────────────────────────────────────────────────────────────────

async def join_waitlist(
    db: AsyncSession, *, shop_id: str, product_id: str, quantity_requested: int, customer_name: str,
) -> ShopWaitlistEntry:
    if quantity_requested <= 0:
        raise ValueError("quantity must be a positive integer")
    result = await db.execute(select(ShopProduct).where(ShopProduct.id == product_id, ShopProduct.shop_id == shop_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError(product_id)

    entry = ShopWaitlistEntry(
        shop_id=shop_id, product_id=product_id,
        customer_name=customer_name.strip()[:120], quantity_requested=quantity_requested,
        status="waiting",
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def cancel_waitlist_entry(db: AsyncSession, shop_id: str, entry_id_or_lookup: str, *, by_lookup: bool = False) -> ShopWaitlistEntry:
    if by_lookup:
        result = await db.execute(
            select(ShopWaitlistEntry).where(ShopWaitlistEntry.shop_id == shop_id, ShopWaitlistEntry.lookup_code == entry_id_or_lookup)
        )
    else:
        result = await db.execute(
            select(ShopWaitlistEntry).where(ShopWaitlistEntry.shop_id == shop_id, ShopWaitlistEntry.id == entry_id_or_lookup)
        )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise WaitlistEntryNotFoundError(entry_id_or_lookup)
    if entry.status == "waiting":
        entry.status = "cancelled"
        await db.flush()
    return entry


async def process_waitlist_for_product(db: AsyncSession, shop_id: str, product_id: str) -> list[ShopReservation]:
    """Called after ANY event that increases a product's stock (reservation
    cancel/expire, manual restock, import, Google Sheets pull). Walks the
    waiting list for this product oldest-first and auto-creates a real
    reservation (holding stock immediately) for as many waiting customers as
    current stock allows. Returns the list of reservations it created so the
    caller can broadcast them over the websocket."""
    created: list[ShopReservation] = []
    while True:
        product = await get_product_locked(db, shop_id, product_id)
        if product.quantity_available <= 0:
            break
        result = await db.execute(
            select(ShopWaitlistEntry)
            .where(
                ShopWaitlistEntry.shop_id == shop_id,
                ShopWaitlistEntry.product_id == product_id,
                ShopWaitlistEntry.status == "waiting",
            )
            .order_by(ShopWaitlistEntry.created_at)
            .limit(1)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            break

        fulfillable = min(entry.quantity_requested, product.quantity_available)
        before = product.quantity_available
        product.quantity_available -= fulfillable

        shop = await _get_shop_locked(db, shop_id)
        reservation = ShopReservation(
            shop_id=shop_id, customer_name=entry.customer_name, status="pending",
            queue_number=shop.next_queue_number,
            is_partial=fulfillable < entry.quantity_requested,
        )
        shop.next_queue_number += 1
        if shop.reservation_timeout_minutes > 0:
            reservation.expires_at = datetime.now(timezone.utc) + timedelta(minutes=shop.reservation_timeout_minutes)
        db.add(reservation)
        await db.flush()

        item = ShopReservationItem(
            reservation_id=reservation.id, product_id=product.id,
            requested_quantity=entry.quantity_requested, quantity=fulfillable,
        )
        db.add(item)
        await record_movement(
            db, shop_id=shop_id, product_id=product.id,
            event_type="waitlist_fulfilled", quantity_delta=-fulfillable, units=fulfillable,
            quantity_before=before, quantity_after=product.quantity_available,
            reference_id=reservation.id,
        )

        # Whether the waitlisted quantity was fully or only partially covered,
        # this entry is done: a real reservation now exists and stock has
        # been allocated. A customer who still wants more than they got can
        # join the waitlist again for the remainder — this avoids the entry
        # being matched a second time in a later round (double allocation).
        entry.status = "fulfilled"
        entry.notified_at = datetime.now(timezone.utc)
        entry.fulfilled_reservation_id = reservation.id
        await db.flush()
        await db.refresh(reservation, attribute_names=["items"])
        created.append(reservation)
    return created


# ─────────────────────────────────────────────────────────────────────────────
# Manual quantity adjustments (owner edits, import, sync) — also logs + triggers waitlist
# ─────────────────────────────────────────────────────────────────────────────

async def adjust_product_quantity(
    db: AsyncSession, shop_id: str, product_id: str, new_quantity: int, *, event_type: str = "adjusted",
) -> ShopProduct:
    """Row-locks the product, sets quantity_available to the given absolute
    value, and logs the delta. Caller is responsible for calling
    process_waitlist_for_product() afterward if new_quantity > old (this
    function only performs the write + ledger entry, kept separate so admin
    routes can batch several adjustments in one transaction before running
    waitlist processing once per touched product)."""
    product = await get_product_locked(db, shop_id, product_id)
    before = product.quantity_available
    delta = new_quantity - before
    product.quantity_available = new_quantity
    await record_movement(
        db, shop_id=shop_id, product_id=product_id, event_type=event_type,
        quantity_delta=delta, units=abs(delta), quantity_before=before, quantity_after=new_quantity,
    )
    await db.flush()
    return product


def generate_qr_svg(public_url: str) -> str:
    """Renders a QR code (SVG, no Pillow dependency — same technique already
    used by services/totp_service.py for 2FA setup) that opens the shop's
    public customer page when scanned."""
    img = qrcode.make(public_url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")
