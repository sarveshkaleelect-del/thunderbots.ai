"""Personal Email AI Assistant — accounts, messages, drafts, digests (Part 1)

Adds four tables backing the new, independent "Personal Email AI
Assistant" module (Gmail OAuth today, architected for Outlook later — see
services/gmail_service.py): personal_email_accounts (per-user connected
mailbox + encrypted OAuth credential), personal_email_messages (synced
inbox/sent/drafts messages plus AI summary/priority/sentiment/deadline/
tasks/action-required fields), personal_email_drafts (AI-generated reply
drafts per style), personal_email_digests (Daily AI Email Digest history).
Purely additive — no existing table is touched, and this module is fully
independent from the customer-support Email Channel / Email & Notification
Service tables.

Revision ID: 020_personal_email_assistant
Revises: 019_ai_supervisor_final_phase
Create Date: 2026-07-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '020_personal_email_assistant'
down_revision = '019_ai_supervisor_final_phase'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── personal_email_accounts ────────────────────────────────────────────
    op.create_table(
        'personal_email_accounts',
        sa.Column('id',                          sa.String(36), primary_key=True),
        sa.Column('user_id',                     sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider',                    sa.String(20), nullable=False, server_default='gmail'),
        sa.Column('email_address',               sa.String(255), nullable=False),
        sa.Column('display_name',                sa.String(255)),
        sa.Column('encrypted_access_token',      sa.Text, nullable=False),
        sa.Column('encrypted_refresh_token',     sa.Text),
        sa.Column('token_expires_at',            sa.DateTime(timezone=True)),
        sa.Column('scopes',                      sa.Text),
        sa.Column('status',                      sa.String(20), nullable=False, server_default='connected'),
        sa.Column('last_error',                  sa.Text),
        sa.Column('sync_enabled',                sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_sync_at',                sa.DateTime(timezone=True)),
        sa.Column('last_sync_status',            sa.String(20)),
        sa.Column('last_history_id',             sa.String(64)),
        sa.Column('digest_enabled',              sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_digest_at',               sa.DateTime(timezone=True)),
        sa.Column('settings',                    JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',                  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',                  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('user_id', 'provider', 'email_address', name='uq_personal_email_account_identity'),
    )
    op.create_index('ix_personal_email_accounts_user_id', 'personal_email_accounts', ['user_id'])
    op.create_index('ix_personal_email_accounts_provider', 'personal_email_accounts', ['provider'])

    # ── personal_email_messages ────────────────────────────────────────────
    op.create_table(
        'personal_email_messages',
        sa.Column('id',                    sa.String(36), primary_key=True),
        sa.Column('account_id',            sa.String(36),
                  sa.ForeignKey('personal_email_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_message_id',   sa.String(128), nullable=False),
        sa.Column('provider_thread_id',    sa.String(128)),
        sa.Column('folder',                sa.String(20), nullable=False),
        sa.Column('is_starred',            sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_read',               sa.Boolean, nullable=False, server_default='true'),
        sa.Column('sender_name',           sa.String(255)),
        sa.Column('sender_email',          sa.String(255)),
        sa.Column('to_addresses',          sa.Text),
        sa.Column('subject',               sa.Text),
        sa.Column('snippet',               sa.Text),
        sa.Column('body_text',             sa.Text),
        sa.Column('body_html',             sa.Text),
        sa.Column('received_at',           sa.DateTime(timezone=True)),
        sa.Column('ai_summary',            sa.Text),
        sa.Column('ai_priority',           sa.String(10)),
        sa.Column('ai_sentiment',          sa.String(10)),
        sa.Column('ai_deadline',           sa.String(64)),
        sa.Column('ai_tasks',              JSONB, nullable=False, server_default='[]'),
        sa.Column('ai_action_required',    sa.Boolean),
        sa.Column('ai_analyzed_at',        sa.DateTime(timezone=True)),
        sa.Column('ai_analysis_error',     sa.Text),
        sa.Column('created_at',            sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',            sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('account_id', 'provider_message_id', name='uq_personal_email_message_identity'),
    )
    op.create_index('ix_personal_email_messages_account_id', 'personal_email_messages', ['account_id'])
    op.create_index('ix_personal_email_messages_folder', 'personal_email_messages', ['folder'])
    op.create_index('ix_personal_email_messages_thread', 'personal_email_messages', ['provider_thread_id'])
    op.create_index('ix_personal_email_messages_sender', 'personal_email_messages', ['sender_email'])
    op.create_index('ix_personal_email_messages_received', 'personal_email_messages', ['received_at'])
    op.create_index('ix_personal_email_messages_account_folder', 'personal_email_messages', ['account_id', 'folder'])

    # ── personal_email_drafts ──────────────────────────────────────────────
    op.create_table(
        'personal_email_drafts',
        sa.Column('id',           sa.String(36), primary_key=True),
        sa.Column('message_id',   sa.String(36),
                  sa.ForeignKey('personal_email_messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('style',        sa.String(20), nullable=False),
        sa.Column('content',      sa.Text, nullable=False),
        sa.Column('is_edited',    sa.Boolean, nullable=False, server_default='false'),
        sa.Column('language',     sa.String(10), nullable=False, server_default='en'),
        sa.Column('created_at',   sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column('updated_at',   sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index('ix_personal_email_drafts_message_id', 'personal_email_drafts', ['message_id'])

    # ── personal_email_digests ─────────────────────────────────────────────
    op.create_table(
        'personal_email_digests',
        sa.Column('id',                      sa.String(36), primary_key=True),
        sa.Column('account_id',              sa.String(36),
                  sa.ForeignKey('personal_email_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('digest_date',             sa.String(10), nullable=False),
        sa.Column('summary',                 sa.Text, nullable=False),
        sa.Column('total_emails',            sa.Integer, nullable=False, server_default='0'),
        sa.Column('action_required_count',   sa.Integer, nullable=False, server_default='0'),
        sa.Column('high_priority_count',     sa.Integer, nullable=False, server_default='0'),
        sa.Column('highlights',              JSONB, nullable=False, server_default='[]'),
        sa.Column('created_at',              sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('account_id', 'digest_date', name='uq_personal_email_digest_day'),
    )
    op.create_index('ix_personal_email_digests_account_id', 'personal_email_digests', ['account_id'])


def downgrade() -> None:
    op.drop_table('personal_email_digests')
    op.drop_table('personal_email_drafts')
    op.drop_table('personal_email_messages')
    op.drop_table('personal_email_accounts')
