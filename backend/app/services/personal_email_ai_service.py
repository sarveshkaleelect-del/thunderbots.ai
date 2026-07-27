"""
ThunderBots Personal Email AI Assistant — AI Service (NEW — Part 1)

All AI calls for the Personal Email module go through the EXISTING AI
Engine provider resolution — app.services.ai_engine.resolve_agent_provider
/ get_provider_for_user / validate_model_for_provider, the identical chain
already used by api/v1/campaigns.py's "AI rewrite" endpoint — using each
provider's `complete()` method (system + messages -> plain text). No new
provider classes, no new API-key storage, and no change to app/engine/*.

Every function below returns a plain Python dict/str and never raises for
"the AI produced something a bit off" — model output is defensively
parsed with sane fallbacks so a malformed JSON response degrades the
result rather than 500ing the request. It DOES let ProviderError /
ValueError propagate (no API key configured, invalid key, quota, etc.) so
callers can surface the same actionable errors campaigns.py already does.

Part 2 additions (NEW — additive only): `classify_email()` (auto-category +
smart labels + spam/phishing screening, one combined call so a sync run
doesn't need a second AI round-trip per message) and
`suggest_follow_up()` (a short nudge draft for a sent message that looks
unanswered). Same `_llm()` plumbing, same defensive-parsing conventions.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.services.ai_engine import (
    get_provider_for_user, resolve_agent_provider, validate_model_for_provider,
)

logger = logging.getLogger(__name__)

VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_SENTIMENTS = {"positive", "neutral", "negative"}
VALID_STYLES = {"professional", "friendly", "short"}
VALID_CATEGORIES = {"work", "personal", "finance", "promotions", "social", "updates", "spam", "other"}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text).rstrip("`").strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        match = _JSON_BLOCK_RE.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:  # noqa: BLE001
                return None
    return None


async def _llm(user_id: str, system: str, prompt: str, *, temperature: float = 0.4, max_tokens: int = 700) -> str:
    provider_id = await resolve_agent_provider(None, user_id)
    llm = await get_provider_for_user(provider_id, user_id)
    model, _ = validate_model_for_provider(provider_id, None)
    result = await llm.complete(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
    )
    return (result or "").strip()


def _truncate(text: Optional[str], limit: int = 6000) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n[…truncated…]"


ANALYSIS_SYSTEM_PROMPT = (
    "You are an assistant that analyzes a single personal email for a busy "
    "professional. Read the email and return ONLY a JSON object (no "
    "preamble, no markdown fences) with EXACTLY these keys: "
    '"summary" (1-2 plain-English sentences capturing what the email is '
    'about), "priority" (one of "low", "medium", "high", "urgent"), '
    '"sentiment" (one of "positive", "neutral", "negative" — the emotional '
    'tone of the email), "deadline" (a short human-readable date/deadline '
    'mentioned in the email, or null if none is mentioned), "tasks" (a '
    'JSON array of short strings — concrete action items the recipient '
    'needs to do, empty array if none), "action_required" (boolean — true '
    "if the recipient is expected to reply or act). Be concise and factual."
)


async def analyze_email(user_id: str, *, subject: str, sender: str, body: str) -> dict:
    """Summarize + classify one email. Returns a dict matching the
    PersonalEmailMessage.ai_* columns, always fully populated (with safe
    defaults if the model's JSON was malformed)."""
    prompt = (
        f"From: {sender}\nSubject: {subject}\n\nBody:\n{_truncate(body)}"
    )
    raw = await _llm(user_id, ANALYSIS_SYSTEM_PROMPT, prompt, temperature=0.2, max_tokens=500)
    parsed = _extract_json(raw) or {}

    priority = str(parsed.get("priority") or "medium").lower()
    if priority not in VALID_PRIORITIES:
        priority = "medium"
    sentiment = str(parsed.get("sentiment") or "neutral").lower()
    if sentiment not in VALID_SENTIMENTS:
        sentiment = "neutral"
    tasks = parsed.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    tasks = [str(t).strip() for t in tasks if str(t).strip()][:10]
    deadline = parsed.get("deadline")
    deadline = str(deadline).strip() if deadline else None
    summary = str(parsed.get("summary") or "").strip() or "No summary available."
    action_required = bool(parsed.get("action_required")) if "action_required" in parsed else bool(tasks)

    return {
        "ai_summary": summary,
        "ai_priority": priority,
        "ai_sentiment": sentiment,
        "ai_deadline": deadline,
        "ai_tasks": tasks,
        "ai_action_required": action_required,
    }


DRAFT_SYSTEM_PROMPTS = {
    "professional": (
        "You write professional, polished email reply drafts. Be clear, "
        "courteous, and businesslike. Return ONLY the reply body text — no "
        "subject line, no preamble, no explanation, no markdown."
    ),
    "friendly": (
        "You write warm, friendly, conversational email reply drafts while "
        "still being clear and appropriate. Return ONLY the reply body "
        "text — no subject line, no preamble, no explanation, no markdown."
    ),
    "short": (
        "You write very short, to-the-point email reply drafts — 2-4 "
        "sentences maximum. Return ONLY the reply body text — no subject "
        "line, no preamble, no explanation, no markdown."
    ),
}


async def generate_reply_draft(
    user_id: str, *, subject: str, sender: str, body: str, style: str,
    instructions: Optional[str] = None, previous_draft: Optional[str] = None,
) -> str:
    style = style if style in VALID_STYLES else "professional"
    system = DRAFT_SYSTEM_PROMPTS[style]
    prompt_parts = [
        f"Original email — From: {sender}\nSubject: {subject}\n\n{_truncate(body, 3000)}",
    ]
    if previous_draft:
        prompt_parts.append(f"\nPrevious draft to improve/regenerate:\n{_truncate(previous_draft, 1500)}")
    if instructions:
        prompt_parts.append(f"\nAdditional instructions: {instructions}")
    prompt_parts.append("\nWrite the reply now.")
    prompt = "\n".join(prompt_parts)
    draft = await _llm(user_id, system, prompt, temperature=0.6, max_tokens=500)
    return draft or "Unable to generate a draft right now — please try again."


TRANSLATE_SYSTEM_PROMPT = (
    "You are a precise translator. Translate the given email reply draft "
    "into the requested target language, preserving tone, meaning, and "
    "formatting. Return ONLY the translated text — no preamble, no "
    "explanation, no quotes."
)


async def translate_text(user_id: str, *, text: str, target_language: str) -> str:
    prompt = f"Target language: {target_language}\n\nText:\n{_truncate(text, 3000)}"
    translated = await _llm(user_id, TRANSLATE_SYSTEM_PROMPT, prompt, temperature=0.2, max_tokens=700)
    return translated or text


DIGEST_SYSTEM_PROMPT = (
    "You write a short daily email digest for a busy professional, "
    "summarizing their inbox activity. Given a JSON list of already-"
    "analyzed emails (subject, sender, summary, priority, action_required, "
    "deadline), write a concise 3-5 sentence digest in plain English "
    "highlighting what most needs attention today, any deadlines, and a "
    "general sense of inbox volume/tone. Return ONLY the digest text — no "
    "preamble, no markdown, no headers."
)


async def generate_digest_summary(user_id: str, *, emails: list) -> str:
    if not emails:
        return "No new emails to summarize for this period."
    payload = json.dumps(emails[:50], ensure_ascii=False)
    prompt = f"Emails:\n{_truncate(payload, 8000)}"
    digest = await _llm(user_id, DIGEST_SYSTEM_PROMPT, prompt, temperature=0.4, max_tokens=400)
    return digest or "Digest could not be generated for this period."


# ─────────────────────────────────────────────────────────────────────────────
# Part 2 — auto-categorize / smart labels / spam & phishing detection
# ─────────────────────────────────────────────────────────────────────────────

CLASSIFY_SYSTEM_PROMPT = (
    "You screen and categorize a single personal email for a busy "
    "professional's inbox. Return ONLY a JSON object (no preamble, no "
    "markdown fences) with EXACTLY these keys: "
    '"category" (one of "work", "personal", "finance", "promotions", '
    '"social", "updates", "spam", "other"), "labels" (a JSON array of 1-4 '
    "short lowercase smart-label strings, e.g. \"invoice\", \"newsletter\", "
    '"meeting-request", "receipt" — no spaces, use hyphens), '
    '"is_spam" (boolean — true if this looks like spam, a scam, or a '
    'phishing attempt), "spam_score" (integer 0-100, confidence that this '
    'is spam/phishing; 0 if clearly legitimate), "spam_reason" (a short '
    'one-sentence explanation if is_spam or spam_score > 40, else null). '
    "Phishing signals to weigh heavily: urgent demands for credentials/"
    "payment/gift cards, mismatched or spoofed sender domains, suspicious "
    "links, generic greetings combined with high-pressure tactics. Be "
    "conservative — do not mark ordinary marketing email as spam unless it "
    "also shows scam/phishing signals."
)


async def classify_email(user_id: str, *, subject: str, sender: str, body: str) -> dict:
    """Auto-categorize + smart-label + spam/phishing screen one email in a
    single AI call. Returns a dict matching the new PersonalEmailMessage
    Part 2 columns, always fully populated with safe defaults."""
    prompt = f"From: {sender}\nSubject: {subject}\n\nBody:\n{_truncate(body, 4000)}"
    raw = await _llm(user_id, CLASSIFY_SYSTEM_PROMPT, prompt, temperature=0.1, max_tokens=350)
    parsed = _extract_json(raw) or {}

    category = str(parsed.get("category") or "other").lower()
    if category not in VALID_CATEGORIES:
        category = "other"
    labels = parsed.get("labels")
    if not isinstance(labels, list):
        labels = []
    labels = [str(l).strip().lower() for l in labels if str(l).strip()][:6]

    is_spam = bool(parsed.get("is_spam"))
    try:
        spam_score = int(parsed.get("spam_score") or 0)
    except (TypeError, ValueError):
        spam_score = 0
    spam_score = max(0, min(100, spam_score))
    if spam_score >= 60:
        is_spam = True
    spam_reason = parsed.get("spam_reason")
    spam_reason = str(spam_reason).strip() if spam_reason else None
    if is_spam and category == "other":
        category = "spam"

    return {
        "category": category,
        "labels": labels,
        "is_spam": is_spam,
        "spam_score": spam_score,
        "spam_reason": spam_reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Part 2 — AI follow-up suggestions for unanswered sent messages
# ─────────────────────────────────────────────────────────────────────────────

FOLLOW_UP_SYSTEM_PROMPT = (
    "You write short, polite follow-up nudge emails for a busy "
    "professional whose earlier message hasn't received a reply yet. Keep "
    "it brief (2-4 sentences), friendly but not pushy, and reference that "
    "this is a gentle follow-up. Return ONLY the follow-up body text — no "
    "subject line, no preamble, no explanation, no markdown."
)


async def suggest_follow_up(user_id: str, *, subject: str, recipient: str, original_body: str, days_since_sent: int) -> str:
    prompt = (
        f"Original message — To: {recipient}\nSubject: {subject}\n\n"
        f"{_truncate(original_body, 2500)}\n\n"
        f"It has been {days_since_sent} day(s) with no reply. Write a short follow-up."
    )
    suggestion = await _llm(user_id, FOLLOW_UP_SYSTEM_PROMPT, prompt, temperature=0.5, max_tokens=250)
    return suggestion or "Just following up on my previous email — happy to answer any questions whenever you get a chance."
