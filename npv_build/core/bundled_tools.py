"""Resolve native helper executables embedded in frozen release bundles."""

from __future__ import annotations

import sys
from pathlib import Path

HELPER_NAMES = frozenset({"npv-inject", "npv-photomode", "npv-tweakdb"})


def bundled_tool_path(name: str) -> Path | None:
    """Return a helper shipped by PyInstaller, or ``None`` in a source checkout."""
    if name not in HELPER_NAMES:
        raise ValueError(f"Unknown bundled helper: {name}")

    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root:
        return None

    executable = f"{name}.exe" if sys.platform == "win32" else name
    candidate = Path(bundle_root) / "npv_helpers" / executable
    return candidate if candidate.is_file() else None
