"""JSON bridge between the pywebview frontend and gui_logic/gui_backend.

Every public method returns JSON-serializable data only. This module must
stay import-safe without a webview (it is unit-tested headless).
"""

from __future__ import annotations

import logging
import queue
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from .config import load_config
from .gui_backend import check_dependencies
from .gui_logic.settings import load_settings, save_settings, validate
from .gui_logic.wizard import WizardModel

logger = logging.getLogger(__name__)


def _app_version() -> str:
    try:
        return pkg_version("npv-build")
    except PackageNotFoundError:
        return "dev"


class WebUiApi:
    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()

    def get_state(self) -> dict:
        s = load_settings()
        game_dir = Path(s.game_dir) if s.game_dir else None
        return {
            "settings": vars(s),
            "deps": check_dependencies(game_dir),
            "needs_onboarding": WizardModel.needs_wizard(load_config()),
            "version": _app_version(),
        }

    def save_config(self, cfg: dict) -> dict:
        s = load_settings()
        for key, value in cfg.items():
            if hasattr(s, key):
                setattr(s, key, value)
        errors = validate(s)
        if errors:
            return {"ok": False, "errors": errors}
        save_settings(s)
        return {"ok": True, "errors": []}
