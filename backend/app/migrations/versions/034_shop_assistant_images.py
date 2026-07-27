"""Smart Shop Assistant — Product Image Support

Purely additive:
  - two new nullable columns on shop_assistant_products (brand, price) —
    display-only, read by no reservation/inventory logic
  - new table shop_assistant_product_images

Revision ID: 034_shop_assistant_images
Revises: 033_shop_assistant_v2
Create Date: 2026-07-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '034_shop_assistant_images'
down_revision = '033_shop_assistant_v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('shop_assistant_products', sa.Column('brand', sa.String(120), nullable=True))
    op.add_column('shop_assistant_products', sa.Column('price', sa.Numeric(10, 2), nullable=True))

    op.create_table(
        'shop_assistant_product_images',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('shop_id', sa.String(36), sa.ForeignKey('shop_assistant_shops.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('shop_assistant_products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('thumbnail_url', sa.String(500), nullable=False),
        sa.Column('width', sa.Integer, nullable=False, server_default='0'),
        sa.Column('height', sa.Integer, nullable=False, server_default='0'),
        sa.Column('file_size', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_cover', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shop_assistant_product_images_shop_id', 'shop_assistant_product_images', ['shop_id'])
    op.create_index('ix_shop_assistant_product_images_product_id', 'shop_assistant_product_images', ['product_id'])
    op.create_index('ix_shop_assistant_product_images_product', 'shop_assistant_product_images', ['product_id', 'sort_order'])


def downgrade() -> None:
    op.drop_table('shop_assistant_product_images')
    op.drop_column('shop_assistant_products', 'price')
    op.drop_column('shop_assistant_products', 'brand')
