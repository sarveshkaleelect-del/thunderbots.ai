"""AI Campaign Manager — campaigns, campaign_history tables

NEW: Backs the Campaign Management System (frontend/app/campaigns).
Purely additive — no existing table is touched.

- campaigns          one row per marketing campaign (name, channel, message,
                      ai_prompt, schedule, status, analytics counters)
- campaign_history    append-only event log per campaign (created, updated,
                      duplicated, paused, resumed, ai_rewrite, ...)

Revision ID: 014_campaigns
Revises: 013_audit_log
Create Date: 2026-07-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '014_campaigns'
down_revision = '013_audit_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'campaigns',
        sa.Column('id',                sa.String(36), primary_key=True),
        sa.Column('user_id',           sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',              sa.String(255), nullable=False),
        sa.Column('channel',           sa.String(20), nullable=False, server_default='whatsapp'),
        sa.Column('template',          sa.String(50)),
        sa.Column('message',           sa.Text, nullable=False, server_default=''),
        sa.Column('ai_prompt',         sa.Text),
        sa.Column('schedule_type',     sa.String(10), nullable=False, server_default='now'),
        sa.Column('scheduled_at',      sa.DateTime(timezone=True)),
        sa.Column('status',            sa.String(20), nullable=False, server_default='draft'),
        sa.Column('sent_count',        sa.Integer, nullable=False, server_default='0'),
        sa.Column('delivered_count',   sa.Integer, nullable=False, server_default='0'),
        sa.Column('failed_count',      sa.Integer, nullable=False, server_default='0'),
        sa.Column('replied_count',     sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at',        sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at',        sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_campaigns_user_id', 'campaigns', ['user_id'])
    op.create_index('ix_campaigns_channel', 'campaigns', ['channel'])
    op.create_index('ix_campaigns_status', 'campaigns', ['status'])
    op.create_index('ix_campaigns_created_at', 'campaigns', ['created_at'])
    op.create_index('idx_campaigns_user_status', 'campaigns', ['user_id', 'status'])

    op.create_table(
        'campaign_history',
        sa.Column('id',             sa.String(36), primary_key=True),
        sa.Column('campaign_id',    sa.String(36),
                  sa.ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id',        sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type',     sa.String(50), nullable=False),
        sa.Column('detail',         JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',     sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_campaign_history_campaign_id', 'campaign_history', ['campaign_id'])
    op.create_index('ix_campaign_history_created_at', 'campaign_history', ['created_at'])


def downgrade() -> None:
    op.drop_table('campaign_history')
    op.drop_table('campaigns')
