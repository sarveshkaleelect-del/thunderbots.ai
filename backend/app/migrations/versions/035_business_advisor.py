"""AI Business Advisor — margin support

Purely additive, no existing column touched:
  - shop_assistant_products.cost_price   (nullable) — per-product cost, used
    to compute real profit. NULL means "unknown", the Business Advisor then
    falls back to the shop's default_margin_percent.
  - shop_assistant_shops.default_margin_percent (nullable, default 30) —
    shop-wide fallback margin used for profit estimation when a product has
    no cost_price set.

Nothing here changes reservation/inventory logic; both columns are read
only by app/services/business_advisor_service.py.

Revision ID: 035_business_advisor
Revises: 034_shop_assistant_images
Create Date: 2026-07-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '035_business_advisor'
down_revision = '034_shop_assistant_images'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('shop_assistant_products', sa.Column('cost_price', sa.Numeric(10, 2), nullable=True))
    op.add_column(
        'shop_assistant_shops',
        sa.Column('default_margin_percent', sa.Numeric(5, 2), nullable=False, server_default='30'),
    )


def downgrade() -> None:
    op.drop_column('shop_assistant_shops', 'default_margin_percent')
    op.drop_column('shop_assistant_products', 'cost_price')
