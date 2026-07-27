"""Active Sessions & Device Management — user_sessions table

NEW (Active Sessions & Device Management — Phase 2): purely additive.

- user_sessions  one row per issued access token that has a "sid" claim
                 (every login/register/google/2fa-verify going forward).
                 Tracks device/browser/OS, IP, best-effort location, and
                 activity/expiry/revocation timestamps. Backs remote logout:
                 core/auth.get_current_user rejects a token whose session
                 row is revoked or expired even though the JWT signature is
                 still valid. Tokens minted before this migration have no
                 "sid" claim at all and are unaffected — they keep working
                 until they naturally expire.

Revision ID: 012_active_sessions
Revises: 011_email_verification
Create Date: 2026-07-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '012_active_sessions'
down_revision = '011_email_verification'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_name', sa.String(length=150), nullable=False, server_default='Unknown device'),
        sa.Column('browser', sa.String(length=50), nullable=False, server_default='Unknown'),
        sa.Column('os', sa.String(length=50), nullable=False, server_default='Unknown'),
        sa.Column('device_type', sa.String(length=20), nullable=False, server_default='unknown'),
        sa.Column('user_agent', sa.Text(), nullable=False, server_default=''),
        sa.Column('ip_address', sa.String(length=64), nullable=False, server_default='unknown'),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.String(length=50), nullable=True),
    )
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])
    op.create_index('ix_user_sessions_user_active', 'user_sessions', ['user_id', 'revoked_at'])


def downgrade() -> None:
    op.drop_index('ix_user_sessions_user_active', table_name='user_sessions')
    op.drop_index('ix_user_sessions_user_id', table_name='user_sessions')
    op.drop_table('user_sessions')
