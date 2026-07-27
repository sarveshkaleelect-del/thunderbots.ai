"""
ThunderBots Telegram Delivery Helper
NEW (Telegram Integration — Part 3).

Best-effort bridge that lets the EXISTING Live Agent module
(app.services.live_agent_service.send_agent_message) deliver a human
agent's reply back to Telegram, keyed only off `session_id` — the same id
Live Agent already tracks for every channel (web_chat/whatsapp/telegram/…).

Looks up the TelegramSubscriber + TelegramChannel for that session,
decrypts the bot token, and sends the message through the existing
TelegramBotClient (app.services.telegram_service). Never raises — a
delivery failure here must never break the Live Agent dashboard or the
human agent's ability to keep chatting.

Guardrail (required by the integration spec): a message is only ever sent
to a chat_id that is on file as a TelegramSubscriber AND still
`is_subscribed` — i.e. only to people who have themselves started the bot
conversation and have not blocked it. There is no path here (or anywhere
else in the Telegram module) that can target an arbitrary chat_id.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.telegram import TelegramChannel, TelegramSubscriber
from app.services import telegram_service as tg

logger = logging.getLogger(__name__)


async def deliver_agent_reply(session_id: str, content: str) -> bool:
    """Sends a human agent's reply to the Telegram subscriber owning this
    session_id. Returns True on a confirmed send, False otherwise (never
    raises)."""
    if not session_id or not content or not content.strip():
        return False
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TelegramSubscriber, TelegramChannel)
                .join(TelegramChannel, TelegramChannel.id == TelegramSubscriber.channel_id)
                .where(TelegramSubscriber.session_id == session_id)
            )
            row = result.first()
            if not row:
                # Not a Telegram session — nothing to do (e.g. web_chat/whatsapp).
                return False
            subscriber, channel = row

            # Never send to someone who hasn't started the bot / has blocked it.
            if not subscriber.is_subscribed:
                logger.info(f"Telegram agent-reply skipped — chat_id={subscriber.chat_id} unsubscribed")
                return False
            if not channel.is_enabled:
                logger.info(f"Telegram agent-reply skipped — channel={channel.id} disabled")
                return False

            client = tg.client_from_channel(channel)
            try:
                await client.send_message(subscriber.chat_id, content)
            except tg.TelegramAPIError as e:
                if e.error_code == 403:
                    subscriber.is_subscribed = False
                channel.messages_failed_count += 1
                await db.commit()
                logger.warning(f"Telegram agent-reply delivery failed channel={channel.id}: {e}")
                return False

            channel.messages_sent_count += 1
            await db.commit()
            return True
    except Exception as e:  # noqa: BLE001 — delivery must never break Live Agent
        logger.error(f"Telegram agent-reply delivery error session={session_id}: {e}", exc_info=True)
        return False
