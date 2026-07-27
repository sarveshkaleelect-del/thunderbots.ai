"""Interactive Tutorial System — progress persistence

Purely additive: one new table (tutorial_progress). No existing table,
column, or route is touched.

Revision ID: 036_tutorial_progress
Revises: 035_business_advisor
Create Date: 2026-07-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '036_tutorial_progress'
down_revision = '035_business_advisor'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'tutorial_progress' not in existing_tables:
        op.create_table(
            'tutorial_progress',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('feature_key', sa.String(100), nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='not_started'),
            sa.Column('current_step', sa.Integer, nullable=False, server_default='0'),
            sa.Column('completed_steps', sa.Integer, nullable=False, server_default='0'),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('user_id', 'feature_key', name='uq_tutorial_progress_user_feature'),
        )

    existing_indexes = {ix['name'] for ix in inspector.get_indexes('tutorial_progress')} \
        if 'tutorial_progress' in inspector.get_table_names() else set()

    if 'ix_tutorial_progress_user_id' not in existing_indexes:
        op.create_index('ix_tutorial_progress_user_id', 'tutorial_progress', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_tutorial_progress_user_id', table_name='tutorial_progress')
    op.drop_table('tutorial_progress')
