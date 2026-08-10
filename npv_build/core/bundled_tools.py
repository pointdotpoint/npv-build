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
    # Each helper is published into its own subdirectory so managed assemblies
    # (System.Text.Json, etc.) are not clobbered across helpers.
    candidate = Path(bundle_root) / "npv_helpers" / name / executable
    if candidate.is_file():
        return candidate
    # Legacy flat layout (pre-2.1.3): npv_helpers/<exe>
    legacy = Path(bundle_root) / "npv_helpers" / executable
    return legacy if legacy.is_file() else None
