"""Email verification — is_email_verified column + email_verification_tokens table

NEW (Email Verification): purely additive.

- users.is_email_verified  boolean, NOT NULL. server_default TRUE so every
                            EXISTING account is backfilled as verified (no
                            current user is retroactively affected). The
                            SQLAlchemy model default is False, so every NEW
                            row created after this migration (register,
                            Google signup) starts unverified until the
                            signup-verification email link is completed.
                            Nothing currently gates on this flag.
- email_verification_tokens  one row per issued verification link. Same
                            shape as password_reset_tokens: only a SHA-256
                            hash of the raw token is stored, single-use
                            (used_at), time-boxed (expires_at).

Revision ID: 011_email_verification
Revises: 010_google_sso_2fa
Create Date: 2026-07-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '011_email_verification'
down_revision = '010_google_sso_2fa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_email_verified', sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_email_verification_tokens_token_hash', 'email_verification_tokens', ['token_hash'], unique=True
    )


def downgrade() -> None:
    op.drop_index('ix_email_verification_tokens_token_hash', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_user_id', table_name='email_verification_tokens')
    op.drop_table('email_verification_tokens')

    op.drop_column('users', 'is_email_verified')
