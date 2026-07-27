"""
ThunderBots AI Call Agent — Voice Agents API (NEW, Voice AI Part 5)

Standalone product surface: CRUD for independent Voice Agents (own AI
provider/model/instructions/personality/voice), each with its own
Knowledge Base (PDF / Text / FAQ), completely separate from the chatbot
Workflow/Builder module and from the generic KnowledgeBase/KBDocument
tables the Builder's own Knowledge Base panel uses.

Registered as its own router (see app/main.py) so call_agent.py (Part 2)
and call_agent_calls.py (Part 3/4) are never touched by this file —
matching the layering convention this feature already established.

Ingestion reuses app/knowledge/pipeline.py's extract/clean/chunk/embed/
index functions unmodified (they are collection-name/text driven and know
nothing about which table owns a document) — this is a second UI/data
surface over the same pipeline, not a second embedding engine.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import get_current_user
from app.core.database import AsyncSessionLocal, get_db
from app.core.redis import CacheService
from app.knowledge.pipeline import kb_pipeline, retrieval_engine
from app.models.call import Call
from app.models.phone_number import PhoneNumber
from app.models.user import User
from app.models.voice_agent import VoiceAgent, VoiceAgentKBDocument
from app.services import audit_service
from app.services.audit_service import Action

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_FILE_TYPES = {"pdf", "docx", "txt", "md", "markdown"}
MAX_TEXT_CHARS = 2_000_000


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class InstructionsPayload(BaseModel):
    behaviour: Optional[str] = ""
    role: Optional[str] = ""
    rules: Optional[str] = ""
    business_policies: Optional[str] = ""
    tone: Optional[str] = ""
    sales_instructions: Optional[str] = ""
    appointment_booking_rules: Optional[str] = ""
    escalation_rules: Optional[str] = ""
    response_restrictions: Optional[str] = ""


class VoiceAgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = ""


class VoiceAgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    instructions: Optional[InstructionsPayload] = None
    personality: Optional[str] = None
    goals: Optional[str] = None
    welcome_message: Optional[str] = None
    fallback_message: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None
    language: Optional[str] = None
    speaking_speed: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    silence_timeout_seconds: Optional[int] = Field(default=None, ge=1, le=60)
    interrupt_enabled: Optional[bool] = None
    memory_enabled: Optional[bool] = None
    conversation_history_enabled: Optional[bool] = None
    is_enabled: Optional[bool] = None


class TextEntryCreate(BaseModel):
    title: str = Field(default="", max_length=500)
    content: str = Field(..., min_length=1)


class FaqItem(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    answer: str = Field(..., min_length=1, max_length=4000)


class FaqEntryCreate(BaseModel):
    title: str = Field(default="FAQ", max_length=500)
    items: list[FaqItem] = Field(..., min_length=1)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_owned_agent(agent_id: str, db: AsyncSession, current_user: User) -> VoiceAgent:
    result = await db.execute(select(VoiceAgent).where(VoiceAgent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Voice Agent not found")
    if str(agent.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this Voice Agent")
    return agent


def _serialize_agent(agent: VoiceAgent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "ai_provider": agent.ai_provider,
        "ai_model": agent.ai_model,
        "instructions": agent.instructions or {},
        "personality": agent.personality,
        "goals": agent.goals,
        "welcome_message": agent.welcome_message,
        "fallback_message": agent.fallback_message,
        "voice_provider": agent.voice_provider,
        "voice_id": agent.voice_id,
        "language": agent.language,
        "speaking_speed": agent.speaking_speed,
        "temperature": agent.temperature,
        "silence_timeout_seconds": agent.silence_timeout_seconds,
        "interrupt_enabled": agent.interrupt_enabled,
        "memory_enabled": agent.memory_enabled,
        "conversation_history_enabled": agent.conversation_history_enabled,
        "is_enabled": agent.is_enabled,
        "status": agent.status,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


def _serialize_doc(doc: VoiceAgentKBDocument) -> dict:
    return {
        "id": doc.id,
        "agent_id": doc.agent_id,
        "kb_type": doc.kb_type,
        "title": doc.title,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "status": doc.status,
        "error_message": doc.error_message,
        "chunk_count": doc.chunk_count,
        "faq_items": doc.faq_items,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
    }


def _user_facing_error(e: Exception) -> str:
    msg = str(e).strip()
    return msg[:2000] if msg else "Something went wrong while indexing this document."


async def _ingest_kb_document(
    doc_id: str, agent_id: str, file_path: Optional[str], file_type: str,
    title: str, collection: str, user_id: str, raw_text: Optional[str] = None,
) -> None:
    logger.info(f"[voice-agent-kb] ingest starting: doc={doc_id} agent={agent_id} title='{title}'")
    async with AsyncSessionLocal() as db:
        try:
            agent_result = await db.execute(select(VoiceAgent).where(VoiceAgent.id == agent_id))
            agent = agent_result.scalar_one_or_none()
            if not agent:
                raise ValueError(f"Voice Agent {agent_id} no longer exists")

            result = await kb_pipeline.ingest(
                file_path=file_path,
                file_type=file_type,
                document_id=doc_id,
                kb_id=agent_id,
                collection_name=collection,
                filename=title,
                user_id=user_id,
                embedding_provider=agent.embedding_provider,
                embedding_model=agent.embedding_model,
                raw_text=raw_text,
            )

            now = datetime.now(timezone.utc)
            await db.execute(
                update(VoiceAgentKBDocument)
                .where(VoiceAgentKBDocument.id == doc_id)
                .values(status="ready", chunk_count=result["chunk_count"], processed_at=now)
            )
            if not agent.embedding_provider:
                agent.embedding_provider = result["embedding_provider"]
                agent.embedding_model = result["embedding_model"]
            await db.commit()

            cache = CacheService()
            await cache.delete_pattern(f"retrieval:{agent_id}:*")

            logger.info(f"[voice-agent-kb] ingest complete: doc={doc_id} agent={agent_id} chunks={result['chunk_count']}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"[voice-agent-kb] ingest FAILED: doc={doc_id} agent={agent_id}: {e}", exc_info=True)
            await db.execute(
                update(VoiceAgentKBDocument)
                .where(VoiceAgentKBDocument.id == doc_id)
                .values(status="error", error_message=_user_facing_error(e))
            )
            await db.commit()
        finally:
            if file_path:
                doc_row = await db.execute(select(VoiceAgentKBDocument.status).where(VoiceAgentKBDocument.id == doc_id))
                row = doc_row.first()
                if row and row[0] != "error":
                    try:
                        os.unlink(file_path)
                    except OSError:
                        pass


# ─────────────────────────────────────────────────────────────────────────────
# Voice Agents — CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/agents")
async def list_voice_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(VoiceAgent).where(VoiceAgent.user_id == current_user.id).order_by(VoiceAgent.created_at.desc())
    )
    return [_serialize_agent(a) for a in result.scalars().all()]


@router.post("/agents", status_code=status.HTTP_201_CREATED)
async def create_voice_agent(
    payload: VoiceAgentCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = VoiceAgent(
        user_id=current_user.id,
        name=payload.name.strip(),
        description=(payload.description or "").strip(),
        welcome_message="Hi! Thanks for reaching out — how can I help you today?",
        fallback_message="I'm not able to help with that right now — let me connect you with our team.",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    audit_service.record_bg(
        background_tasks, Action.CALL_AGENT_SETTINGS_UPDATE, actor=current_user, request=request,
        target_type="voice_agent", target_id=agent.id, target_label=agent.name,
    )
    return _serialize_agent(agent)


@router.get("/agents/{agent_id}")
async def get_voice_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    return _serialize_agent(agent)


@router.put("/agents/{agent_id}")
async def update_voice_agent(
    agent_id: str,
    payload: VoiceAgentUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    data = payload.model_dump(exclude_unset=True)

    if "instructions" in data and data["instructions"] is not None:
        agent.instructions = data.pop("instructions")
    elif "instructions" in data:
        data.pop("instructions")

    for field, value in data.items():
        if field == "name" and value is not None:
            value = value.strip()
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    audit_service.record_bg(
        background_tasks, Action.CALL_AGENT_SETTINGS_UPDATE, actor=current_user, request=request,
        target_type="voice_agent", target_id=agent.id, target_label=agent.name,
    )
    return _serialize_agent(agent)


@router.delete("/agents/{agent_id}")
async def delete_voice_agent(
    agent_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    name = agent.name

    try:
        await kb_pipeline.delete_collection(agent.chroma_collection)
    except Exception as e:  # noqa: BLE001 — an already-gone collection must not block deletion
        logger.warning(f"[voice-agent] collection cleanup failed for agent={agent_id}: {e}")

    # Unbind any phone numbers pointed at this agent rather than leaving a
    # dangling reference (the FK is ON DELETE SET NULL, but doing it
    # explicitly here keeps behavior identical pre-commit).
    await db.execute(
        update(PhoneNumber).where(PhoneNumber.voice_agent_id == agent_id).values(voice_agent_id=None)
    )
    await db.delete(agent)
    await db.commit()

    audit_service.record_bg(
        background_tasks, Action.CALL_AGENT_SETTINGS_UPDATE, actor=current_user, request=request,
        target_type="voice_agent", target_id=agent_id, target_label=name,
    )
    return {"deleted": True}


# ─────────────────────────────────────────────────────────────────────────────
# Voice Agent Knowledge Base — PDF upload / Text / FAQ
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/knowledge")
async def list_knowledge_documents(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_agent(agent_id, db, current_user)
    result = await db.execute(
        select(VoiceAgentKBDocument)
        .where(VoiceAgentKBDocument.agent_id == agent_id)
        .order_by(VoiceAgentKBDocument.created_at.desc())
    )
    return [_serialize_doc(d) for d in result.scalars().all()]


@router.post("/agents/{agent_id}/knowledge/upload", status_code=status.HTTP_201_CREATED)
async def upload_pdf_document(
    agent_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)

    suffix = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in ALLOWED_FILE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '.{suffix}'. Allowed: {', '.join(sorted(ALLOWED_FILE_TYPES))}")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(status_code=413, detail=f"File size {size_mb:.1f}MB exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    doc_id = str(uuid.uuid4())
    temp_path = os.path.join(settings.UPLOAD_DIR, f"{doc_id}.{suffix}")
    with open(temp_path, "wb") as fh:
        fh.write(content)

    doc = VoiceAgentKBDocument(
        id=doc_id,
        agent_id=agent_id,
        kb_type="pdf",
        title=file.filename or "Untitled document",
        file_type=suffix,
        file_size=len(content),
        status="processing",
        doc_metadata={"content_hash": hashlib.sha256(content).hexdigest()},
    )
    db.add(doc)
    await db.commit()

    background_tasks.add_task(
        _ingest_kb_document, doc_id, agent_id, temp_path, suffix, doc.title, agent.chroma_collection, str(current_user.id),
    )
    audit_service.record_bg(
        background_tasks, Action.KNOWLEDGE_BASE_UPLOAD, actor=current_user, request=request,
        target_type="voice_agent_kb_document", target_id=doc_id, target_label=doc.title,
        metadata={"agent_id": agent_id, "file_type": suffix},
    )
    return {"id": doc_id, "title": doc.title, "status": "processing"}


@router.post("/agents/{agent_id}/knowledge/text", status_code=status.HTTP_201_CREATED)
async def create_text_document(
    agent_id: str,
    payload: TextEntryCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(content) > MAX_TEXT_CHARS:
        raise HTTPException(status_code=413, detail=f"Text exceeds the {MAX_TEXT_CHARS:,}-character limit")

    title = payload.title.strip() or f"Text entry ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})"
    doc_id = str(uuid.uuid4())
    doc = VoiceAgentKBDocument(
        id=doc_id, agent_id=agent_id, kb_type="text", title=title, file_type="txt",
        file_size=len(content.encode("utf-8")), status="processing", raw_text=content,
        doc_metadata={"content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()},
    )
    db.add(doc)
    await db.commit()

    background_tasks.add_task(
        _ingest_kb_document, doc_id, agent_id, None, "txt", title, agent.chroma_collection, str(current_user.id), content,
    )
    audit_service.record_bg(
        background_tasks, Action.KNOWLEDGE_BASE_UPLOAD, actor=current_user, request=request,
        target_type="voice_agent_kb_document", target_id=doc_id, target_label=title,
        metadata={"agent_id": agent_id, "source_type": "text"},
    )
    return {"id": doc_id, "title": title, "status": "processing"}


@router.get("/agents/{agent_id}/knowledge/{doc_id}/text")
async def get_text_document(
    agent_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_agent(agent_id, db, current_user)
    result = await db.execute(
        select(VoiceAgentKBDocument).where(VoiceAgentKBDocument.id == doc_id, VoiceAgentKBDocument.agent_id == agent_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": doc.id, "title": doc.title, "content": doc.raw_text or "", "status": doc.status}


@router.post("/agents/{agent_id}/knowledge/faq", status_code=status.HTTP_201_CREATED)
async def create_faq_document(
    agent_id: str,
    payload: FaqEntryCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    items = [item.model_dump() for item in payload.items]
    combined_text = "\n\n".join(f"Q: {it['question']}\nA: {it['answer']}" for it in items)
    title = payload.title.strip() or "FAQ"
    doc_id = str(uuid.uuid4())

    doc = VoiceAgentKBDocument(
        id=doc_id, agent_id=agent_id, kb_type="faq", title=title, file_type="txt",
        file_size=len(combined_text.encode("utf-8")), status="processing",
        raw_text=combined_text, faq_items=items,
    )
    db.add(doc)
    await db.commit()

    background_tasks.add_task(
        _ingest_kb_document, doc_id, agent_id, None, "txt", title, agent.chroma_collection, str(current_user.id), combined_text,
    )
    audit_service.record_bg(
        background_tasks, Action.KNOWLEDGE_BASE_UPLOAD, actor=current_user, request=request,
        target_type="voice_agent_kb_document", target_id=doc_id, target_label=title,
        metadata={"agent_id": agent_id, "source_type": "faq", "items": len(items)},
    )
    return {"id": doc_id, "title": title, "status": "processing"}


@router.post("/agents/{agent_id}/knowledge/{doc_id}/retry")
async def retry_document(
    agent_id: str,
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    result = await db.execute(
        select(VoiceAgentKBDocument).where(VoiceAgentKBDocument.id == doc_id, VoiceAgentKBDocument.agent_id == agent_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status != "error":
        raise HTTPException(status_code=400, detail="Only a failed document can be retried")

    doc.status = "processing"
    doc.error_message = None
    await db.commit()

    file_path = None
    if doc.kb_type == "pdf":
        file_path = os.path.join(settings.UPLOAD_DIR, f"{doc.id}.{doc.file_type}")
        if not os.path.exists(file_path):
            raise HTTPException(status_code=400, detail="The original file is no longer available — delete and re-upload it.")

    background_tasks.add_task(
        _ingest_kb_document, doc.id, agent_id, file_path, doc.file_type, doc.title,
        agent.chroma_collection, str(current_user.id), doc.raw_text,
    )
    return {"id": doc.id, "status": "processing"}


@router.delete("/agents/{agent_id}/knowledge/{doc_id}")
async def delete_document(
    agent_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    result = await db.execute(
        select(VoiceAgentKBDocument).where(VoiceAgentKBDocument.id == doc_id, VoiceAgentKBDocument.agent_id == agent_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        await kb_pipeline.delete_document(doc_id, agent.chroma_collection)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[voice-agent-kb] vector cleanup failed for doc={doc_id}: {e}")

    await db.delete(doc)
    await db.commit()
    return {"deleted": True}


# Note: the voice catalog is already exposed at GET /call-agent/voices by
# call_agent_calls.py (Part 3/4) — reused as-is by the frontend for Voice
# Agents too, rather than duplicating tts_engine wiring here.


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard + Analytics + Embed
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def voice_agent_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agents_result = await db.execute(select(func.count(VoiceAgent.id)).where(VoiceAgent.user_id == current_user.id))
    total_agents = agents_result.scalar() or 0

    enabled_result = await db.execute(
        select(func.count(VoiceAgent.id)).where(VoiceAgent.user_id == current_user.id, VoiceAgent.is_enabled == True)  # noqa: E712
    )
    enabled_agents = enabled_result.scalar() or 0

    numbers_result = await db.execute(
        select(func.count(PhoneNumber.id)).where(PhoneNumber.user_id == current_user.id, PhoneNumber.voice_agent_id.isnot(None))
    )
    bound_numbers = numbers_result.scalar() or 0

    calls_result = await db.execute(select(func.count(Call.id)).where(Call.user_id == current_user.id))
    total_calls = calls_result.scalar() or 0

    kb_result = await db.execute(
        select(func.count(VoiceAgentKBDocument.id))
        .join(VoiceAgent, VoiceAgent.id == VoiceAgentKBDocument.agent_id)
        .where(VoiceAgent.user_id == current_user.id)
    )
    total_kb_documents = kb_result.scalar() or 0

    return {
        "total_agents": total_agents,
        "enabled_agents": enabled_agents,
        "bound_phone_numbers": bound_numbers,
        "total_calls": total_calls,
        "total_knowledge_documents": total_kb_documents,
    }


@router.get("/agents/{agent_id}/analytics")
async def voice_agent_analytics(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_agent(agent_id, db, current_user)

    calls_result = await db.execute(
        select(Call).join(PhoneNumber, PhoneNumber.id == Call.phone_number_id)
        .where(PhoneNumber.voice_agent_id == agent_id)
    )
    calls = calls_result.scalars().all()

    total = len(calls)
    completed = sum(1 for c in calls if c.status == "completed")
    failed = sum(1 for c in calls if c.status == "failed")
    interrupted = sum(1 for c in calls if c.interrupted_count > 0)
    durations = [c.duration_seconds for c in calls if c.duration_seconds]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else None

    return {
        "agent_id": agent_id,
        "total_calls": total,
        "completed_calls": completed,
        "failed_calls": failed,
        "interrupted_calls": interrupted,
        "avg_duration_seconds": avg_duration,
        "resolution_rate": round(completed / total, 3) if total else None,
    }


@router.get("/agents/{agent_id}/embed")
async def voice_agent_embed_snippet(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    api_url = settings.APP_API_URL
    snippet = (
        f'<script src="{api_url}/voice-widget.js" '
        f'data-agent-id="{agent.id}" data-mode="voice-bubble" async></script>'
    )
    return {"agent_id": agent.id, "embed_snippet": snippet}


# ─────────────────────────────────────────────────────────────────────────────
# NEW — Publish / Unpublish lifecycle (additive; does not touch is_enabled,
# Embed, Preview, or the Voice Widget in any way).
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/agents/{agent_id}/publish")
async def publish_voice_agent(
    agent_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    agent.status = "published"
    await db.commit()
    await db.refresh(agent)
    audit_service.record_bg(
        background_tasks, Action.CALL_AGENT_SETTINGS_UPDATE, actor=current_user, request=request,
        target_type="voice_agent", target_id=agent.id, target_label=agent.name,
    )
    return _serialize_agent(agent)


@router.post("/agents/{agent_id}/unpublish")
async def unpublish_voice_agent(
    agent_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    agent = await _get_owned_agent(agent_id, db, current_user)
    agent.status = "draft"
    await db.commit()
    await db.refresh(agent)
    audit_service.record_bg(
        background_tasks, Action.CALL_AGENT_SETTINGS_UPDATE, actor=current_user, request=request,
        target_type="voice_agent", target_id=agent.id, target_label=agent.name,
    )
    return _serialize_agent(agent)


# ─────────────────────────────────────────────────────────────────────────────
# NEW — Test Voice Agent dialog backend. Text in/text out only: the browser
# does its own mic capture (SpeechRecognition) and speech playback
# (speechSynthesis); this endpoint just runs one conversational turn through
# the agent's own provider/model/instructions — the exact same prompt
# composition call_stream_ws.py already uses for real calls (imported, never
# duplicated) — so a Test conversation reflects the real agent honestly.
# Entirely scratch/in-memory: no Call row, no transcript row, nothing
# persisted, so testing never pollutes real call history or analytics.
# ─────────────────────────────────────────────────────────────────────────────

class TestChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=8000)


class TestChatRequest(BaseModel):
    messages: list[TestChatTurn] = Field(default_factory=list, max_length=50)


@router.post("/agents/{agent_id}/test-chat")
async def test_voice_agent_chat(
    agent_id: str,
    payload: TestChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.api.ws.call_stream_ws import _compose_voice_agent_instructions
    from app.services.ai_engine import get_provider_for_user, resolve_agent_provider, ProviderError

    agent = await _get_owned_agent(agent_id, db, current_user)

    system_prompt = _compose_voice_agent_instructions(agent)
    if agent.welcome_message and not payload.messages:
        # Mirrors what a real call would open with, so Testing starts the
        # same way a caller would actually experience it.
        return {"role": "assistant", "content": agent.welcome_message}

    try:
        provider_id = await resolve_agent_provider(agent.ai_provider, str(current_user.id))
        provider = await get_provider_for_user(provider_id, str(current_user.id))
        reply = await provider.complete(
            system=system_prompt,
            messages=[{"role": m.role, "content": m.content} for m in payload.messages],
            temperature=agent.temperature,
            model=agent.ai_model or None,
            max_tokens=600,
        )
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"role": "assistant", "content": reply}
