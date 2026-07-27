"""
ThunderBots Knowledge Base Models
FIX v4: ondelete CASCADE + passive_deletes on all relationships.

ROOT CAUSE FIX (v7): KBDocument declared a mapped column literally named
`metadata`. SQLAlchemy's Declarative API reserves the `metadata` attribute
name on every mapped class for the class-level `MetaData` registry object
(`Base.metadata`) — declaring a column attribute with that exact name makes
mapper configuration for KBDocument raise:
    sqlalchemy.exc.InvalidRequestError: Attribute name 'metadata' is
    reserved when using the Declarative API.
This is raised the moment SQLAlchemy configures the KBDocument mapper
(during `_as_declarative()` attribute scanning), which happens well before
any query runs. Every code path that touches KBDocument — upload, list,
delete, and the background ingestion status update — instantiates or
queries this model and therefore hit this exception. The column was never
even read anywhere in the pipeline (grep confirms zero usages beyond the
declaration), so it's renamed to `doc_metadata` rather than removed, in
case downstream integrations expect a free-form metadata bucket per
document. See migrations/versions/003_fix_kb_document_metadata_column.py
for the corresponding column rename.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    chroma_collection: Mapped[str] = mapped_column(String(255), nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    # NEW (Voice AI Part 4): "file" | "text" — purely a UI/organizational
    # label for the frontend's "Knowledge Base" vs "Text Knowledge Base"
    # sections. The underlying storage (KBDocument + this same ChromaDB
    # collection) is identical either way — a "text" KB just only ever
    # gets documents with KBDocument.source_type="pasted_text". Nothing in
    # the pipeline or retrieval branches on this value.
    kb_type: Mapped[str] = mapped_column(String(10), default="file", nullable=False)
    # ROOT CAUSE FIX: records which embedding provider/model actually produced
    # the vectors currently stored in this KB's Chroma collection. Set once,
    # on the first successful document ingest, and reused for every later
    # ingest/retrieval against this KB regardless of the user's *current*
    # default AI provider — different providers/models produce
    # different-dimensional vectors (e.g. OpenAI text-embedding-3-small is
    # 1536-dim, Gemini gemini-embedding-001 is 3072-dim), and a single Chroma
    # collection can only ever hold one dimensionality. Left NULL until the
    # first document is successfully ingested. To switch a KB to a different
    # embedding provider, delete it and create a new one (existing supported
    # flow) — this intentionally avoids silently corrupting or partially
    # re-embedding an existing collection.
    embedding_provider: Mapped[str | None] = mapped_column(String(50))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User", back_populates="knowledge_bases", passive_deletes=True)
    documents: Mapped[list["KBDocument"]] = relationship(
        "KBDocument", back_populates="knowledge_base", cascade="all, delete-orphan", passive_deletes=True
    )


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="processing")
    error_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    # ROOT CAUSE FIX (v7): was `metadata` — a name reserved by SQLAlchemy's
    # Declarative API. See module docstring above.
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    # NEW (Voice AI Part 4): "upload" (existing file-upload flow, unchanged)
    # or "pasted_text" (Text Knowledge Base). raw_text is only populated for
    # "pasted_text" documents — it's the source of truth for edit/append,
    # since chunks/embeddings are a derived, re-creatable artifact of it.
    source_type: Mapped[str] = mapped_column(String(20), default="upload", nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase", back_populates="documents", passive_deletes=True
    )
