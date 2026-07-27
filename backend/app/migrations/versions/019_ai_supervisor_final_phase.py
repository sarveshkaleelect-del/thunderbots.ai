"""AI Supervisor final phase — supervisor_conversation_meta & supervisor_activity_log

NEW (AI Supervisor module, final phase): purely additive.

- supervisor_conversation_meta   1:1 overlay per conversation: tags,
                                  priority (low|medium|high|critical), pinned
                                  state, and supervisor close/reopen state.
- supervisor_activity_log        append-only audit trail of every
                                  supervisor action (assign/reassign,
                                  close/reopen, tag/priority changes,
                                  pin/unpin, export, bulk actions).

Does not alter conversations, messages, live_agent_handoffs, workflows, or
any other existing table/column.

Revision ID: 019_ai_supervisor_final_phase
Revises: 018_ai_supervisor_controls
Create Date: 2026-07-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '019_ai_supervisor_final_phase'
down_revision = '018_ai_supervisor_controls'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'supervisor_conversation_meta',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('conversation_id', sa.String(length=36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=False, server_default='medium'),
        sa.Column('tags', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('pinned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reopened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('conversation_id', name='uq_supervisor_meta_conversation'),
    )
    op.create_index('ix_supervisor_conversation_meta_conversation_id', 'supervisor_conversation_meta', ['conversation_id'])
    op.create_index('ix_supervisor_conversation_meta_owner_id', 'supervisor_conversation_meta', ['owner_id'])
    op.create_index('idx_supervisor_meta_owner_priority', 'supervisor_conversation_meta', ['owner_id', 'priority'])
    op.create_index('idx_supervisor_meta_owner_pinned', 'supervisor_conversation_meta', ['owner_id', 'is_pinned'])

    op.create_table(
        'supervisor_activity_log',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('conversation_id', sa.String(length=36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('owner_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('detail', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_supervisor_activity_log_conversation_id', 'supervisor_activity_log', ['conversation_id'])
    op.create_index('ix_supervisor_activity_log_owner_id', 'supervisor_activity_log', ['owner_id'])
    op.create_index('ix_supervisor_activity_log_actor_id', 'supervisor_activity_log', ['actor_id'])
    op.create_index('ix_supervisor_activity_log_event_type', 'supervisor_activity_log', ['event_type'])
    op.create_index('ix_supervisor_activity_log_created_at', 'supervisor_activity_log', ['created_at'])
    op.create_index('idx_supervisor_activity_conv_created', 'supervisor_activity_log', ['conversation_id', 'created_at'])
    op.create_index('idx_supervisor_activity_owner_created', 'supervisor_activity_log', ['owner_id', 'created_at'])
    op.create_index('idx_supervisor_activity_owner_actor', 'supervisor_activity_log', ['owner_id', 'actor_id'])


def downgrade() -> None:
    op.drop_index('idx_supervisor_activity_owner_actor', table_name='supervisor_activity_log')
    op.drop_index('idx_supervisor_activity_owner_created', table_name='supervisor_activity_log')
    op.drop_index('idx_supervisor_activity_conv_created', table_name='supervisor_activity_log')
    op.drop_index('ix_supervisor_activity_log_created_at', table_name='supervisor_activity_log')
    op.drop_index('ix_supervisor_activity_log_event_type', table_name='supervisor_activity_log')
    op.drop_index('ix_supervisor_activity_log_actor_id', table_name='supervisor_activity_log')
    op.drop_index('ix_supervisor_activity_log_owner_id', table_name='supervisor_activity_log')
    op.drop_index('ix_supervisor_activity_log_conversation_id', table_name='supervisor_activity_log')
    op.drop_table('supervisor_activity_log')

    op.drop_index('idx_supervisor_meta_owner_pinned', table_name='supervisor_conversation_meta')
    op.drop_index('idx_supervisor_meta_owner_priority', table_name='supervisor_conversation_meta')
    op.drop_index('ix_supervisor_conversation_meta_owner_id', table_name='supervisor_conversation_meta')
    op.drop_index('ix_supervisor_conversation_meta_conversation_id', table_name='supervisor_conversation_meta')
    op.drop_table('supervisor_conversation_meta')
