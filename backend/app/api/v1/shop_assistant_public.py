"""
ThunderBots Smart Shop Assistant — Public Customer API (independent product)

No authentication — this is what a customer's phone hits after scanning the
shop's QR code. Every route is scoped by the shop's unguessable
`public_slug`, never its internal `id`, and never exposes `owner_id` or any
other shop's data. Rate limiting (v107): search/reservation-create/waitlist-
join — the anonymous, high-fanout, write-capable routes — are now throttled
per-IP via the existing rate_limiter (app/core/rate_limit.py), fails open if
Redis is unavailable, same convention as auth.py's login/register limits.

v2 — Smart Reservation System: a reservation can now cover several products
at once. A customer can no longer be silently rejected because ONE item in
their cart is short — see /reservations/preview (read-only "5 of 7
available, want it anyway?") and the partial-fulfillment behavior baked
into create_reservation itself, which holds whatever IS available and skips
(never fails outright on) anything that's completely out of stock, so the
customer can be offered the waiting list for just that item.

Every mutation here is scoped to the caller's own `lookup_code` — a
customer can view/edit/cancel only the one reservation (or waitlist entry)
whose unguessable code they were handed, never anyone else's, even though
there is no login of any kind.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from app.core.rate_limit import rate_limiter
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.shop_assistant import Shop, ShopProduct, ShopReservation, ShopWaitlistEntry
from app.services import shop_assistant_service as svc
from app.services import shop_assistant_ws_manager as ws_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ShopPublicOut(BaseModel):
    name: str
    is_active: bool
    reservation_timeout_minutes: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)


class PublicProductImageOut(BaseModel):
    id: str
    url: str
    thumbnail_url: str
    width: int
    height: int
    is_cover: bool


class ProductMatchOut(BaseModel):
    id: str
    name: str
    sku: Optional[str]
    category: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[float] = None
    quantity_available: int
    in_stock: bool
    match_score: float
    is_exact_match: bool
    cover_image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    images: list[PublicProductImageOut] = []


class ReservationItemIn(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0, le=1000)


class ReservationCreateRequest(BaseModel):
    items: list[ReservationItemIn] = Field(..., min_length=1, max_length=50)
    customer_name: str = Field(..., min_length=1, max_length=120)


class ReservationPreviewRequest(BaseModel):
    items: list[ReservationItemIn] = Field(..., min_length=1, max_length=50)


class ReservationItemPreviewOut(BaseModel):
    product_id: str
    product_name: str
    requested_quantity: int
    fulfillable_quantity: int
    quantity_available: int
    is_partial: bool
    is_unavailable: bool


class ReservationItemOut(BaseModel):
    product_id: str
    product_name: str
    requested_quantity: int
    quantity: int
    cover_image_url: Optional[str] = None


class ReservationPublicOut(BaseModel):
    lookup_code: str
    queue_token: str
    queue_number: int
    queue_position: Optional[int] = None
    status: str
    is_partial: bool
    expires_at: Optional[str]
    items: list[ReservationItemOut]
    unavailable_product_ids: list[str] = []


class WaitlistJoinRequest(BaseModel):
    product_id: str
    quantity_requested: int = Field(..., gt=0, le=1000)
    customer_name: str = Field(..., min_length=1, max_length=120)


class WaitlistPublicOut(BaseModel):
    lookup_code: str
    product_id: str
    product_name: str
    quantity_requested: int
    status: str
    fulfilled_reservation_lookup_code: Optional[str] = None


class QueueStatusOut(BaseModel):
    total_waiting: int


def _product_to_dict(p: ShopProduct) -> dict:
    payload = {
        "id": p.id, "name": p.name, "sku": p.sku, "category": p.category,
        "brand": p.brand, "price": float(p.price) if p.price is not None else None,
        "quantity_available": p.quantity_available,
    }
    if "images" in p.__dict__:
        cover = _cover_image(p)
        payload["cover_image_url"] = cover.thumbnail_url if cover else None
    return payload


def _cover_image(p: ShopProduct):
    if not p.images:
        return None
    return next((im for im in p.images if im.is_cover), p.images[0])


def _product_match_to_out(m) -> "ProductMatchOut":
    p = m.product
    images = [
        PublicProductImageOut(id=im.id, url=im.url, thumbnail_url=im.thumbnail_url,
                               width=im.width, height=im.height, is_cover=im.is_cover)
        for im in p.images
    ]
    cover = _cover_image(p)
    return ProductMatchOut(
        id=p.id, name=p.name, sku=p.sku, category=p.category, brand=p.brand,
        price=float(p.price) if p.price is not None else None,
        quantity_available=p.quantity_available, in_stock=p.quantity_available > 0,
        match_score=round(m.score, 2), is_exact_match=m.score >= 0.999,
        cover_image_url=cover.url if cover else None,
        thumbnail_url=cover.thumbnail_url if cover else None,
        images=images,
    )


def _product_to_match_out(p: ShopProduct, *, score: float = 0.0, is_exact_match: bool = False) -> "ProductMatchOut":
    images = [
        PublicProductImageOut(id=im.id, url=im.url, thumbnail_url=im.thumbnail_url,
                               width=im.width, height=im.height, is_cover=im.is_cover)
        for im in p.images
    ]
    cover = _cover_image(p)
    return ProductMatchOut(
        id=p.id, name=p.name, sku=p.sku, category=p.category, brand=p.brand,
        price=float(p.price) if p.price is not None else None,
        quantity_available=p.quantity_available, in_stock=p.quantity_available > 0,
        match_score=score, is_exact_match=is_exact_match,
        cover_image_url=cover.url if cover else None,
        thumbnail_url=cover.thumbnail_url if cover else None,
        images=images,
    )


async def _get_active_shop_by_slug(db: AsyncSession, slug: str) -> Shop:
    result = await db.execute(select(Shop).where(Shop.public_slug == slug))
    shop = result.scalar_one_or_none()
    if shop is None or not shop.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return shop


async def _queue_position(db: AsyncSession, shop_id: str, reservation: ShopReservation) -> int:
    result = await db.execute(
        select(ShopReservation).where(
            ShopReservation.shop_id == shop_id,
            ShopReservation.status.in_(("pending", "confirmed", "ready")),
            ShopReservation.queue_number <= reservation.queue_number,
        )
    )
    return len(result.scalars().all())


async def _reservation_to_public_out(
    db: AsyncSession, reservation: ShopReservation, *, unavailable_product_ids: list[str] | None = None,
) -> ReservationPublicOut:
    await db.refresh(reservation, attribute_names=["items"])
    product_ids = [it.product_id for it in reservation.items]
    products = {}
    if product_ids:
        result = await db.execute(
            select(ShopProduct).where(ShopProduct.id.in_(product_ids)).options(selectinload(ShopProduct.images))
        )
        products = {p.id: p for p in result.scalars().all()}
    items = [
        ReservationItemOut(
            product_id=it.product_id,
            product_name=products[it.product_id].name if it.product_id in products else "(no longer available)",
            requested_quantity=it.requested_quantity, quantity=it.quantity,
            cover_image_url=(_cover_image(products[it.product_id]).thumbnail_url
                              if it.product_id in products and _cover_image(products[it.product_id]) else None),
        )
        for it in reservation.items
    ]
    position = None
    if reservation.status in ("pending", "confirmed", "ready"):
        position = await _queue_position(db, reservation.shop_id, reservation)
    return ReservationPublicOut(
        lookup_code=reservation.lookup_code, queue_token=reservation.queue_token,
        queue_number=reservation.queue_number, queue_position=position,
        status=reservation.status, is_partial=reservation.is_partial,
        expires_at=reservation.expires_at.isoformat() if reservation.expires_at else None,
        items=items, unavailable_product_ids=unavailable_product_ids or [],
    )


async def _broadcast_new_or_updated_reservation(db: AsyncSession, shop_id: str, reservation: ShopReservation) -> None:
    await db.refresh(reservation, attribute_names=["items"])
    product_ids = [it.product_id for it in reservation.items]
    products = {}
    if product_ids:
        result = await db.execute(
            select(ShopProduct).where(ShopProduct.id.in_(product_ids)).options(selectinload(ShopProduct.images))
        )
        products = {p.id: p for p in result.scalars().all()}
    await ws_manager.broadcast_booking_update(shop_id, {
        "id": reservation.id, "customer_name": reservation.customer_name, "status": reservation.status,
        "queue_token": reservation.queue_token, "queue_number": reservation.queue_number,
        "lookup_code": reservation.lookup_code, "is_partial": reservation.is_partial,
        "expires_at": reservation.expires_at.isoformat() if reservation.expires_at else None,
        "created_at": reservation.created_at.isoformat(),
        "items": [
            {"product_id": it.product_id, "product_name": products[it.product_id].name if it.product_id in products else "?",
             "requested_quantity": it.requested_quantity, "quantity": it.quantity}
            for it in reservation.items
        ],
    })
    await ws_manager.broadcast_reservation_status(shop_id, {
        "lookup_code": reservation.lookup_code, "status": reservation.status,
        "queue_token": reservation.queue_token, "queue_number": reservation.queue_number,
        "expires_at": reservation.expires_at.isoformat() if reservation.expires_at else None,
    })
    for p in products.values():
        await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(p))
    result = await db.execute(
        select(ShopReservation).where(
            ShopReservation.shop_id == shop_id, ShopReservation.status.in_(("pending", "confirmed", "ready"))
        )
    )
    await ws_manager.broadcast_queue_update(shop_id, {"total_waiting": len(result.scalars().all())})


# ─────────────────────────────────────────────────────────────────────────────
# Shop / search
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/shops/{slug}", response_model=ShopPublicOut)
async def get_public_shop(slug: str, db: AsyncSession = Depends(get_db)):
    shop = await _get_active_shop_by_slug(db, slug)
    return ShopPublicOut(
        name=shop.name, is_active=shop.is_active,
        reservation_timeout_minutes=shop.reservation_timeout_minutes,
    )


@router.post("/shops/{slug}/search", response_model=list[ProductMatchOut])
async def search_shop_products(
    slug: str, body: SearchRequest, db: AsyncSession = Depends(get_db),
    _rl=Depends(rate_limiter("shop_search", limit=30, window_seconds=60)),
):
    """Never returns a text-only result — every match carries its cover
    image (or None, so the frontend renders the placeholder) plus enough
    data (price, brand, category, stock) for a full product card.
    `is_exact_match` tells the frontend which layout to use: a single
    "found it" card (exact/substring name match) vs a "similar products"
    grid (fuzzy/typo-tolerant matches only) — see svc.search_products for
    how the underlying match score is computed. If nothing clears the
    match-score cutoff at all, falls back to a handful of real, live
    in-stock products from the same shop ("Related products") rather than
    ever showing an empty, text-only "no results" screen."""
    shop = await _get_active_shop_by_slug(db, slug)
    matches = await svc.search_products(db, shop.id, body.query)
    if matches:
        return [_product_match_to_out(m) for m in matches]

    # No fuzzy match cleared the cutoff at all — offer real related
    # products instead of a dead end. Prioritizes in-stock items; this is
    # still live inventory data, never a fabricated suggestion.
    result = await db.execute(
        select(ShopProduct).where(ShopProduct.shop_id == shop.id)
        .options(selectinload(ShopProduct.images))
        .order_by(ShopProduct.quantity_available.desc(), ShopProduct.created_at.desc())
        .limit(8)
    )
    fallback = list(result.scalars().all())
    return [_product_to_match_out(p, score=0.0, is_exact_match=False) for p in fallback]


@router.get("/shops/{slug}/products/browse", response_model=list[ProductMatchOut])
async def browse_shop_products(slug: str, category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """General browse / "related products" endpoint — same card shape as
    search results, used by the frontend for an initial "what's here"
    grid and for the related-products rail under an exact-match result."""
    shop = await _get_active_shop_by_slug(db, slug)
    query = select(ShopProduct).where(ShopProduct.shop_id == shop.id).options(selectinload(ShopProduct.images))
    if category:
        query = query.where(ShopProduct.category == category)
    query = query.order_by(ShopProduct.quantity_available.desc(), ShopProduct.name).limit(24)
    result = await db.execute(query)
    products = list(result.scalars().all())
    return [_product_to_match_out(p) for p in products]


@router.get("/shops/{slug}/queue", response_model=QueueStatusOut)
async def get_queue_status(slug: str, db: AsyncSession = Depends(get_db)):
    shop = await _get_active_shop_by_slug(db, slug)
    result = await db.execute(
        select(ShopReservation).where(
            ShopReservation.shop_id == shop.id, ShopReservation.status.in_(("pending", "confirmed", "ready"))
        )
    )
    return QueueStatusOut(total_waiting=len(result.scalars().all()))


# ─────────────────────────────────────────────────────────────────────────────
# Reservations — preview, create, view, edit, cancel, history
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/shops/{slug}/reservations/preview", response_model=list[ReservationItemPreviewOut])
async def preview_reservation(slug: str, body: ReservationPreviewRequest, db: AsyncSession = Depends(get_db)):
    """Read-only, no stock is held. Lets the customer see, BEFORE
    committing, whether every item in their cart is fully available — and
    if not, exactly how many of each ARE available — so they can decide
    whether to accept a Partial Reservation. Stock can still move between
    this call and the real POST /reservations call, which re-verifies
    everything under a row lock; this is advisory only."""
    shop = await _get_active_shop_by_slug(db, slug)
    try:
        previews = await svc.preview_reservation(
            db, shop.id, [svc.ReservationItemPlan(product_id=i.product_id, requested_quantity=i.quantity) for i in body.items]
        )
    except svc.ProductNotFoundError:
        raise HTTPException(status_code=404, detail="One or more products were not found")
    return [
        ReservationItemPreviewOut(
            product_id=p.product_id, product_name=p.product_name,
            requested_quantity=p.requested_quantity, fulfillable_quantity=p.fulfillable_quantity,
            quantity_available=p.quantity_available, is_partial=p.is_partial, is_unavailable=p.is_unavailable,
        )
        for p in previews
    ]


@router.post("/shops/{slug}/reservations", response_model=ReservationPublicOut, status_code=status.HTTP_201_CREATED)
async def create_public_reservation(
    slug: str, body: ReservationCreateRequest, db: AsyncSession = Depends(get_db),
    _rl=Depends(rate_limiter("shop_reservation_create", limit=10, window_seconds=300)),
):
    shop = await _get_active_shop_by_slug(db, slug)
    plans = [svc.ReservationItemPlan(product_id=i.product_id, requested_quantity=i.quantity) for i in body.items]
    requested_ids = {i.product_id for i in body.items}
    try:
        reservation = await svc.create_reservation(
            db, shop_id=shop.id, items=plans, customer_name=body.customer_name,
        )
    except svc.ProductNotFoundError:
        await db.rollback()
        raise HTTPException(status_code=404, detail="One or more products were not found")
    except svc.DuplicateReservationError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except svc.EmptyReservationError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    fulfilled_ids = {it.product_id for it in reservation.items}
    unavailable_ids = list(requested_ids - fulfilled_ids)

    await _broadcast_new_or_updated_reservation(db, shop.id, reservation)
    return await _reservation_to_public_out(db, reservation, unavailable_product_ids=unavailable_ids)


async def _get_own_reservation(db: AsyncSession, shop_id: str, lookup_code: str) -> ShopReservation:
    result = await db.execute(
        select(ShopReservation).where(ShopReservation.shop_id == shop_id, ShopReservation.lookup_code == lookup_code)
    )
    reservation = result.scalar_one_or_none()
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return reservation


@router.get("/shops/{slug}/reservations/{lookup_code}", response_model=ReservationPublicOut)
async def get_public_reservation_status(slug: str, lookup_code: str, db: AsyncSession = Depends(get_db)):
    shop = await _get_active_shop_by_slug(db, slug)
    reservation = await _get_own_reservation(db, shop.id, lookup_code)
    return await _reservation_to_public_out(db, reservation)


@router.get("/shops/{slug}/reservations", response_model=list[ReservationPublicOut])
async def get_reservation_history(
    slug: str, codes: str = Query(..., description="Comma-separated lookup codes"),
    db: AsyncSession = Depends(get_db),
):
    """Reservation history for a customer with no login: the frontend keeps
    every lookup_code it's ever been handed (in local storage) and passes
    them all here to render a "My Reservations" list, current and past."""
    shop = await _get_active_shop_by_slug(db, slug)
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:50]
    if not code_list:
        return []
    result = await db.execute(
        select(ShopReservation)
        .where(ShopReservation.shop_id == shop.id, ShopReservation.lookup_code.in_(code_list))
        .order_by(ShopReservation.created_at.desc())
    )
    reservations = list(result.scalars().all())
    return [await _reservation_to_public_out(db, r) for r in reservations]


@router.patch("/shops/{slug}/reservations/{lookup_code}", response_model=ReservationPublicOut)
async def edit_own_reservation(
    slug: str, lookup_code: str, body: ReservationCreateRequest, db: AsyncSession = Depends(get_db),
):
    """Editing before confirmation, customer-initiated — only works while
    the reservation is still 'pending' (staff haven't confirmed it yet)."""
    shop = await _get_active_shop_by_slug(db, slug)
    reservation = await _get_own_reservation(db, shop.id, lookup_code)
    requested_ids = {i.product_id for i in body.items}
    try:
        reservation = await svc.edit_reservation(
            db, shop.id, reservation.id,
            [svc.ReservationItemPlan(product_id=i.product_id, requested_quantity=i.quantity) for i in body.items],
        )
    except svc.InvalidReservationStateError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except svc.EmptyReservationError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except (svc.ProductNotFoundError, ValueError) as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    fulfilled_ids = {it.product_id for it in reservation.items}
    unavailable_ids = list(requested_ids - fulfilled_ids)
    await _broadcast_new_or_updated_reservation(db, shop.id, reservation)
    return await _reservation_to_public_out(db, reservation, unavailable_product_ids=unavailable_ids)


@router.patch("/shops/{slug}/reservations/{lookup_code}/cancel", response_model=ReservationPublicOut)
async def cancel_own_reservation(slug: str, lookup_code: str, db: AsyncSession = Depends(get_db)):
    """Customer-initiated cancellation — restores stock immediately and, if
    that stock now covers someone on the waiting list, auto-reserves it for
    them right away."""
    shop = await _get_active_shop_by_slug(db, slug)
    reservation = await _get_own_reservation(db, shop.id, lookup_code)
    reservation, affected_product_ids = await svc.cancel_reservation(
        db, shop.id, reservation.id, reason="cancelled_by_customer"
    )
    for product_id in set(affected_product_ids):
        await svc.process_waitlist_for_product(db, shop.id, product_id)
    await db.commit()
    await _broadcast_new_or_updated_reservation(db, shop.id, reservation)
    return await _reservation_to_public_out(db, reservation)


# ─────────────────────────────────────────────────────────────────────────────
# Waiting list
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/shops/{slug}/waitlist", response_model=WaitlistPublicOut, status_code=status.HTTP_201_CREATED)
async def join_waitlist(
    slug: str, body: WaitlistJoinRequest, db: AsyncSession = Depends(get_db),
    _rl=Depends(rate_limiter("shop_waitlist_join", limit=10, window_seconds=300)),
):
    shop = await _get_active_shop_by_slug(db, slug)
    try:
        entry = await svc.join_waitlist(
            db, shop_id=shop.id, product_id=body.product_id,
            quantity_requested=body.quantity_requested, customer_name=body.customer_name,
        )
    except svc.ProductNotFoundError:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Product not found")
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    result = await db.execute(select(ShopProduct).where(ShopProduct.id == entry.product_id))
    product = result.scalar_one()
    return WaitlistPublicOut(
        lookup_code=entry.lookup_code, product_id=entry.product_id, product_name=product.name,
        quantity_requested=entry.quantity_requested, status=entry.status,
    )


@router.get("/shops/{slug}/waitlist/{lookup_code}", response_model=WaitlistPublicOut)
async def get_waitlist_status(slug: str, lookup_code: str, db: AsyncSession = Depends(get_db)):
    shop = await _get_active_shop_by_slug(db, slug)
    result = await db.execute(
        select(ShopWaitlistEntry, ShopProduct.name)
        .join(ShopProduct, ShopProduct.id == ShopWaitlistEntry.product_id)
        .where(ShopWaitlistEntry.shop_id == shop.id, ShopWaitlistEntry.lookup_code == lookup_code)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    entry, product_name = row
    fulfilled_code = None
    if entry.fulfilled_reservation_id:
        res_result = await db.execute(select(ShopReservation).where(ShopReservation.id == entry.fulfilled_reservation_id))
        res = res_result.scalar_one_or_none()
        fulfilled_code = res.lookup_code if res else None
    return WaitlistPublicOut(
        lookup_code=entry.lookup_code, product_id=entry.product_id, product_name=product_name,
        quantity_requested=entry.quantity_requested, status=entry.status,
        fulfilled_reservation_lookup_code=fulfilled_code,
    )


@router.patch("/shops/{slug}/waitlist/{lookup_code}/cancel", response_model=WaitlistPublicOut)
async def cancel_own_waitlist_entry(slug: str, lookup_code: str, db: AsyncSession = Depends(get_db)):
    shop = await _get_active_shop_by_slug(db, slug)
    try:
        entry = await svc.cancel_waitlist_entry(db, shop.id, lookup_code, by_lookup=True)
    except svc.WaitlistEntryNotFoundError:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    await db.commit()
    result = await db.execute(select(ShopProduct).where(ShopProduct.id == entry.product_id))
    product = result.scalar_one()
    return WaitlistPublicOut(
        lookup_code=entry.lookup_code, product_id=entry.product_id, product_name=product.name,
        quantity_requested=entry.quantity_requested, status=entry.status,
    )
