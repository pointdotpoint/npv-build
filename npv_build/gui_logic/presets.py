"""Vendored default-V presets for from-scratch builds."""

from __future__ import annotations

import json
from pathlib import Path

from ..core.errors import NpvError

RIGS = ("pwa", "pma")


def _preset_dir() -> Path:
    return Path(__file__).parents[1] / "data" / "presets"


def preset_path(rig: str) -> Path:
    return _preset_dir() / f"default_v_{rig}.json"


def list_presets() -> list[dict]:
    return [{"rig": rig, "available": preset_path(rig).is_file()} for rig in RIGS]


def load_preset(rig: str) -> dict:
    if rig not in RIGS:
        raise NpvError(
            f"Unknown body rig: {rig}",
            remediation="Valid rigs: pwa, pma.",
        )

    path = preset_path(rig)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise NpvError(
            f"No default-V preset for {rig} is bundled yet.",
            remediation=(
                "Generate it with scripts/make_preset.py from an untouched default-V save."
            ),
        ) from error
    except ValueError as error:
        raise NpvError(
            f"Preset for {rig} is corrupt: {error}",
            remediation="Regenerate it with scripts/make_preset.py.",
        ) from error
