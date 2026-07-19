"""Per-save-file appearance overrides (spec: 'Overrides persist per-save-file
in config'). One JSON file per save under <config>/overrides/."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _overrides_dir() -> Path:
    from ..config import get_config_dir  # verified/added alongside this module

    return Path(get_config_dir()) / "overrides"


def store_path(save_path: str) -> Path:
    digest = hashlib.sha256(str(save_path).encode("utf-8")).hexdigest()[:16]
    return _overrides_dir() / f"{digest}.json"


def load_overrides(save_path: str) -> dict:
    try:
        data = json.loads(store_path(save_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_overrides(save_path: str, overrides: dict) -> None:
    p = store_path(save_path)
    if not overrides:
        p.unlink(missing_ok=True)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(overrides, indent=2, sort_keys=True), encoding="utf-8")
