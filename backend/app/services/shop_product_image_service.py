"""
ThunderBots Smart Shop Assistant — Product Image Service (NEW)

Handles everything about turning an uploaded file into two optimized, safe,
on-disk WEBP variants:

  - validate_image_upload()   type/size/decodability validation — rejects
                               anything that isn't a real, openable raster
                               image before a single byte is written to disk.
  - process_and_store_image() auto-orients (EXIF), downsamples, and
                               re-encodes as WEBP at two sizes (display +
                               thumbnail), then writes both under
                               UPLOAD_DIR/shop_products/{shop_id}/{product_id}/
                               and returns everything needed to create the
                               ShopProductImage row.

Follows the exact same storage/serving convention as branding assets
(api/v1/deploy.py's upload_brand_asset): UPLOAD_DIR on disk, served back
from the already-mounted `/uploads` static route — no new infrastructure.

Every upload is fully re-encoded (never stored byte-for-byte as uploaded) —
this is what "compress and optimize automatically" means here, and it also
strips any embedded metadata/payload from the original file as a side
effect (Pillow re-encodes pixel data only).
"""
import io
import os
import uuid
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}
# Real content-sniffing, not just trusting the filename extension — Pillow's
# format identifier after opening the file, checked against this set.
ALLOWED_PIL_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "MPO"}  # MPO: some phone cameras tag JPEGs this way

DISPLAY_MAX_EDGE = 1400
THUMBNAIL_MAX_EDGE = 420
DISPLAY_QUALITY = 82
THUMBNAIL_QUALITY = 78

MAX_IMAGES_PER_PRODUCT = 12


class InvalidImageError(ValueError):
    pass


def validate_image_upload(filename: str, content: bytes) -> Image.Image:
    """Raises InvalidImageError with a user-facing message on any problem.
    Returns the decoded, EXIF-oriented PIL Image on success (caller re-uses
    it — no need to decode twice)."""
    if not filename:
        raise InvalidImageError("Filename is required")

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_IMAGE_EXT:
        raise InvalidImageError("Unsupported file type. Allowed: PNG, JPG, WEBP, GIF")

    if not content:
        raise InvalidImageError("File is empty")

    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_PRODUCT_IMAGE_SIZE_MB:
        raise InvalidImageError(
            f"File size {size_mb:.1f}MB exceeds {settings.MAX_PRODUCT_IMAGE_SIZE_MB}MB limit"
        )

    try:
        img = Image.open(io.BytesIO(content))
        img.verify()  # cheap structural check — raises on truncated/malformed files
        # verify() leaves the file object unusable — re-open for real decoding.
        img = Image.open(io.BytesIO(content))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise InvalidImageError("This file isn't a valid, readable image") from e

    if img.format not in ALLOWED_PIL_FORMATS:
        raise InvalidImageError("Unsupported file type. Allowed: PNG, JPG, WEBP, GIF")

    # Auto-orient using EXIF (phone photos are very commonly rotated only in
    # metadata) BEFORE we resize/measure — otherwise thumbnails can end up
    # sideways.
    img = ImageOps.exif_transpose(img)
    return img


def _resize_to_max_edge(img: Image.Image, max_edge: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / longest
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def _encode_webp(img: Image.Image, quality: int) -> bytes:
    # Flatten transparency onto white for formats that can carry alpha (PNG/
    # GIF) — WEBP supports alpha too, but a flat product photo background is
    # both smaller and safer for older WEBP renderers; keep alpha only when
    # already RGBA/LA and it's meaningfully used.
    if img.mode in ("P", "LA"):
        img = img.convert("RGBA")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=6)
    return buf.getvalue()


def process_and_store_image(
    *, shop_id: str, product_id: str, filename: str, content: bytes,
) -> dict:
    """Validates, compresses (two WEBP variants), writes to disk, and
    returns {url, thumbnail_url, width, height, file_size} ready to persist
    on a ShopProductImage row. Raises InvalidImageError on any problem —
    nothing is written to disk in that case."""
    img = validate_image_upload(filename, content)
    width, height = img.size

    display_img = _resize_to_max_edge(img, DISPLAY_MAX_EDGE)
    thumb_img = _resize_to_max_edge(img, THUMBNAIL_MAX_EDGE)

    display_bytes = _encode_webp(display_img, DISPLAY_QUALITY)
    thumb_bytes = _encode_webp(thumb_img, THUMBNAIL_QUALITY)

    asset_dir = os.path.join(settings.UPLOAD_DIR, "shop_products", shop_id, product_id)
    os.makedirs(asset_dir, exist_ok=True)

    base_name = uuid.uuid4().hex[:16]
    display_filename = f"{base_name}.webp"
    thumb_filename = f"{base_name}-thumb.webp"

    with open(os.path.join(asset_dir, display_filename), "wb") as f:
        f.write(display_bytes)
    with open(os.path.join(asset_dir, thumb_filename), "wb") as f:
        f.write(thumb_bytes)

    base_url = f"{settings.APP_API_URL}/uploads/shop_products/{shop_id}/{product_id}"
    return {
        "url": f"{base_url}/{display_filename}",
        "thumbnail_url": f"{base_url}/{thumb_filename}",
        "width": display_img.size[0],
        "height": display_img.size[1],
        "file_size": len(display_bytes),
    }


def delete_image_files(url: str, thumbnail_url: str) -> None:
    """Best-effort disk cleanup — a missing file is not an error (the DB row
    is always the source of truth for what "exists")."""
    for url_val in (url, thumbnail_url):
        try:
            rel = url_val.split("/uploads/", 1)[-1]
            disk_path = os.path.join(settings.UPLOAD_DIR, rel)
            if os.path.isfile(disk_path):
                os.remove(disk_path)
        except Exception as e:  # noqa: BLE001 — disk cleanup must never break the API response
            logger.warning(f"Shop Assistant: could not remove image file for {url_val}: {e}")
