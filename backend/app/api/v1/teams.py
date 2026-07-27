"""
ThunderBots Team Workspace API (NEW)

Purely additive module — mirrors the conventions already established in
api/v1/admin.py (thin serializers, get_current_user reused as-is from the
existing auth flow, no changes to any other router/model).

Team Workspace is intentionally separate from Personal Workspace:
- Workflow.user_id (Personal Workspace ownership) is never read or written
  here.
- A user can belong to any number of teams (team_members has no per-user
  uniqueness across teams, only within one team).
- Nothing here is polled or preloaded — every route is called on-demand by
  the frontend only once the Team Workspace UI is actually opened.

Role hierarchy (most -> least privileged): owner > admin > editor > viewer.
  - owner:  full access, including deleting the team and transferring/
            changing any member's role, including other admins.
  - admin:  manage team (invite/remove members, change editor/viewer roles)
            and manage workflows association-level actions surfaced to the
            Team Workspace UI. Cannot remove the owner or delete the team.
  - editor: create/edit workflows surfaced within the team context.
  - viewer: read-only.
"""
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.team import Team, TeamMember, TeamInvite, TEAM_ROLES
from app.services import email_service, audit_service
from app.services.audit_service import Action

router = APIRouter()
logger = logging.getLogger(__name__)

# Roles that may manage team membership / invite / change roles.
MANAGE_ROLES = ("owner", "admin")
# Roles allowed to create/edit workflows in the team context.
EDIT_ROLES = ("owner", "admin", "editor")


# ── Schemas ──────────────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = Field(default="viewer")


class RoleUpdate(BaseModel):
    role: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _serialize_team(t: Team, my_role: Optional[str] = None, member_count: Optional[int] = None) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "my_role": my_role,
        "member_count": member_count,
    }


def _serialize_member(m: TeamMember, user: Optional[User]) -> dict:
    return {
        "id": m.id,
        "team_id": m.team_id,
        "user_id": m.user_id,
        "email": user.email if user else None,
        "name": user.name if user else None,
        "role": m.role,
        "joined_at": m.joined_at.isoformat() if m.joined_at else None,
    }


def _serialize_invite(i: TeamInvite) -> dict:
    return {
        "id": i.id,
        "team_id": i.team_id,
        "email": i.email,
        "role": i.role,
        "status": i.status,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
    }


async def _get_membership(db: AsyncSession, team_id: str, user_id: str) -> Optional[TeamMember]:
    result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def require_membership(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TeamMember:
    """Any role — used for read-only team endpoints. Raises 404 (not 403) if
    the user isn't a member, so team existence isn't leaked to non-members."""
    membership = await _get_membership(db, team_id, user.id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return membership


async def require_manage_role(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TeamMember:
    """owner/admin only — invite, remove members, change roles."""
    membership = await require_membership(team_id, db, user)
    if membership.role not in MANAGE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or Owner access required")
    return membership


async def require_owner_role(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TeamMember:
    membership = await require_membership(team_id, db, user)
    if membership.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    return membership


# ── Teams: create / list / detail / delete ──────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team = Team(name=body.name, created_by=user.id)
    db.add(team)
    await db.flush()  # obtain team.id before creating the owner membership row

    membership = TeamMember(team_id=team.id, user_id=user.id, role="owner")
    db.add(membership)
    await db.commit()
    await db.refresh(team)

    logger.info(f"User {user.email} created team '{team.name}' ({team.id})")
    await audit_service.record(
        db, Action.TEAM_CREATE, actor=user, request=request,
        target_type="team", target_id=team.id, target_label=team.name,
    )
    return _serialize_team(team, my_role="owner", member_count=1)


@router.get("")
async def list_my_teams(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Only the caller's own memberships — one query, no N+1. This is the
    only call made when the Team Workspace nav entry is opened; nothing about
    a team's members/invites is fetched until a specific team is opened."""
    result = await db.execute(
        select(Team, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
        .order_by(Team.created_at.desc())
    )
    rows = result.all()
    team_ids = [t.id for t, _ in rows]
    counts: dict[str, int] = {}
    if team_ids:
        count_rows = await db.execute(
            select(TeamMember.team_id, func.count())
            .where(TeamMember.team_id.in_(team_ids))
            .group_by(TeamMember.team_id)
        )
        counts = dict(count_rows.all())

    return {
        "teams": [_serialize_team(t, my_role=role, member_count=counts.get(t.id, 0)) for t, role in rows]
    }


@router.get("/{team_id}")
async def get_team(
    membership: TeamMember = Depends(require_membership),
    db: AsyncSession = Depends(get_db),
):
    team = await db.get(Team, membership.team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    count = (await db.execute(
        select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team.id)
    )).scalar_one()
    return _serialize_team(team, my_role=membership.role, member_count=count)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: str,
    request: Request,
    _owner: TeamMember = Depends(require_owner_role),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    team_name = team.name
    # ondelete="CASCADE" on team_members/team_invites handles the rest.
    await db.delete(team)
    await db.commit()
    logger.info(f"User {user.email} deleted team '{team.name}' ({team_id})")
    await audit_service.record(
        db, Action.TEAM_DELETE, actor=user, request=request,
        target_type="team", target_id=team_id, target_label=team_name,
    )
    return None


# ── Members ──────────────────────────────────────────────────────────────────

@router.get("/{team_id}/members")
async def list_members(
    membership: TeamMember = Depends(require_membership),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == membership.team_id)
        .order_by(TeamMember.joined_at.asc())
    )
    return {"members": [_serialize_member(m, u) for m, u in result.all()]}


@router.patch("/{team_id}/members/{member_id}/role")
async def update_member_role(
    team_id: str,
    member_id: str,
    body: RoleUpdate,
    manager: TeamMember = Depends(require_manage_role),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.role not in TEAM_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Role must be one of {TEAM_ROLES}")

    target = await db.get(TeamMember, member_id)
    if not target or target.team_id != team_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target.role == "owner":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The team owner's role cannot be changed")
    if body.role == "owner":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ownership transfer isn't supported here")
    # Admins may only manage editor/viewer members — not other admins.
    if manager.role == "admin" and target.role == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can change an admin's role")

    target.role = body.role
    await db.commit()
    await db.refresh(target)
    target_user = await db.get(User, target.user_id)
    logger.info(f"User {user.email} set role={body.role} for member {member_id} in team {team_id}")
    return _serialize_member(target, target_user)


@router.delete("/{team_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: str,
    member_id: str,
    manager: TeamMember = Depends(require_manage_role),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = await db.get(TeamMember, member_id)
    if not target or target.team_id != team_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target.role == "owner":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The team owner cannot be removed")
    if manager.role == "admin" and target.role == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can remove an admin")

    await db.delete(target)
    await db.commit()
    logger.info(f"User {user.email} removed member {member_id} from team {team_id}")
    return None


@router.delete("/{team_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    membership: TeamMember = Depends(require_membership),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The owner cannot leave the team. Delete the team or transfer ownership instead.",
        )
    await db.delete(membership)
    await db.commit()
    logger.info(f"User {user.email} left team {membership.team_id}")
    return None


# ── Invites ──────────────────────────────────────────────────────────────────

@router.post("/{team_id}/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    team_id: str,
    body: InviteCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    _manager: TeamMember = Depends(require_manage_role),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.role not in TEAM_ROLES or body.role == "owner":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role for an invite")

    email = body.email.lower()

    # Already a member?
    existing_user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing_user:
        already_member = await _get_membership(db, team_id, existing_user.id)
        if already_member:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This person is already on the team")

    # Already invited (pending)?
    pending = (await db.execute(
        select(TeamInvite).where(
            TeamInvite.team_id == team_id, TeamInvite.email == email, TeamInvite.status == "pending"
        )
    )).scalar_one_or_none()
    if pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An invite is already pending for this email")

    invite = TeamInvite(
        team_id=team_id,
        email=email,
        role=body.role,
        invited_by=user.id,
        token=secrets.token_urlsafe(32),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    logger.info(f"User {user.email} invited {email} to team {team_id} as {body.role}")

    # NEW (Email & Notification Service): send the invite email in the
    # background so it never adds latency to — or can fail — this request.
    team = await db.get(Team, team_id)
    background_tasks.add_task(
        email_service.send_team_invite_email,
        email,
        team.name if team else "a team",
        user.name,
        body.role,
        invite.token,
    )
    audit_service.record_bg(
        background_tasks, Action.TEAM_INVITE_CREATE, actor=user, request=request,
        target_type="team_invite", target_id=invite.id, target_label=email,
        metadata={"team_id": team_id, "role": body.role},
    )
    return _serialize_invite(invite)


@router.get("/{team_id}/invites")
async def list_invites(
    manager: TeamMember = Depends(require_manage_role),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TeamInvite).where(TeamInvite.team_id == manager.team_id).order_by(TeamInvite.created_at.desc())
    )
    return {"invites": [_serialize_invite(i) for i in result.scalars().all()]}


@router.delete("/{team_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    team_id: str,
    invite_id: str,
    request: Request,
    _manager: TeamMember = Depends(require_manage_role),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    invite = await db.get(TeamInvite, invite_id)
    if not invite or invite.team_id != team_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    invite_email = invite.email
    await db.delete(invite)
    await db.commit()
    await audit_service.record(
        db, Action.TEAM_INVITE_REVOKE, actor=user, request=request,
        target_type="team_invite", target_id=invite_id, target_label=invite_email,
        metadata={"team_id": team_id},
    )
    return None


@router.get("/invites/pending")
async def list_my_pending_invites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Invites addressed to the current user's email, awaiting acceptance."""
    result = await db.execute(
        select(TeamInvite, Team.name)
        .join(Team, Team.id == TeamInvite.team_id)
        .where(TeamInvite.email == user.email.lower(), TeamInvite.status == "pending")
        .order_by(TeamInvite.created_at.desc())
    )
    return {
        "invites": [
            {**_serialize_invite(i), "team_name": team_name}
            for i, team_name in result.all()
        ]
    }


@router.post("/invites/{token}/accept")
async def accept_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    invite = (await db.execute(select(TeamInvite).where(TeamInvite.token == token))).scalar_one_or_none()
    if not invite or invite.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found or already used")
    if invite.email != user.email.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This invite was sent to a different email address")

    existing = await _get_membership(db, invite.team_id, user.id)
    if not existing:
        db.add(TeamMember(team_id=invite.team_id, user_id=user.id, role=invite.role))
    invite.status = "accepted"
    from datetime import datetime, timezone
    invite.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    team = await db.get(Team, invite.team_id)
    logger.info(f"User {user.email} accepted invite to team {invite.team_id}")
    await audit_service.record(
        db, Action.TEAM_INVITE_ACCEPT, actor=user,
        target_type="team", target_id=invite.team_id, target_label=team.name if team else None,
        metadata={"role": invite.role},
    )
    return _serialize_team(team, my_role=invite.role)


@router.post("/invites/{token}/decline")
async def decline_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    invite = (await db.execute(select(TeamInvite).where(TeamInvite.token == token))).scalar_one_or_none()
    if not invite or invite.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found or already used")
    if invite.email != user.email.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This invite was sent to a different email address")

    invite.status = "revoked"
    from datetime import datetime, timezone
    invite.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return None
