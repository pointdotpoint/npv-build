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

from .config import get_cache_dir, load_config
from .core.errors import NpvError
from .core.platform import find_game_dirs
from .core.platform import open_folder as platform_open_folder
from .gui_backend import BuildWorker, check_dependencies, resolve_tool_paths
from .gui_backend import preview_save as preview_save_file
from .gui_logic.appearance import inspector_rows, option_lists, validate_overrides
from .gui_logic.discovery import entry_for_path
from .gui_logic.discovery import list_saves as discover_saves
from .gui_logic.modmanager import (
    delete_mod as mm_delete_mod,
)
from .gui_logic.modmanager import (
    install_mod as mm_install_mod,
)
from .gui_logic.modmanager import (
    list_mods as mm_list_mods,
)
from .gui_logic.modmanager import (
    uninstall_mod as mm_uninstall_mod,
)
from .gui_logic.overrides_store import load_overrides, save_overrides
from .gui_logic.settings import load_settings, save_settings, validate
from .gui_logic.wizard import WizardModel
from .hair_mod_helper import install_hair_mod
from .installer import auto_install_missing
from .mapping import resolve_table_key
from .part_resolver import extract_hair_components, get_index_path
from .save_parser import parse_save as parse_save_for_inspector
from .wk_cli import WolvenKit, WolvenKitConfig

logger = logging.getLogger(__name__)


def _app_version() -> str:
    try:
        return pkg_version("npv-build")
    except PackageNotFoundError:
        return "dev"


# Cache subdirectories the GUI may clear. "tools" re-downloads on next build;
# everything else is a pure cache.
_CLEARABLE_CACHE_DIRS = ("index", "bake", "bake_heb", "templates", "thumbs", "tools")


def load_part_index(patch: str) -> dict:
    """Cached part index for this patch, or {} when it was never generated.

    Never generates it here — index generation needs WolvenKit and minutes.
    The index cache is keyed by the vendored *table* key, not the raw save
    patch (e.g. save patch "2.31" shares tables with "2.13"), so resolve
    through resolve_table_key before looking up the cache path.
    """
    import json

    try:
        path = get_index_path(resolve_table_key(patch))
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _display_names() -> dict:
    import json

    p = Path(__file__).parent / "data" / "display_names.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class WebUiApi:
    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._worker: BuildWorker | None = None
        self._tool_queue: queue.Queue = queue.Queue()
        self._tool_thread = None

    def cache_info(self) -> dict:
        """Size per cache subdirectory (~/.cache/npv)."""
        cache = get_cache_dir()
        entries = []
        for sub in sorted(p for p in cache.iterdir() if p.is_dir()) if cache.is_dir() else []:
            size = sum(f.stat().st_size for f in sub.rglob("*") if f.is_file())
            entries.append({"name": sub.name, "path": str(sub), "size": size,
                            "clearable": sub.name in _CLEARABLE_CACHE_DIRS})
        return {"ok": True, "entries": entries}

    def clear_cache(self, name: str) -> dict:
        import shutil

        if name not in _CLEARABLE_CACHE_DIRS:
            return {"ok": False, "error": f"'{name}' is not a clearable cache.",
                    "remediation": ""}
        target = get_cache_dir() / name
        try:
            if target.is_dir():
                shutil.rmtree(target)
        except OSError as e:
            return {"ok": False, "error": f"Could not clear {name}: {e}",
                    "remediation": "Close any running builds and retry."}
        return {"ok": True}

    def install_tools(self) -> dict:
        """Download/install missing external tools in the background;
        progress arrives via poll_tool_events()."""
        import threading

        if self._tool_thread is not None and self._tool_thread.is_alive():
            return {"ok": True}

        def run() -> None:
            try:
                auto_install_missing(
                    lambda message, value: self._tool_queue.put(
                        ("tool_progress", {"message": message, "value": value}))
                )
                self._tool_queue.put(("tool_done", {}))
            except Exception as e:  # noqa: BLE001 - worker thread must not die silently
                logger.exception("tool install failed")
                self._tool_queue.put(("tool_error", {"message": str(e)}))

        self._tool_thread = threading.Thread(target=run, daemon=True)
        self._tool_thread.start()
        return {"ok": True}

    def poll_tool_events(self) -> list[dict]:
        events: list[dict] = []
        while True:
            try:
                kind, val = self._tool_queue.get_nowait()
            except queue.Empty:
                return events
            events.append({"kind": kind, **val})

    def get_state(self) -> dict:
        s = load_settings()
        game_dir = Path(s.game_dir) if s.game_dir else None
        return {
            "settings": vars(s),
            "default_output_root": s.output_dir or str(Path.home() / "npv_builds"),
            "deps": check_dependencies(game_dir),
            "tool_paths": resolve_tool_paths(),
            "needs_onboarding": WizardModel.needs_wizard(load_config()),
            "version": _app_version(),
        }

    def detect_game_dirs(self) -> dict:
        """Auto-detected Cyberpunk 2077 install candidates (onboarding)."""
        return {"ok": True, "dirs": [str(d) for d in find_game_dirs()]}

    def save_config(self, cfg: dict) -> dict:
        s = load_settings()
        for key, value in cfg.items():
            if hasattr(s, key):
                setattr(s, key, value)
        errors = validate(s)
        if errors:
            return {"ok": False, "errors": errors}
        try:
            save_settings(s)
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            logger.exception("save_settings failed")
            return {"ok": False, "errors": [f"Could not save settings: {e}"]}
        return {"ok": True, "errors": []}

    @staticmethod
    def _save_entry_dict(e) -> dict:
        return {"path": str(e.path), "name": e.name, "mtime": e.mtime,
                "thumbnail": str(e.thumbnail) if e.thumbnail else None,
                "patch": e.patch}

    def list_saves(self) -> list[dict]:
        return [self._save_entry_dict(e) for e in discover_saves()]

    def add_save_path(self, path: str) -> dict:
        """Register a manually chosen save file (Browse… or drag & drop)."""
        p = Path(path)
        if p.is_dir():
            p = p / "sav.dat"
        if not p.is_file():
            return {"ok": False,
                    "error": f"No save file at {path}.",
                    "remediation": "Pick the sav.dat file, or the save folder containing it."}
        return {"ok": True, "save": self._save_entry_dict(entry_for_path(p))}

    def browse_for_save(self) -> dict:
        """Open a native file dialog (desktop app only)."""
        try:
            import webview

            if not webview.windows:
                raise RuntimeError("no webview window")
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Cyberpunk save (*.dat)", "All files (*.*)"),
            )
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False,
                    "error": "File dialog is unavailable outside the desktop app.",
                    "remediation": "Drag & drop the save folder instead.",
                    "details": str(e)}
        if not result:
            return {"ok": False, "cancelled": True, "error": ""}
        return self.add_save_path(result[0])

    def preview_save(self, path: str) -> dict:
        try:
            info = preview_save_file(Path(path))
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": str(e), "remediation": ""}
        return {"ok": True, **info}

    def add_hair_mod(self, path: str, body_rig: str = "pwa") -> dict:
        """Install a CCXL/hair mod file into the game and return its token.

        The mod is a runtime dependency of the built NPV (the .app is attached
        by appearance reference), so installing into the game dir here is the
        end state, not a side effect."""
        s = load_settings()
        if not s.game_dir:
            return {"ok": False, "error": "Game directory not configured.",
                    "remediation": "Set it in Settings."}
        game_dir = Path(s.game_dir)
        try:
            token, _installed = install_hair_mod(Path(path), game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        except (ValueError, OSError) as e:
            return {"ok": False, "error": str(e),
                    "remediation": "Pick a hair mod file: .archive, .zip, .7z or .rar."}
        # Probe: does the installed mod actually carry a findable hair .app?
        # extract_hair_components pre-filters candidates by filename/.xl
        # sidecar, so this lists ~1 archive, not the whole mod dir.
        try:
            wk = WolvenKit(WolvenKitConfig(game_dir=game_dir, verbosity=0))
            _comps, src, app_depot, _app_name = extract_hair_components(
                game_dir, token, body_rig, verbosity=0, wk=wk)
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            logger.exception("hair mod probe failed")
            return {"ok": False, "error": f"Could not inspect the hair mod: {e}",
                    "remediation": "Check the file and try again."}
        if not app_depot:
            return {"ok": False,
                    "error": f"No hair appearance found in '{Path(path).name}'.",
                    "remediation": "This does not look like a CCXL/hair mod — "
                                   "pick the mod's main .archive (or its zip/7z/rar)."}
        return {"ok": True, "token": token, "source": src or "",
                "warning": "The NPV needs this hair mod to stay installed."}

    def browse_for_hair_mod(self) -> dict:
        try:
            import webview

            if not webview.windows:
                raise RuntimeError("no webview window")
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Hair mod (*.archive;*.zip;*.7z;*.rar)",
                            "All files (*.*)"),
            )
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False,
                    "error": "File dialog is unavailable outside the desktop app.",
                    "remediation": "Drag & drop the mod file instead.",
                    "details": str(e)}
        if not result:
            return {"ok": False, "cancelled": True, "error": ""}
        return self.add_hair_mod(result[0])

    def zip_info(self, output_dir: str) -> dict:
        """Describe the built mod zip in output_dir (path, size, contents)."""
        import zipfile

        zips = sorted(Path(output_dir).glob("*.zip"))
        if not zips:
            return {"ok": False, "error": f"No mod zip found in {output_dir}.",
                    "remediation": "Rebuild the mod."}
        z = zips[0]
        try:
            with zipfile.ZipFile(z) as zf:
                files = [{"name": i.filename, "size": i.file_size}
                         for i in zf.infolist()]
        except (OSError, zipfile.BadZipFile) as e:
            return {"ok": False, "error": f"Could not read {z.name}: {e}",
                    "remediation": "Rebuild the mod."}
        return {"ok": True, "zip": {"path": str(z), "size": z.stat().st_size,
                                    "files": files}}

    def open_folder(self, path: str) -> dict:
        """Open a folder in the OS file manager."""
        p = Path(path)
        if not p.is_dir():
            return {"ok": False, "error": f"Folder not found: {path}",
                    "remediation": "Rebuild the mod."}
        try:
            platform_open_folder(p)
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": f"Could not open folder: {e}",
                    "remediation": "Open it manually in your file manager."}
        return {"ok": True}

    def _settings_for_mods(self) -> tuple[Path, Path]:
        s = load_settings()
        output_root = Path(s.output_dir) if s.output_dir else Path.home() / "npv_builds"
        if not s.game_dir:
            raise NpvError("Game directory not configured.",
                           remediation="Set it in Settings.")
        return output_root, Path(s.game_dir)

    @staticmethod
    def _build_meta(entry) -> dict:
        """Rebuild metadata written by start_build; empty for older builds."""
        import json

        meta_path = entry.archive_path.parents[3] / "build_meta.json"
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def list_mods(self) -> dict:
        try:
            output_root, game_dir = self._settings_for_mods()
            mods = []
            for m in mm_list_mods(output_root, game_dir):
                meta = self._build_meta(m)
                mods.append(
                    {"mod_id": m.mod_id, "archive_path": str(m.archive_path),
                     "installed": m.installed, "built_at": m.built_at,
                     "npv_name": meta.get("npv_name"),
                     "save_path": meta.get("save_path")}
                )
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True, "mods": mods}

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

    def delete_mod(self, mod_id: str) -> dict:
        try:
            entry, game_dir = self._find_mod(mod_id)
            mm_delete_mod(entry, game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True}

    def appearance_data(self, save_path: str) -> dict:
        try:
            cc = parse_save_for_inspector(Path(save_path))
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": str(e), "remediation": ""}
        options = option_lists(load_part_index(cc.get("patch", "")),
                               cc.get("body_rig", "pwa"))
        rows = inspector_rows(cc, options, _display_names())
        categories = list(dict.fromkeys(r["category"] for r in rows))
        return {"ok": True, "rows": rows, "categories": categories,
                "overrides": load_overrides(save_path)}

    def get_overrides(self, save_path: str) -> dict:
        return {"ok": True, "overrides": load_overrides(save_path)}

    def set_overrides(self, save_path: str, overrides: dict) -> dict:
        try:
            cc = parse_save_for_inspector(Path(save_path))
            options = option_lists(load_part_index(cc.get("patch", "")),
                                   cc.get("body_rig", "pwa"))
        except Exception:  # noqa: BLE001 - index/parse problems fall back to slot-only checks
            options = {}
        problems = validate_overrides(overrides, options)
        if problems:
            return {"ok": False, "error": "; ".join(problems),
                    "remediation": "Pick values from the dropdowns."}
        save_overrides(save_path, overrides)
        return {"ok": True}

    def start_build(self, req: dict) -> dict:
        import json

        s = load_settings()
        if not s.game_dir:
            return {"ok": False, "error": "Game directory not configured.",
                    "remediation": "Set it in Settings."}
        try:
            out_dir = Path(req["output_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "build_meta.json").write_text(
                json.dumps({"npv_name": req["npv_name"],
                            "save_path": req["save_path"]}),
                encoding="utf-8",
            )
        except OSError as e:
            return {"ok": False, "error": f"Cannot write to output directory: {e}",
                    "remediation": "Check the output directory path and permissions."}
        self._worker = BuildWorker(self._queue)
        self._worker.start(
            save_path=Path(req["save_path"]),
            npv_name=req["npv_name"],
            output_dir=Path(req["output_dir"]),
            game_dir=Path(s.game_dir),
            template_cache=get_cache_dir() / "templates",
            clear_cache=bool(req.get("clear_cache", False)),
            resume=bool(req.get("resume", False)),
            cc_overrides=load_overrides(req["save_path"]),
        )
        return {"ok": True}

    def cancel_build(self) -> dict:
        if self._worker is not None:
            self._worker.cancel()
        return {"ok": True}

    def poll_events(self) -> list[dict]:
        events: list[dict] = []
        while True:
            try:
                kind, val = self._queue.get_nowait()
            except queue.Empty:
                return events
            if kind == "log":
                events.append({"kind": "log", "text": val})
            elif kind == "progress":
                events.append({"kind": "progress", "value": val})
            elif kind == "stage":
                events.append({"kind": "stage", **val})
            elif kind == "done":
                events.append({"kind": "done", "output_dir": val})
            elif kind == "error":
                events.append({"kind": "error", "message": val})
