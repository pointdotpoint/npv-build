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
from .core.errors import NpvError
from .gui_backend import check_dependencies
from .gui_backend import preview_save as preview_save_file
from .gui_logic.discovery import list_saves as discover_saves
from .gui_logic.modmanager import (
    install_mod as mm_install_mod,
)
from .gui_logic.modmanager import (
    list_mods as mm_list_mods,
)
from .gui_logic.modmanager import (
    uninstall_mod as mm_uninstall_mod,
)
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

    def list_saves(self) -> list[dict]:
        return [
            {"path": str(e.path), "name": e.name, "mtime": e.mtime,
             "thumbnail": str(e.thumbnail) if e.thumbnail else None}
            for e in discover_saves()
        ]

    def preview_save(self, path: str) -> dict:
        try:
            info = preview_save_file(Path(path))
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True, **info}

    def _settings_for_mods(self) -> tuple[Path, Path]:
        s = load_settings()
        output_root = Path(s.output_dir) if s.output_dir else Path.home() / "npv_builds"
        if not s.game_dir:
            raise NpvError("Game directory not configured.",
                           remediation="Set it in Settings.")
        return output_root, Path(s.game_dir)

    def list_mods(self) -> list[dict]:
        output_root, game_dir = self._settings_for_mods()
        return [
            {"mod_id": m.mod_id, "archive_path": str(m.archive_path),
             "installed": m.installed}
            for m in mm_list_mods(output_root, game_dir)
        ]

    def _find_mod(self, mod_id: str):
        output_root, game_dir = self._settings_for_mods()
        for m in mm_list_mods(output_root, game_dir):
            if m.mod_id == mod_id:
                return m, game_dir
        raise NpvError(f"Mod '{mod_id}' not found.",
                       remediation="Refresh the library.")

    def install_mod(self, mod_id: str) -> dict:
        try:
            entry, game_dir = self._find_mod(mod_id)
            mm_install_mod(entry, game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True}

    def uninstall_mod(self, mod_id: str) -> dict:
        try:
            entry, game_dir = self._find_mod(mod_id)
            mm_uninstall_mod(entry, game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True}
