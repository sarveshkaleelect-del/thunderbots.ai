"""Email & Notification Service — password_reset_tokens, email_logs

NEW (Email & Notification Service): adds two new tables. Purely additive —
no existing table or column is touched.

- password_reset_tokens   one row per issued "forgot password" request.
                          Only a SHA-256 hash of the token is stored.
- email_logs              audit trail of every email send attempt (welcome,
                          password reset, team invite, usage/error
                          notifications), regardless of outcome.

Revision ID: 009_email_notifications
Revises: 008_team_workspace
Create Date: 2026-07-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '009_email_notifications'
down_revision = '008_team_workspace'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])
    op.create_index('ix_password_reset_tokens_token_hash', 'password_reset_tokens', ['token_hash'], unique=True)

    op.create_table(
        'email_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('email_type', sa.String(length=50), nullable=False),
        sa.Column('to_email', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default=''),
        sa.Column('error', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_email_logs_email_type', 'email_logs', ['email_type'])
    op.create_index('ix_email_logs_to_email', 'email_logs', ['to_email'])
    op.create_index('ix_email_logs_status', 'email_logs', ['status'])
    op.create_index('ix_email_logs_created_at', 'email_logs', ['created_at'])


def downgrade() -> None:
    op.drop_table('email_logs')
    op.drop_table('password_reset_tokens')
