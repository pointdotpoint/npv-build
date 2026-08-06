"""Golden-image comparison for appearance previews. Pure Pillow, no repo goldens."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops


def rms_diff(a: Path, b: Path) -> float:
    """Root-mean-square pixel difference over RGBA, 0.0..255.0.

    Returns +inf when dimensions differ — resizing would hide layout bugs.
    """
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != ib.size:
            return float("inf")
        diff = ImageChops.difference(ia.convert("RGBA"), ib.convert("RGBA"))
        histogram = diff.histogram()
    total_sq = 0
    count = 0
    for channel in range(4):
        for value, n in enumerate(histogram[channel * 256 : (channel + 1) * 256]):
            total_sq += n * value * value
            count += n
    return math.sqrt(total_sq / count) if count else 0.0


def compare(candidate: Path, golden: Path, threshold: float = 3.0) -> dict:
    """Compare candidate image to golden, return match dict."""
    rms = rms_diff(candidate, golden)
    if rms == float("inf"):
        return {"match": False, "rms": rms, "reason": "dimension mismatch"}
    if rms > threshold:
        return {"match": False, "rms": rms, "reason": f"rms {rms:.2f} > threshold {threshold}"}
    return {"match": True, "rms": rms, "reason": ""}
