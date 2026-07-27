"""AI Call Agent — Call Sessions & Transcripts (Voice AI Part 3)

Adds the call automation layer that Part 2 (027_call_agent_phone_numbers)
explicitly left out: binds a phone_number to a Workflow, and adds the
`calls` / `call_transcript_entries` tables backing the call dashboard,
call history, transcripts, duration, and recording. Purely additive:
no column is dropped or renamed, no existing table's data is touched.

Revision ID: 028_call_agent_calls
Revises: 027_call_agent_phone_numbers
Create Date: 2026-07-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '028_call_agent_calls'
down_revision = '027_call_agent_phone_numbers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── phone_numbers: bind to a Workflow + per-number call settings ──────
    op.add_column(
        'phone_numbers',
        sa.Column('workflow_id', sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='SET NULL'), nullable=True),
    )
    op.add_column(
        'phone_numbers',
        sa.Column('call_settings', postgresql.JSONB, nullable=False, server_default='{}'),
    )
    op.create_index('ix_phone_numbers_workflow_id', 'phone_numbers', ['workflow_id'])

    # ── calls ───────────────────────────────────────────────────────────────
    op.create_table(
        'calls',
        sa.Column('id',                     sa.String(36), primary_key=True),
        sa.Column('user_id',                sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone_number_id',        sa.String(36),
                  sa.ForeignKey('phone_numbers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id',            sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='SET NULL'), nullable=True),
        sa.Column('direction',              sa.String(10), nullable=False),
        sa.Column('from_number',            sa.String(20), nullable=False),
        sa.Column('to_number',              sa.String(20), nullable=False),
        sa.Column('status',                 sa.String(20), nullable=False, server_default='queued'),
        sa.Column('end_reason',             sa.String(50)),
        sa.Column('error_message',          sa.Text),
        sa.Column('provider',               sa.String(20), nullable=False, server_default='twilio'),
        sa.Column('provider_call_sid',      sa.String(64)),
        sa.Column('session_id',             sa.String(36), nullable=False),
        sa.Column('ai_voice_provider',      sa.String(30)),
        sa.Column('ai_voice_id',            sa.String(100)),
        sa.Column('voice_speed',            sa.Float, nullable=False, server_default='1.0'),
        sa.Column('language',               sa.String(10), nullable=False, server_default='en-US'),
        sa.Column('recording_enabled',      sa.Boolean, nullable=False, server_default='false'),
        sa.Column('recording_url',          sa.Text),
        sa.Column('recording_provider_sid', sa.String(64)),
        sa.Column('interrupted_count',      sa.Integer, nullable=False, server_default='0'),
        sa.Column('fallback_triggered',     sa.Boolean, nullable=False, server_default='false'),
        sa.Column('handed_off_to_human',    sa.Boolean, nullable=False, server_default='false'),
        sa.Column('started_at',             sa.DateTime(timezone=True)),
        sa.Column('answered_at',            sa.DateTime(timezone=True)),
        sa.Column('ended_at',               sa.DateTime(timezone=True)),
        sa.Column('duration_seconds',       sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at',             sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',             sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('idx_calls_user_status', 'calls', ['user_id', 'status'])
    op.create_index('idx_calls_phone_number_id', 'calls', ['phone_number_id'])
    op.create_index('idx_calls_created_at', 'calls', ['created_at'])
    op.create_index('ix_calls_user_id', 'calls', ['user_id'])
    op.create_index('ix_calls_workflow_id', 'calls', ['workflow_id'])
    op.create_index('ix_calls_status', 'calls', ['status'])
    op.create_index('ix_calls_provider_call_sid', 'calls', ['provider_call_sid'])
    op.create_index('ix_calls_session_id', 'calls', ['session_id'])

    # ── call_transcript_entries ────────────────────────────────────────────
    op.create_table(
        'call_transcript_entries',
        sa.Column('id',            sa.String(36), primary_key=True),
        sa.Column('call_id',       sa.String(36),
                  sa.ForeignKey('calls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role',          sa.String(10), nullable=False),
        sa.Column('content',       sa.Text, nullable=False),
        sa.Column('sequence',      sa.Integer, nullable=False),
        sa.Column('was_interrupted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at',    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('idx_call_transcript_call_id', 'call_transcript_entries', ['call_id'])


def downgrade() -> None:
    op.drop_index('idx_call_transcript_call_id', table_name='call_transcript_entries')
    op.drop_table('call_transcript_entries')

    op.drop_index('ix_calls_session_id', table_name='calls')
    op.drop_index('ix_calls_provider_call_sid', table_name='calls')
    op.drop_index('ix_calls_status', table_name='calls')
    op.drop_index('ix_calls_workflow_id', table_name='calls')
    op.drop_index('ix_calls_user_id', table_name='calls')
    op.drop_index('idx_calls_created_at', table_name='calls')
    op.drop_index('idx_calls_phone_number_id', table_name='calls')
    op.drop_index('idx_calls_user_status', table_name='calls')
    op.drop_table('calls')

    op.drop_index('ix_phone_numbers_workflow_id', table_name='phone_numbers')
    op.drop_column('phone_numbers', 'call_settings')
    op.drop_column('phone_numbers', 'workflow_id')
