"""
ThunderBots Smart Shop Assistant — Admin API (independent product)

Everything here is authenticated (get_current_user, reused as-is) and
owner-scoped: every query filters by `Shop.owner_id == user.id` so one
account can never read or modify another shop's inventory or bookings —
see `_get_owned_shop`, the single chokepoint every route goes through.

v2 adds three route groups on top of the original Live Inventory + Live
Customer Bookings panel:
  - Reservation lifecycle (edit-before-confirm / confirm / ready / complete
    / cancel) and the waiting list, backing the Smart Reservation System.
  - AI Inventory Intelligence — every figure is read straight out of
    shop_inventory_intelligence_service, which computes everything from the
    live ShopProduct + ShopProductMovement ledger. Nothing here invents a
    number.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.config import settings
from app.models.user import User
from app.models.shop_assistant import (
    Shop, ShopProduct, ShopReservation, ShopWaitlistEntry, ShopSyncConfig, ShopProductImage,
)
from app.services import shop_assistant_service as svc
from app.services import shop_inventory_intelligence_service as intel_svc
from app.services import shop_sync_service as sync_svc
from app.services import shop_assistant_ws_manager as ws_manager
from app.services import shop_product_image_service as image_svc

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ShopCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class ShopSettingsUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    is_active: Optional[bool] = None
    reservation_timeout_minutes: Optional[int] = Field(None, ge=0, le=1440)
    low_stock_threshold: Optional[int] = Field(None, ge=0)


class ShopOut(BaseModel):
    id: str
    name: str
    public_slug: str
    public_url: str
    is_active: bool
    reservation_timeout_minutes: int
    low_stock_threshold: int

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    sku: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    brand: Optional[str] = Field(None, max_length=120)
    price: Optional[float] = Field(None, ge=0)
    quantity_available: int = Field(..., ge=0)
    low_stock_threshold: Optional[int] = Field(None, ge=0)
    reorder_quantity: Optional[int] = Field(None, ge=0)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    sku: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = Field(None, max_length=120)
    price: Optional[float] = Field(None, ge=0)
    quantity_available: Optional[int] = Field(None, ge=0)
    low_stock_threshold: Optional[int] = Field(None, ge=0)
    reorder_quantity: Optional[int] = Field(None, ge=0)


class ProductImageOut(BaseModel):
    id: str
    url: str
    thumbnail_url: str
    width: int
    height: int
    is_cover: bool
    sort_order: int

    class Config:
        from_attributes = True


class ProductOut(BaseModel):
    id: str
    name: str
    sku: Optional[str]
    category: Optional[str]
    brand: Optional[str] = None
    price: Optional[float] = None
    quantity_available: int
    low_stock_threshold: Optional[int]
    reorder_quantity: Optional[int]
    images: list[ProductImageOut] = []

    class Config:
        from_attributes = True


class ReservationItemIn(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0, le=1000)


class ReservationItemOut(BaseModel):
    product_id: str
    product_name: str
    requested_quantity: int
    quantity: int


class ReservationOut(BaseModel):
    id: str
    customer_name: str
    status: str
    queue_token: str
    queue_number: int
    lookup_code: str
    is_partial: bool
    expires_at: Optional[str]
    confirmed_at: Optional[str]
    ready_at: Optional[str]
    completed_at: Optional[str]
    cancelled_at: Optional[str]
    cancelled_reason: Optional[str]
    created_at: str
    items: list[ReservationItemOut]


class WaitlistOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    customer_name: str
    quantity_requested: int
    status: str
    lookup_code: str
    created_at: str
    notified_at: Optional[str]


class GoogleSheetsConnect(BaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    worksheet_name: str = Field("Inventory", min_length=1, max_length=200)
    service_account_json: str = Field(..., min_length=1)


def _product_to_dict(p: ShopProduct) -> dict:
    payload = {
        "id": p.id, "name": p.name, "sku": p.sku, "category": p.category,
        "brand": p.brand, "price": float(p.price) if p.price is not None else None,
        "quantity_available": p.quantity_available,
        "low_stock_threshold": p.low_stock_threshold, "reorder_quantity": p.reorder_quantity,
    }
    # Only include image data if the relationship happens to already be
    # loaded on this instance — never trigger an implicit lazy load here
    # (unsupported under the async ORM, and this function is called from
    # several different contexts where `images` may or may not be eager-loaded).
    if "images" in p.__dict__:
        images = p.images or []
        cover = next((im for im in images if im.is_cover), images[0] if images else None)
        payload["cover_image_url"] = cover.thumbnail_url if cover else None
        payload["image_count"] = len(images)
        payload["images"] = [
            {
                "id": im.id, "url": im.url, "thumbnail_url": im.thumbnail_url,
                "width": im.width, "height": im.height,
                "is_cover": im.is_cover, "sort_order": im.sort_order,
            }
            for im in images
        ]
    return payload


async def _reservation_to_out(db: AsyncSession, r: ShopReservation) -> ReservationOut:
    if "items" not in r.__dict__ or r.items is None:
        await db.refresh(r, attribute_names=["items"])
    product_ids = [it.product_id for it in r.items]
    products = {}
    if product_ids:
        result = await db.execute(select(ShopProduct).where(ShopProduct.id.in_(product_ids)))
        products = {p.id: p for p in result.scalars().all()}
    items = [
        ReservationItemOut(
            product_id=it.product_id,
            product_name=products[it.product_id].name if it.product_id in products else "(deleted product)",
            requested_quantity=it.requested_quantity, quantity=it.quantity,
        )
        for it in r.items
    ]
    return ReservationOut(
        id=r.id, customer_name=r.customer_name, status=r.status,
        queue_token=r.queue_token, queue_number=r.queue_number, lookup_code=r.lookup_code,
        is_partial=r.is_partial,
        expires_at=r.expires_at.isoformat() if r.expires_at else None,
        confirmed_at=r.confirmed_at.isoformat() if r.confirmed_at else None,
        ready_at=r.ready_at.isoformat() if r.ready_at else None,
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        cancelled_at=r.cancelled_at.isoformat() if r.cancelled_at else None,
        cancelled_reason=r.cancelled_reason,
        created_at=r.created_at.isoformat(), items=items,
    )


def _reservation_ws_payload(out: ReservationOut) -> dict:
    return out.model_dump()


async def _get_owned_shop(db: AsyncSession, user: User, shop_id: str) -> Shop:
    result = await db.execute(
        select(Shop).where(Shop.id == shop_id, Shop.owner_id == user.id)
    )
    shop = result.scalar_one_or_none()
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return shop


def _shop_to_out(shop: Shop) -> ShopOut:
    return ShopOut(
        id=shop.id, name=shop.name, public_slug=shop.public_slug, is_active=shop.is_active,
        public_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/shop/{shop.public_slug}",
        reservation_timeout_minutes=shop.reservation_timeout_minutes,
        low_stock_threshold=shop.low_stock_threshold,
    )


async def _broadcast_reservation(db: AsyncSession, shop_id: str, reservation: ShopReservation) -> ReservationOut:
    out = await _reservation_to_out(db, reservation)
    await ws_manager.broadcast_booking_update(shop_id, _reservation_ws_payload(out))
    await ws_manager.broadcast_reservation_status(shop_id, {
        "lookup_code": out.lookup_code, "status": out.status,
        "queue_token": out.queue_token, "queue_number": out.queue_number,
        "expires_at": out.expires_at,
    })
    return out


async def _broadcast_queue(db: AsyncSession, shop_id: str) -> None:
    result = await db.execute(
        select(ShopReservation).where(
            ShopReservation.shop_id == shop_id,
            ShopReservation.status.in_(("pending", "confirmed", "ready")),
        )
    )
    total_waiting = len(result.scalars().all())
    await ws_manager.broadcast_queue_update(shop_id, {"total_waiting": total_waiting})


async def _maybe_broadcast_low_stock(db: AsyncSession, shop: Shop, product: ShopProduct) -> None:
    threshold = product.low_stock_threshold if product.low_stock_threshold is not None else shop.low_stock_threshold
    if product.quantity_available <= threshold:
        await ws_manager.broadcast_inventory_alert(shop.id, {
            "product_id": product.id, "product_name": product.name,
            "quantity_available": product.quantity_available, "threshold": threshold,
            "severity": "out_of_stock" if product.quantity_available == 0 else "low",
        })


# ─────────────────────────────────────────────────────────────────────────────
# Shops
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/shops", response_model=ShopOut, status_code=status.HTTP_201_CREATED)
async def create_shop(
    body: ShopCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    shop = Shop(owner_id=user.id, name=body.name.strip())
    db.add(shop)
    await db.commit()
    await db.refresh(shop)
    return _shop_to_out(shop)


@router.get("/shops", response_model=list[ShopOut])
async def list_shops(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Shop).where(Shop.owner_id == user.id).order_by(Shop.created_at.desc()))
    return [_shop_to_out(s) for s in result.scalars().all()]


@router.get("/shops/{shop_id}", response_model=ShopOut)
async def get_shop(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    shop = await _get_owned_shop(db, user, shop_id)
    return _shop_to_out(shop)


@router.patch("/shops/{shop_id}", response_model=ShopOut)
async def update_shop_settings(
    shop_id: str, body: ShopSettingsUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Lets the owner configure the reservation hold timeout (Smart
    Reservation System) and the default low-stock alert threshold (AI
    Inventory Intelligence) per shop."""
    shop = await _get_owned_shop(db, user, shop_id)
    if body.name is not None:
        shop.name = body.name.strip()
    if body.is_active is not None:
        shop.is_active = body.is_active
    if body.reservation_timeout_minutes is not None:
        shop.reservation_timeout_minutes = body.reservation_timeout_minutes
    if body.low_stock_threshold is not None:
        shop.low_stock_threshold = body.low_stock_threshold
    await db.commit()
    await db.refresh(shop)
    return _shop_to_out(shop)


@router.get("/shops/{shop_id}/qr")
async def get_shop_qr(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    shop = await _get_owned_shop(db, user, shop_id)
    public_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/shop/{shop.public_slug}"
    svg = svc.generate_qr_svg(public_url)
    return Response(content=svg, media_type="image/svg+xml")


# ─────────────────────────────────────────────────────────────────────────────
# Inventory (Live Inventory panel)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/shops/{shop_id}/products", response_model=list[ProductOut])
async def list_products(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    result = await db.execute(
        select(ShopProduct).where(ShopProduct.shop_id == shop_id)
        .options(selectinload(ShopProduct.images))
        .order_by(ShopProduct.name)
    )
    return list(result.scalars().all())


@router.post("/shops/{shop_id}/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    shop_id: str, body: ProductCreate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    product = ShopProduct(
        shop_id=shop_id, name=body.name.strip(), sku=body.sku, category=body.category,
        brand=body.brand, price=body.price,
        quantity_available=body.quantity_available,
        low_stock_threshold=body.low_stock_threshold, reorder_quantity=body.reorder_quantity,
    )
    db.add(product)
    await db.flush()
    await svc.record_movement(
        db, shop_id=shop_id, product_id=product.id, event_type="created",
        quantity_delta=0, units=0, quantity_before=0, quantity_after=product.quantity_available,
    )
    await db.commit()
    await db.refresh(product, attribute_names=["images"])
    await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(product))
    return product


@router.patch("/shops/{shop_id}/products/{product_id}", response_model=ProductOut)
async def update_product(
    shop_id: str, product_id: str, body: ProductUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    shop = await _get_owned_shop(db, user, shop_id)
    result = await db.execute(
        select(ShopProduct).where(ShopProduct.id == product_id, ShopProduct.shop_id == shop_id).with_for_update()
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if body.name is not None:
        product.name = body.name.strip()
    if body.sku is not None:
        product.sku = body.sku
    if body.category is not None:
        product.category = body.category
    if body.brand is not None:
        product.brand = body.brand
    if body.price is not None:
        product.price = body.price
    if body.low_stock_threshold is not None:
        product.low_stock_threshold = body.low_stock_threshold
    if body.reorder_quantity is not None:
        product.reorder_quantity = body.reorder_quantity

    quantity_increased = False
    if body.quantity_available is not None and body.quantity_available != product.quantity_available:
        before = product.quantity_available
        quantity_increased = body.quantity_available > before
        product.quantity_available = body.quantity_available
        await svc.record_movement(
            db, shop_id=shop_id, product_id=product_id, event_type="adjusted",
            quantity_delta=body.quantity_available - before, units=abs(body.quantity_available - before),
            quantity_before=before, quantity_after=product.quantity_available,
        )

    if quantity_increased:
        await svc.process_waitlist_for_product(db, shop_id, product_id)

    await db.commit()
    await db.refresh(product, attribute_names=["images"])
    await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(product))
    await _maybe_broadcast_low_stock(db, shop, product)
    return product


@router.delete("/shops/{shop_id}/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    shop_id: str, product_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    result = await db.execute(
        select(ShopProduct).where(ShopProduct.id == product_id, ShopProduct.shop_id == shop_id)
        .options(selectinload(ShopProduct.images))
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    image_files = [(im.url, im.thumbnail_url) for im in product.images]
    await db.delete(product)
    await db.commit()
    for url, thumb_url in image_files:
        image_svc.delete_image_files(url, thumb_url)
    await ws_manager.broadcast_inventory_update(shop_id, {"id": product_id, "deleted": True})


# ─────────────────────────────────────────────────────────────────────────────
# Product images (NEW — Product Image Support)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_owned_product(db: AsyncSession, user: User, shop_id: str, product_id: str) -> ShopProduct:
    await _get_owned_shop(db, user, shop_id)
    result = await db.execute(
        select(ShopProduct).where(ShopProduct.id == product_id, ShopProduct.shop_id == shop_id)
        .options(selectinload(ShopProduct.images))
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/shops/{shop_id}/products/{product_id}/images", response_model=list[ProductImageOut], status_code=status.HTTP_201_CREATED)
async def upload_product_images(
    shop_id: str, product_id: str, files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Accepts one or more images in a single request (drag-and-drop of a
    multi-file selection maps directly to this). Each is validated,
    compressed into a display + thumbnail WEBP pair, and stored — see
    shop_product_image_service for the pipeline. The very first image ever
    uploaded for a product automatically becomes its cover; after that, the
    owner picks the cover explicitly via the /cover endpoint below."""
    product = await _get_owned_product(db, user, shop_id, product_id)
    if len(product.images) + len(files) > image_svc.MAX_IMAGES_PER_PRODUCT:
        raise HTTPException(
            status_code=400,
            detail=f"A product can have at most {image_svc.MAX_IMAGES_PER_PRODUCT} images "
                   f"({len(product.images)} already uploaded)",
        )

    next_sort_order = (max((im.sort_order for im in product.images), default=-1)) + 1
    has_cover = any(im.is_cover for im in product.images)
    created: list[ShopProductImage] = []

    for file in files:
        content = await file.read()
        try:
            result = image_svc.process_and_store_image(
                shop_id=shop_id, product_id=product_id, filename=file.filename or "", content=content,
            )
        except image_svc.InvalidImageError as e:
            raise HTTPException(status_code=400, detail=f"{file.filename}: {e}")

        image = ShopProductImage(
            shop_id=shop_id, product_id=product_id,
            url=result["url"], thumbnail_url=result["thumbnail_url"],
            width=result["width"], height=result["height"], file_size=result["file_size"],
            is_cover=not has_cover, sort_order=next_sort_order,
        )
        has_cover = True
        next_sort_order += 1
        db.add(image)
        created.append(image)

    await db.commit()
    for image in created:
        await db.refresh(image)

    await db.refresh(product, attribute_names=["images"])
    await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(product))
    return created


@router.delete("/shops/{shop_id}/products/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_image(
    shop_id: str, product_id: str, image_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    product = await _get_owned_product(db, user, shop_id, product_id)
    image = next((im for im in product.images if im.id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    was_cover = image.is_cover
    url, thumb_url = image.url, image.thumbnail_url
    await db.delete(image)
    await db.flush()

    if was_cover:
        # Promote the next image (lowest sort_order) to cover, if any remain.
        remaining = sorted((im for im in product.images if im.id != image_id), key=lambda im: im.sort_order)
        if remaining:
            remaining[0].is_cover = True

    await db.commit()
    image_svc.delete_image_files(url, thumb_url)

    await db.refresh(product, attribute_names=["images"])
    await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(product))


@router.patch("/shops/{shop_id}/products/{product_id}/images/{image_id}/cover", response_model=list[ProductImageOut])
async def set_product_cover_image(
    shop_id: str, product_id: str, image_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    product = await _get_owned_product(db, user, shop_id, product_id)
    target = next((im for im in product.images if im.id == image_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Image not found")

    for im in product.images:
        im.is_cover = (im.id == image_id)
    await db.commit()

    await db.refresh(product, attribute_names=["images"])
    await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(product))
    return product.images


@router.get("/shops/{shop_id}/products/export")
async def export_products(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    shop = await _get_owned_shop(db, user, shop_id)
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id).order_by(ShopProduct.name))
    xlsx_bytes = sync_svc.export_to_xlsx(list(result.scalars().all()))
    filename = f"{shop.name.replace(' ', '_')}_inventory.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/shops/{shop_id}/products/import")
async def import_products(
    shop_id: str, file: UploadFile = File(...),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    file_bytes = await file.read()
    try:
        rows = sync_svc.parse_xlsx(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    summary = await sync_svc.apply_rows_to_db(db, shop_id, rows)
    await db.commit()

    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id))
    products = list(result.scalars().all())
    for p in products:
        await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(p))
    for product_id in summary.get("increased_product_ids", []):
        await svc.process_waitlist_for_product(db, shop_id, product_id)
    await db.commit()
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Google Sheets sync
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/shops/{shop_id}/sync/google-sheets")
async def connect_google_sheets(
    shop_id: str, body: GoogleSheetsConnect,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    try:
        encrypted = sync_svc.encrypt_credentials(body.service_account_json)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await db.execute(select(ShopSyncConfig).where(ShopSyncConfig.shop_id == shop_id))
    config = result.scalar_one_or_none()
    if config is None:
        config = ShopSyncConfig(shop_id=shop_id, spreadsheet_id=body.spreadsheet_id,
                                 worksheet_name=body.worksheet_name, encrypted_credentials=encrypted)
        db.add(config)
    else:
        config.spreadsheet_id = body.spreadsheet_id
        config.worksheet_name = body.worksheet_name
        config.encrypted_credentials = encrypted
    await db.commit()
    return {"connected": True}


@router.post("/shops/{shop_id}/sync/google-sheets/push")
async def push_google_sheets(
    shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    result = await db.execute(select(ShopSyncConfig).where(ShopSyncConfig.shop_id == shop_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=400, detail="Google Sheets is not connected for this shop")
    products_result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id))
    products = list(products_result.scalars().all())
    try:
        sync_svc.push_to_google_sheet(config, products)
        sync_svc.mark_sync_result(config, error=None)
    except Exception as e:
        logger.warning(f"Shop Assistant: Google Sheets push failed for shop={shop_id}: {e}")
        sync_svc.mark_sync_result(config, error=str(e))
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Google Sheets push failed: {e}")
    await db.commit()
    return {"pushed": len(products)}


@router.post("/shops/{shop_id}/sync/google-sheets/pull")
async def pull_google_sheets(
    shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    result = await db.execute(select(ShopSyncConfig).where(ShopSyncConfig.shop_id == shop_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=400, detail="Google Sheets is not connected for this shop")
    try:
        rows = sync_svc.pull_from_google_sheet(config)
        summary = await sync_svc.apply_rows_to_db(db, shop_id, rows, event_type="sync_pull")
        sync_svc.mark_sync_result(config, error=None)
    except Exception as e:
        logger.warning(f"Shop Assistant: Google Sheets pull failed for shop={shop_id}: {e}")
        sync_svc.mark_sync_result(config, error=str(e))
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Google Sheets pull failed: {e}")
    await db.commit()

    products_result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id))
    for p in products_result.scalars().all():
        await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(p))
    for product_id in summary.get("increased_product_ids", []):
        await svc.process_waitlist_for_product(db, shop_id, product_id)
    await db.commit()
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Reservations (Live Customer Bookings panel + Smart Reservation System)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/shops/{shop_id}/reservations", response_model=list[ReservationOut])
async def list_reservations(
    shop_id: str, status_filter: Optional[str] = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Also backs Reservation History — pass status_filter=completed (or
    cancelled/expired) to see past reservations instead of active ones."""
    await _get_owned_shop(db, user, shop_id)
    query = select(ShopReservation).where(ShopReservation.shop_id == shop_id).order_by(ShopReservation.created_at.desc())
    if status_filter:
        query = query.where(ShopReservation.status == status_filter)
    result = await db.execute(query)
    reservations = list(result.scalars().all())
    return [await _reservation_to_out(db, r) for r in reservations]


@router.get("/shops/{shop_id}/reservations/{reservation_id}", response_model=ReservationOut)
async def get_reservation(
    shop_id: str, reservation_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    result = await db.execute(
        select(ShopReservation).where(ShopReservation.id == reservation_id, ShopReservation.shop_id == shop_id)
    )
    reservation = result.scalar_one_or_none()
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return await _reservation_to_out(db, reservation)


@router.patch("/shops/{shop_id}/reservations/{reservation_id}", response_model=ReservationOut)
async def edit_reservation(
    shop_id: str, reservation_id: str, body: list[ReservationItemIn],
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Editing before confirmation — only allowed while status is still
    'pending'. Replaces the reservation's line items; anything no longer
    fulfillable is silently dropped (mirrors the partial-reservation logic
    used at creation time)."""
    await _get_owned_shop(db, user, shop_id)
    try:
        reservation = await svc.edit_reservation(
            db, shop_id, reservation_id,
            [svc.ReservationItemPlan(product_id=i.product_id, requested_quantity=i.quantity) for i in body],
        )
    except svc.ReservationNotFoundError:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Reservation not found")
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
    out = await _broadcast_reservation(db, shop_id, reservation)
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id))
    for p in result.scalars().all():
        await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(p))
    return out


@router.patch("/shops/{shop_id}/reservations/{reservation_id}/confirm", response_model=ReservationOut)
async def confirm_reservation_route(
    shop_id: str, reservation_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    try:
        reservation = await svc.confirm_reservation(db, shop_id, reservation_id)
    except svc.ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except svc.InvalidReservationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await db.commit()
    return await _broadcast_reservation(db, shop_id, reservation)


@router.patch("/shops/{shop_id}/reservations/{reservation_id}/ready", response_model=ReservationOut)
async def mark_reservation_ready(
    shop_id: str, reservation_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    try:
        reservation = await svc.mark_ready(db, shop_id, reservation_id)
    except svc.ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    except svc.InvalidReservationStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await db.commit()
    return await _broadcast_reservation(db, shop_id, reservation)


@router.patch("/shops/{shop_id}/reservations/{reservation_id}/complete", response_model=ReservationOut)
async def mark_reservation_completed(
    shop_id: str, reservation_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    try:
        reservation = await svc.complete_reservation(db, shop_id, reservation_id)
    except svc.ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")
    await db.commit()
    out = await _broadcast_reservation(db, shop_id, reservation)
    await _broadcast_queue(db, shop_id)
    return out


@router.patch("/shops/{shop_id}/reservations/{reservation_id}/cancel", response_model=ReservationOut)
async def mark_reservation_cancelled(
    shop_id: str, reservation_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    shop = await _get_owned_shop(db, user, shop_id)
    try:
        reservation, affected_product_ids = await svc.cancel_reservation(db, shop_id, reservation_id, reason="cancelled_by_shop")
    except svc.ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="Reservation not found")

    for product_id in set(affected_product_ids):
        await svc.process_waitlist_for_product(db, shop_id, product_id)
    await db.commit()

    out = await _broadcast_reservation(db, shop_id, reservation)
    result = await db.execute(select(ShopProduct).where(ShopProduct.shop_id == shop_id, ShopProduct.id.in_(affected_product_ids)))
    for p in result.scalars().all():
        await ws_manager.broadcast_inventory_update(shop_id, _product_to_dict(p))
    await _broadcast_queue(db, shop_id)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Waiting list
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/shops/{shop_id}/waitlist", response_model=list[WaitlistOut])
async def list_waitlist(
    shop_id: str, status_filter: Optional[str] = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    query = (
        select(ShopWaitlistEntry, ShopProduct.name)
        .join(ShopProduct, ShopProduct.id == ShopWaitlistEntry.product_id)
        .where(ShopWaitlistEntry.shop_id == shop_id)
        .order_by(ShopWaitlistEntry.created_at)
    )
    if status_filter:
        query = query.where(ShopWaitlistEntry.status == status_filter)
    result = await db.execute(query)
    return [
        WaitlistOut(
            id=e.id, product_id=e.product_id, product_name=name, customer_name=e.customer_name,
            quantity_requested=e.quantity_requested, status=e.status, lookup_code=e.lookup_code,
            created_at=e.created_at.isoformat(), notified_at=e.notified_at.isoformat() if e.notified_at else None,
        )
        for e, name in result.all()
    ]


@router.patch("/shops/{shop_id}/waitlist/{entry_id}/cancel", response_model=WaitlistOut)
async def cancel_waitlist_admin(
    shop_id: str, entry_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    try:
        entry = await svc.cancel_waitlist_entry(db, shop_id, entry_id)
    except svc.WaitlistEntryNotFoundError:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    await db.commit()
    result = await db.execute(select(ShopProduct).where(ShopProduct.id == entry.product_id))
    product = result.scalar_one_or_none()
    return WaitlistOut(
        id=entry.id, product_id=entry.product_id, product_name=product.name if product else "(deleted product)",
        customer_name=entry.customer_name, quantity_requested=entry.quantity_requested,
        status=entry.status, lookup_code=entry.lookup_code, created_at=entry.created_at.isoformat(),
        notified_at=entry.notified_at.isoformat() if entry.notified_at else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI Inventory Intelligence
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/shops/{shop_id}/intelligence/low-stock")
async def low_stock_alerts(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_low_stock_alerts(db, shop_id)


@router.get("/shops/{shop_id}/intelligence/out-of-stock-predictions")
async def out_of_stock_predictions(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_out_of_stock_predictions(db, shop_id)


@router.get("/shops/{shop_id}/intelligence/fast-moving")
async def fast_moving_products(shop_id: str, limit: int = 10, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_fast_moving_products(db, shop_id, limit=limit)


@router.get("/shops/{shop_id}/intelligence/slow-moving")
async def slow_moving_products(shop_id: str, limit: int = 10, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_slow_moving_products(db, shop_id, limit=limit)


@router.get("/shops/{shop_id}/intelligence/dead-stock")
async def dead_stock(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_dead_stock(db, shop_id)


@router.get("/shops/{shop_id}/intelligence/reorder-suggestions")
async def reorder_suggestions(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_reorder_suggestions(db, shop_id)


@router.get("/shops/{shop_id}/intelligence/best-sellers")
async def best_sellers(shop_id: str, limit: int = 10, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_best_selling_products(db, shop_id, limit=limit)


@router.get("/shops/{shop_id}/intelligence/demand-trend")
async def demand_trend(
    shop_id: str, product_id: Optional[str] = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_demand_trend(db, shop_id, product_id)


@router.get("/shops/{shop_id}/intelligence/health")
async def inventory_health(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_inventory_health(db, shop_id)


@router.get("/shops/{shop_id}/intelligence/insights")
async def inventory_insights(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return {"insights": await intel_svc.build_insights(db, shop_id)}


@router.get("/shops/{shop_id}/intelligence/timeline")
async def inventory_timeline(shop_id: str, limit: int = 200, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_inventory_timeline(db, shop_id, limit=limit)


@router.get("/shops/{shop_id}/products/{product_id}/movements")
async def product_movement_history(
    shop_id: str, product_id: str, limit: int = 100,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    return await intel_svc.get_product_movement_history(db, shop_id, product_id, limit=limit)
