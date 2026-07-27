"""Instagram DM Channel — accounts, contacts, message dedup log, webhook logs

Adds four tables backing the Instagram Direct Message integration:
instagram_accounts (per-workflow Meta OAuth connection + health/stats),
instagram_contacts (IGSID -> Workflow Runtime session_id mapping),
instagram_message_logs (mid-based duplicate-webhook-processing guard),
instagram_webhook_logs (connection & webhook delivery log for the Settings
UI). Purely additive — no existing table is touched.

Revision ID: 017_instagram
Revises: 016_live_agent
Create Date: 2026-07-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '017_instagram'
down_revision = '016_live_agent'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── instagram_accounts ──────────────────────────────────────────────────
    op.create_table(
        'instagram_accounts',
        sa.Column('id',                          sa.String(36), primary_key=True),
        sa.Column('workflow_id',                  sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id',                      sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('platform',                     sa.String(20), nullable=False, server_default='instagram'),
        sa.Column('ig_user_id',                   sa.String(64), nullable=False),
        sa.Column('ig_username',                  sa.String(255)),
        sa.Column('facebook_page_id',             sa.String(64), nullable=False),
        sa.Column('facebook_page_name',           sa.String(255)),
        sa.Column('encrypted_page_access_token',  sa.Text, nullable=False),
        sa.Column('encrypted_user_access_token',  sa.Text),
        sa.Column('token_expires_at',             sa.DateTime(timezone=True)),
        sa.Column('status',                       sa.String(20), nullable=False, server_default='disconnected'),
        sa.Column('is_enabled',                   sa.Boolean, nullable=False, server_default='false'),
        sa.Column('health_status',                sa.String(20), nullable=False, server_default='unknown'),
        sa.Column('last_error',                   sa.Text),
        sa.Column('last_sync_at',                 sa.DateTime(timezone=True)),
        sa.Column('last_webhook_at',               sa.DateTime(timezone=True)),
        sa.Column('last_tested_at',                sa.DateTime(timezone=True)),
        sa.Column('last_token_refresh_at',         sa.DateTime(timezone=True)),
        sa.Column('messages_received_count',       sa.Integer, nullable=False, server_default='0'),
        sa.Column('messages_sent_count',           sa.Integer, nullable=False, server_default='0'),
        sa.Column('messages_failed_count',         sa.Integer, nullable=False, server_default='0'),
        sa.Column('settings',                      JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',                    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',                    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_instagram_accounts_workflow_id', 'instagram_accounts', ['workflow_id'], unique=True)
    op.create_index('ix_instagram_accounts_user_id', 'instagram_accounts', ['user_id'])
    op.create_index('ix_instagram_accounts_platform', 'instagram_accounts', ['platform'])
    op.create_index('ix_instagram_accounts_status', 'instagram_accounts', ['status'])

    # ── instagram_contacts ───────────────────────────────────────────────────
    op.create_table(
        'instagram_contacts',
        sa.Column('id',                sa.String(36), primary_key=True),
        sa.Column('account_id',        sa.String(36),
                  sa.ForeignKey('instagram_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',       sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('igsid',             sa.String(64), nullable=False),
        sa.Column('username',          sa.String(255)),
        sa.Column('profile_pic_url',   sa.Text),
        sa.Column('session_id',        sa.String(128), nullable=False, unique=True),
        sa.Column('message_count',     sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_message_at',   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('created_at',        sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('account_id', 'igsid', name='uq_instagram_contact_account_igsid'),
    )
    op.create_index('ix_instagram_contacts_account_id', 'instagram_contacts', ['account_id'])
    op.create_index('ix_instagram_contacts_workflow_id', 'instagram_contacts', ['workflow_id'])
    op.create_index('ix_instagram_contacts_session_id', 'instagram_contacts', ['session_id'], unique=True)
    op.create_index('idx_ig_contact_account_igsid', 'instagram_contacts', ['account_id', 'igsid'])

    # ── instagram_message_logs (duplicate-webhook-processing guard) ─────────
    op.create_table(
        'instagram_message_logs',
        sa.Column('id',                sa.String(36), primary_key=True),
        sa.Column('account_id',        sa.String(36),
                  sa.ForeignKey('instagram_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',       sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('mid',               sa.String(128), nullable=False),
        sa.Column('igsid',             sa.String(64), nullable=False),
        sa.Column('direction',         sa.String(10), nullable=False, server_default='inbound'),
        sa.Column('message_type',      sa.String(20), nullable=False, server_default='text'),
        sa.Column('attachment_type',   sa.String(20)),
        sa.Column('attachment_url',    sa.Text),
        sa.Column('status',            sa.String(20), nullable=False, server_default='processed'),
        sa.Column('error',             sa.Text),
        sa.Column('created_at',        sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('account_id', 'mid', name='uq_instagram_message_account_mid'),
    )
    op.create_index('ix_instagram_message_logs_account_id', 'instagram_message_logs', ['account_id'])
    op.create_index('ix_instagram_message_logs_workflow_id', 'instagram_message_logs', ['workflow_id'])
    op.create_index('ix_instagram_message_logs_mid', 'instagram_message_logs', ['mid'])

    # ── instagram_webhook_logs ───────────────────────────────────────────────
    op.create_table(
        'instagram_webhook_logs',
        sa.Column('id',            sa.String(36), primary_key=True),
        sa.Column('account_id',    sa.String(36),
                  sa.ForeignKey('instagram_accounts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('event_type',    sa.String(30), nullable=False),
        sa.Column('level',         sa.String(10), nullable=False, server_default='info'),
        sa.Column('message',       sa.Text, nullable=False),
        sa.Column('detail',        JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_instagram_webhook_logs_account_id', 'instagram_webhook_logs', ['account_id'])
    op.create_index('ix_instagram_webhook_logs_event_type', 'instagram_webhook_logs', ['event_type'])
    op.create_index('ix_instagram_webhook_logs_created_at', 'instagram_webhook_logs', ['created_at'])


def downgrade() -> None:
    op.drop_table('instagram_webhook_logs')
    op.drop_table('instagram_message_logs')
    op.drop_table('instagram_contacts')
    op.drop_table('instagram_accounts')
