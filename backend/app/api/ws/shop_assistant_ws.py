"""
ThunderBots Smart Shop Assistant — WebSocket endpoints (NEW)

Two routes, mirroring the shape of api/ws/live_agent_ws.py:

- /ws/shop-assistant/admin/{shop_id}    Owner-only, JWT-authenticated via a
                                        `token` query param (WebSocket
                                        requests can't send an Authorization
                                        header) — same convention already
                                        used by live_agent_ws.py. Ownership
                                        is re-checked against the DB before
                                        the socket is accepted, so a token
                                        for a different owner (or a shop_id
                                        that isn't theirs) is rejected with a
                                        close, not silently subscribed.
- /ws/shop-assistant/public/{slug}      No auth — anyone with the shop's
                                        public link (i.e. anyone who scanned
                                        the QR code) can subscribe to
                                        inventory-only updates for that shop.
                                        Looked up by slug so the shop's
                                        internal id is never exposed here
                                        either.

Both are pure broadcast recipients — the client never needs to send
anything after connecting, but incoming messages are drained harmlessly (a
stray ping, etc.) so the socket doesn't error out on unexpected client input.
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.auth import verify_token
from app.models.shop_assistant import Shop
from app.services import shop_assistant_ws_manager as ws_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/shop-assistant/admin/{shop_id}")
async def shop_admin_ws(websocket: WebSocket, shop_id: str, token: str = Query(...)):
    user_id = verify_token(token)
    if not user_id:
        await websocket.close(code=4401)
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Shop).where(Shop.id == shop_id, Shop.owner_id == user_id)
        )
        shop = result.scalar_one_or_none()
    if shop is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    ws_manager.register_admin(shop_id, websocket)
    try:
        while True:
            # Admin page never needs to send anything after connecting; just
            # drain incoming frames so idle browser pings don't error out.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Shop Assistant admin WS closed for shop={shop_id}: {e}")
    finally:
        ws_manager.unregister_admin(shop_id, websocket)


@router.websocket("/shop-assistant/public/{slug}")
async def shop_public_ws(websocket: WebSocket, slug: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Shop).where(Shop.public_slug == slug))
        shop = result.scalar_one_or_none()
    if shop is None or not shop.is_active:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    ws_manager.register_public(shop.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Shop Assistant public WS closed for shop={shop.id}: {e}")
    finally:
        ws_manager.unregister_public(shop.id, websocket)
