"""AI Call Agent — Part 5: Standalone Voice Agents

Purely additive, following the exact convention 027/028/029 already
established for this feature. Nothing dropped, nothing renamed, no
existing row touched.

Adds:
  - voice_agents: an independent AI Call Agent persona — own provider/
    model/instructions/personality/voice — with zero dependency on
    workflows, deployments, or knowledge_bases.
  - voice_agent_kb_documents: each Voice Agent's own Knowledge Base
    (pdf | text | faq | url), completely separate storage from
    kb_documents (the chatbot Builder's Knowledge Base panel).
  - phone_numbers.voice_agent_id: nullable FK, additive alongside the
    existing workflow_id column (untouched) so a phone number can now be
    bound to a standalone Voice Agent instead of a chatbot Workflow.

Revision ID: 030_call_agent_voice_agents
Revises: 029_call_agent_part4
Create Date: 2026-07-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '030_call_agent_voice_agents'
down_revision = '029_call_agent_part4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'voice_agents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('ai_provider', sa.String(50), nullable=True),
        sa.Column('ai_model', sa.String(100), nullable=True),
        sa.Column('instructions', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('personality', sa.Text(), nullable=False, server_default=''),
        sa.Column('goals', sa.Text(), nullable=False, server_default=''),
        sa.Column('welcome_message', sa.Text(), nullable=False, server_default=''),
        sa.Column('fallback_message', sa.Text(), nullable=False, server_default=''),
        sa.Column('voice_provider', sa.String(30), nullable=True),
        sa.Column('voice_id', sa.String(100), nullable=True),
        sa.Column('language', sa.String(10), nullable=False, server_default='en-US'),
        sa.Column('speaking_speed', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('temperature', sa.Float(), nullable=False, server_default='0.7'),
        sa.Column('silence_timeout_seconds', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('interrupt_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('memory_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('conversation_history_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('embedding_provider', sa.String(50), nullable=True),
        sa.Column('embedding_model', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'voice_agent_kb_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('voice_agents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('kb_type', sa.String(10), nullable=False, server_default='text'),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('file_type', sa.String(20), nullable=False, server_default='txt'),
        sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(20), nullable=False, server_default='processing'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('faq_items', postgresql.JSONB(), nullable=True),
        sa.Column('source_url', sa.String(2000), nullable=True),
        sa.Column('doc_metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_voice_agent_kb_documents_agent_id', 'voice_agent_kb_documents', ['agent_id'])

    op.add_column(
        'phone_numbers',
        sa.Column('voice_agent_id', sa.String(36), sa.ForeignKey('voice_agents.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_phone_numbers_voice_agent_id', 'phone_numbers', ['voice_agent_id'])


def downgrade() -> None:
    op.drop_index('ix_phone_numbers_voice_agent_id', table_name='phone_numbers')
    op.drop_column('phone_numbers', 'voice_agent_id')
    op.drop_index('idx_voice_agent_kb_documents_agent_id', table_name='voice_agent_kb_documents')
    op.drop_table('voice_agent_kb_documents')
    op.drop_table('voice_agents')
