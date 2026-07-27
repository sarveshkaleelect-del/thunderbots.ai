"""AI Supervisor interaction controls — supervisor_notes & message_reviews

NEW (AI Supervisor module, part 2): purely additive.

- supervisor_notes   internal, team-only note attached to a conversation.
- message_reviews    Correct/Incorrect QA verdict on one AI (bot) reply,
                     one verdict per message (upsert on message_id).

Pause/Resume and Take-over/Return-to-AI reuse the existing
`live_agent_handoffs.status` column (no schema change — "paused" is simply
a new value alongside the existing ai|waiting|active|closed, which was
never DB-constrained to a fixed enum).

Revision ID: 018_ai_supervisor_controls
Revises: 017_instagram
Create Date: 2026-07-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '018_ai_supervisor_controls'
down_revision = '017_instagram'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'supervisor_notes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('conversation_id', sa.String(length=36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('author_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_supervisor_notes_conversation_id', 'supervisor_notes', ['conversation_id'])
    op.create_index('ix_supervisor_notes_owner_id', 'supervisor_notes', ['owner_id'])
    op.create_index('ix_supervisor_notes_author_id', 'supervisor_notes', ['author_id'])
    op.create_index('idx_supervisor_note_conv_created', 'supervisor_notes', ['conversation_id', 'created_at'])
    op.create_index('idx_supervisor_note_owner', 'supervisor_notes', ['owner_id'])

    op.create_table(
        'message_reviews',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('message_id', sa.String(length=36), sa.ForeignKey('messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', sa.String(length=36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reviewer_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('verdict', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('message_id', name='uq_message_review_message'),
    )
    op.create_index('ix_message_reviews_message_id', 'message_reviews', ['message_id'])
    op.create_index('ix_message_reviews_conversation_id', 'message_reviews', ['conversation_id'])
    op.create_index('ix_message_reviews_owner_id', 'message_reviews', ['owner_id'])
    op.create_index('ix_message_reviews_reviewer_id', 'message_reviews', ['reviewer_id'])
    op.create_index('idx_message_review_conv', 'message_reviews', ['conversation_id'])
    op.create_index('idx_message_review_owner', 'message_reviews', ['owner_id'])


def downgrade() -> None:
    op.drop_index('idx_message_review_owner', table_name='message_reviews')
    op.drop_index('idx_message_review_conv', table_name='message_reviews')
    op.drop_index('ix_message_reviews_reviewer_id', table_name='message_reviews')
    op.drop_index('ix_message_reviews_owner_id', table_name='message_reviews')
    op.drop_index('ix_message_reviews_conversation_id', table_name='message_reviews')
    op.drop_index('ix_message_reviews_message_id', table_name='message_reviews')
    op.drop_table('message_reviews')

    op.drop_index('idx_supervisor_note_owner', table_name='supervisor_notes')
    op.drop_index('idx_supervisor_note_conv_created', table_name='supervisor_notes')
    op.drop_index('ix_supervisor_notes_author_id', table_name='supervisor_notes')
    op.drop_index('ix_supervisor_notes_owner_id', table_name='supervisor_notes')
    op.drop_index('ix_supervisor_notes_conversation_id', table_name='supervisor_notes')
    op.drop_table('supervisor_notes')
