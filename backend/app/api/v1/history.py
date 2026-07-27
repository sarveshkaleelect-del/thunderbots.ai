import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.models.user import User
from app.models.workflow import Workflow, WorkflowHistory

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{workflow_id}/versions")
async def list_versions(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # FIX: verify ownership first
    wf = await db.execute(
        select(Workflow.id).where(
            Workflow.id == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    if not wf.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workflow not found")

    result = await db.execute(
        select(
            WorkflowHistory.id,
            WorkflowHistory.version_number,
            WorkflowHistory.label,
            WorkflowHistory.created_at,
        )
        .where(WorkflowHistory.workflow_id == workflow_id)
        .order_by(WorkflowHistory.version_number.desc())
    )
    rows = result.mappings().all()
    return [
        {
            "id": str(r["id"]),
            "version_number": r["version_number"],
            "label": r["label"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.get("/{workflow_id}/versions/{version_id}")
async def get_version(
    workflow_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ownership check via workflow
    wf = await db.execute(
        select(Workflow.id).where(
            Workflow.id == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    if not wf.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workflow not found")

    result = await db.execute(
        select(WorkflowHistory).where(
            WorkflowHistory.id == version_id,
            WorkflowHistory.workflow_id == workflow_id,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    return {
        "id": str(version.id),
        "workflow_id": str(version.workflow_id),
        "version_number": version.version_number,
        "label": version.label,
        "nodes": version.nodes or [],
        "edges": version.edges or [],
        "canvas_state": version.canvas_state or {"x": 0, "y": 0, "zoom": 1},
        "settings": version.settings or {},
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


@router.post("/{workflow_id}/restore/{version_id}")
async def restore_version(
    workflow_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Restore workflow to a saved version.
    Returns confirmation only — client fetches version detail separately
    via GET /versions/{version_id} to update its canvas.
    """
    v_result = await db.execute(
        select(WorkflowHistory).where(
            WorkflowHistory.id == version_id,
            WorkflowHistory.workflow_id == workflow_id,
        )
    )
    version = v_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    wf_result = await db.execute(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await db.execute(
        update(Workflow)
        .where(Workflow.id == workflow_id)
        .values(
            nodes=version.nodes,
            edges=version.edges,
            canvas_state=version.canvas_state,
            settings=version.settings,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    cache = CacheService()
    await cache.delete(f"workflow:{workflow_id}")

    return {
        "message": f"Restored to version {version.version_number}",
        "version_number": version.version_number,
        "version_id": version_id,
        "workflow_id": workflow_id,
    }


@router.patch("/{workflow_id}/versions/{version_id}/label")
async def label_version(
    workflow_id: str,
    version_id: str,
    label: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify ownership
    wf = await db.execute(
        select(Workflow.id).where(
            Workflow.id == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    if not wf.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workflow not found")

    result = await db.execute(
        select(WorkflowHistory).where(
            WorkflowHistory.id == version_id,
            WorkflowHistory.workflow_id == workflow_id,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    version.label = label[:255]
    await db.commit()
    return {"id": version_id, "label": version.label}
