"""Smart Shop Assistant v2 — Reservation System + Inventory Intelligence

Purely additive:
  - new columns on shop_assistant_shops (reservation_timeout_minutes,
    low_stock_threshold, next_queue_number)
  - new columns on shop_assistant_products (low_stock_threshold, reorder_quantity)
  - new columns on shop_assistant_reservations (queue_number, expires_at,
    is_partial, confirmed_at, ready_at, completed_at, cancelled_at,
    cancelled_reason) — product_id/quantity DROPPED, moved into the new
    shop_assistant_reservation_items table
  - new tables: shop_assistant_reservation_items, shop_assistant_waitlist_entries,
    shop_assistant_product_movements

Revision ID: 033_shop_assistant_v2
Revises: 032_shop_assistant
Create Date: 2026-07-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '033_shop_assistant_v2'
down_revision = '032_shop_assistant'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── shop_assistant_shops: new configurable fields ───────────────────────
    op.add_column('shop_assistant_shops', sa.Column('reservation_timeout_minutes', sa.Integer, nullable=False, server_default='30'))
    op.add_column('shop_assistant_shops', sa.Column('low_stock_threshold', sa.Integer, nullable=False, server_default='5'))
    op.add_column('shop_assistant_shops', sa.Column('next_queue_number', sa.Integer, nullable=False, server_default='1'))

    # ── shop_assistant_products: per-product AI Inventory Intelligence overrides
    op.add_column('shop_assistant_products', sa.Column('low_stock_threshold', sa.Integer, nullable=True))
    op.add_column('shop_assistant_products', sa.Column('reorder_quantity', sa.Integer, nullable=True))

    # ── shop_assistant_reservations: becomes a header row ───────────────────
    op.add_column('shop_assistant_reservations', sa.Column('queue_number', sa.Integer, nullable=False, server_default='0'))
    op.add_column('shop_assistant_reservations', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shop_assistant_reservations', sa.Column('is_partial', sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column('shop_assistant_reservations', sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shop_assistant_reservations', sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shop_assistant_reservations', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shop_assistant_reservations', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('shop_assistant_reservations', sa.Column('cancelled_reason', sa.String(40), nullable=True))

    op.create_index('ix_shop_assistant_reservations_shop_queue', 'shop_assistant_reservations', ['shop_id', 'queue_number'])
    op.create_index('ix_shop_assistant_reservations_expiry', 'shop_assistant_reservations', ['status', 'expires_at'])

    # ── shop_assistant_reservation_items (new) ──────────────────────────────
    op.create_table(
        'shop_assistant_reservation_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('reservation_id', sa.String(36), sa.ForeignKey('shop_assistant_reservations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('shop_assistant_products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requested_quantity', sa.Integer, nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shop_assistant_reservation_items_reservation', 'shop_assistant_reservation_items', ['reservation_id'])
    op.create_index('ix_shop_assistant_reservation_items_product', 'shop_assistant_reservation_items', ['product_id'])

    # ── Backfill: migrate each existing reservation's product_id/quantity
    # into a single ShopReservationItem row, so no in-flight reservation is
    # silently dropped by the schema change.
    conn = op.get_bind()
    existing = conn.execute(sa.text(
        "SELECT id, product_id, quantity, created_at FROM shop_assistant_reservations"
    )).fetchall()
    for row in existing:
        conn.execute(
            sa.text(
                "INSERT INTO shop_assistant_reservation_items "
                "(id, reservation_id, product_id, requested_quantity, quantity, created_at) "
                "VALUES (:id, :reservation_id, :product_id, :qty, :qty, :created_at)"
            ),
            {
                "id": __import__("uuid").uuid4().hex,
                "reservation_id": row.id,
                "product_id": row.product_id,
                "qty": row.quantity,
                "created_at": row.created_at,
            },
        )

    # Assign gapless per-shop queue numbers to pre-existing reservations in
    # creation order, and bump each shop's next_queue_number accordingly.
    shops = conn.execute(sa.text("SELECT id FROM shop_assistant_shops")).fetchall()
    for shop in shops:
        rows = conn.execute(
            sa.text(
                "SELECT id FROM shop_assistant_reservations WHERE shop_id = :sid ORDER BY created_at"
            ),
            {"sid": shop.id},
        ).fetchall()
        n = 1
        for r in rows:
            conn.execute(
                sa.text("UPDATE shop_assistant_reservations SET queue_number = :n WHERE id = :id"),
                {"n": n, "id": r.id},
            )
            n += 1
        conn.execute(
            sa.text("UPDATE shop_assistant_shops SET next_queue_number = :n WHERE id = :id"),
            {"n": n, "id": shop.id},
        )

    # Now that every row is migrated, drop the old single-product columns.
    with op.batch_alter_table('shop_assistant_reservations') as batch_op:
        batch_op.drop_column('product_id')
        batch_op.drop_column('quantity')

    # ── shop_assistant_waitlist_entries (new) ───────────────────────────────
    op.create_table(
        'shop_assistant_waitlist_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('shop_id', sa.String(36), sa.ForeignKey('shop_assistant_shops.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('shop_assistant_products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_name', sa.String(120), nullable=False),
        sa.Column('quantity_requested', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='waiting'),
        sa.Column('lookup_code', sa.String(64), nullable=False, unique=True),
        sa.Column('fulfilled_reservation_id', sa.String(36), sa.ForeignKey('shop_assistant_reservations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_shop_assistant_waitlist_shop_id', 'shop_assistant_waitlist_entries', ['shop_id'])
    op.create_index('ix_shop_assistant_waitlist_product_id', 'shop_assistant_waitlist_entries', ['product_id'])
    op.create_index('ix_shop_assistant_waitlist_lookup_code', 'shop_assistant_waitlist_entries', ['lookup_code'])
    op.create_index(
        'ix_shop_assistant_waitlist_shop_product_status', 'shop_assistant_waitlist_entries',
        ['shop_id', 'product_id', 'status'],
    )

    # ── shop_assistant_product_movements (new) ──────────────────────────────
    op.create_table(
        'shop_assistant_product_movements',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('shop_id', sa.String(36), sa.ForeignKey('shop_assistant_shops.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('shop_assistant_products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('quantity_delta', sa.Integer, nullable=False, server_default='0'),
        sa.Column('units', sa.Integer, nullable=False, server_default='0'),
        sa.Column('quantity_before', sa.Integer, nullable=False),
        sa.Column('quantity_after', sa.Integer, nullable=False),
        sa.Column('reference_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shop_assistant_movements_shop_id', 'shop_assistant_product_movements', ['shop_id'])
    op.create_index('ix_shop_assistant_movements_product_id', 'shop_assistant_product_movements', ['product_id'])
    op.create_index('ix_shop_assistant_movements_shop_created', 'shop_assistant_product_movements', ['shop_id', 'created_at'])
    op.create_index('ix_shop_assistant_movements_product_created', 'shop_assistant_product_movements', ['product_id', 'created_at'])
    op.create_index('ix_shop_assistant_movements_created_at', 'shop_assistant_product_movements', ['created_at'])

    # Seed one "created" movement per pre-existing product so historic
    # inventory has a non-empty ledger baseline (real data — its starting
    # quantity — not a fabricated figure).
    products = conn.execute(sa.text(
        "SELECT id, shop_id, quantity_available, created_at FROM shop_assistant_products"
    )).fetchall()
    for p in products:
        conn.execute(
            sa.text(
                "INSERT INTO shop_assistant_product_movements "
                "(id, shop_id, product_id, event_type, quantity_delta, units, quantity_before, quantity_after, created_at) "
                "VALUES (:id, :shop_id, :product_id, 'created', 0, 0, :qty, :qty, :created_at)"
            ),
            {
                "id": __import__("uuid").uuid4().hex,
                "shop_id": p.shop_id,
                "product_id": p.id,
                "qty": p.quantity_available,
                "created_at": p.created_at,
            },
        )


def downgrade() -> None:
    op.drop_table('shop_assistant_product_movements')
    op.drop_table('shop_assistant_waitlist_entries')

    with op.batch_alter_table('shop_assistant_reservations') as batch_op:
        batch_op.add_column(sa.Column('product_id', sa.String(36), nullable=True))
        batch_op.add_column(sa.Column('quantity', sa.Integer, nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT reservation_id, product_id, quantity FROM shop_assistant_reservation_items"
    )).fetchall()
    seen = set()
    for r in rows:
        if r.reservation_id in seen:
            continue  # downgrade path only keeps the first item — lossy by necessity
        seen.add(r.reservation_id)
        conn.execute(
            sa.text(
                "UPDATE shop_assistant_reservations SET product_id = :pid, quantity = :qty WHERE id = :id"
            ),
            {"pid": r.product_id, "qty": r.quantity, "id": r.reservation_id},
        )

    op.drop_table('shop_assistant_reservation_items')

    op.drop_index('ix_shop_assistant_reservations_expiry', table_name='shop_assistant_reservations')
    op.drop_index('ix_shop_assistant_reservations_shop_queue', table_name='shop_assistant_reservations')
    with op.batch_alter_table('shop_assistant_reservations') as batch_op:
        batch_op.drop_column('cancelled_reason')
        batch_op.drop_column('cancelled_at')
        batch_op.drop_column('completed_at')
        batch_op.drop_column('ready_at')
        batch_op.drop_column('confirmed_at')
        batch_op.drop_column('is_partial')
        batch_op.drop_column('expires_at')
        batch_op.drop_column('queue_number')

    op.drop_column('shop_assistant_products', 'reorder_quantity')
    op.drop_column('shop_assistant_products', 'low_stock_threshold')

    op.drop_column('shop_assistant_shops', 'next_queue_number')
    op.drop_column('shop_assistant_shops', 'low_stock_threshold')
    op.drop_column('shop_assistant_shops', 'reservation_timeout_minutes')
