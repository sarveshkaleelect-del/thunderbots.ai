"""
ThunderBots Interactive Tutorial System — API (NEW, v106)

Isolated, additive router. Reads/writes only the new `tutorial_progress`
table. Does not touch Builder, Runtime, Workflow Engine, AI Engine, Auth,
or any other feature's tables or logic.

Progress is keyed by (user_id, feature_key) so each ThunderBots feature
(dashboard, workflow-builder, shop-assistant, ai-chat, knowledge-base,
call-agent, ...) tracks its own tutorial independently, per user.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.tutorial_progress import TutorialProgress

logger = logging.getLogger(__name__)
router = APIRouter()


class ProgressOut(BaseModel):
    feature_key: str
    status: str
    current_step: int
    completed_steps: int

    class Config:
        from_attributes = True


class ProgressUpsert(BaseModel):
    feature_key: str = Field(..., min_length=1, max_length=100)
    status: str = Field(..., pattern="^(not_started|in_progress|completed|skipped)$")
    current_step: int = Field(0, ge=0)
    completed_steps: int = Field(0, ge=0)


@router.get("/progress", response_model=list[ProgressOut])
async def list_progress(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """All tutorial progress rows for the current user — the frontend
    tutorial store hydrates from this once on load, then merges with
    localStorage for instant, offline-tolerant behaviour."""
    result = await db.execute(select(TutorialProgress).where(TutorialProgress.user_id == user.id))
    return result.scalars().all()


@router.put("/progress", response_model=ProgressOut)
async def upsert_progress(
    payload: ProgressUpsert,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent upsert for a single feature's tutorial state. Called on
    Next/Previous/Skip/Finish/Restart — never removes other features'
    progress."""
    result = await db.execute(
        select(TutorialProgress).where(
            TutorialProgress.user_id == user.id,
            TutorialProgress.feature_key == payload.feature_key,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = TutorialProgress(user_id=user.id, feature_key=payload.feature_key)
        db.add(row)

    row.status = payload.status
    row.current_step = payload.current_step
    row.completed_steps = payload.completed_steps
    row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    return row


@router.post("/progress/{feature_key}/restart", response_model=ProgressOut)
async def restart_progress(
    feature_key: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Explicit user-initiated restart — the ONLY way a completed tutorial
    is shown again, per spec."""
    result = await db.execute(
        select(TutorialProgress).where(
            TutorialProgress.user_id == user.id,
            TutorialProgress.feature_key == feature_key,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = TutorialProgress(user_id=user.id, feature_key=feature_key)
        db.add(row)

    row.status = "in_progress"
    row.current_step = 0
    row.completed_steps = 0
    row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    return row
