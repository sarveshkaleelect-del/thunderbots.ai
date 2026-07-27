"""
SECURITY FIX: SVG uploads can carry an executable payload (<script>,
on*="..." event handlers, javascript: URIs, <foreignObject> with embedded
HTML). Both the node-media upload (api/v1/workflows.py) and the branding
asset upload (api/v1/deploy.py) accept .svg alongside png/jpg/webp and serve
the result back from the same origin as a static file — if a user is
tricked into opening an uploaded SVG's URL directly (rather than it only
ever being used as an <img> source), an inline script would execute in the
API's origin. This is a lightweight content check (not a full sanitizer):
legitimate SVGs render exactly as before; only files with active-content
markers are rejected, extension/size limits are unchanged.
"""
import re

_SVG_DANGER_PATTERNS = (
    re.compile(rb"<\s*script", re.IGNORECASE),
    re.compile(rb"\son\w+\s*=", re.IGNORECASE),          # onload=, onclick=, ...
    re.compile(rb"javascript\s*:", re.IGNORECASE),
    re.compile(rb"<\s*foreignobject", re.IGNORECASE),
    re.compile(rb"<\s*iframe", re.IGNORECASE),
)


def is_svg_content_safe(content: bytes) -> bool:
    """Returns False if the SVG contains any active-content marker."""
    return not any(p.search(content) for p in _SVG_DANGER_PATTERNS)
