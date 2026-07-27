"""AI Call Agent — Phone Number Connection & Verification (Voice AI Part 2)

Adds the two tables backing phone number setup/verification for the
upcoming AI Call Agent module: phone_numbers (per-user connected numbers +
verification/connection lifecycle) and phone_verification_codes (hashed,
single-use, expiring codes — never plaintext). Purely additive — no
existing table is touched, and nothing here binds a phone number to a
Workflow, the Runtime, or any call automation (out of scope for this part).

Revision ID: 027_call_agent_phone_numbers
Revises: 026_campaign_qr_scans
Create Date: 2026-07-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '027_call_agent_phone_numbers'
down_revision = '026_campaign_qr_scans'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── phone_numbers ──────────────────────────────────────────────────────
    op.create_table(
        'phone_numbers',
        sa.Column('id',                    sa.String(36), primary_key=True),
        sa.Column('user_id',                sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone_number',           sa.String(20), nullable=False),
        sa.Column('label',                  sa.String(100), nullable=False, server_default=''),
        sa.Column('status',                 sa.String(20), nullable=False, server_default='pending'),
        sa.Column('verification_method',    sa.String(10)),
        sa.Column('is_connected',           sa.Boolean, nullable=False, server_default='true'),
        sa.Column('is_enabled',             sa.Boolean, nullable=False, server_default='false'),
        sa.Column('last_verified_at',       sa.DateTime(timezone=True)),
        sa.Column('last_error',             sa.Text),
        sa.Column('disconnected_at',        sa.DateTime(timezone=True)),
        sa.Column('created_at',             sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',             sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint('user_id', 'phone_number', name='uq_phone_number_user_number'),
    )
    op.create_index('ix_phone_numbers_user_id', 'phone_numbers', ['user_id'])
    op.create_index('ix_phone_numbers_status', 'phone_numbers', ['status'])

    # ── phone_verification_codes ───────────────────────────────────────────
    op.create_table(
        'phone_verification_codes',
        sa.Column('id',                     sa.String(36), primary_key=True),
        sa.Column('phone_number_id',        sa.String(36),
                  sa.ForeignKey('phone_numbers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code_hash',              sa.Text, nullable=False),
        sa.Column('method',                 sa.String(10), nullable=False),
        sa.Column('expires_at',             sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at',                sa.DateTime(timezone=True)),
        sa.Column('attempts',               sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at',             sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('idx_phone_verification_phone_id', 'phone_verification_codes', ['phone_number_id'])


def downgrade() -> None:
    op.drop_index('idx_phone_verification_phone_id', table_name='phone_verification_codes')
    op.drop_table('phone_verification_codes')
    op.drop_index('ix_phone_numbers_status', table_name='phone_numbers')
    op.drop_index('ix_phone_numbers_user_id', table_name='phone_numbers')
    op.drop_table('phone_numbers')
