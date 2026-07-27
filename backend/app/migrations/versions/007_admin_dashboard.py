"""Admin Dashboard — role + account-status flags on users

NEW (Admin Dashboard): adds two nullable-free, server-defaulted columns to
`users` so existing rows never end up NULL:

- is_admin  (default false) — gates every /api/v1/admin/* route.
- is_active (default true)  — an admin-triggered "disable" switch; existing
  accounts are unaffected (they all become is_active=true on upgrade).

Purely additive: no existing column, table, or relationship is touched.

Revision ID: 007_admin_dashboard
Revises: 006_kb_embedding_provider
Create Date: 2026-07-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '007_admin_dashboard'
down_revision = '006_kb_embedding_provider'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'is_admin')
