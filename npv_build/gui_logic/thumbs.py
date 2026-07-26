"""Lazy, cached thumbnails for the vanilla clothing picker."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from PIL import Image, ImageOps


def _source_image(image_rel: str, images_dir: str) -> Path | None:
    root = Path(images_dir).expanduser()
    if not root.is_dir():
        return None

    relative = Path(image_rel.lstrip("/\\"))
    candidates = (root / relative.name, root / relative)
    resolved_root = root.resolve()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(resolved_root):
                continue
            if resolved.is_file():
                return resolved
        except OSError:
            continue
    return None


def thumbnail_b64(
    image_rel: str,
    images_dir: str | None,
    cache_dir: Path,
    size: int = 256,
) -> str | None:
    """Return a base64 JPEG thumbnail, or ``None`` for text-only degradation."""
    if not images_dir or size <= 0:
        return None
    source = _source_image(image_rel, images_dir)
    if source is None:
        return None

    digest = hashlib.sha256(f"{source}\0{size}".encode()).hexdigest()[:16]
    thumb_dir = cache_dir / "thumbs"
    cached = thumb_dir / f"{digest}.jpg"
    try:
        if not cached.is_file():
            thumb_dir.mkdir(parents=True, exist_ok=True)
            temporary = cached.with_suffix(".jpg.tmp")
            with Image.open(source) as original:
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.thumbnail((size, size), Image.Resampling.LANCZOS)
                image.save(temporary, "JPEG", quality=80, optimize=True)
            temporary.replace(cached)
        return base64.b64encode(cached.read_bytes()).decode("ascii")
    except OSError:
        return None
