"""Audit Log & Activity Log — audit_logs table

NEW (v58 — Production-Ready Audit Log & Activity Log): purely additive.

- audit_logs  append-only record of security/administrative-relevant
              actions: auth events (login/logout/SSO/2FA/password reset/
              email verification), workflow/knowledge-base/team/api-key
              mutations, and admin operations. actor_id uses ON DELETE
              SET NULL so deleting a user never deletes their own audit
              trail. No downgrade-safe data is lost by adding this table;
              downgrade simply drops it.

Revision ID: 013_audit_log
Revises: 012_active_sessions
Create Date: 2026-07-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '013_audit_log'
down_revision = '012_active_sessions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('actor_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('actor_email', sa.String(length=255), nullable=True),
        sa.Column('actor_name', sa.String(length=255), nullable=True),
        sa.Column('actor_type', sa.String(length=20), nullable=False, server_default='user'),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=True),
        sa.Column('target_id', sa.String(length=36), nullable=True),
        sa.Column('target_label', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='success'),
        sa.Column('status_detail', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(length=36), nullable=False),
        sa.Column('audit_metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('ix_audit_logs_target_id', 'audit_logs', ['target_id'])
    op.create_index('ix_audit_logs_status', 'audit_logs', ['status'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_logs_action_created', 'audit_logs', ['action', 'created_at'])
    op.create_index('ix_audit_logs_actor_created', 'audit_logs', ['actor_id', 'created_at'])
    op.create_index('ix_audit_logs_resource_created', 'audit_logs', ['resource_type', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_resource_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_status', table_name='audit_logs')
    op.drop_index('ix_audit_logs_target_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_resource_type', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor_id', table_name='audit_logs')
    op.drop_table('audit_logs')
