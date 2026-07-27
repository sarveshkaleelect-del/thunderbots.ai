"""
ThunderBots Smart Shop Assistant — Models (independent product)

v2 (Reservation System + Inventory Intelligence): purely additive on top of
the original four tables — no existing column removed, no type changed.

Seven tables now:

- Shop                     One row per physical shop. Adds
                           `reservation_timeout_minutes` (configurable
                           per-shop expiry timeout) and `low_stock_threshold`
                           (shop-wide default alert threshold) and
                           `next_queue_number` (atomically incremented under
                           a row lock to hand out gapless, ordered queue
                           numbers — see shop_assistant_service.create_reservation).
- ShopProduct              Live inventory. Adds optional per-product
                           `low_stock_threshold` / `reorder_quantity`
                           overrides (fall back to the shop defaults when
                           NULL).
- ShopReservation          Now a HEADER row only — one customer's booking,
                           which may cover several products (see
                           ShopReservationItem). `quantity_available` is
                           decremented/restored per-item, never on this row.
                           `queue_number` is a monotonically increasing,
                           per-shop, gapless integer handed out at creation
                           (customer-facing `queue_token` is unchanged — a
                           short human string). `expires_at` drives the
                           automatic-expiry background loop
                           (shop_assistant_reservation_scheduler.py) and is
                           cleared the moment staff confirm the reservation.
- ShopReservationItem      One product line within a reservation.
                           `requested_quantity` is what the customer asked
                           for; `quantity` is what was actually held (can be
                           less than requested — a Partial Reservation).
- ShopWaitlistEntry        A customer waiting on a currently-insufficient
                           product. Processed automatically the moment stock
                           increases for that product (cancel, expiry,
                           manual restock, or a sync/import) — see
                           shop_assistant_service.process_waitlist_for_product.
- ShopProductMovement      Append-only ledger — the single source of truth
                           every AI Inventory Intelligence figure is computed
                           from (never a fabricated number). Every quantity
                           change of any kind writes exactly one row here.
- ShopProductImage         NEW — Product Image Support. One row per uploaded,
                           server-compressed image; purely display data, read
                           by no reservation/inventory logic.
- ShopSyncConfig           Unchanged — optional per-shop Google Sheets link.
"""
import uuid
import secrets
import string
from datetime import datetime, timezone
from sqlalchemy import (
    String, Text, DateTime, ForeignKey, Integer, Boolean, Index, UniqueConstraint, Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# Full reservation lifecycle. "pending" is the only status the automatic
# expiry timer ever acts on; every later status (confirmed/ready) has had
# its expires_at cleared and is no longer at risk of silently expiring.
RESERVATION_STATUSES = ("pending", "confirmed", "ready", "completed", "cancelled", "expired")
ACTIVE_RESERVATION_STATUSES = ("pending", "confirmed", "ready")
TERMINAL_RESERVATION_STATUSES = ("completed", "cancelled", "expired")

WAITLIST_STATUSES = ("waiting", "notified", "fulfilled", "cancelled")

# Every distinct reason `quantity_available` (or a waitlist/queue counter) can
# change, recorded verbatim on ShopProductMovement.event_type. Kept as a
# closed set so inventory-intelligence aggregation never has to guess what a
# free-text reason means.
MOVEMENT_EVENT_TYPES = (
    "created",                 # product row first added, or import created it
    "adjusted",                 # owner manually edited quantity_available
    "import",                   # Excel import set an absolute quantity
    "sync_pull",                 # Google Sheets pull set an absolute quantity
    "reservation_hold",          # stock decremented at reservation creation
    "reservation_edit_hold",     # stock decremented after a pre-confirmation edit
    "reservation_cancelled",     # stock restored — reservation cancelled
    "reservation_expired",       # stock restored — reservation auto-expired
    "reservation_completed",     # sale finalized; NO stock delta (already held)
    "waitlist_fulfilled",        # stock decremented — auto-reserved from waitlist
)

_SLUG_ALPHABET = string.ascii_lowercase + string.digits


def _gen_uuid() -> str:
    return str(uuid.uuid4())


def _gen_public_slug() -> str:
    # 10 chars from a 36-symbol alphabet ~= 51 bits of entropy — unguessable
    # enough for a QR-only, no-auth public link, short enough to type by hand
    # if a customer's QR scan fails and they type it in manually.
    return "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(10))


def _gen_queue_token() -> str:
    # Human-readable reservation token shown on-screen and at the counter,
    # e.g. "A-4821". Not a security boundary (see ShopReservation.lookup_code
    # for that) — just a friendly short reference.
    return f"{secrets.choice(string.ascii_uppercase)}-{secrets.randbelow(9000) + 1000}"


def _gen_lookup_code() -> str:
    # Unguessable per-reservation code used by the customer's own status-check
    # request (GET /public/shops/{slug}/reservations/{lookup_code}) so one
    # customer can never poll another customer's reservation by guessing a
    # small sequential id.
    return secrets.token_urlsafe(16)


class Shop(Base):
    __tablename__ = "shop_assistant_shops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Unguessable public identifier — embedded in the QR code and the
    # customer-facing URL. Never expose `id` or `owner_id` to the public API.
    public_slug: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, default=_gen_public_slug, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # NEW — Smart Reservation System: how many minutes a "pending" hold
    # survives before the background loop auto-expires it and restores
    # stock. Configurable per shop (a butcher counter and a furniture
    # showroom want very different holds); 0 disables auto-expiry entirely.
    reservation_timeout_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    # NEW — AI Inventory Intelligence: shop-wide default "low stock" alert
    # threshold. Any ShopProduct.low_stock_threshold overrides this per item.
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # NEW — atomically incremented (under a row lock on this Shop row) each
    # time a reservation is created, handing out gapless per-shop queue
    # numbers even under concurrent requests.
    next_queue_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # NEW — AI Business Advisor: shop-wide fallback profit margin (%), used
    # to estimate profit for any product that has no explicit cost_price set.
    default_margin_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=30, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    products: Mapped[list["ShopProduct"]] = relationship(
        back_populates="shop", cascade="all, delete-orphan", passive_deletes=True
    )
    reservations: Mapped[list["ShopReservation"]] = relationship(
        back_populates="shop", cascade="all, delete-orphan", passive_deletes=True
    )
    waitlist_entries: Mapped[list["ShopWaitlistEntry"]] = relationship(
        back_populates="shop", cascade="all, delete-orphan", passive_deletes=True
    )
    movements: Mapped[list["ShopProductMovement"]] = relationship(
        back_populates="shop", cascade="all, delete-orphan", passive_deletes=True
    )
    sync_config: Mapped["ShopSyncConfig | None"] = relationship(
        back_populates="shop", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )


class ShopProduct(Base):
    __tablename__ = "shop_assistant_products"
    __table_args__ = (
        # Case-insensitive uniqueness is enforced in the service layer (SQLite/
        # Postgres COLLATE differences), this index just keeps lookups fast.
        Index("ix_shop_assistant_products_shop_name", "shop_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_shops.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # NEW — Product Image Support: purely for display on customer-facing
    # cards/search results. Optional, additive, no reservation/inventory
    # logic reads either of these — a shop that never sets them sees no
    # behavior change anywhere.
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # NEW — AI Business Advisor: optional per-product cost. NULL means "use
    # the shop's default_margin_percent" to estimate profit instead.
    cost_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # The single source of truth for "how many are left to sell". Every
    # reservation and every Excel/Sheets sync ultimately reads/writes this.
    quantity_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # NEW — AI Inventory Intelligence overrides. NULL means "use the shop
    # default" (see Shop.low_stock_threshold / inventory_intelligence_service
    # default reorder heuristic).
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reorder_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    shop: Mapped["Shop"] = relationship(back_populates="products")
    items: Mapped[list["ShopReservationItem"]] = relationship(
        back_populates="product", passive_deletes=True
    )
    waitlist_entries: Mapped[list["ShopWaitlistEntry"]] = relationship(
        back_populates="product", passive_deletes=True
    )
    movements: Mapped[list["ShopProductMovement"]] = relationship(
        back_populates="product", passive_deletes=True
    )
    images: Mapped[list["ShopProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True,
        order_by="(ShopProductImage.is_cover.desc(), ShopProductImage.sort_order)",
    )


class ShopReservation(Base):
    """Header row for one customer's booking. May cover multiple products —
    see ShopReservationItem. Never holds a product_id/quantity itself."""
    __tablename__ = "shop_assistant_reservations"
    __table_args__ = (
        Index("ix_shop_assistant_reservations_shop_status", "shop_id", "status"),
        Index("ix_shop_assistant_reservations_shop_queue", "shop_id", "queue_number"),
        Index("ix_shop_assistant_reservations_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_shops.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    queue_token: Mapped[str] = mapped_column(String(20), nullable=False, default=_gen_queue_token)
    # Gapless, per-shop, monotonically increasing — see Shop.next_queue_number.
    queue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Opaque, unguessable — lets the *customer's own device* poll/display the
    # status of just this one reservation without any login and without
    # being able to enumerate anyone else's.
    lookup_code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=_gen_lookup_code, index=True
    )

    # NEW — Smart Reservation System
    # Cleared (set NULL) the moment status leaves "pending" — confirmed /
    # ready reservations are never auto-expired.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    shop: Mapped["Shop"] = relationship(back_populates="reservations")
    items: Mapped[list["ShopReservationItem"]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ShopReservationItem.created_at",
    )


class ShopReservationItem(Base):
    """One product line within a ShopReservation. `quantity` is what was
    actually held against ShopProduct.quantity_available — it can be less
    than `requested_quantity` when the reservation is Partial."""
    __tablename__ = "shop_assistant_reservation_items"
    __table_args__ = (
        Index("ix_shop_assistant_reservation_items_reservation", "reservation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    reservation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_reservations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    reservation: Mapped["ShopReservation"] = relationship(back_populates="items")
    product: Mapped["ShopProduct"] = relationship(back_populates="items")


class ShopProductImage(Base):
    """NEW — Product Image Support. One row per uploaded image (a product
    may have several — see `is_cover` / `sort_order` for gallery ordering).

    Every upload is transcoded server-side (see shop_product_image_service)
    into two WEBP variants stored on disk under UPLOAD_DIR/shop_products/
    {shop_id}/{product_id}/ and served back from the existing /uploads
    static mount, exactly like branding assets already are:
      - `url`            display-size image (max ~1400px edge), used on the
                          product detail / lightbox / reservation pages.
      - `thumbnail_url`   small compressed variant (~400px edge), used on
                          search results and product cards for fast loading.
    Nothing here is read by any reservation/inventory logic — purely
    additive, display-only data."""
    __tablename__ = "shop_assistant_product_images"
    __table_args__ = (
        Index("ix_shop_assistant_product_images_product", "product_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_shops.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    product: Mapped["ShopProduct"] = relationship(back_populates="images")


class ShopWaitlistEntry(Base):
    """A customer waiting on a currently out-of-stock (or insufficiently
    stocked) product. See shop_assistant_service.process_waitlist_for_product
    for the auto-notify-and-reserve logic that fires whenever stock for this
    product increases."""
    __tablename__ = "shop_assistant_waitlist_entries"
    __table_args__ = (
        Index("ix_shop_assistant_waitlist_shop_product_status", "shop_id", "product_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_shops.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting")
    lookup_code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=_gen_lookup_code, index=True
    )
    # Populated once auto-fulfilled — the reservation created on the
    # customer's behalf when enough stock became available.
    fulfilled_reservation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("shop_assistant_reservations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    shop: Mapped["Shop"] = relationship(back_populates="waitlist_entries")
    product: Mapped["ShopProduct"] = relationship(back_populates="waitlist_entries")


class ShopProductMovement(Base):
    """Append-only inventory ledger. Every single quantity change of any
    kind — manual edit, import, sync, reservation hold/cancel/expire/
    complete, waitlist auto-fulfil — writes exactly one row here, and every
    AI Inventory Intelligence figure (fast/slow movers, dead stock, demand
    trend, best sellers, out-of-stock prediction, reorder suggestions) is
    computed ONLY from this table plus the current live ShopProduct row —
    never a fabricated or estimated number."""
    __tablename__ = "shop_assistant_product_movements"
    __table_args__ = (
        Index("ix_shop_assistant_movements_shop_created", "shop_id", "created_at"),
        Index("ix_shop_assistant_movements_product_created", "product_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_shops.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Actual delta applied to quantity_available at this event (0 for
    # "reservation_completed" — stock already left at hold time).
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Magnitude relevant to demand/sales analytics (e.g. the reservation
    # quantity) — always positive, independent of quantity_delta's sign.
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    shop: Mapped["Shop"] = relationship(back_populates="movements")
    product: Mapped["ShopProduct"] = relationship(back_populates="movements")


class ShopSyncConfig(Base):
    """
    Optional per-shop Google Sheets connection. Absence of a row (the normal
    default state) means Google Sheets sync is simply off — Excel
    import/export always works with zero configuration since it needs no
    external credentials.
    """
    __tablename__ = "shop_assistant_sync_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_gen_uuid)
    shop_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shop_assistant_shops.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    spreadsheet_id: Mapped[str] = mapped_column(String(200), nullable=False)
    worksheet_name: Mapped[str] = mapped_column(String(200), nullable=False, default="Inventory")
    # Fernet-encrypted service-account JSON — see shop_sync_service.encrypt_credentials.
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    shop: Mapped["Shop"] = relationship(back_populates="sync_config")
