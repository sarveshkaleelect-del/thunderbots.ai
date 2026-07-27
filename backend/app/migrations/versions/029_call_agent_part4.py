"""AI Call Agent — Part 4: Text Knowledge Base, Handoff, Analytics, Summary

Purely additive, following the exact convention 027/028 already established
for this feature. Nothing dropped, nothing renamed, no existing row touched.

Adds:
  - knowledge_bases.kb_type ("file" | "text") — lets the frontend show a
    distinct "Text Knowledge Base" section; the underlying KBDocument/
    ChromaDB pipeline is unchanged and shared by both types (no duplicate
    ingestion/retrieval logic — see app/knowledge/pipeline.py).
  - kb_documents.source_type ("upload" | "pasted_text") and .raw_text (the
    original pasted text, kept so it can be edited/appended/replaced —
    uploaded files have no raw_text, only their derived chunks).
  - calls.summary — AI-generated recording/transcript summary.
  - call_transcript_entries.response_time_ms — latency from end-of-caller-
    speech to start-of-AI-speech for that turn, backing the "Average
    response time" analytics card.

Revision ID: 029_call_agent_part4
Revises: 028_call_agent_calls
Create Date: 2026-07-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '029_call_agent_part4'
down_revision = '028_call_agent_calls'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Text Knowledge Base support (shared KB/KBDocument infra) ──────────
    op.add_column(
        'knowledge_bases',
        sa.Column('kb_type', sa.String(10), nullable=False, server_default='file'),
    )
    op.add_column(
        'kb_documents',
        sa.Column('source_type', sa.String(20), nullable=False, server_default='upload'),
    )
    op.add_column(
        'kb_documents',
        sa.Column('raw_text', sa.Text, nullable=True),
    )

    # ── Call recording summary ─────────────────────────────────────────────
    op.add_column('calls', sa.Column('summary', sa.Text, nullable=True))

    # ── Per-turn response-time tracking (avg response time analytics) ─────
    op.add_column(
        'call_transcript_entries',
        sa.Column('response_time_ms', sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('call_transcript_entries', 'response_time_ms')
    op.drop_column('calls', 'summary')
    op.drop_column('kb_documents', 'raw_text')
    op.drop_column('kb_documents', 'source_type')
    op.drop_column('knowledge_bases', 'kb_type')
