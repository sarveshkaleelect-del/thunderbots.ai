"""Google SSO & TOTP 2FA — auth columns on users

NEW (Google SSO & 2FA): purely additive to the `users` table.

- password         relaxed to nullable. A "Sign in with Google" account may
                    never set a local password. Existing rows are untouched
                    (they already have a non-null bcrypt hash); login() still
                    refuses to authenticate a row where password IS NULL.
- google_id         nullable, unique. Google's stable per-account subject
                    ("sub") claim, set the first time a user completes
                    Google Sign-In — either creating a new account or
                    linking an existing email/password one.
- totp_secret       nullable. Fernet-encrypted TOTP secret (same cipher as
                    user_api_keys.encrypted_key). Present while a 2FA setup
                    is pending confirmation, or once 2FA is enabled.
- totp_enabled      boolean, default false. Gates whether login/google
                    require a follow-up POST /auth/2fa/verify step.
- totp_backup_codes nullable. JSON array of SHA-256-hashed one-time backup
                    codes (raw codes are shown to the user exactly once).

Revision ID: 010_google_sso_2fa
Revises: 009_email_notifications
Create Date: 2026-07-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '010_google_sso_2fa'
down_revision = '009_email_notifications'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('users', 'password', existing_type=sa.String(length=255), nullable=True)

    op.add_column('users', sa.Column('google_id', sa.String(length=255), nullable=True))
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=True)

    op.add_column('users', sa.Column('totp_secret', sa.Text(), nullable=True))
    op.add_column(
        'users',
        sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('users', sa.Column('totp_backup_codes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'totp_backup_codes')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')

    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_column('users', 'google_id')

    # NOTE: cannot safely revert password to NOT NULL if any Google-only
    # (password IS NULL) accounts were created while this migration was
    # applied — doing so blindly would corrupt those rows. Downgrading past
    # this revision on a database with Google-only accounts requires a
    # manual data decision (delete or assign a password) first.
    op.alter_column('users', 'password', existing_type=sa.String(length=255), nullable=False)
