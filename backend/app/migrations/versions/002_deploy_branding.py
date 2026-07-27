"""Deploy branding, design, chat settings & widget config

Revision ID: 002_deploy_branding
Revises: 001_initial
Create Date: 2026-07-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '002_deploy_branding'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── workflows: draft deploy-experience state ──────────────────────────────
    op.add_column('workflows', sa.Column('branding', JSONB, nullable=False, server_default='{}'))
    op.add_column('workflows', sa.Column('design', JSONB, nullable=False, server_default='{}'))
    op.add_column('workflows', sa.Column('chat_settings', JSONB, nullable=False, server_default='{}'))
    op.add_column('workflows', sa.Column('widget_config', JSONB, nullable=False, server_default='{}'))

    # ── deployments: published snapshot ───────────────────────────────────────
    op.add_column('deployments', sa.Column('branding', JSONB, nullable=False, server_default='{}'))
    op.add_column('deployments', sa.Column('design', JSONB, nullable=False, server_default='{}'))
    op.add_column('deployments', sa.Column('chat_settings', JSONB, nullable=False, server_default='{}'))


def downgrade() -> None:
    op.drop_column('deployments', 'chat_settings')
    op.drop_column('deployments', 'design')
    op.drop_column('deployments', 'branding')

    op.drop_column('workflows', 'widget_config')
    op.drop_column('workflows', 'chat_settings')
    op.drop_column('workflows', 'design')
    op.drop_column('workflows', 'branding')
