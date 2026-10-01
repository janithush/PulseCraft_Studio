"""Low-resolution WebP asset proxies (M6 60 FPS gallery rule).

Thumbnails are downscaled with Pillow (`max 480px`, `quality 60`) so the
glass gallery scrolls full-size PNGs only on demand.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

THUMB_MAX_PX = 480
THUMB_QUALITY = 60


def make_thumbnail(source: Path, max_px: int = THUMB_MAX_PX, quality: int = THUMB_QUALITY) -> bytes:
    """Return WebP bytes for an image file. Raises FileNotFoundError/ValueError."""
    from PIL import Image

    if not source.is_file():
        raise FileNotFoundError(f"asset not found: {source}")
    with Image.open(source) as img:
        img = img.convert("RGB")
        img.thumbnail((max_px, max_px))
        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=quality)
        data = buffer.getvalue()
    logger.info("web.thumb source=%s bytes=%d", source.name, len(data))
    return data
