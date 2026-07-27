"""AI Broadcast & Auto-Reply Engine — campaign_recipients, campaigns.workflow_id

NEW: Backs the Campaign send/auto-reply pipeline. Purely additive:
- campaigns.workflow_id  nullable FK, added via ALTER TABLE (existing rows
                         get NULL — auto-resolved at send-time, see
                         services/campaign_dispatch_service.py)
- campaign_recipients    new table, one row per (campaign, contact): delivery
                         status, read status, retry bookkeeping, and
                         conversation outcome (replied/ai_resolved/escalated/
                         human_takeover)

Revision ID: 015_campaign_broadcast
Revises: 014_campaigns
Create Date: 2026-07-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '015_campaign_broadcast'
down_revision = '014_campaigns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('campaigns', sa.Column('workflow_id', sa.String(36), nullable=True))
    op.create_foreign_key(
        'fk_campaigns_workflow_id', 'campaigns', 'workflows',
        ['workflow_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_campaigns_workflow_id', 'campaigns', ['workflow_id'])

    op.create_table(
        'campaign_recipients',
        sa.Column('id',                    sa.String(36), primary_key=True),
        sa.Column('campaign_id',           sa.String(36),
                  sa.ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id',               sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel',               sa.String(20), nullable=False),
        sa.Column('contact_identifier',    sa.String(255), nullable=False),
        sa.Column('contact_name',          sa.String(255)),
        sa.Column('session_id',            sa.String(128), nullable=False),
        sa.Column('workflow_id',           sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='SET NULL')),
        sa.Column('status',                sa.String(20), nullable=False, server_default='pending'),
        sa.Column('provider_message_id',   sa.String(128)),
        sa.Column('error_message',         sa.Text),
        sa.Column('retry_count',           sa.Integer, nullable=False, server_default='0'),
        sa.Column('max_retries',           sa.Integer, nullable=False, server_default='3'),
        sa.Column('opened',                sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('replied',               sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('ai_resolved',           sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('escalated',             sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('human_takeover',        sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('last_attempt_at',       sa.DateTime(timezone=True)),
        sa.Column('sent_at',               sa.DateTime(timezone=True)),
        sa.Column('delivered_at',          sa.DateTime(timezone=True)),
        sa.Column('read_at',               sa.DateTime(timezone=True)),
        sa.Column('replied_at',            sa.DateTime(timezone=True)),
        sa.Column('created_at',            sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at',            sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('campaign_id', 'contact_identifier', name='uq_campaign_recipient_contact'),
    )
    op.create_index('ix_campaign_recipients_campaign_id', 'campaign_recipients', ['campaign_id'])
    op.create_index('ix_campaign_recipients_user_id', 'campaign_recipients', ['user_id'])
    op.create_index('ix_campaign_recipients_workflow_id', 'campaign_recipients', ['workflow_id'])
    op.create_index('ix_campaign_recipients_session_id', 'campaign_recipients', ['session_id'])
    op.create_index('ix_campaign_recipients_status', 'campaign_recipients', ['status'])
    op.create_index('ix_campaign_recipients_provider_message_id', 'campaign_recipients', ['provider_message_id'])
    op.create_index(
        'idx_campaign_recipients_campaign_status', 'campaign_recipients', ['campaign_id', 'status'],
    )


def downgrade() -> None:
    op.drop_table('campaign_recipients')
    op.drop_index('ix_campaigns_workflow_id', table_name='campaigns')
    op.drop_constraint('fk_campaigns_workflow_id', 'campaigns', type_='foreignkey')
    op.drop_column('campaigns', 'workflow_id')
