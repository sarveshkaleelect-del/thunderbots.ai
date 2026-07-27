"""
ThunderBots Workflow API
FIX v4:
- delete_workflow: explicitly delete children before parent (belt+suspenders with passive_deletes)
- save_workflow: re-fetch workflow after bulk UPDATE instead of refresh() on stale object
- history snapshot: ON CONFLICT DO NOTHING on unique version to handle race condition gracefully
- list_workflows: COALESCE for null-safe node_count
"""
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update, text
from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.core.file_validation import is_svg_content_safe
from app.models.user import User
from app.models.workflow import Workflow, WorkflowHistory
from app.config import settings
from app.services import audit_service
from app.services.audit_service import Action

router = APIRouter()

# ── Node Media Attachment (e.g. Multiple Choice node images) ──────────────────
NODE_MEDIA_ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "svg"}
NODE_MEDIA_MAX_SIZE_MB = 10


# ── Schemas ───────────────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None


class WorkflowSave(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    canvas_state: dict[str, Any] = {}


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    knowledge_base_id: Optional[str] = None


# ── Background history snapshot ───────────────────────────────────────────────

async def _create_history_snapshot(workflow_id: str, user_id: str, old_state: dict):
    """
    FIX: Uses INSERT ... ON CONFLICT DO NOTHING to handle the race condition
    where two concurrent saves read the same max(version_number).
    The UniqueConstraint on (workflow_id, version_number) prevents duplicates;
    the losing transaction simply skips its insert rather than raising IntegrityError.
    """
    from app.core.database import AsyncSessionLocal
    import logging
    logger = logging.getLogger(__name__)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.max(WorkflowHistory.version_number)).where(
                    WorkflowHistory.workflow_id == workflow_id
                )
            )
            max_v = result.scalar() or 0
            next_v = max_v + 1

            # Use raw INSERT with ON CONFLICT DO NOTHING to handle race gracefully
            await db.execute(
                text("""
                    INSERT INTO workflow_history
                        (id, workflow_id, user_id, version_number,
                         canvas_state, nodes, edges, settings, created_at)
                    VALUES
                        (:id, :workflow_id, :user_id, :version_number,
                         :canvas_state::jsonb, :nodes::jsonb, :edges::jsonb,
                         :settings::jsonb, :created_at)
                    ON CONFLICT (workflow_id, version_number) DO NOTHING
                """),
                {
                    "id": str(__import__("uuid").uuid4()),
                    "workflow_id": workflow_id,
                    "user_id": user_id,
                    "version_number": next_v,
                    "canvas_state": __import__("json").dumps(old_state.get("canvas_state", {})),
                    "nodes": __import__("json").dumps(old_state.get("nodes", [])),
                    "edges": __import__("json").dumps(old_state.get("edges", [])),
                    "settings": __import__("json").dumps(old_state.get("settings", {})),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            # Prune: keep most recent MAX_HISTORY_VERSIONS only
            subq = (
                select(WorkflowHistory.id)
                .where(WorkflowHistory.workflow_id == workflow_id)
                .order_by(WorkflowHistory.version_number.desc())
                .offset(settings.MAX_HISTORY_VERSIONS)
            )
            await db.execute(delete(WorkflowHistory).where(WorkflowHistory.id.in_(subq)))
            await db.commit()

    except Exception as e:
        logger.error(f"History snapshot failed for {workflow_id}: {e}", exc_info=True)


# ── Provider list (static route must be before /{workflow_id}) ────────────────

@router.get("/providers/list")
async def list_providers(current_user: User = Depends(get_current_user)):
    from app.services.ai_engine import ai_engine
    return ai_engine.get_available_providers()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(
            Workflow.id,
            Workflow.name,
            Workflow.description,
            Workflow.status,
            Workflow.knowledge_base_id,
            Workflow.created_at,
            Workflow.updated_at,
            # FIX: COALESCE handles NULL (workflow with no nodes column data)
            func.coalesce(func.jsonb_array_length(Workflow.nodes), 0).label("node_count"),
        )
        .where(Workflow.user_id == current_user.id)
        .order_by(Workflow.updated_at.desc())
    )
    rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "description": r["description"],
            "status": r["status"],
            "knowledge_base_id": str(r["knowledge_base_id"]) if r["knowledge_base_id"] else None,
            "node_count": r["node_count"] or 0,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.post("/", status_code=201)
async def create_workflow(
    payload: WorkflowCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = Workflow(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        nodes=[],
        edges=[],
        canvas_state={"x": 0, "y": 0, "zoom": 1},
        settings={},
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    await audit_service.record(
        db, Action.WORKFLOW_CREATE, actor=current_user, request=request,
        target_type="workflow", target_id=workflow.id, target_label=workflow.name,
    )
    return _serialize(workflow)


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = await _get_or_404(workflow_id, current_user.id, db)
    return _serialize(workflow)


@router.post("/{workflow_id}/node-media")
async def upload_node_media(
    workflow_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload an optional image attachment for a workflow node (e.g. the
    Multiple Choice node's Media Attachment). Purely additive: stores the
    file and returns its URL/metadata for the frontend to save onto the
    node's `data.image` field. Does not touch node execution logic, existing
    workflow data, or any other endpoint."""
    workflow = await _get_or_404(workflow_id, current_user.id, db)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower().lstrip(".")
    if suffix not in NODE_MEDIA_ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Allowed: PNG, JPG, JPEG, WEBP, SVG",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")

    size_mb = len(content) / (1024 * 1024)
    if size_mb > NODE_MEDIA_MAX_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File size {size_mb:.1f}MB exceeds {NODE_MEDIA_MAX_SIZE_MB}MB limit",
        )

    if suffix == "svg" and not is_svg_content_safe(content):
        raise HTTPException(
            status_code=400,
            detail="This SVG contains active content (script/event handlers) and can't be uploaded",
        )

    media_dir = os.path.join(settings.UPLOAD_DIR, "node-media", workflow_id)
    os.makedirs(media_dir, exist_ok=True)

    filename = f"img-{uuid.uuid4().hex[:10]}.{suffix}"
    disk_path = os.path.join(media_dir, filename)
    with open(disk_path, "wb") as f:
        f.write(content)

    url = f"{settings.APP_API_URL}/uploads/node-media/{workflow_id}/{filename}"

    return {
        "url": url,
        "filename": file.filename,
        "size": len(content),
        "mime_type": file.content_type,
    }


@router.post("/{workflow_id}/save")
async def save_workflow(
    workflow_id: str,
    payload: WorkflowSave,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fast-path save. Target: < 100ms.
    FIX: Re-fetches the workflow after UPDATE instead of refreshing the stale
    ORM object, guaranteeing the response reflects what was actually written.
    """
    workflow = await _get_or_404(workflow_id, current_user.id, db)

    # Capture pre-save state for history snapshot
    old_state = {
        "canvas_state": workflow.canvas_state,
        "nodes": workflow.nodes,
        "edges": workflow.edges,
        "settings": workflow.settings,
    }

    now = datetime.now(timezone.utc)

    # Bulk UPDATE — fastest path
    await db.execute(
        update(Workflow)
        .where(Workflow.id == workflow_id)
        .values(
            nodes=payload.nodes,
            edges=payload.edges,
            canvas_state=payload.canvas_state,
            updated_at=now,
        )
    )
    await db.commit()

    # FIX: Re-fetch after core UPDATE to avoid returning stale ORM object.
    # The session has expire_on_commit=False so the in-memory object still has
    # old node/edge values. refresh() should fix it but re-fetching is explicit
    # and guaranteed correct.
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id)
    )
    updated_workflow = result.scalar_one()

    # Invalidate Redis cache
    cache = CacheService()
    await cache.delete(f"workflow:{workflow_id}")

    # History snapshot in background — non-blocking
    background_tasks.add_task(
        _create_history_snapshot, workflow_id, current_user.id, old_state
    )

    return _serialize(updated_workflow)


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = await _get_or_404(workflow_id, current_user.id, db)

    if payload.name is not None:
        workflow.name = payload.name
    if payload.description is not None:
        workflow.description = payload.description
    if payload.status is not None:
        if payload.status not in ("draft", "published"):
            raise HTTPException(status_code=400, detail="status must be 'draft' or 'published'")
        workflow.status = payload.status
    if payload.knowledge_base_id is not None:
        workflow.knowledge_base_id = payload.knowledge_base_id or None

    await db.commit()
    await db.refresh(workflow)

    cache = CacheService()
    await cache.delete(f"workflow:{workflow_id}")
    await audit_service.record(
        db, Action.WORKFLOW_UPDATE, actor=current_user, request=request,
        target_type="workflow", target_id=workflow.id, target_label=workflow.name,
        metadata={"fields_changed": [f for f in ("name", "description", "status", "knowledge_base_id") if getattr(payload, f) is not None]},
    )
    return _serialize(workflow)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    FIX: Explicitly delete child rows before deleting the parent workflow.
    Even with passive_deletes=True on the ORM relationship, we do this
    belt-and-suspenders to ensure no MissingGreenlet error in edge cases.
    The DB ondelete=CASCADE handles any children we may have missed.
    """
    workflow = await _get_or_404(workflow_id, current_user.id, db)
    workflow_name = workflow.name

    # Explicitly delete history and deployment rows first.
    # passive_deletes=True means the ORM won't try to load them,
    # and ondelete=CASCADE in the FK means the DB would clean them up anyway.
    # This explicit delete is for clarity and belt-and-suspenders safety.
    await db.execute(
        delete(WorkflowHistory).where(WorkflowHistory.workflow_id == workflow_id)
    )

    from app.models.workflow import Deployment
    await db.execute(
        delete(Deployment).where(Deployment.workflow_id == workflow_id)
    )

    await db.delete(workflow)
    await db.commit()

    cache = CacheService()
    await cache.delete(f"workflow:{workflow_id}")
    await audit_service.record(
        db, Action.WORKFLOW_DELETE, actor=current_user, request=request,
        target_type="workflow", target_id=workflow_id, target_label=workflow_name,
    )


@router.post("/{workflow_id}/duplicate")
async def duplicate_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Duplicate a workflow as a new draft."""
    source = await _get_or_404(workflow_id, current_user.id, db)

    import copy
    duplicate = Workflow(
        user_id=current_user.id,
        name=f"{source.name} (Copy)",
        description=source.description,
        nodes=copy.deepcopy(source.nodes or []),
        edges=copy.deepcopy(source.edges or []),
        canvas_state=copy.deepcopy(source.canvas_state or {"x": 0, "y": 0, "zoom": 1}),
        settings=copy.deepcopy(source.settings or {}),
        knowledge_base_id=source.knowledge_base_id,
        status="draft",
    )
    db.add(duplicate)
    await db.commit()
    await db.refresh(duplicate)
    return _serialize(duplicate)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(workflow_id: str, user_id: str, db: AsyncSession) -> Workflow:
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == user_id)
    )
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return w


def _serialize(w: Workflow) -> dict:
    return {
        "id": str(w.id),
        "name": w.name,
        "description": w.description,
        "status": w.status,
        "nodes": w.nodes or [],
        "edges": w.edges or [],
        "canvas_state": w.canvas_state or {"x": 0, "y": 0, "zoom": 1},
        "settings": w.settings or {},
        "knowledge_base_id": str(w.knowledge_base_id) if w.knowledge_base_id else None,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }
