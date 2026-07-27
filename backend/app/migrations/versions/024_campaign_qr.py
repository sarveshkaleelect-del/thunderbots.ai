"""Campaign QR Marketing System (Part 1) — QR acquisition codes

Adds campaign_qr_codes: one row per generated QR code, scoped to a
connected Telegram/WhatsApp channel (workflow) plus a business-facing
print placement (Shop Entrance, Cash Counter, ...). Purely additive — no
existing table is touched.

Revision ID: 024_campaign_qr
Revises: 023_telegram
Create Date: 2026-07-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '024_campaign_qr'
down_revision = '023_telegram'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'campaign_qr_codes',
        sa.Column('id',              sa.String(36), primary_key=True),
        sa.Column('user_id',         sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',     sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel',         sa.String(20), nullable=False),
        sa.Column('placement',       sa.String(30), nullable=False, server_default='other'),
        sa.Column('label',           sa.String(120)),
        sa.Column('short_code',      sa.String(64), nullable=False),
        sa.Column('scan_count',      sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_scanned_at', sa.DateTime(timezone=True)),
        sa.Column('is_active',       sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at',      sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',      sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('short_code', name='uq_campaign_qr_short_code'),
    )
    op.create_index('ix_campaign_qr_codes_user_id', 'campaign_qr_codes', ['user_id'])
    op.create_index('ix_campaign_qr_codes_workflow_id', 'campaign_qr_codes', ['workflow_id'])
    op.create_index('ix_campaign_qr_codes_channel', 'campaign_qr_codes', ['channel'])
    op.create_index('ix_campaign_qr_codes_short_code', 'campaign_qr_codes', ['short_code'], unique=True)
    op.create_index('ix_campaign_qr_codes_is_active', 'campaign_qr_codes', ['is_active'])
    op.create_index('idx_campaign_qr_user_workflow', 'campaign_qr_codes', ['user_id', 'workflow_id'])


def downgrade() -> None:
    op.drop_table('campaign_qr_codes')
