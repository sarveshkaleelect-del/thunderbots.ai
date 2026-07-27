"""Smart Shop Assistant — initial tables (NEW, independent product)

Purely additive — four new tables, no existing table touched:
  - shop_assistant_shops
  - shop_assistant_products
  - shop_assistant_reservations
  - shop_assistant_sync_configs

Revision ID: 032_shop_assistant
Revises: 031_call_agent_voice_agent_status
Create Date: 2026-07-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '032_shop_assistant'
down_revision = '031_call_agent_voice_agent_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'shop_assistant_shops',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('public_slug', sa.String(32), nullable=False, unique=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shop_assistant_shops_owner_id', 'shop_assistant_shops', ['owner_id'])
    op.create_index('ix_shop_assistant_shops_public_slug', 'shop_assistant_shops', ['public_slug'])

    op.create_table(
        'shop_assistant_products',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('shop_id', sa.String(36), sa.ForeignKey('shop_assistant_shops.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('quantity_available', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shop_assistant_products_shop_id', 'shop_assistant_products', ['shop_id'])
    op.create_index('ix_shop_assistant_products_shop_name', 'shop_assistant_products', ['shop_id', 'name'])

    op.create_table(
        'shop_assistant_reservations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('shop_id', sa.String(36), sa.ForeignKey('shop_assistant_shops.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('shop_assistant_products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_name', sa.String(120), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('queue_token', sa.String(20), nullable=False),
        sa.Column('lookup_code', sa.String(64), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shop_assistant_reservations_shop_id', 'shop_assistant_reservations', ['shop_id'])
    op.create_index('ix_shop_assistant_reservations_product_id', 'shop_assistant_reservations', ['product_id'])
    op.create_index('ix_shop_assistant_reservations_shop_status', 'shop_assistant_reservations', ['shop_id', 'status'])
    op.create_index('ix_shop_assistant_reservations_lookup_code', 'shop_assistant_reservations', ['lookup_code'])

    op.create_table(
        'shop_assistant_sync_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('shop_id', sa.String(36), sa.ForeignKey('shop_assistant_shops.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('spreadsheet_id', sa.String(200), nullable=False),
        sa.Column('worksheet_name', sa.String(200), nullable=False, server_default='Inventory'),
        sa.Column('encrypted_credentials', sa.Text, nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shop_assistant_sync_configs_shop_id', 'shop_assistant_sync_configs', ['shop_id'])


def downgrade() -> None:
    op.drop_table('shop_assistant_sync_configs')
    op.drop_table('shop_assistant_reservations')
    op.drop_table('shop_assistant_products')
    op.drop_table('shop_assistant_shops')
