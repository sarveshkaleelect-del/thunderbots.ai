"""Team Workspace — teams, team_members, team_invites

NEW (Team Workspace): adds three new tables. Purely additive — no existing
table or column is touched, and Personal Workspace (workflows.user_id
ownership) is completely unaffected.

- teams          one row per team.
- team_members   membership + role (owner/admin/editor/viewer). A user may
                  have many rows here (one per team), unique per team.
- team_invites    pending email invitations, resolved into a team_members
                  row on acceptance.

Revision ID: 008_team_workspace
Revises: 007_admin_dashboard
Create Date: 2026-07-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '008_team_workspace'
down_revision = '007_admin_dashboard'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'teams',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_by', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_teams_created_by', 'teams', ['created_by'])
    op.create_index('ix_teams_created_at', 'teams', ['created_at'])

    op.create_table(
        'team_members',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('team_id', sa.String(length=36), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='viewer'),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_members_team_user'),
    )
    op.create_index('ix_team_members_team_id', 'team_members', ['team_id'])
    op.create_index('ix_team_members_user_id', 'team_members', ['user_id'])
    op.create_index('ix_team_members_user_team', 'team_members', ['user_id', 'team_id'])

    op.create_table(
        'team_invites',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('team_id', sa.String(length=36), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='viewer'),
        sa.Column('invited_by', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('token', sa.String(length=64), nullable=False, unique=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_team_invites_team_id', 'team_invites', ['team_id'])
    op.create_index('ix_team_invites_email', 'team_invites', ['email'])
    op.create_index('ix_team_invites_token', 'team_invites', ['token'], unique=True)
    op.create_index('ix_team_invites_status', 'team_invites', ['status'])
    op.create_index('ix_team_invites_email_status', 'team_invites', ['email', 'status'])


def downgrade() -> None:
    op.drop_table('team_invites')
    op.drop_table('team_members')
    op.drop_table('teams')
