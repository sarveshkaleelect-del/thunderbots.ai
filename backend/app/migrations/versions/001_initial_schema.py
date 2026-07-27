"""Initial schema — all ThunderBots v3 tables

Revision ID: 001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id',          sa.String(36), primary_key=True),
        sa.Column('email',       sa.String(255), nullable=False, unique=True),
        sa.Column('name',        sa.String(255), nullable=False),
        sa.Column('password',    sa.String(255), nullable=False),
        sa.Column('preferences', JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # ── user_api_keys ──────────────────────────────────────────────────────────
    op.create_table(
        'user_api_keys',
        sa.Column('id',            sa.String(36), primary_key=True),
        sa.Column('user_id',       sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider',      sa.String(50), nullable=False),
        sa.Column('encrypted_key', sa.Text, nullable=False),
        sa.Column('label',         sa.String(100), nullable=False, server_default=''),
        sa.Column('is_valid',      sa.Boolean, nullable=False, server_default='false'),
        sa.Column('base_url',      sa.String(500)),
        sa.Column('created_at',    sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('last_tested',   sa.DateTime(timezone=True)),
    )
    op.create_index('ix_user_api_keys_user_id', 'user_api_keys', ['user_id'])

    # ── knowledge_bases ────────────────────────────────────────────────────────
    op.create_table(
        'knowledge_bases',
        sa.Column('id',               sa.String(36), primary_key=True),
        sa.Column('user_id',          sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',             sa.String(255), nullable=False),
        sa.Column('description',      sa.Text),
        sa.Column('chroma_collection',sa.String(255), nullable=False),
        sa.Column('document_count',   sa.Integer, nullable=False, server_default='0'),
        sa.Column('chunk_count',      sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at',       sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',       sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_knowledge_bases_user_id', 'knowledge_bases', ['user_id'])

    # ── kb_documents ───────────────────────────────────────────────────────────
    op.create_table(
        'kb_documents',
        sa.Column('id',                sa.String(36), primary_key=True),
        sa.Column('knowledge_base_id', sa.String(36),
                  sa.ForeignKey('knowledge_bases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename',          sa.String(500), nullable=False),
        sa.Column('file_type',         sa.String(20), nullable=False),
        sa.Column('file_size',         sa.Integer, nullable=False, server_default='0'),
        sa.Column('status',            sa.String(20), nullable=False, server_default='processing'),
        sa.Column('error_message',     sa.Text),
        sa.Column('chunk_count',       sa.Integer, nullable=False, server_default='0'),
        sa.Column('metadata',          JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',        sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('processed_at',      sa.DateTime(timezone=True)),
    )
    op.create_index('ix_kb_documents_knowledge_base_id', 'kb_documents', ['knowledge_base_id'])

    # ── workflows ──────────────────────────────────────────────────────────────
    op.create_table(
        'workflows',
        sa.Column('id',                 sa.String(36), primary_key=True),
        sa.Column('user_id',            sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',               sa.String(255), nullable=False),
        sa.Column('description',        sa.Text),
        sa.Column('status',             sa.String(20), nullable=False, server_default='draft'),
        sa.Column('canvas_state',       JSONB, nullable=False, server_default='{}'),
        sa.Column('nodes',              JSONB, nullable=False, server_default='[]'),
        sa.Column('edges',              JSONB, nullable=False, server_default='[]'),
        sa.Column('settings',           JSONB, nullable=False, server_default='{}'),
        sa.Column('knowledge_base_id',  sa.String(36),
                  sa.ForeignKey('knowledge_bases.id', ondelete='SET NULL')),
        sa.Column('created_at',         sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',         sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_workflows_user_id',   'workflows', ['user_id'])
    op.create_index('ix_workflows_status',    'workflows', ['status'])
    op.create_index('ix_workflows_created_at','workflows', ['created_at'])

    # ── workflow_history ───────────────────────────────────────────────────────
    op.create_table(
        'workflow_history',
        sa.Column('id',             sa.String(36), primary_key=True),
        sa.Column('workflow_id',    sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id',        sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_number', sa.Integer, nullable=False),
        sa.Column('label',          sa.String(255)),
        sa.Column('canvas_state',   JSONB, nullable=False),
        sa.Column('nodes',          JSONB, nullable=False),
        sa.Column('edges',          JSONB, nullable=False),
        sa.Column('settings',       JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',     sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        # FIX: unique constraint prevents race condition duplicate versions
        sa.UniqueConstraint('workflow_id', 'version_number', name='uq_workflow_version'),
    )
    op.create_index('ix_workflow_history_workflow_id', 'workflow_history', ['workflow_id'])
    op.create_index('idx_wh_workflow_version', 'workflow_history',
                    ['workflow_id', 'version_number'])

    # ── deployments ────────────────────────────────────────────────────────────
    op.create_table(
        'deployments',
        sa.Column('id',               sa.String(36), primary_key=True),
        sa.Column('workflow_id',      sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('user_id',          sa.String(36),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('slug',             sa.String(100), nullable=False, unique=True),
        sa.Column('is_active',        sa.Boolean, nullable=False, server_default='true'),
        sa.Column('deployed_nodes',   JSONB, nullable=False, server_default='[]'),
        sa.Column('deployed_edges',   JSONB, nullable=False, server_default='[]'),
        sa.Column('deployed_settings',JSONB, nullable=False, server_default='{}'),
        sa.Column('embed_config',     JSONB, nullable=False, server_default='{}'),
        sa.Column('deployed_at',      sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('updated_at',       sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index('ix_deployments_workflow_id', 'deployments', ['workflow_id'])
    op.create_index('ix_deployments_slug',        'deployments', ['slug'])


def downgrade() -> None:
    op.drop_table('deployments')
    op.drop_table('workflow_history')
    op.drop_table('workflows')
    op.drop_table('kb_documents')
    op.drop_table('knowledge_bases')
    op.drop_table('user_api_keys')
    op.drop_table('users')
