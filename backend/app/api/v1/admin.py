"""
ThunderBots Admin Dashboard API (NEW)

Every route in this module is gated by get_current_admin_user (is_admin=True
AND is_active=True — see app/core/auth.py). This module is purely additive:
it does not alter any existing router, model, or relationship. Deleting a
user or a bot (workflow) relies on the ondelete="CASCADE" foreign keys
already established across models/user.py, models/workflow.py,
models/analytics.py, models/whatsapp.py — exactly the same cascade the
platform already uses everywhere else, so no new deletion logic is
introduced here.

Lightweight by design: every "Platform Status" check has its own short
timeout and never blocks the dashboard on a dependency that's slow or down —
a hung ChromaDB or Redis simply reports "down", it doesn't hang the request.
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, Request
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_admin_user
from app.core.redis import get_redis
from app.config import settings
from app.models.user import User
from app.models.workflow import Workflow, Deployment
from app.models.analytics import Conversation
from app.services import email_service
from app.services import audit_service
from app.services.audit_service import Action

router = APIRouter()
logger = logging.getLogger(__name__)

STATUS_CHECK_TIMEOUT = 2.5  # seconds — keeps the dashboard snappy even if a dependency hangs

# Same provider catalogs already defined in api/v1/settings.py — repeated here
# (not imported) to avoid coupling this read-only status check to that
# module's request/response schemas. Google Gemini is the only supported AI
# (LLM) provider; the remaining entries are voice-only TTS vendors.
_LLM_PROVIDERS = ("gemini",)
_VOICE_ONLY_PROVIDERS = ("elevenlabs", "azure_speech", "google_tts")


# ── Helpers ────────────────────────────────────────────────────────────────

def _serialize_user(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "is_admin": u.is_admin,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _serialize_bot(w: Workflow, owner_email: Optional[str]) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "status": w.status,
        "owner_id": w.user_id,
        "owner_email": owner_email,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


async def _check_database(db: AsyncSession) -> dict:
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=STATUS_CHECK_TIMEOUT)
        return {"name": "Database", "status": "operational", "detail": "PostgreSQL responding"}
    except Exception as e:
        return {"name": "Database", "status": "down", "detail": str(e)[:150]}


async def _check_redis() -> dict:
    redis = get_redis()
    if not redis:
        return {"name": "Redis Cache", "status": "down", "detail": "Not connected"}
    try:
        await asyncio.wait_for(redis.ping(), timeout=STATUS_CHECK_TIMEOUT)
        return {"name": "Redis Cache", "status": "operational", "detail": "Connected"}
    except Exception as e:
        return {"name": "Redis Cache", "status": "down", "detail": str(e)[:150]}


async def _check_chromadb() -> dict:
    def _heartbeat():
        import chromadb
        client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        return client.heartbeat()

    try:
        await asyncio.wait_for(asyncio.to_thread(_heartbeat), timeout=STATUS_CHECK_TIMEOUT)
        return {"name": "ChromaDB", "status": "operational", "detail": "Vector store responding"}
    except Exception as e:
        return {"name": "ChromaDB", "status": "down", "detail": str(e)[:150]}


async def _check_ai_providers(db: AsyncSession) -> dict:
    env_configured = bool(settings.GEMINI_API_KEY)
    from app.models.user import UserAPIKey
    result = await db.execute(
        select(func.count()).select_from(UserAPIKey).where(
            UserAPIKey.provider.in_(_LLM_PROVIDERS), UserAPIKey.is_valid.is_(True)
        )
    )
    valid_user_keys = result.scalar_one() or 0
    if env_configured or valid_user_keys > 0:
        return {
            "name": "AI Providers",
            "status": "operational",
            "detail": f"{valid_user_keys} verified user key(s)" + (" + env fallback" if env_configured else ""),
        }
    return {"name": "AI Providers", "status": "not_configured", "detail": "No provider keys configured yet"}


async def _check_voice_service(db: AsyncSession) -> dict:
    from app.models.user import UserAPIKey
    result = await db.execute(
        select(func.count()).select_from(UserAPIKey).where(
            or_(
                UserAPIKey.provider.in_(_VOICE_ONLY_PROVIDERS),
                UserAPIKey.provider == "gemini",
            ),
            UserAPIKey.is_valid.is_(True),
        )
    )
    valid_voice_keys = result.scalar_one() or 0
    if valid_voice_keys > 0:
        return {"name": "Voice Service", "status": "operational", "detail": f"{valid_voice_keys} verified voice-capable key(s)"}
    return {"name": "Voice Service", "status": "not_configured", "detail": "No voice-capable keys configured yet"}


# ── Overview ───────────────────────────────────────────────────────────────

@router.get("/overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    total_workflows = (await db.execute(select(func.count()).select_from(Workflow))).scalar_one()
    # "Bots" = live/published chatbots; "Workflows" = every chatbot project
    # including drafts. Same underlying table, different lens for admins.
    total_bots = (await db.execute(
        select(func.count()).select_from(Workflow).where(Workflow.status == "published")
    )).scalar_one()
    total_conversations = (await db.execute(select(func.count()).select_from(Conversation))).scalar_one()
    total_deployments = (await db.execute(select(func.count()).select_from(Deployment))).scalar_one()

    return {
        "total_users": total_users,
        "total_bots": total_bots,
        "total_workflows": total_workflows,
        "total_conversations": total_conversations,
        "total_deployments": total_deployments,
    }


# ── Platform Status ────────────────────────────────────────────────────────

@router.get("/status")
async def get_platform_status(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    checks = await asyncio.gather(
        _check_database(db),
        _check_redis(),
        _check_chromadb(),
        _check_ai_providers(db),
        _check_voice_service(db),
    )
    services = [{"name": "Backend API", "status": "operational", "detail": "Responding"}, *checks]
    overall = "operational" if all(s["status"] in ("operational", "not_configured") for s in services) else "degraded"
    return {"overall": overall, "services": services}


# ── Recent Activity ────────────────────────────────────────────────────────

@router.get("/activity")
async def get_recent_activity(
    limit: int = Query(8, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    new_users_res = await db.execute(select(User).order_by(User.created_at.desc()).limit(limit))
    new_bots_res = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()).limit(limit))
    deployments = (await db.execute(
        select(Deployment).order_by(Deployment.deployed_at.desc()).limit(limit)
    )).scalars().all()
    owner_ids = {d.user_id for d in deployments}
    owners = {}
    if owner_ids:
        owners_res = await db.execute(select(User.id, User.email).where(User.id.in_(owner_ids)))
        owners = dict(owners_res.all())

    return {
        "new_users": [
            {"id": u.id, "name": u.name, "email": u.email, "created_at": u.created_at.isoformat() if u.created_at else None}
            for u in new_users_res.scalars().all()
        ],
        "new_bots": [
            {"id": w.id, "name": w.name, "status": w.status, "created_at": w.created_at.isoformat() if w.created_at else None}
            for w in new_bots_res.scalars().all()
        ],
        "recent_deployments": [
            {
                "id": d.id,
                "workflow_id": d.workflow_id,
                "slug": d.slug,
                "owner_email": owners.get(d.user_id),
                "is_active": d.is_active,
                "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
            }
            for d in deployments
        ],
    }


# ── User Management ────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    search: str = Query("", max_length=255),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    if search.strip():
        like = f"%{search.strip()}%"
        cond = or_(User.name.ilike(like), User.email.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    users = (await db.execute(stmt)).scalars().all()

    return {
        "users": [_serialize_user(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/users/{user_id}/status")
async def set_user_status(
    user_id: str,
    is_active: bool,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    if user_id == admin.id and not is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot disable your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    logger.info(f"Admin {admin.email} set is_active={is_active} for user {user.email}")
    # NEW (Email & Notification Service): let the affected user know their
    # account status changed — fire-and-forget, never blocks this response.
    background_tasks.add_task(email_service.send_account_status_email, user.email, user.name, is_active)
    audit_service.record_bg(
        background_tasks, Action.ADMIN_USER_STATUS_CHANGE, actor=admin, request=request,
        target_type="user", target_id=user.id, target_label=user.email,
        metadata={"is_active": is_active},
    )
    return _serialize_user(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user_email = user.email

    # ondelete="CASCADE" on every child FK (workflows, knowledge_bases,
    # api_keys, conversations, deployments, ...) handles the rest at the DB level.
    await db.delete(user)
    await db.commit()
    logger.info(f"Admin {admin.email} deleted user {user.email}")
    await audit_service.record(
        db, Action.ADMIN_USER_DELETE, actor=admin, request=request,
        target_type="user", target_id=user_id, target_label=user_email,
    )
    return None


# ── Bot (Workflow) Management ───────────────────────────────────────────────

@router.get("/bots")
async def list_bots(
    search: str = Query("", max_length=255),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    stmt = select(Workflow)
    count_stmt = select(func.count()).select_from(Workflow)
    if search.strip():
        like = f"%{search.strip()}%"
        cond = Workflow.name.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Workflow.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    bots = (await db.execute(stmt)).scalars().all()

    owner_ids = {b.user_id for b in bots}
    owners = {}
    if owner_ids:
        owners_res = await db.execute(select(User.id, User.email).where(User.id.in_(owner_ids)))
        owners = dict(owners_res.all())

    return {
        "bots": [_serialize_bot(b, owners.get(b.user_id)) for b in bots],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.delete("/bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    bot_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(Workflow).where(Workflow.id == bot_id))
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    bot_name = bot.name

    # ondelete="CASCADE" handles history, deployment, conversations, etc.
    await db.delete(bot)
    await db.commit()
    logger.info(f"Admin {admin.email} deleted bot '{bot.name}' ({bot.id})")
    await audit_service.record(
        db, Action.ADMIN_BOT_DELETE, actor=admin, request=request,
        target_type="workflow", target_id=bot_id, target_label=bot_name,
    )
    return None
