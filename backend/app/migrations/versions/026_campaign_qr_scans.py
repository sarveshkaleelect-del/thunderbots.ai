"""Campaign QR Marketing System (Part 3) — scan log for analytics

Adds campaign_qr_scans: one row per QR scan, backing Unique QR Scans and
Daily/Weekly/Monthly growth. Purely additive — no existing table is touched,
campaign_qr_codes.scan_count/last_scanned_at are untouched.

Revision ID: 026_campaign_qr_scans
Revises: 025_owner_assistant
Create Date: 2026-07-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '026_campaign_qr_scans'
down_revision = '025_owner_assistant'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'campaign_qr_scans',
        sa.Column('id',            sa.String(36), primary_key=True),
        sa.Column('qr_id',         sa.String(36),
                  sa.ForeignKey('campaign_qr_codes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id',       sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('visitor_hash',  sa.String(64), nullable=False),
        sa.Column('converted',    sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at',   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_campaign_qr_scans_qr_id', 'campaign_qr_scans', ['qr_id'])
    op.create_index('ix_campaign_qr_scans_user_id', 'campaign_qr_scans', ['user_id'])
    op.create_index('ix_campaign_qr_scans_visitor_hash', 'campaign_qr_scans', ['visitor_hash'])
    op.create_index('ix_campaign_qr_scans_created_at', 'campaign_qr_scans', ['created_at'])
    op.create_index('idx_campaign_qr_scans_qr_created', 'campaign_qr_scans', ['qr_id', 'created_at'])
    op.create_index('idx_campaign_qr_scans_visitor', 'campaign_qr_scans', ['qr_id', 'visitor_hash'])


def downgrade() -> None:
    op.drop_table('campaign_qr_scans')
