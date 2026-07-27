"""Track which embedding provider/model produced a KB's stored vectors

ROOT CAUSE: app/knowledge/pipeline.py's generate_embeddings() always called
OpenAI, regardless of which AI provider the user actually had configured.
Any user running exclusively on Gemini (no OpenAI key saved anywhere) had
every single Knowledge Base upload fail at the embedding stage with
"No OpenAI API key available for embeddings" — the document was left in
status='error' forever, and retrieval (which calls the same embedding
function to embed the search query) failed identically. This is fixed by
having generate_embeddings() auto-detect the embedding-capable provider
(openai or gemini) the user has actually configured.

Because different embedding providers/models produce vectors of different
dimensionality (OpenAI text-embedding-3-small = 1536-dim, Gemini
gemini-embedding-001 = 3072-dim) and a single Chroma collection can only
ever hold one fixed dimensionality, the provider/model actually used for a
KB's first successful ingest must be pinned and reused for every later
ingest/retrieval against that same KB — otherwise a later change to the
user's default provider would corrupt retrieval for existing KBs (mismatched
or meaningless nearest-neighbor results, or a hard Chroma dimension error).
These two nullable columns store that pin. NULL means "no document has been
successfully embedded into this KB yet" — the pipeline resolves and records
a provider on the next successful ingest.

Revision ID: 006_kb_embedding_provider
Revises: 005_whatsapp
Create Date: 2026-07-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '006_kb_embedding_provider'
down_revision = '005_whatsapp'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('knowledge_bases', sa.Column('embedding_provider', sa.String(50), nullable=True))
    op.add_column('knowledge_bases', sa.Column('embedding_model', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('knowledge_bases', 'embedding_model')
    op.drop_column('knowledge_bases', 'embedding_provider')
