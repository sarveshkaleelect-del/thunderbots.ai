"""Human Handoff / Live Agent — agent_profiles & live_agent_handoffs tables

NEW (Live Agent module): purely additive.

- agent_profiles       presence/status (online|busy|offline) + concurrent-chat
                        load for a human agent within a bot owner's workspace.
- live_agent_handoffs  1:1 overlay on an existing `conversations` row
                        tracking queue/assignment state (ai|waiting|active|
                        closed). Chat content itself stays in the existing
                        `messages` table — no new message-storage table.

Revision ID: 016_live_agent
Revises: 015_campaign_broadcast
Create Date: 2026-07-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '016_live_agent'
down_revision = '015_campaign_broadcast'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_profiles',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('owner_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='offline'),
        sa.Column('max_concurrent_chats', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('active_chat_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('owner_id', 'user_id', name='uq_agent_profile_owner_user'),
    )
    op.create_index('ix_agent_profiles_owner_id', 'agent_profiles', ['owner_id'])
    op.create_index('ix_agent_profiles_user_id', 'agent_profiles', ['user_id'])
    op.create_index('ix_agent_profiles_status', 'agent_profiles', ['status'])
    op.create_index('idx_agent_owner_status', 'agent_profiles', ['owner_id', 'status'])

    op.create_table(
        'live_agent_handoffs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('conversation_id', sa.String(length=36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('workflow_id', sa.String(length=36), sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ai'),
        sa.Column('channel', sa.String(length=20), nullable=False, server_default='web_chat'),
        sa.Column('requested_by', sa.String(length=20), nullable=True),
        sa.Column('handoff_reason', sa.Text(), nullable=True),
        sa.Column('assigned_agent_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('visitor_label', sa.String(length=255), nullable=True),
        sa.Column('last_message_preview', sa.Text(), nullable=True),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_live_agent_handoffs_conversation_id', 'live_agent_handoffs', ['conversation_id'])
    op.create_index('ix_live_agent_handoffs_workflow_id', 'live_agent_handoffs', ['workflow_id'])
    op.create_index('ix_live_agent_handoffs_owner_id', 'live_agent_handoffs', ['owner_id'])
    op.create_index('ix_live_agent_handoffs_session_id', 'live_agent_handoffs', ['session_id'])
    op.create_index('ix_live_agent_handoffs_status', 'live_agent_handoffs', ['status'])
    op.create_index('ix_live_agent_handoffs_channel', 'live_agent_handoffs', ['channel'])
    op.create_index('ix_live_agent_handoffs_assigned_agent_id', 'live_agent_handoffs', ['assigned_agent_id'])
    op.create_index('idx_handoff_owner_status', 'live_agent_handoffs', ['owner_id', 'status'])
    op.create_index('idx_handoff_owner_agent', 'live_agent_handoffs', ['owner_id', 'assigned_agent_id'])
    op.create_index('idx_handoff_owner_updated', 'live_agent_handoffs', ['owner_id', 'last_message_at'])


def downgrade() -> None:
    op.drop_index('idx_handoff_owner_updated', table_name='live_agent_handoffs')
    op.drop_index('idx_handoff_owner_agent', table_name='live_agent_handoffs')
    op.drop_index('idx_handoff_owner_status', table_name='live_agent_handoffs')
    op.drop_index('ix_live_agent_handoffs_assigned_agent_id', table_name='live_agent_handoffs')
    op.drop_index('ix_live_agent_handoffs_channel', table_name='live_agent_handoffs')
    op.drop_index('ix_live_agent_handoffs_status', table_name='live_agent_handoffs')
    op.drop_index('ix_live_agent_handoffs_session_id', table_name='live_agent_handoffs')
    op.drop_index('ix_live_agent_handoffs_owner_id', table_name='live_agent_handoffs')
    op.drop_index('ix_live_agent_handoffs_workflow_id', table_name='live_agent_handoffs')
    op.drop_index('ix_live_agent_handoffs_conversation_id', table_name='live_agent_handoffs')
    op.drop_table('live_agent_handoffs')

    op.drop_index('idx_agent_owner_status', table_name='agent_profiles')
    op.drop_index('ix_agent_profiles_status', table_name='agent_profiles')
    op.drop_index('ix_agent_profiles_user_id', table_name='agent_profiles')
    op.drop_index('ix_agent_profiles_owner_id', table_name='agent_profiles')
    op.drop_table('agent_profiles')
