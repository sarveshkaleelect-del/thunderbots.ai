"""Owner Assistant — Campaign QR Marketing System (Part 2)

Adds owner_assistant_links: maps a Telegram chat_id or WhatsApp wa_id to
the ThunderBots account that owns the bot it linked to, so the owner can
control campaigns conversationally from their own phone. Purely additive —
no existing table is touched.

Revision ID: 025_owner_assistant
Revises: 024_campaign_qr
Create Date: 2026-07-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '025_owner_assistant'
down_revision = '024_campaign_qr'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'owner_assistant_links',
        sa.Column('id',                sa.String(36), primary_key=True),
        sa.Column('user_id',           sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',       sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='SET NULL'), nullable=True),
        sa.Column('channel',           sa.String(20), nullable=False),
        sa.Column('external_chat_id',  sa.String(64), nullable=False),
        sa.Column('is_active',         sa.Boolean, nullable=False, server_default='true'),
        sa.Column('linked_at',         sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('last_used_at',      sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('channel', 'external_chat_id', name='uq_owner_assistant_channel_chat'),
    )
    op.create_index('ix_owner_assistant_links_user_id', 'owner_assistant_links', ['user_id'])
    op.create_index('ix_owner_assistant_links_workflow_id', 'owner_assistant_links', ['workflow_id'])
    op.create_index('ix_owner_assistant_links_channel', 'owner_assistant_links', ['channel'])
    op.create_index('ix_owner_assistant_links_external_chat_id', 'owner_assistant_links', ['external_chat_id'])
    op.create_index('ix_owner_assistant_links_is_active', 'owner_assistant_links', ['is_active'])
    op.create_index('idx_owner_assistant_user', 'owner_assistant_links', ['user_id', 'is_active'])


def downgrade() -> None:
    op.drop_table('owner_assistant_links')
