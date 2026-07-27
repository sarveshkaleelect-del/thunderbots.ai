"""Analytics Dashboard — conversations & messages

Adds the two tables backing the Analytics Dashboard (overview cards,
time-series charts, conversation history/search/export, traffic sources,
top bots, KB usage, AI provider usage, performance/latency & errors).
Purely additive — no existing table is touched.

Revision ID: 004_analytics
Revises: 003_fix_kb_metadata
Create Date: 2026-07-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '004_analytics'
down_revision = '003_fix_kb_metadata'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── conversations ──────────────────────────────────────────────────────────
    op.create_table(
        'conversations',
        sa.Column('id',                     sa.String(36), primary_key=True),
        sa.Column('workflow_id',            sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id',               sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id',             sa.String(64), nullable=False, unique=True),
        sa.Column('source',                 sa.String(20), nullable=False, server_default='direct'),
        sa.Column('visitor_key',            sa.String(64)),
        sa.Column('is_returning',           sa.Boolean, nullable=False, server_default='false'),
        sa.Column('status',                 sa.String(20), nullable=False, server_default='active'),
        sa.Column('message_count',          sa.Integer, nullable=False, server_default='0'),
        sa.Column('user_message_count',     sa.Integer, nullable=False, server_default='0'),
        sa.Column('bot_message_count',      sa.Integer, nullable=False, server_default='0'),
        sa.Column('error_count',            sa.Integer, nullable=False, server_default='0'),
        sa.Column('first_response_time_ms', sa.Integer),
        sa.Column('avg_response_time_ms',   sa.Float),
        sa.Column('satisfaction_rating',    sa.Integer),
        sa.Column('meta',                   JSONB, nullable=False, server_default='{}'),
        sa.Column('started_at',             sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('last_activity_at',       sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('ended_at',               sa.DateTime(timezone=True)),
    )
    op.create_index('ix_conversations_workflow_id', 'conversations', ['workflow_id'])
    op.create_index('ix_conversations_owner_id', 'conversations', ['owner_id'])
    op.create_index('ix_conversations_session_id', 'conversations', ['session_id'], unique=True)
    op.create_index('ix_conversations_source', 'conversations', ['source'])
    op.create_index('ix_conversations_visitor_key', 'conversations', ['visitor_key'])
    op.create_index('ix_conversations_status', 'conversations', ['status'])
    op.create_index('ix_conversations_started_at', 'conversations', ['started_at'])
    op.create_index('idx_conv_owner_started', 'conversations', ['owner_id', 'started_at'])
    op.create_index('idx_conv_workflow_started', 'conversations', ['workflow_id', 'started_at'])
    op.create_index('idx_conv_owner_source', 'conversations', ['owner_id', 'source'])
    op.create_index('idx_conv_visitor', 'conversations', ['owner_id', 'visitor_key'])

    # ── messages ───────────────────────────────────────────────────────────────
    op.create_table(
        'messages',
        sa.Column('id',              sa.String(36), primary_key=True),
        sa.Column('conversation_id', sa.String(36),
                  sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',     sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id',        sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role',            sa.String(10), nullable=False),
        sa.Column('content',         sa.Text, nullable=False, server_default=''),
        sa.Column('node_id',         sa.String(100)),
        sa.Column('node_type',       sa.String(50)),
        sa.Column('provider',        sa.String(30)),
        sa.Column('model',           sa.String(100)),
        sa.Column('latency_ms',      sa.Integer),
        sa.Column('is_error',        sa.Boolean, nullable=False, server_default='false'),
        sa.Column('error_message',   sa.Text),
        sa.Column('citations',       JSONB, nullable=False, server_default='[]'),
        sa.Column('created_at',      sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_workflow_id', 'messages', ['workflow_id'])
    op.create_index('ix_messages_owner_id', 'messages', ['owner_id'])
    op.create_index('ix_messages_node_type', 'messages', ['node_type'])
    op.create_index('ix_messages_provider', 'messages', ['provider'])
    op.create_index('ix_messages_is_error', 'messages', ['is_error'])
    op.create_index('ix_messages_created_at', 'messages', ['created_at'])
    op.create_index('idx_msg_owner_created', 'messages', ['owner_id', 'created_at'])
    op.create_index('idx_msg_workflow_created', 'messages', ['workflow_id', 'created_at'])
    op.create_index('idx_msg_owner_role', 'messages', ['owner_id', 'role'])
    op.create_index('idx_msg_owner_provider', 'messages', ['owner_id', 'provider'])
    op.create_index('idx_msg_owner_error', 'messages', ['owner_id', 'is_error'])


def downgrade() -> None:
    op.drop_table('messages')
    op.drop_table('conversations')
