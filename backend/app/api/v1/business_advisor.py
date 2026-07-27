"""
ThunderBots AI Business Advisor — API (NEW)

Authenticated, owner-scoped, additive on top of the existing Smart Shop
Assistant / AI Inventory Intelligence. Every route reuses
`_get_owned_shop` (mirrors shop_assistant.py's chokepoint) so one account
can never read another shop's business data.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.shop_assistant import Shop
from app.services import business_advisor_service as advisor_svc
from app.services import business_advisor_ai_service as advisor_ai_svc
from app.services import business_advisor_report_service as report_svc

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatQuestion(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


async def _get_owned_shop(db: AsyncSession, user: User, shop_id: str) -> Shop:
    result = await db.execute(select(Shop).where(Shop.id == shop_id, Shop.owner_id == user.id))
    shop = result.scalar_one_or_none()
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return shop


@router.get("/shops/{shop_id}/overview")
async def get_overview(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await advisor_svc.get_overview(db, shop_id)


@router.get("/shops/{shop_id}/recommendations")
async def get_recommendations(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return {"recommendations": await advisor_svc.get_recommendations(db, shop_id)}


@router.get("/shops/{shop_id}/predictions")
async def get_predictions(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await advisor_svc.get_predictions(db, shop_id)


@router.get("/shops/{shop_id}/alerts")
async def get_alerts(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return {"alerts": await advisor_svc.get_alerts(db, shop_id)}


@router.post("/shops/{shop_id}/chat")
async def chat(
    shop_id: str, body: ChatQuestion,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _get_owned_shop(db, user, shop_id)
    return await advisor_ai_svc.ask(db, shop_id, user.id, body.question)


@router.get("/shops/{shop_id}/daily-summary")
async def daily_summary(shop_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _get_owned_shop(db, user, shop_id)
    return await advisor_ai_svc.generate_daily_summary(db, shop_id, user.id)


@router.get("/shops/{shop_id}/reports/{period}")
async def get_report(
    shop_id: str, period: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if period not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="period must be one of: daily, weekly, monthly")
    await _get_owned_shop(db, user, shop_id)
    return await advisor_svc.get_report(db, shop_id, period)


@router.get("/shops/{shop_id}/reports/{period}/export/pdf")
async def export_report_pdf(
    shop_id: str, period: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if period not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="period must be one of: daily, weekly, monthly")
    shop = await _get_owned_shop(db, user, shop_id)
    report = await advisor_svc.get_report(db, shop_id, period)
    pdf_bytes = report_svc.build_pdf(report)
    filename = f"{shop.name.replace(' ', '_')}_{period}_business_report.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/shops/{shop_id}/reports/{period}/export/xlsx")
async def export_report_xlsx(
    shop_id: str, period: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if period not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="period must be one of: daily, weekly, monthly")
    shop = await _get_owned_shop(db, user, shop_id)
    report = await advisor_svc.get_report(db, shop_id, period)
    xlsx_bytes = report_svc.build_xlsx(report)
    filename = f"{shop.name.replace(' ', '_')}_{period}_business_report.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
