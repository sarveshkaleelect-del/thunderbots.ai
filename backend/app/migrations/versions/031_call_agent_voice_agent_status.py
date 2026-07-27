"""AI Call Agent — Voice Agent Publish/Unpublish status

Purely additive, following the exact convention every prior migration in
this feature established. Nothing dropped, nothing renamed, no existing
row touched.

Adds:
  - voice_agents.status: nullable-safe string column ("draft" |
    "published"), server_default 'draft' so every existing row backfills
    safely. Independent of the existing is_enabled column (On/Off runtime
    toggle) — this is a separate lifecycle gate for the new Publish /
    Unpublish buttons.

Revision ID: 031_call_agent_voice_agent_status
Revises: 030_call_agent_voice_agents
Create Date: 2026-07-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '031_call_agent_voice_agent_status'
down_revision = '030_call_agent_voice_agents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'voice_agents',
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
    )


def downgrade() -> None:
    op.drop_column('voice_agents', 'status')
