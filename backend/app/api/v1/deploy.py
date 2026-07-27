"""
ThunderBots Deploy API v6.4
FIX v4: Static routes (/live/{slug}, /embed/{slug}) moved BEFORE dynamic
     route (/{workflow_id}) so FastAPI matches them correctly.

NEW v6.4 — Production Deploy Experience:
 - Deploy Branding (bot name/logo/avatar/welcome copy/browser title/favicon/theme+accent color)
 - Deploy Page Customization (background, bubbles, typography, radius, shadow, glass, dark/light)
 - Secure logo/asset upload (png/jpg/svg/webp), served from /uploads
 - Deploy URL rename without breaking existing deployments (slug changes, id is stable)
 - Deployment Settings (show logo/name/timestamp/typing/restart/powered-by, sound, uploads, markdown, autoscroll)
 - Embed Widget config (launcher icon/color/size/position/radius/animation/greeting)
 - Draft state lives on Workflow.branding/design/chat_settings/widget_config so the builder's
   live preview never needs a publish; publish() snapshots the draft onto Deployment.
"""
import os
import re
import json
import html as html_lib
import uuid
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.core.file_validation import is_svg_content_safe
from app.models.user import User
from app.models.workflow import Workflow, Deployment
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "svg", "webp"}
ALLOWED_ASSET_FIELDS = {
    "logo", "avatar", "favicon", "background_image", "launcher_icon",
}

# ── Sensible defaults so the frontend always has something to render ──────────
DEFAULT_BRANDING = {
    "bot_name": "My Chatbot",
    "logo_url": None,
    "avatar_url": None,
    "welcome_title": "Hi there! 👋",
    "welcome_description": "Ask me anything, I'm happy to help.",
    "browser_title": None,
    "favicon_url": None,
    "theme_color": "#6366f1",
    "accent_color": "#818cf8",
}
DEFAULT_DESIGN = {
    "background_color": "#070708",
    "background_gradient": None,
    "background_image": None,
    "bot_bubble_color": "#161616",
    "user_bubble_color": "#6366f1",
    "font_family": "Inter, system-ui, sans-serif",
    "font_size": 15,
    "border_radius": 16,
    "shadows": True,
    "glassmorphism": False,
    "mode": "dark",  # 'dark' | 'light'
}
DEFAULT_CHAT_SETTINGS = {
    "show_bot_logo": True,
    "show_bot_name": True,
    "show_timestamp": False,
    "show_typing_indicator": True,
    "show_restart_button": True,
    "show_powered_by": True,
    "enable_sound": False,
    "enable_file_upload": False,
    "enable_markdown": True,
    "enable_auto_scroll": True,
    # Voice Responses (additive — lives inside the existing chat_settings
    # JSONB bucket, so no migration/schema change is required).
    # response_mode: 'text_only' | 'voice_text' | 'voice_only'
    # provider:      'browser' | 'gemini' | 'elevenlabs' | 'azure_speech' | 'google_tts'
    # gender:        preference used to auto-pick a voice when voice_id is unset
    # allow_mute:    whether end users see the Speaker ON/OFF control at all
    # default_state: initial Speaker state shown to end users ('on' | 'off')
    "voice": {
        "enabled": False,
        "response_mode": "text_only",
        "provider": "browser",
        "voice_id": None,
        "gender": "neutral",
        "allow_mute": True,
        "default_state": "on",
    },
}
DEFAULT_WIDGET_CONFIG = {
    "launcher_icon": None,
    "launcher_color": "#6366f1",
    "size": "medium",       # 'small' | 'medium' | 'large'
    "position": "bottom-right",
    "border_radius": 16,
    "animation": "pop",     # 'pop' | 'slide' | 'fade' | 'none'
    "initial_greeting": "👋 Need help? Chat with us!",
}


# ── Output sanitization for the server-rendered embed widget ─────────────────
# SECURITY FIX: branding/design fields (bot_name, logo_url, font_family,
# colors, border_radius, ...) are free-form user input (BrandingUpdate takes
# arbitrary dicts, unvalidated) and were previously interpolated directly into
# the HTML/CSS/<script> of GET /embed/{slug} — a fully public, unauthenticated
# route. That allowed stored XSS: a workflow owner could set e.g.
# branding.bot_name to a <script> payload that would execute in every
# visitor's browser when the embed widget loaded. These helpers constrain
# every value to a safe shape (or fall back to the existing default) before
# it is placed into HTML text, an HTML attribute, inline CSS, or a <script>
# string literal — no visible behavior changes for legitimate values.
_HEX_OR_NAMED_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9.,%\s]+\)|[a-zA-Z]+)$")
_FONT_FAMILY_RE = re.compile(r"^[A-Za-z0-9 ,'\"\-]{1,120}$")


def _safe_color(value, default: str) -> str:
    if isinstance(value, str) and _HEX_OR_NAMED_COLOR_RE.match(value.strip()):
        return value.strip()
    return default


def _safe_font(value, default: str) -> str:
    if isinstance(value, str) and _FONT_FAMILY_RE.match(value.strip()):
        return value.strip()
    return default


def _safe_radius(value, default: int = 16) -> int:
    try:
        return max(0, min(64, int(value)))
    except (TypeError, ValueError):
        return default


def _safe_url(value):
    """Only allow http(s) URLs (or None) for src="" attributes; anything else
    (e.g. javascript:) is dropped."""
    if isinstance(value, str) and re.match(r"^https?://", value.strip(), re.IGNORECASE):
        return value.strip()
    return None


def _esc(value) -> str:
    """HTML-escape for text nodes and attribute values."""
    return html_lib.escape(str(value), quote=True)


def _merged(draft: dict | None, defaults: dict) -> dict:
    merged = {**defaults, **(draft or {})}
    # One extra level of merging for nested-dict defaults (currently just
    # chat_settings.voice): a bot saved before new Voice Responses fields
    # existed has a partial voice dict on disk, and a naive top-level merge
    # would silently drop the new keys (allow_mute, provider, ...) instead
    # of falling back to their defaults.
    for key, default_val in defaults.items():
        if isinstance(default_val, dict):
            draft_val = (draft or {}).get(key)
            merged[key] = {**default_val, **draft_val} if isinstance(draft_val, dict) else default_val
    return merged


class DeployRequest(BaseModel):
    slug:         Optional[str]  = None
    embed_config: Optional[dict] = None


class BrandingUpdate(BaseModel):
    branding:      Optional[dict] = None
    design:        Optional[dict] = None
    chat_settings: Optional[dict] = None
    widget_config: Optional[dict] = None


class SlugUpdate(BaseModel):
    slug: str


# ── FIX: Static routes FIRST, dynamic routes AFTER ────────────────────────────

@router.get("/live/{slug}/config")
async def get_live_config(slug: str, db: AsyncSession = Depends(get_db)):
    """Public — no auth. Returns full deployed config for the public chat page / widget."""
    cache  = CacheService()
    cached = await cache.get(f"deploy:{slug}")
    if cached:
        return cached

    result = await db.execute(
        select(Deployment).where(
            Deployment.slug      == slug,
            Deployment.is_active == True,  # noqa: E712
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Bot not found or not published")

    data = {
        "workflow_id":   str(dep.workflow_id),
        "slug":          dep.slug,
        "branding":      _merged(dep.branding, DEFAULT_BRANDING),
        "design":        _merged(dep.design, DEFAULT_DESIGN),
        "chat_settings": _merged(dep.chat_settings, DEFAULT_CHAT_SETTINGS),
        "embed_config":  _merged(dep.embed_config, DEFAULT_WIDGET_CONFIG),
    }
    await cache.set(f"deploy:{slug}", data, ttl=300)
    return data


@router.get("/embed/{slug}", response_class=HTMLResponse)
async def embed_widget(slug: str, db: AsyncSession = Depends(get_db)):
    """Returns a self-contained, branded HTML chat widget for iframing."""
    api_url = settings.APP_API_URL
    ws_url  = api_url.replace("http://", "ws://").replace("https://", "wss://")

    result = await db.execute(
        select(Deployment).where(Deployment.slug == slug, Deployment.is_active == True)  # noqa: E712
    )
    dep = result.scalar_one_or_none()
    branding = _merged(dep.branding if dep else None, DEFAULT_BRANDING)
    design   = _merged(dep.design if dep else None, DEFAULT_DESIGN)
    cs       = _merged(dep.chat_settings if dep else None, DEFAULT_CHAT_SETTINGS)

    is_light = design.get("mode") == "light"
    theme   = _safe_color(branding.get("theme_color"), DEFAULT_BRANDING["theme_color"])
    bg      = _safe_color(design.get("background_color"), "#ffffff" if is_light else "#070708")
    fg      = "#0a0a0a" if is_light else "#ffffff"
    bot_bg  = _safe_color(design.get("bot_bubble_color"), "#f2f2f5" if is_light else "#161616")
    user_bg = _safe_color(design.get("user_bubble_color"), theme)
    radius  = _safe_radius(design.get("border_radius", 16))
    font    = _safe_font(design.get("font_family"), "Inter, system-ui, sans-serif")
    glass   = design.get("glassmorphism")
    logo    = _safe_url(branding.get("logo_url") or branding.get("avatar_url"))
    bot_name = str(branding.get("bot_name") or "Chatbot")[:200]
    powered = "" if not cs.get("show_powered_by", True) else '<div id="pwr">Powered by ThunderBots</div>'
    header_logo = f'<img src="{_esc(logo)}" id="hlogo"/>' if (logo and cs.get("show_bot_logo", True)) else ""
    header_name = _esc(bot_name) if cs.get("show_bot_name", True) else ""
    safe_title = _esc(bot_name)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{safe_title}</title>
<style>
@keyframes tbFadeUp{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes tbBlink{{0%,80%,100%{{opacity:.2}}40%{{opacity:1}}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:{font};background:{bg};color:{fg};height:100vh;display:flex;flex-direction:column;animation:tbFadeUp .25s ease both}}
#hdr{{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid rgba(127,127,127,.15);flex-shrink:0}}
#hlogo{{width:22px;height:22px;border-radius:6px;object-fit:cover}}
#hname{{font-size:13px;font-weight:600}}
#messages{{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}}
.msg{{max-width:85%;padding:10px 14px;border-radius:{radius}px;font-size:14px;line-height:1.5;word-break:break-word;animation:tbFadeUp .18s ease both}}
.user{{align-self:flex-end;background:{user_bg};color:#fff;border-bottom-right-radius:4px}}
.bot{{align-self:flex-start;background:{bot_bg};{'backdrop-filter:blur(10px);' if glass else ''}border-bottom-left-radius:4px;color:{fg}dd}}
.sys{{align-self:center;font-size:11px;color:{fg}55;font-style:italic}}
#footer{{padding:12px;border-top:1px solid rgba(127,127,127,.15);display:flex;gap:8px}}
#inp{{flex:1;background:{bot_bg};border:1px solid rgba(127,127,127,.2);border-radius:{max(radius-4,6)}px;padding:10px 14px;color:{fg};font-size:14px;outline:none;transition:border-color .15s}}
#inp:focus{{border-color:{theme}}}
#btn{{background:{theme};border:none;border-radius:{max(radius-4,6)}px;padding:10px 18px;color:#fff;cursor:pointer;font-size:14px;font-weight:600;transition:transform .12s,opacity .12s}}
#btn:hover{{transform:translateY(-1px)}}
#btn:disabled{{opacity:.4;cursor:not-allowed;transform:none}}
#start{{display:block;margin:auto;margin-top:35%;background:{theme};border:none;border-radius:{max(radius-4,6)}px;padding:12px 28px;color:#fff;cursor:pointer;font-size:14px;font-weight:600;transition:transform .12s}}
#start:hover{{transform:translateY(-1px) scale(1.02)}}
#pwr{{text-align:center;font-size:10px;opacity:.35;padding:6px 0 2px}}
.dot{{display:inline-block;width:6px;height:6px;border-radius:50%;background:{fg}55;animation:tbBlink 1.4s infinite both;margin:0 2px}}
.dot:nth-child(2){{animation-delay:.2s}}.dot:nth-child(3){{animation-delay:.4s}}
.choice-btn{{transition:background .15s,border-color .15s}}
</style>
</head>
<body>
<div id="hdr">{header_logo}<span id="hname">{header_name}</span></div>
<div id="messages"><button id="start" onclick="go()">Start Chat</button></div>
<div id="footer" style="display:none">
  <input id="inp" placeholder="Type a message…" disabled
         onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();send()}}"/>
  <button id="btn" disabled onclick="send()">Send</button>
</div>
{powered}
<script>
const SLUG={json.dumps(slug)},API={json.dumps(api_url)},WS={json.dumps(ws_url)};
let ws,buf=null,busy=false;
const msgs=document.getElementById('messages');
const inp=document.getElementById('inp');
const btn=document.getElementById('btn');
function add(cls,txt){{const d=document.createElement('div');d.className='msg '+cls;if(txt)d.textContent=txt;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;return d;}}
function setBusy(v){{busy=v;btn.disabled=v||!inp.value.trim();inp.disabled=v;document.querySelectorAll('.choice-btn').forEach(b=>b.disabled=v);}}
function addChoices(choices){{
  const wrap=document.createElement('div');
  wrap.style.cssText='display:flex;flex-wrap:wrap;gap:8px;margin-top:4px;align-self:flex-start;max-width:90%';
  choices.forEach(c=>{{
    const b=document.createElement('button');
    b.textContent=c.label;b.className='choice-btn';
    b.style.cssText='font-size:13px;padding:7px 12px;border-radius:{max(radius-6,8)}px;border:1px solid {theme}55;background:transparent;color:{theme};cursor:pointer';
    b.onclick=()=>{{ if(!busy){{ send(c.label); }} }};
    wrap.appendChild(b);
  }});
  msgs.appendChild(wrap);msgs.scrollTop=msgs.scrollHeight;
}}
async function go(){{
  document.getElementById('start').remove();
  document.getElementById('footer').style.display='flex';
  try{{
    const cfg=await fetch(API+'/api/v1/deploy/live/'+SLUG+'/config').then(r=>{{if(!r.ok)throw new Error('Bot not found or not published');return r.json();}});
    ws=new WebSocket(WS+'/ws/chat/'+cfg.workflow_id);
    ws.onopen=()=>{{setBusy(false);}};
    ws.onmessage=(e)=>{{
      let d; try{{d=JSON.parse(e.data);}}catch(_){{return;}}
      if(d.type==='token'){{if(!buf)buf=add('bot','');buf.textContent+=d.content;msgs.scrollTop=msgs.scrollHeight;}}
      else if(d.type==='done'){{buf=null;setBusy(false);}}
      else if(d.type==='message'){{
        if(d.content)add('bot',d.content);
        if(d.choices&&d.choices.length)addChoices(d.choices);
        setBusy(false);
      }}
      else if(d.type==='connected'){{setBusy(false);}}
      else if(d.type==='ended'){{setBusy(false);}}
      else if(d.type==='error'){{add('sys','Error: '+(d.content||'Something went wrong'));setBusy(false);buf=null;}}
    }};
    ws.onerror=()=>{{add('sys','Connection error — check that the backend is reachable.');setBusy(false);}};
    ws.onclose=()=>{{setBusy(true);btn.disabled=true;inp.disabled=true;add('sys','Disconnected');}};
  }}catch(e){{add('sys','Failed to start chat: '+(e.message||'Unknown error'));}}
}}
function send(text){{
  const m=(text!==undefined?text:inp.value).trim();
  if(!m||!ws||ws.readyState!==1||busy)return;
  add('user',m);ws.send(JSON.stringify({{message:m}}));inp.value='';
  setBusy(true);
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


# ── Dynamic routes AFTER static routes ────────────────────────────────────────

@router.get("/{workflow_id}")
async def get_deployment(
    workflow_id:  str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    wf = await db.execute(
        select(Workflow.id).where(
            Workflow.id      == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    if not wf.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workflow not found")

    result = await db.execute(
        select(Deployment).where(Deployment.workflow_id == workflow_id)
    )
    dep = result.scalar_one_or_none()
    if not dep:
        return {"deployed": False, "workflow_id": workflow_id}

    return _serialize(dep)


@router.get("/{workflow_id}/branding")
async def get_branding(
    workflow_id:  str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """Returns the DRAFT branding/design/chat_settings/widget_config for live preview.
    This is independent of publish state — edits here never need a Publish click
    to show up in the builder's live preview."""
    wf_result = await db.execute(
        select(Workflow).where(
            Workflow.id      == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "workflow_id":   workflow_id,
        "branding":      _merged(workflow.branding, DEFAULT_BRANDING),
        "design":        _merged(workflow.design, DEFAULT_DESIGN),
        "chat_settings": _merged(workflow.chat_settings, DEFAULT_CHAT_SETTINGS),
        "widget_config": _merged(workflow.widget_config, DEFAULT_WIDGET_CONFIG),
    }


@router.put("/{workflow_id}/branding")
async def update_branding(
    workflow_id:  str,
    payload:      BrandingUpdate,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """Partial-merge update of draft branding/design/chat_settings/widget_config.
    Called on every debounced change from the Deploy panel for instant preview."""
    wf_result = await db.execute(
        select(Workflow).where(
            Workflow.id      == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if payload.branding is not None:
        workflow.branding = {**(workflow.branding or {}), **payload.branding}
    if payload.design is not None:
        workflow.design = {**(workflow.design or {}), **payload.design}
    if payload.chat_settings is not None:
        workflow.chat_settings = {**(workflow.chat_settings or {}), **payload.chat_settings}
    if payload.widget_config is not None:
        workflow.widget_config = {**(workflow.widget_config or {}), **payload.widget_config}

    workflow.updated_at = datetime.now(timezone.utc)
    await db.commit()

    # If already published, keep the live site in sync automatically too —
    # branding/design changes should not require a full republish.
    dep_result = await db.execute(
        select(Deployment).where(Deployment.workflow_id == workflow_id)
    )
    dep = dep_result.scalar_one_or_none()
    if dep and dep.is_active:
        dep.branding      = workflow.branding
        dep.design        = workflow.design
        dep.chat_settings = workflow.chat_settings
        dep.embed_config  = workflow.widget_config
        dep.updated_at    = datetime.now(timezone.utc)
        await db.commit()
        cache = CacheService()
        await cache.delete(f"deploy:{dep.slug}")

    return {
        "workflow_id":   workflow_id,
        "branding":      _merged(workflow.branding, DEFAULT_BRANDING),
        "design":        _merged(workflow.design, DEFAULT_DESIGN),
        "chat_settings": _merged(workflow.chat_settings, DEFAULT_CHAT_SETTINGS),
        "widget_config": _merged(workflow.widget_config, DEFAULT_WIDGET_CONFIG),
    }


@router.post("/{workflow_id}/assets")
async def upload_brand_asset(
    workflow_id:  str,
    field:        str          = Form(...),
    file:         UploadFile   = File(...),
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """Secure upload for logo / avatar / favicon / background image / launcher icon.
    Accepts PNG, JPG, SVG, WEBP. Stored under UPLOAD_DIR/branding/{workflow_id}/
    and served back from the /uploads static mount, then wired automatically
    into workflow.branding / workflow.design / workflow.widget_config."""
    wf_result = await db.execute(
        select(Workflow).where(
            Workflow.id      == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if field not in ALLOWED_ASSET_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unknown asset field '{field}'")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_IMAGE_EXT:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Allowed: PNG, JPG, SVG, WEBP",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")

    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_BRANDING_ASSET_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File size {size_mb:.1f}MB exceeds {settings.MAX_BRANDING_ASSET_SIZE_MB}MB limit",
        )

    if suffix == "svg" and not is_svg_content_safe(content):
        raise HTTPException(
            status_code=400,
            detail="This SVG contains active content (script/event handlers) and can't be uploaded",
        )

    asset_dir = os.path.join(settings.UPLOAD_DIR, "branding", workflow_id)
    os.makedirs(asset_dir, exist_ok=True)

    filename = f"{field}-{uuid.uuid4().hex[:10]}.{suffix}"
    disk_path = os.path.join(asset_dir, filename)
    with open(disk_path, "wb") as f:
        f.write(content)

    url = f"{settings.APP_API_URL}/uploads/branding/{workflow_id}/{filename}"

    # Auto-wire the uploaded asset into the right draft config bucket
    field_to_bucket_key = {
        "logo":             ("branding", "logo_url"),
        "avatar":           ("branding", "avatar_url"),
        "favicon":          ("branding", "favicon_url"),
        "background_image": ("design", "background_image"),
        "launcher_icon":    ("widget_config", "launcher_icon"),
    }
    bucket, key = field_to_bucket_key[field]
    current = getattr(workflow, bucket) or {}
    setattr(workflow, bucket, {**current, key: url})
    workflow.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"field": field, "url": url}


@router.put("/{workflow_id}/slug")
async def rename_slug(
    workflow_id:  str,
    payload:      SlugUpdate,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """Rename the deploy URL without breaking the existing deployment —
    the Deployment row (and workflow_id it points to) is preserved, only
    the slug column changes, so history/analytics tied to the deployment id
    stay intact."""
    wf_result = await db.execute(
        select(Workflow).where(
            Workflow.id      == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    dep_result = await db.execute(
        select(Deployment).where(Deployment.workflow_id == workflow_id)
    )
    dep = dep_result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="This bot hasn't been published yet")

    new_slug = _make_slug(payload.slug)
    if not new_slug:
        raise HTTPException(status_code=400, detail="Invalid deploy name")

    if new_slug != dep.slug:
        conflict = await db.execute(
            select(Deployment.id).where(
                Deployment.slug        == new_slug,
                Deployment.workflow_id != workflow_id,
            )
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"'{new_slug}' is already taken")

        old_slug = dep.slug
        dep.slug = new_slug
        dep.updated_at = datetime.now(timezone.utc)
        await db.commit()

        cache = CacheService()
        await cache.delete(f"deploy:{old_slug}")
        await cache.delete(f"deploy:{new_slug}")

    return _serialize(dep)


@router.post("/{workflow_id}/publish")
async def publish_workflow(
    workflow_id:  str,
    payload:      DeployRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    wf_result = await db.execute(
        select(Workflow).where(
            Workflow.id      == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not any(n.get("type") == "start" for n in (workflow.nodes or [])):
        raise HTTPException(
            status_code=400,
            detail="Workflow must contain a Start node before publishing",
        )

    dep_result = await db.execute(
        select(Deployment).where(Deployment.workflow_id == workflow_id)
    )
    dep = dep_result.scalar_one_or_none()

    # Deploy name only participates in slug generation on first publish, or
    # when explicitly provided — republishing never silently changes the URL.
    slug = _make_slug(payload.slug or (dep.slug if dep else workflow.name))

    conflict = await db.execute(
        select(Deployment.id).where(
            Deployment.slug        == slug,
            Deployment.workflow_id != workflow_id,
        )
    )
    if conflict.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    embed_cfg = payload.embed_config or workflow.widget_config or {}
    now       = datetime.now(timezone.utc)

    if dep:
        dep.slug              = slug
        dep.is_active         = True
        dep.deployed_nodes    = workflow.nodes    or []
        dep.deployed_edges    = workflow.edges    or []
        dep.deployed_settings = workflow.settings or {}
        dep.embed_config      = embed_cfg
        dep.branding          = workflow.branding or {}
        dep.design            = workflow.design or {}
        dep.chat_settings     = workflow.chat_settings or {}
        dep.updated_at        = now
    else:
        dep = Deployment(
            workflow_id=workflow_id,
            user_id=current_user.id,
            slug=slug,
            deployed_nodes=workflow.nodes    or [],
            deployed_edges=workflow.edges    or [],
            deployed_settings=workflow.settings or {},
            embed_config=embed_cfg,
            branding=workflow.branding or {},
            design=workflow.design or {},
            chat_settings=workflow.chat_settings or {},
        )
        db.add(dep)

    workflow.status = "published"
    await db.commit()
    await db.refresh(dep)

    cache = CacheService()
    await cache.delete(f"workflow:{workflow_id}")
    await cache.delete(f"deploy:{dep.slug}")
    await cache.delete(f"deployment:{workflow_id}")  # FIX: invalidate WS public-snapshot cache too

    return _serialize(dep)


@router.post("/{workflow_id}/unpublish")
async def unpublish_workflow(
    workflow_id:  str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    wf_result = await db.execute(
        select(Workflow).where(
            Workflow.id      == workflow_id,
            Workflow.user_id == current_user.id,
        )
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    dep_result = await db.execute(
        select(Deployment).where(Deployment.workflow_id == workflow_id)
    )
    dep = dep_result.scalar_one_or_none()
    if dep:
        dep.is_active   = False
        workflow.status = "draft"
        await db.commit()
        cache = CacheService()
        await cache.delete(f"deploy:{dep.slug}")
        await cache.delete(f"workflow:{workflow_id}")
        await cache.delete(f"deployment:{workflow_id}")  # FIX: invalidate WS public-snapshot cache too

    return {"published": False, "workflow_id": workflow_id}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_slug(name: str) -> str:
    slug = (name or "").lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+',       '-', slug)
    slug = re.sub(r'-+',           '-', slug).strip('-')
    return slug[:60] or "bot"


def _serialize(dep: Deployment) -> dict:
    api_url  = settings.APP_API_URL
    base_url = settings.APP_BASE_URL

    def esc(v) -> str:
        return str(v).replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

    return {
        "id":            str(dep.id),
        "workflow_id":   str(dep.workflow_id),
        "slug":          dep.slug,
        "is_active":     dep.is_active,
        "embed_config":  _merged(dep.embed_config, DEFAULT_WIDGET_CONFIG),
        "branding":      _merged(dep.branding, DEFAULT_BRANDING),
        "design":        _merged(dep.design, DEFAULT_DESIGN),
        "chat_settings": _merged(dep.chat_settings, DEFAULT_CHAT_SETTINGS),
        "share_url":     f"{base_url}/chat/{dep.slug}",
        "share_url_alt": f"{base_url}/b/{dep.slug}",
        "embed_snippet": (
            f'<iframe src="{api_url}/api/v1/deploy/embed/{dep.slug}" '
            f'width="400" height="600" frameborder="0" '
            f'style="border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.12)"></iframe>'
        ),
        "widget_script": (
            f'<script src="{api_url}/widget.js" data-slug="{esc(dep.slug)}" '
            f'data-position="{esc((dep.embed_config or {}).get("position", "bottom-right"))}" '
            f'data-color="{esc((dep.embed_config or {}).get("launcher_color", "#6366f1"))}" '
            f'data-size="{esc((dep.embed_config or {}).get("size", "medium"))}" '
            f'data-radius="{esc((dep.embed_config or {}).get("border_radius", 16))}" '
            f'data-animation="{esc((dep.embed_config or {}).get("animation", "pop"))}" '
            f'data-greeting="{esc((dep.embed_config or {}).get("initial_greeting", ""))}" '
            f'async></script>'
        ),
        "deployed_at": dep.deployed_at.isoformat() if dep.deployed_at else None,
        "updated_at":  dep.updated_at.isoformat()  if dep.updated_at  else None,
    }
