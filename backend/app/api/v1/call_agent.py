"""
ThunderBots AI Call Agent API — Phone Number Setup & Verification
NEW (Voice AI Part 2)

Scope of this module, precisely:
  - Add / list / remove phone numbers on the current user's account.
  - Send a verification code (OTP / SMS / Call) and verify it.
  - Connect / disconnect / reconnect a phone number.
  - An `is_enabled` readiness toggle, gated on the number being verified
    and connected, for a future phase to key real AI Call Agent behavior
    off of.

Explicitly OUT of scope (left for a future part):
  - Placing or receiving any real phone call.
  - Any binding between a phone number and a Workflow/Builder/Runtime.
  - Any change to the existing chat/campaign/channel logic.

Authenticated, owner-scoped throughout — reuses the exact same
get_current_user dependency (app.core.auth) and rate_limiter dependency
(app.core.rate_limit, from the security audit) already used across the
rest of the API. No new auth mechanism, no new rate-limiting mechanism.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.models.phone_number import PhoneNumber, PhoneVerificationCode
from app.services import phone_verification_service as verification

router = APIRouter()
logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r'^\+[1-9]\d{7,14}$')

# Same class of per-IP protection already applied to /auth/2fa/verify and
# /auth/verify-email — sending or checking a code is a sensitive,
# brute-forceable action even though it's behind auth.
_send_code_rate_limit = Depends(rate_limiter("phone_send_code", limit=5, window_seconds=300))
_verify_code_rate_limit = Depends(rate_limiter("phone_verify_code", limit=10, window_seconds=300))


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class PhoneNumberCreate(BaseModel):
    phone_number: str = Field(..., min_length=8, max_length=20)
    label: Optional[str] = Field(default="", max_length=100)

    @field_validator("phone_number")
    @classmethod
    def _normalize_phone(cls, v: str) -> str:
        digits = re.sub(r'[^\d+]', '', v.strip())
        if not digits.startswith('+'):
            digits = '+' + digits
        if not _PHONE_RE.match(digits):
            raise ValueError(
                "Enter a valid phone number in international format, e.g. +14155551234"
            )
        return digits


class SendCodeRequest(BaseModel):
    method: str = Field(..., pattern="^(otp|sms|call)$")


class VerifyCodeRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=8)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_owned_number(number_id: str, db: AsyncSession, current_user: User) -> PhoneNumber:
    result = await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id))
    number = result.scalar_one_or_none()
    if not number:
        raise HTTPException(status_code=404, detail="Phone number not found")
    if str(number.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this phone number")
    return number


async def _latest_code(number_id: str, db: AsyncSession) -> Optional[PhoneVerificationCode]:
    result = await db.execute(
        select(PhoneVerificationCode)
        .where(PhoneVerificationCode.phone_number_id == number_id)
        .order_by(PhoneVerificationCode.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _serialize(number: PhoneNumber) -> dict:
    return {
        "id": number.id,
        "phone_number": number.phone_number,
        "label": number.label,
        "status": number.status,
        "verification_method": number.verification_method,
        "is_connected": number.is_connected,
        "is_enabled": number.is_enabled,
        "last_verified_at": number.last_verified_at.isoformat() if number.last_verified_at else None,
        "last_error": number.last_error,
        "disconnected_at": number.disconnected_at.isoformat() if number.disconnected_at else None,
        "created_at": number.created_at.isoformat() if number.created_at else None,
        "updated_at": number.updated_at.isoformat() if number.updated_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Routes — CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/phone-numbers")
async def list_phone_numbers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PhoneNumber)
        .where(PhoneNumber.user_id == current_user.id)
        .order_by(PhoneNumber.created_at.asc())
    )
    return [_serialize(n) for n in result.scalars().all()]


@router.post("/phone-numbers", status_code=status.HTTP_201_CREATED)
async def add_phone_number(
    payload: PhoneNumberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(PhoneNumber).where(
            PhoneNumber.user_id == current_user.id,
            PhoneNumber.phone_number == payload.phone_number,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This phone number is already on your account")

    number = PhoneNumber(
        user_id=current_user.id,
        phone_number=payload.phone_number,
        label=payload.label or "",
        status="pending",
        is_connected=True,
        is_enabled=False,
    )
    db.add(number)
    await db.commit()
    await db.refresh(number)
    return _serialize(number)


@router.delete("/phone-numbers/{number_id}")
async def delete_phone_number(
    number_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = await _get_owned_number(number_id, db, current_user)
    await db.delete(number)
    await db.commit()
    return {"deleted": True}


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Verification
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/phone-numbers/{number_id}/send-code")
async def send_code(
    number_id: str,
    payload: SendCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rl=_send_code_rate_limit,
):
    number = await _get_owned_number(number_id, db, current_user)

    if number.status == "verified" and number.is_connected:
        raise HTTPException(
            status_code=400,
            detail="This phone number is already verified. Disconnect it first to re-verify.",
        )

    code = verification.generate_code()
    verification_code = PhoneVerificationCode(
        phone_number_id=number.id,
        code_hash=verification.hash_code(code),
        method=payload.method,
        expires_at=verification.code_expiry(),
    )
    db.add(verification_code)

    try:
        await verification.send_verification_code(number.phone_number, code, payload.method)
    except verification.DeliveryError as e:
        number.last_error = str(e)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    number.status = "pending"
    number.verification_method = payload.method
    number.last_error = None
    await db.commit()
    await db.refresh(number)
    return _serialize(number)


@router.post("/phone-numbers/{number_id}/verify")
async def verify_code(
    number_id: str,
    payload: VerifyCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rl=_verify_code_rate_limit,
):
    number = await _get_owned_number(number_id, db, current_user)
    latest = await _latest_code(number.id, db)

    if not latest or latest.used_at is not None:
        raise HTTPException(
            status_code=400,
            detail="No pending verification code for this number. Request a new one.",
        )

    now = datetime.now(timezone.utc)
    if latest.expires_at < now:
        number.status = "expired"
        number.last_error = "The verification code expired before it was confirmed."
        await db.commit()
        raise HTTPException(status_code=400, detail="This code has expired. Request a new one.")

    from app.config import settings as app_settings
    max_attempts = app_settings.PHONE_VERIFICATION_MAX_ATTEMPTS

    if latest.attempts >= max_attempts:
        number.status = "failed"
        number.last_error = "Too many incorrect attempts."
        await db.commit()
        raise HTTPException(status_code=400, detail="Too many incorrect attempts. Request a new code.")

    if not verification.verify_code_hash(payload.code, latest.code_hash):
        latest.attempts += 1
        if latest.attempts >= max_attempts:
            number.status = "failed"
            number.last_error = "Too many incorrect attempts."
        await db.commit()
        remaining = max(max_attempts - latest.attempts, 0)
        raise HTTPException(
            status_code=400,
            detail=f"Incorrect code. {remaining} attempt(s) remaining." if remaining else "Too many incorrect attempts. Request a new code.",
        )

    latest.used_at = now
    number.status = "verified"
    number.last_verified_at = now
    number.last_error = None
    number.is_connected = True
    await db.commit()
    await db.refresh(number)
    return _serialize(number)


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Connection lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/phone-numbers/{number_id}/disconnect")
async def disconnect_phone_number(
    number_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = await _get_owned_number(number_id, db, current_user)
    number.is_connected = False
    number.is_enabled = False
    number.disconnected_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(number)
    return _serialize(number)


@router.post("/phone-numbers/{number_id}/reconnect")
async def reconnect_phone_number(
    number_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = await _get_owned_number(number_id, db, current_user)
    if number.status != "verified":
        raise HTTPException(
            status_code=400,
            detail="This number must be verified before it can be reconnected.",
        )
    number.is_connected = True
    number.disconnected_at = None
    await db.commit()
    await db.refresh(number)
    return _serialize(number)


# ─────────────────────────────────────────────────────────────────────────────
# Routes — AI Call Agent readiness toggle (no call automation wired yet)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/phone-numbers/{number_id}/enable")
async def enable_call_agent(
    number_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = await _get_owned_number(number_id, db, current_user)
    if number.status != "verified" or not number.is_connected:
        raise HTTPException(
            status_code=400,
            detail="Verify and connect this phone number before enabling AI Call Agent features.",
        )
    number.is_enabled = True
    await db.commit()
    await db.refresh(number)
    return _serialize(number)


@router.post("/phone-numbers/{number_id}/disable")
async def disable_call_agent(
    number_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = await _get_owned_number(number_id, db, current_user)
    number.is_enabled = False
    await db.commit()
    await db.refresh(number)
    return _serialize(number)
