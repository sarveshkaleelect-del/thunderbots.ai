"""Personal Email AI Assistant — Part 2: send/schedule/automation (additive)

Adds Part 2 columns to the existing personal_email_messages and
personal_email_drafts tables (categorization, smart labels, spam/phishing
detection, unanswered-reply tracking, attachment metadata, send lifecycle,
approval workflow) and two new tables: personal_email_auto_reply_rules
(optional, opt-in auto-reply rules) and personal_email_ai_followups
(AI follow-up suggestions for sent-but-unanswered messages).

Purely additive — no Part 1 column, table, or constraint is altered or
dropped. Still fully independent from the customer-support Email Channel /
Email & Notification Service tables.

Revision ID: 021_personal_email_part2
Revises: 020_personal_email_assistant
Create Date: 2026-07-14 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '021_personal_email_part2'
down_revision = '020_personal_email_assistant'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── personal_email_messages — Part 2 columns ───────────────────────────
    op.add_column('personal_email_messages', sa.Column('category', sa.String(30)))
    op.add_column('personal_email_messages', sa.Column('labels', JSONB, nullable=False, server_default='[]'))
    op.add_column('personal_email_messages', sa.Column('is_spam', sa.Boolean, nullable=False, server_default='false'))
    op.add_column('personal_email_messages', sa.Column('spam_score', sa.Integer))
    op.add_column('personal_email_messages', sa.Column('spam_reason', sa.Text))
    op.add_column('personal_email_messages', sa.Column('is_answered', sa.Boolean, nullable=False, server_default='false'))
    op.add_column('personal_email_messages', sa.Column('answered_at', sa.DateTime(timezone=True)))
    op.add_column('personal_email_messages', sa.Column('last_reminder_at', sa.DateTime(timezone=True)))
    op.add_column('personal_email_messages', sa.Column('has_attachments', sa.Boolean, nullable=False, server_default='false'))
    op.add_column('personal_email_messages', sa.Column('attachments', JSONB, nullable=False, server_default='[]'))
    op.create_index('ix_personal_email_messages_category', 'personal_email_messages', ['category'])
    op.create_index('ix_personal_email_messages_is_spam', 'personal_email_messages', ['is_spam'])

    # ── personal_email_auto_reply_rules (new table, referenced by drafts) ──
    op.create_table(
        'personal_email_auto_reply_rules',
        sa.Column('id',                 sa.String(36), primary_key=True),
        sa.Column('account_id',         sa.String(36),
                  sa.ForeignKey('personal_email_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',               sa.String(255), nullable=False),
        sa.Column('is_active',          sa.Boolean, nullable=False, server_default='true'),
        sa.Column('sender_contains',    sa.String(255)),
        sa.Column('subject_contains',   sa.String(255)),
        sa.Column('category',           sa.String(30)),
        sa.Column('priority',           sa.String(10)),
        sa.Column('style',              sa.String(20), nullable=False, server_default='professional'),
        sa.Column('instructions',       sa.Text),
        sa.Column('require_approval',   sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_triggered_at',  sa.DateTime(timezone=True)),
        sa.Column('trigger_count',      sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at',         sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column('updated_at',         sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index('ix_personal_email_auto_reply_rules_account_id', 'personal_email_auto_reply_rules', ['account_id'])

    # ── personal_email_drafts — Part 2 columns ─────────────────────────────
    op.add_column('personal_email_drafts', sa.Column('send_status', sa.String(20), nullable=False, server_default='draft'))
    op.add_column('personal_email_drafts', sa.Column('approval_status', sa.String(20), nullable=False, server_default='not_required'))
    op.add_column('personal_email_drafts', sa.Column('scheduled_at', sa.DateTime(timezone=True)))
    op.add_column('personal_email_drafts', sa.Column('sent_at', sa.DateTime(timezone=True)))
    op.add_column('personal_email_drafts', sa.Column('sent_provider_message_id', sa.String(128)))
    op.add_column('personal_email_drafts', sa.Column('send_error', sa.Text))
    op.add_column('personal_email_drafts', sa.Column('to_addresses', sa.Text))
    op.add_column('personal_email_drafts', sa.Column('cc', sa.Text))
    op.add_column('personal_email_drafts', sa.Column('bcc', sa.Text))
    op.add_column('personal_email_drafts', sa.Column('subject_override', sa.Text))
    op.add_column('personal_email_drafts', sa.Column('attachments', JSONB, nullable=False, server_default='[]'))
    op.add_column('personal_email_drafts', sa.Column('created_by_rule_id', sa.String(36),
                  sa.ForeignKey('personal_email_auto_reply_rules.id', ondelete='SET NULL')))
    op.create_index('ix_personal_email_drafts_scheduled_at', 'personal_email_drafts', ['scheduled_at'])

    # ── personal_email_ai_followups (new table) ────────────────────────────
    op.create_table(
        'personal_email_ai_followups',
        sa.Column('id',                 sa.String(36), primary_key=True),
        sa.Column('message_id',         sa.String(36),
                  sa.ForeignKey('personal_email_messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('suggested_content',  sa.Text, nullable=False),
        sa.Column('status',             sa.String(20), nullable=False, server_default='suggested'),
        sa.Column('created_at',         sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index('ix_personal_email_ai_followups_message_id', 'personal_email_ai_followups', ['message_id'])


def downgrade() -> None:
    op.drop_table('personal_email_ai_followups')
    op.drop_index('ix_personal_email_drafts_scheduled_at', table_name='personal_email_drafts')
    for col in (
        'created_by_rule_id', 'attachments', 'subject_override', 'bcc', 'cc', 'to_addresses',
        'send_error', 'sent_provider_message_id', 'sent_at', 'scheduled_at', 'approval_status', 'send_status',
    ):
        op.drop_column('personal_email_drafts', col)

    op.drop_index('ix_personal_email_auto_reply_rules_account_id', table_name='personal_email_auto_reply_rules')
    op.drop_table('personal_email_auto_reply_rules')

    op.drop_index('ix_personal_email_messages_is_spam', table_name='personal_email_messages')
    op.drop_index('ix_personal_email_messages_category', table_name='personal_email_messages')
    for col in (
        'attachments', 'has_attachments', 'last_reminder_at', 'answered_at', 'is_answered',
        'spam_reason', 'spam_score', 'is_spam', 'labels', 'category',
    ):
        op.drop_column('personal_email_messages', col)
