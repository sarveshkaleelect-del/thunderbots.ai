"""WhatsApp Channel — connection, contacts/sessions, media assets

Adds the three tables backing the WhatsApp Cloud API integration:
whatsapp_channels (per-workflow connection + health/stats),
whatsapp_contacts (wa_id -> Workflow Runtime session_id mapping),
whatsapp_media_assets (downloaded incoming media metadata).
Purely additive — no existing table is touched.

Revision ID: 005_whatsapp
Revises: 004_analytics
Create Date: 2026-07-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '005_whatsapp'
down_revision = '004_analytics'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── whatsapp_channels ──────────────────────────────────────────────────────
    op.create_table(
        'whatsapp_channels',
        sa.Column('id',                       sa.String(36), primary_key=True),
        sa.Column('workflow_id',               sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id',                   sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone_number_id',           sa.String(64), nullable=False),
        sa.Column('business_account_id',       sa.String(64), nullable=False),
        sa.Column('encrypted_access_token',    sa.Text, nullable=False),
        sa.Column('encrypted_verify_token',    sa.Text, nullable=False),
        sa.Column('encrypted_app_secret',      sa.Text),
        sa.Column('display_phone_number',      sa.String(32)),
        sa.Column('verified_name',             sa.String(255)),
        sa.Column('quality_rating',            sa.String(32)),
        sa.Column('status',                    sa.String(20), nullable=False, server_default='disconnected'),
        sa.Column('is_enabled',                sa.Boolean, nullable=False, server_default='false'),
        sa.Column('health_status',             sa.String(20), nullable=False, server_default='unknown'),
        sa.Column('last_error',                sa.Text),
        sa.Column('last_sync_at',              sa.DateTime(timezone=True)),
        sa.Column('last_webhook_at',           sa.DateTime(timezone=True)),
        sa.Column('last_tested_at',            sa.DateTime(timezone=True)),
        sa.Column('messages_received_count',   sa.Integer, nullable=False, server_default='0'),
        sa.Column('messages_sent_count',       sa.Integer, nullable=False, server_default='0'),
        sa.Column('messages_failed_count',     sa.Integer, nullable=False, server_default='0'),
        sa.Column('settings',                  JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',                sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',                sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_whatsapp_channels_workflow_id', 'whatsapp_channels', ['workflow_id'], unique=True)
    op.create_index('ix_whatsapp_channels_user_id', 'whatsapp_channels', ['user_id'])
    op.create_index('ix_whatsapp_channels_status', 'whatsapp_channels', ['status'])

    # ── whatsapp_contacts ──────────────────────────────────────────────────────
    op.create_table(
        'whatsapp_contacts',
        sa.Column('id',                sa.String(36), primary_key=True),
        sa.Column('channel_id',        sa.String(36),
                  sa.ForeignKey('whatsapp_channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',       sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('wa_id',             sa.String(32), nullable=False),
        sa.Column('profile_name',      sa.String(255)),
        sa.Column('session_id',        sa.String(128), nullable=False, unique=True),
        sa.Column('message_count',     sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_message_at',   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('created_at',        sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('channel_id', 'wa_id', name='uq_whatsapp_contact_channel_wa_id'),
    )
    op.create_index('ix_whatsapp_contacts_channel_id', 'whatsapp_contacts', ['channel_id'])
    op.create_index('ix_whatsapp_contacts_workflow_id', 'whatsapp_contacts', ['workflow_id'])
    op.create_index('ix_whatsapp_contacts_session_id', 'whatsapp_contacts', ['session_id'], unique=True)
    op.create_index('idx_wa_contact_channel_wa', 'whatsapp_contacts', ['channel_id', 'wa_id'])

    # ── whatsapp_media_assets ──────────────────────────────────────────────────
    op.create_table(
        'whatsapp_media_assets',
        sa.Column('id',            sa.String(36), primary_key=True),
        sa.Column('channel_id',    sa.String(36),
                  sa.ForeignKey('whatsapp_channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',   sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('wa_media_id',   sa.String(128), nullable=False),
        sa.Column('media_type',    sa.String(20), nullable=False),
        sa.Column('mime_type',     sa.String(100)),
        sa.Column('filename',      sa.String(500)),
        sa.Column('file_path',     sa.String(1000), nullable=False),
        sa.Column('file_size',     sa.Integer),
        sa.Column('sha256',        sa.String(64)),
        sa.Column('created_at',    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_whatsapp_media_assets_channel_id', 'whatsapp_media_assets', ['channel_id'])
    op.create_index('ix_whatsapp_media_assets_workflow_id', 'whatsapp_media_assets', ['workflow_id'])
    op.create_index('ix_whatsapp_media_assets_wa_media_id', 'whatsapp_media_assets', ['wa_media_id'])


def downgrade() -> None:
    op.drop_table('whatsapp_media_assets')
    op.drop_table('whatsapp_contacts')
    op.drop_table('whatsapp_channels')
