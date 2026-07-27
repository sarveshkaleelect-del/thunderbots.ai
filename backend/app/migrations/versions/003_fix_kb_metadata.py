"""Fix kb_documents reserved 'metadata' column name

ROOT CAUSE: 'metadata' is a reserved attribute name on every SQLAlchemy
Declarative model (it collides with Base.metadata, the MetaData registry).
The KBDocument ORM class declared a column literally named `metadata`,
which made mapper configuration for KBDocument raise
`InvalidRequestError: Attribute name 'metadata' is reserved when using
the Declarative API` — breaking every KB upload/list/delete/ingest code
path that touches the model. This migration renames the underlying
column to match the corrected ORM attribute `doc_metadata`.

Revision ID: 003_fix_kb_metadata
Revises: 002_deploy_branding
Create Date: 2026-07-02 00:00:00.000000
"""
from alembic import op

revision = '003_fix_kb_metadata'
down_revision = '002_deploy_branding'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('kb_documents', 'metadata', new_column_name='doc_metadata')


def downgrade() -> None:
    op.alter_column('kb_documents', 'doc_metadata', new_column_name='metadata')
