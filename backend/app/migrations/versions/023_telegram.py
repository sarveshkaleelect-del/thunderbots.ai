"""Telegram Channel (Part 1) — connection + subscribers

Adds the two tables backing the Telegram Bot API integration:
telegram_channels (per-workflow bot connection + health/stats),
telegram_subscribers (chat_id -> Workflow Runtime session_id mapping,
only ever populated for chats that have started the bot conversation).
Purely additive — no existing table is touched.

Revision ID: 023_telegram
Revises: 022_campaign_audience
Create Date: 2026-07-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '023_telegram'
down_revision = '022_campaign_audience'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── telegram_channels ──────────────────────────────────────────────────────
    op.create_table(
        'telegram_channels',
        sa.Column('id',                        sa.String(36), primary_key=True),
        sa.Column('workflow_id',                sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id',                    sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('encrypted_bot_token',        sa.Text, nullable=False),
        sa.Column('encrypted_webhook_secret',   sa.Text, nullable=False),
        sa.Column('bot_id',                     sa.String(32)),
        sa.Column('bot_username',               sa.String(255)),
        sa.Column('bot_first_name',             sa.String(255)),
        sa.Column('status',                     sa.String(20), nullable=False, server_default='disconnected'),
        sa.Column('is_enabled',                 sa.Boolean, nullable=False, server_default='false'),
        sa.Column('health_status',              sa.String(20), nullable=False, server_default='unknown'),
        sa.Column('last_error',                 sa.Text),
        sa.Column('webhook_registered',         sa.Boolean, nullable=False, server_default='false'),
        sa.Column('last_sync_at',               sa.DateTime(timezone=True)),
        sa.Column('last_webhook_at',            sa.DateTime(timezone=True)),
        sa.Column('last_tested_at',             sa.DateTime(timezone=True)),
        sa.Column('messages_received_count',    sa.Integer, nullable=False, server_default='0'),
        sa.Column('messages_sent_count',        sa.Integer, nullable=False, server_default='0'),
        sa.Column('messages_failed_count',      sa.Integer, nullable=False, server_default='0'),
        sa.Column('settings',                   JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',                 sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',                 sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_telegram_channels_workflow_id', 'telegram_channels', ['workflow_id'], unique=True)
    op.create_index('ix_telegram_channels_user_id', 'telegram_channels', ['user_id'])
    op.create_index('ix_telegram_channels_status', 'telegram_channels', ['status'])

    # ── telegram_subscribers ───────────────────────────────────────────────────
    op.create_table(
        'telegram_subscribers',
        sa.Column('id',                sa.String(36), primary_key=True),
        sa.Column('channel_id',        sa.String(36),
                  sa.ForeignKey('telegram_channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',       sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chat_id',           sa.String(64), nullable=False),
        sa.Column('username',         sa.String(255)),
        sa.Column('first_name',       sa.String(255)),
        sa.Column('last_name',        sa.String(255)),
        sa.Column('session_id',       sa.String(128), nullable=False, unique=True),
        sa.Column('is_subscribed',    sa.Boolean, nullable=False, server_default='true'),
        sa.Column('message_count',    sa.Integer, nullable=False, server_default='0'),
        sa.Column('subscribed_at',    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('last_message_at',  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('created_at',       sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('channel_id', 'chat_id', name='uq_telegram_subscriber_channel_chat_id'),
    )
    op.create_index('ix_telegram_subscribers_channel_id', 'telegram_subscribers', ['channel_id'])
    op.create_index('ix_telegram_subscribers_workflow_id', 'telegram_subscribers', ['workflow_id'])
    op.create_index('ix_telegram_subscribers_session_id', 'telegram_subscribers', ['session_id'], unique=True)
    op.create_index('idx_tg_subscriber_channel_chat', 'telegram_subscribers', ['channel_id', 'chat_id'])


def downgrade() -> None:
    op.drop_table('telegram_subscribers')
    op.drop_table('telegram_channels')
