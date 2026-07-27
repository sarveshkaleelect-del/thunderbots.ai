"""
ThunderBots AI Call Agent — Call Summary Service (NEW, Voice AI Part 4)

Generates a short summary of a completed call from its transcript. Reuses
the exact same AI-provider resolution already established for every other
AI-generated text in this codebase — app.services.ai_engine.resolve_agent_provider
+ get_provider_for_user (the same pair app/engine/node_handlers/__init__.py
and app/services/thunderguide_service.py already call through) — so this
never becomes a second, parallel way of picking a provider/key.

Best-effort only: a summary is a "nice to have" analytics artifact, never a
call-blocking or call-affecting operation. Any failure here is logged and
swallowed — it must never raise into the call-ending code path.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.call import Call, CallTranscriptEntry
from app.services import ai_engine

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS_FOR_SUMMARY = 12_000  # keep the summarization prompt small/cheap
SUMMARY_SYSTEM_PROMPT = (
    "You summarize phone call transcripts for a business's call log. Write 2-4 "
    "concise sentences covering: why the caller called, what was discussed or "
    "resolved, and any follow-up/action needed. Plain prose, no headers, no "
    "bullet points, no preamble like 'Summary:' — just the sentences."
)


def _format_transcript(entries: list[CallTranscriptEntry]) -> str:
    lines = []
    for e in entries:
        if e.role == "caller":
            lines.append(f"Caller: {e.content}")
        elif e.role == "ai":
            lines.append(f"AI Agent: {e.content}")
        elif e.role == "system" and not e.content.startswith("["):
            lines.append(f"Note: {e.content}")
    text = "\n".join(lines)
    if len(text) > MAX_TRANSCRIPT_CHARS_FOR_SUMMARY:
        text = text[-MAX_TRANSCRIPT_CHARS_FOR_SUMMARY:]  # keep the most recent context
    return text


async def generate_and_store_summary(call_id: str, owner_id: str) -> Optional[str]:
    """Fetches the call's transcript, generates a short summary via the
    owner's configured AI provider, and persists it onto Call.summary.
    Returns the summary text, or None if there was nothing to summarize or
    generation failed (never raises)."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CallTranscriptEntry)
                .where(CallTranscriptEntry.call_id == call_id)
                .order_by(CallTranscriptEntry.sequence.asc())
            )
            entries = result.scalars().all()
            if not any(e.role in ("caller", "ai") for e in entries):
                logger.info(f"[call:summary] call={call_id}: no caller/AI turns to summarize, skipping")
                return None

            transcript_text = _format_transcript(entries)
            if not transcript_text.strip():
                return None

            provider_id = await ai_engine.resolve_agent_provider(None, owner_id)
            provider = await ai_engine.get_provider_for_user(provider_id, owner_id)
            summary = await provider.complete(
                system=SUMMARY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": transcript_text}],
                temperature=0.3,
                max_tokens=220,
            )
            summary = (summary or "").strip()
            if not summary:
                return None

            call_result = await db.execute(select(Call).where(Call.id == call_id))
            call = call_result.scalar_one_or_none()
            if call:
                call.summary = summary[:4000]
                await db.commit()
                logger.info(f"[call:summary] call={call_id}: summary generated ({len(summary)} chars)")
            return summary
    except Exception as e:  # noqa: BLE001 — summary generation must never break call teardown
        logger.warning(f"[call:summary] call={call_id}: summary generation failed: {e}")
        return None
