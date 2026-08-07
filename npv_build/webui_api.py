"""JSON bridge between the pywebview frontend and gui_logic/gui_backend.

Every public method returns JSON-serializable data only. This module must
stay import-safe without a webview (it is unit-tested headless).
"""

from __future__ import annotations

import base64
import json
import logging
import queue
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from .appearance_render import render_appearance
from .config import get_cache_dir, load_config
from .core.errors import NpvError
from .core.platform import find_game_dirs
from .core.platform import open_folder as platform_open_folder
from .gui_backend import BuildWorker, check_dependencies, resolve_tool_paths, summarize_cc
from .gui_backend import preview_save as preview_save_file
from .gui_logic.appearance import inspector_rows, option_lists, validate_overrides
from .gui_logic.clothing_catalog import (
    build_catalog_from_game,
    catalog_selection,
    catalog_source_fingerprints,
    load_catalog,
    validate_catalog_selection,
)
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
from .gui_logic.presets import list_presets as list_gui_presets
from .gui_logic.presets import load_preset
from .gui_logic.settings import load_settings, save_settings, validate
from .gui_logic.thumbs import thumbnail_b64
from .gui_logic.wizard import WizardModel
from .hair_mod_helper import install_hair_mod
from .installer import auto_install_missing
from .mapping import resolve_table_key
from .part_resolver import (
    extract_hair_components,
    get_index_path,
    hair_registration_status,
)
from .photomode import (
    runtime_dependency_status,
    thumbnail_preview_data_url,
    validate_thumbnail,
)
from .save_parser import parse_save as parse_save_for_inspector
from .wk_cli import WolvenKit, WolvenKitConfig

logger = logging.getLogger(__name__)


def list_mod_archive_apps(wk: WolvenKit, archive_path: Path) -> list[str]:
    """List depot paths of every .app file inside a specific mod archive."""
    return wk.list_archive(r".*\.app$", archive=archive_path)


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


def load_clothing_catalog() -> list[dict] | None:
    """Load the default runtime catalog through a monkeypatchable bridge seam."""
    settings = load_settings()
    expected = catalog_source_fingerprints(Path(settings.game_dir)) if settings.game_dir else None
    return load_catalog(
        get_cache_dir() / "clothing_catalog.json",
        expected_fingerprints=expected,
    )


def _split_garment_overrides(overrides: dict) -> tuple[dict, list]:
    cc_overrides = {}
    garments = []
    for slot_id, value in overrides.items():
        if slot_id.startswith("garment_"):
            garments.append(value)
        else:
            cc_overrides[slot_id] = value
    return cc_overrides, garments


def _validate_garment_overrides(overrides: dict, rig: str) -> list[str]:
    garment_rows = [
        (slot_id.removeprefix("garment_"), value)
        for slot_id, value in overrides.items()
        if slot_id.startswith("garment_")
    ]
    if not garment_rows:
        return []
    entries = load_clothing_catalog()
    problems = []
    for slot, selection in garment_rows:
        problem = validate_catalog_selection(
            selection,
            entries,
            rig,
            expected_slot=slot,
        )
        if problem:
            problems.append(f"garment_{slot}: {problem}")
    return problems


def _garment_values(cc: dict) -> dict[str, str]:
    """Human-readable current/fallback values for the four picker rows."""
    import json

    values: dict[str, str] = {}
    for item in cc.get("clothing") or []:
        slot = item.get("slot")
        if slot:
            values[slot] = item.get("name") or "Equipped garment"
    fallback_path = Path(__file__).parent / "data" / "fallback_outfit.json"
    try:
        fallback = json.loads(fallback_path.read_text())
    except (OSError, ValueError):
        fallback = {}
    for slot, item in fallback.get(cc.get("body_rig", "pwa"), {}).items():
        values.setdefault(slot, item.get("name") or "Fallback garment")
    return values


class WebUiApi:
    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._worker: BuildWorker | None = None
        self._tool_queue: queue.Queue = queue.Queue()
        self._tool_thread = None
        self._catalog_queue: queue.Queue = queue.Queue()
        self._catalog_thread = None

    def cache_info(self) -> dict:
        """Size per cache subdirectory (~/.cache/npv)."""
        cache = get_cache_dir()
        entries = []
        for sub in sorted(p for p in cache.iterdir() if p.is_dir()) if cache.is_dir() else []:
            size = sum(f.stat().st_size for f in sub.rglob("*") if f.is_file())
            entries.append(
                {
                    "name": sub.name,
                    "path": str(sub),
                    "size": size,
                    "clearable": sub.name in _CLEARABLE_CACHE_DIRS,
                }
            )
        return {"ok": True, "entries": entries}

    def clear_cache(self, name: str) -> dict:
        import shutil

        if name not in _CLEARABLE_CACHE_DIRS:
            return {"ok": False, "error": f"'{name}' is not a clearable cache.", "remediation": ""}
        target = get_cache_dir() / name
        try:
            if target.is_dir():
                shutil.rmtree(target)
        except OSError as e:
            return {
                "ok": False,
                "error": f"Could not clear {name}: {e}",
                "remediation": "Close any running builds and retry.",
            }
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
                        ("tool_progress", {"message": message, "value": value})
                    )
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

    def clothing_catalog_status(self) -> dict:
        entries = load_clothing_catalog()
        return {
            "ok": True,
            "built": entries is not None,
            "count": len(entries or []),
        }

    def build_clothing_catalog(self) -> dict:
        """Build the archive-validated catalog in a background thread."""
        import threading

        if self._catalog_thread is not None and self._catalog_thread.is_alive():
            return {"ok": True}
        settings = load_settings()
        if not settings.game_dir:
            return {
                "ok": False,
                "error": "Game directory not configured.",
                "remediation": "Set it in Settings before building the clothing catalog.",
            }
        game_dir = Path(settings.game_dir)
        clothes_path = Path(__file__).parent / "data" / "clothes.json"
        cache_path = get_cache_dir() / "clothing_catalog.json"

        def run() -> None:
            try:
                self._catalog_queue.put(
                    (
                        "catalog_progress",
                        {"message": "Indexing vanilla garment meshes…", "value": 10},
                    )
                )
                wk = WolvenKit(WolvenKitConfig(game_dir=game_dir, verbosity=0))
                entries = build_catalog_from_game(
                    game_dir,
                    wk,
                    clothes_path,
                    cache_path,
                )
                self._catalog_queue.put(("catalog_done", {"count": len(entries)}))
            except Exception as error:  # noqa: BLE001 - worker must report to the UI
                logger.exception("clothing catalog build failed")
                self._catalog_queue.put(
                    (
                        "catalog_error",
                        {
                            "message": str(error),
                            "remediation": "Check the game path and WolvenKit installation.",
                        },
                    )
                )

        self._catalog_thread = threading.Thread(target=run, daemon=True)
        self._catalog_thread.start()
        return {"ok": True}

    def poll_catalog_events(self) -> list[dict]:
        events: list[dict] = []
        while True:
            try:
                kind, value = self._catalog_queue.get_nowait()
            except queue.Empty:
                return events
            events.append({"kind": kind, **value})

    def clothing_search(
        self,
        query: str,
        slot: str | None,
        rig: str,
        limit: int = 50,
    ) -> dict:
        if rig not in {"pwa", "pma"}:
            return {
                "ok": False,
                "error": f"Unsupported body rig: {rig}",
                "remediation": "Reload the appearance screen.",
                "items": [],
            }
        entries = load_clothing_catalog()
        if entries is None:
            return {
                "ok": False,
                "error": "Clothing catalog has not been built.",
                "remediation": "Build the catalog first.",
                "items": [],
            }
        needle = str(query or "").casefold().strip()
        result = []
        for entry in entries:
            if slot and entry.get("slot") != slot:
                continue
            if needle and needle not in str(entry.get("name", "")).casefold():
                continue
            item = dict(entry)
            buildable = bool(item.get(f"buildable_{rig}"))
            item["buildable"] = buildable
            item["mesh"] = item.get(f"mesh_{rig}") if buildable else None
            item["appearance"] = item.get(f"appearance_{rig}") if buildable else None
            item["components"] = item.get(f"components_{rig}") if buildable else []
            item["selection"] = catalog_selection(item, rig)
            result.append(item)
        result.sort(
            key=lambda item: (
                not item["buildable"],
                str(item.get("name", "")).casefold(),
                str(item.get("item_id", "")),
            )
        )
        try:
            bounded_limit = max(1, min(int(limit), 200))
        except (TypeError, ValueError):
            bounded_limit = 50
        return {"ok": True, "items": result[:bounded_limit]}

    def clothing_thumb(self, image_rel: str) -> dict:
        settings = load_settings()
        return {
            "ok": True,
            "b64": thumbnail_b64(
                image_rel,
                settings.clothing_images_dir,
                get_cache_dir(),
            ),
        }

    def get_state(self) -> dict:
        s = load_settings()
        game_dir = Path(s.game_dir) if s.game_dir else None
        return {
            "settings": vars(s),
            "default_output_root": s.output_dir or str(Path.home() / "npv_builds"),
            "deps": check_dependencies(game_dir),
            "photomode_deps": runtime_dependency_status(game_dir),
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
        return {
            "path": str(e.path),
            "name": e.name,
            "mtime": e.mtime,
            "thumbnail": str(e.thumbnail) if e.thumbnail else None,
            "patch": e.patch,
        }

    def list_saves(self) -> list[dict]:
        return [self._save_entry_dict(e) for e in discover_saves()]

    def add_save_path(self, path: str) -> dict:
        """Register a manually chosen save file (Browse… or drag & drop)."""
        p = Path(path)
        if p.is_dir():
            p = p / "sav.dat"
        if not p.is_file():
            return {
                "ok": False,
                "error": f"No save file at {path}.",
                "remediation": "Pick the sav.dat file, or the save folder containing it.",
            }
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
            return {
                "ok": False,
                "error": "File dialog is unavailable outside the desktop app.",
                "remediation": "Drag & drop the save folder instead.",
                "details": str(e),
            }
        if not result:
            return {"ok": False, "cancelled": True, "error": ""}
        return self.add_save_path(result[0])

    def preview_save(self, path: str) -> dict:
        try:
            info = preview_save_file(Path(path))
        except NpvError as e:
            return {"ok": False, "error": e.user_message, "remediation": e.remediation or ""}
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": str(e), "remediation": ""}
        return {"ok": True, **info}

    def list_presets(self) -> dict:
        return {"ok": True, "presets": list_gui_presets()}

    def preview_preset(self, rig: str) -> dict:
        try:
            cc = load_preset(rig)
            summary = summarize_cc(cc)
        except NpvError as error:
            return {
                "ok": False,
                "error": error.user_message,
                "remediation": error.remediation or "",
            }
        except Exception as error:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": str(error), "remediation": ""}
        return {"ok": True, **summary}

    def add_hair_mod(self, path: str, body_rig: str = "pwa") -> dict:
        """Install a CCXL/hair mod file into the game and return its token.

        The mod is a runtime dependency of the built NPV (the .app is attached
        by appearance reference), so installing into the game dir here is the
        end state, not a side effect."""
        s = load_settings()
        if not s.game_dir:
            return {
                "ok": False,
                "error": "Game directory not configured.",
                "remediation": "Set it in Settings.",
            }
        game_dir = Path(s.game_dir)
        try:
            _filename_token, installed = install_hair_mod(Path(path), game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message, "remediation": e.remediation or ""}
        except (ValueError, OSError) as e:
            return {
                "ok": False,
                "error": str(e),
                "remediation": "Pick a hair mod file: .archive, .zip, .7z or .rar.",
            }
        archive_path = next((p for p in installed if str(p).lower().endswith(".archive")), None)
        if archive_path is None:
            return {
                "ok": False,
                "error": f"No hair appearance found in '{Path(path).name}'.",
                "remediation": "This does not look like a CCXL/hair mod — "
                "pick the mod's main .archive (or its zip/7z/rar).",
            }
        archive_path = Path(archive_path)
        # Probe: list the *installed archive's own* .app files rather than
        # trusting a token derived from the archive filename — mod filenames
        # (e.g. "ANRUI_MiyaviHair_Fluffypony_CCXL.archive") frequently have no
        # relationship to the internal depot paths, so a filename-derived token
        # can never match anything inside extract_hair_components' tokenizer.
        try:
            wk = WolvenKit(WolvenKitConfig(game_dir=game_dir, verbosity=0))
            app_paths = list_mod_archive_apps(wk, archive_path)
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            logger.exception("hair mod probe failed")
            return {
                "ok": False,
                "error": f"Could not inspect the hair mod: {e}",
                "remediation": "Check the file and try again.",
            }
        gender_pref = "fhair_" if body_rig == "pwa" else "mhair_"
        candidates = []
        for p in app_paths:
            if "\\fpp\\" in p.lower():
                continue
            bn = p.replace("\\", "/").rsplit("/", 1)[-1]
            bn_low = bn.lower()
            if bn_low.startswith("fhair_") or bn_low.startswith("mhair_") or "hair" in bn_low:
                candidates.append((p, bn))
        if not candidates:
            return {
                "ok": False,
                "error": f"No hair appearance found in '{Path(path).name}'.",
                "remediation": "This does not look like a CCXL/hair mod — "
                "pick the mod's main .archive (or its zip/7z/rar).",
            }

        def score(item: tuple[str, str]) -> int:
            _p, bn = item
            bn_low = bn.lower()
            s = 0
            if bn_low.startswith(gender_pref):
                s += 4
            if "cyb" not in bn_low and "shaved" not in bn_low:
                s += 1
            return s

        _best_path, best_basename = max(candidates, key=score)
        token = best_basename
        if token.lower().endswith(".app"):
            token = token[: -len(".app")]
        for pre in ("fhair_", "mhair_"):
            if token.lower().startswith(pre):
                token = token[len(pre) :]
                break

        try:
            _comps, src, app_depot, _app_name = extract_hair_components(
                game_dir, token, body_rig, verbosity=0, wk=wk
            )
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            logger.exception("hair mod probe failed")
            return {
                "ok": False,
                "error": f"Could not inspect the hair mod: {e}",
                "remediation": "Check the file and try again.",
            }
        if not app_depot:
            return {
                "ok": False,
                "error": f"Hair mod installed but its hair could not be resolved "
                f"(token '{token}').",
                "remediation": "Open an issue with the mod name — its naming "
                "defeats token matching.",
            }
        return {
            "ok": True,
            "token": token,
            "source": src or archive_path.name,
            "warning": "The NPV needs this hair mod to stay installed.",
        }

    def browse_for_hair_mod(self, body_rig: str = "pwa") -> dict:
        try:
            import webview

            if not webview.windows:
                raise RuntimeError("no webview window")
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Hair mod (*.archive;*.zip;*.7z;*.rar)", "All files (*.*)"),
            )
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {
                "ok": False,
                "error": "File dialog is unavailable outside the desktop app.",
                "remediation": "Drag & drop the mod file instead.",
                "details": str(e),
            }
        if not result:
            return {"ok": False, "cancelled": True, "error": ""}
        return self.add_hair_mod(result[0], body_rig)

    def add_photomode_thumbnail(self, path: str) -> dict:
        try:
            thumbnail = validate_thumbnail(Path(path))
            preview = thumbnail_preview_data_url(thumbnail)
        except NpvError as error:
            return {
                "ok": False,
                "error": error.user_message,
                "remediation": error.remediation,
            }
        return {
            "ok": True,
            "thumbnail": {
                "path": str(thumbnail.source),
                "name": thumbnail.source.name,
                "width": thumbnail.width,
                "height": thumbnail.height,
                "preview": preview,
            },
        }

    def browse_for_photomode_thumbnail(self) -> dict:
        try:
            import webview

            if not webview.windows:
                raise RuntimeError("no webview window")
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=(
                    "Images (*.png;*.jpg;*.jpeg;*.webp)",
                    "All files (*.*)",
                ),
            )
        except Exception as error:  # noqa: BLE001 - bridge boundary
            return {
                "ok": False,
                "error": "File dialog is unavailable outside the desktop app.",
                "remediation": "Drag and drop an image onto the thumbnail card.",
                "details": str(error),
            }
        if not result:
            return {"ok": False, "cancelled": True, "error": ""}
        return self.add_photomode_thumbnail(result[0])

    def zip_info(self, output_dir: str) -> dict:
        """Describe the built mod zip in output_dir (path, size, contents)."""
        import zipfile

        zips = sorted(Path(output_dir).glob("*.zip"))
        if not zips:
            return {
                "ok": False,
                "error": f"No mod zip found in {output_dir}.",
                "remediation": "Rebuild the mod.",
            }
        z = zips[0]
        try:
            with zipfile.ZipFile(z) as zf:
                files = [{"name": i.filename, "size": i.file_size} for i in zf.infolist()]
        except (OSError, zipfile.BadZipFile) as e:
            return {
                "ok": False,
                "error": f"Could not read {z.name}: {e}",
                "remediation": "Rebuild the mod.",
            }
        return {"ok": True, "zip": {"path": str(z), "size": z.stat().st_size, "files": files}}

    def open_folder(self, path: str) -> dict:
        """Open a folder in the OS file manager."""
        p = Path(path)
        if not p.is_dir():
            return {
                "ok": False,
                "error": f"Folder not found: {path}",
                "remediation": "Rebuild the mod.",
            }
        try:
            platform_open_folder(p)
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {
                "ok": False,
                "error": f"Could not open folder: {e}",
                "remediation": "Open it manually in your file manager.",
            }
        return {"ok": True}

    def _settings_for_mods(self) -> tuple[Path, Path]:
        s = load_settings()
        output_root = Path(s.output_dir) if s.output_dir else Path.home() / "npv_builds"
        if not s.game_dir:
            raise NpvError("Game directory not configured.", remediation="Set it in Settings.")
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
                thumbnail = None
                thumbnail_path = meta.get("photomode_thumbnail")
                if thumbnail_path:
                    thumbnail_out = self.add_photomode_thumbnail(thumbnail_path)
                    if thumbnail_out.get("ok"):
                        thumbnail = thumbnail_out["thumbnail"]
                mods.append(
                    {
                        "mod_id": m.mod_id,
                        "archive_path": str(m.archive_path),
                        "installed": m.installed,
                        "built_at": m.built_at,
                        "npv_name": meta.get("npv_name"),
                        "save_path": meta.get("save_path"),
                        "preset_rig": meta.get("preset_rig"),
                        "photomode_thumbnail": thumbnail,
                        "photomode_thumbnail_missing": bool(thumbnail_path and not thumbnail),
                        "output_dir": str(m.archive_path.parents[3]),
                    }
                )
        except NpvError as e:
            return {"ok": False, "error": e.user_message, "remediation": e.remediation or ""}
        return {"ok": True, "mods": mods}

    def _find_mod(self, mod_id: str):
        output_root, game_dir = self._settings_for_mods()
        for m in mm_list_mods(output_root, game_dir):
            if m.mod_id == mod_id:
                return m, game_dir
        raise NpvError(f"Mod '{mod_id}' not found.", remediation="Refresh the library.")

    def install_mod(self, mod_id: str) -> dict:
        try:
            entry, game_dir = self._find_mod(mod_id)
            mm_install_mod(entry, game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message, "remediation": e.remediation or ""}
        return {"ok": True}

    def uninstall_mod(self, mod_id: str) -> dict:
        try:
            entry, game_dir = self._find_mod(mod_id)
            mm_uninstall_mod(entry, game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message, "remediation": e.remediation or ""}
        return {"ok": True}

    def delete_mod(self, mod_id: str) -> dict:
        try:
            entry, game_dir = self._find_mod(mod_id)
            mm_delete_mod(entry, game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message, "remediation": e.remediation or ""}
        return {"ok": True}

    def appearance_data(self, save_path: str) -> dict:
        try:
            cc = parse_save_for_inspector(Path(save_path))
        except NpvError as e:
            return {"ok": False, "error": e.user_message, "remediation": e.remediation or ""}
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": str(e), "remediation": ""}
        saved_hair = None
        hair = cc.get("hair") or {}
        if hair.get("kind") == "modded":
            settings = load_settings()
            registration = (
                hair_registration_status(
                    Path(settings.game_dir),
                    str(hair.get("selection_label") or ""),
                )
                if settings.game_dir
                else {
                    "state": "unverified",
                    "selection_label": hair.get("selection_label") or "",
                    "depot": "",
                    "source": "",
                }
            )
            saved_hair = {
                **registration,
                "mesh_appearance": hair.get("mesh_appearance") or "",
            }
        return self._appearance_payload(
            cc,
            load_overrides(save_path),
            saved_hair=saved_hair,
        )

    # Live progress per output_dir, written by render_npv_preview's callback and
    # polled concurrently by the frontend (pywebview dispatches each JS bridge
    # call on its own thread, so render_preview_progress can answer while
    # render_npv_preview blocks).
    _render_progress: dict = {}

    def render_preview_progress(self, output_dir: str) -> dict:
        state = self._render_progress.get(str(output_dir))
        if not state:
            return {"active": False, "message": "", "current": 0, "total": 0}
        return dict(state)

    def render_npv_preview(self, output_dir: str) -> dict:
        settings = load_settings()
        if not settings.game_dir:
            return {
                "ok": False,
                "error": "Game directory not configured.",
                "remediation": "Set the game directory in Settings",
            }

        def _progress(message: str, current: int, total: int) -> None:
            self._render_progress[str(output_dir)] = {
                "active": True,
                "message": message,
                "current": current,
                "total": total,
            }

        try:
            wk = WolvenKit(WolvenKitConfig(game_dir=Path(settings.game_dir)))
            paths = render_appearance(wk, Path(output_dir), progress=_progress)
        except NpvError as e:
            return {"ok": False, "error": e.user_message, "remediation": e.remediation or ""}
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": str(e), "remediation": ""}
        finally:
            self._render_progress.pop(str(output_dir), None)
        images = []
        for p in paths:
            data = base64.b64encode(p.read_bytes()).decode("ascii")
            images.append(
                {
                    "view": p.stem,
                    "path": str(p),
                    "data_url": f"data:image/png;base64,{data}",
                }
            )
        # render_appearance is best-effort: some components may have been
        # skipped (mesh not found, or WolvenKit couldn't export it). Surface
        # that so the preview is never presented as complete when it isn't.
        skipped = []
        report_path = paths[0].parent / "render_report.json" if paths else None
        if report_path and report_path.exists():
            try:
                skipped = json.loads(report_path.read_text(encoding="utf-8")).get("skipped", [])
            except (OSError, ValueError):
                skipped = []
        return {"ok": True, "images": images, "skipped": skipped}

    def preset_appearance_data(self, rig: str) -> dict:
        try:
            cc = load_preset(rig)
        except NpvError as e:
            return {
                "ok": False,
                "error": e.user_message,
                "remediation": e.remediation or "",
            }
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": str(e), "remediation": ""}
        return self._appearance_payload(cc, {})

    @staticmethod
    def _appearance_payload(
        cc: dict,
        overrides: dict,
        *,
        saved_hair: dict | None = None,
    ) -> dict:
        options = option_lists(
            load_part_index(cc.get("patch", "")),
            cc.get("body_rig", "pwa"),
            cc,
        )
        rows = inspector_rows(cc, options, _display_names())
        categories = list(dict.fromkeys(r["category"] for r in rows))
        return {
            "ok": True,
            "rows": rows,
            "categories": categories,
            "overrides": overrides,
            "garments": _garment_values(cc),
            "saved_hair": saved_hair,
        }

    def get_overrides(self, save_path: str) -> dict:
        return {"ok": True, "overrides": load_overrides(save_path)}

    def set_overrides(self, save_path: str, overrides: dict) -> dict:
        rig = "pwa"
        try:
            cc = parse_save_for_inspector(Path(save_path))
            rig = cc.get("body_rig", rig)
            options = option_lists(
                load_part_index(cc.get("patch", "")),
                rig,
                cc,
            )
        except Exception:  # noqa: BLE001 - index/parse problems fall back to slot-only checks
            options = {}
        problems = validate_overrides(overrides, options)
        problems.extend(
            _validate_garment_overrides(
                overrides,
                rig,
            )
        )
        if problems:
            return {
                "ok": False,
                "error": "; ".join(problems),
                "remediation": "Pick values from the dropdowns.",
            }
        save_overrides(save_path, overrides)
        return {"ok": True}

    def start_build(self, req: dict) -> dict:
        import json

        s = load_settings()
        if not s.game_dir:
            return {
                "ok": False,
                "error": "Game directory not configured.",
                "remediation": "Set it in Settings.",
            }
        preset_rig = req.get("preset_rig")
        source_save_path = req.get("save_path")
        if bool(preset_rig) == bool(source_save_path):
            return {
                "ok": False,
                "error": "Choose exactly one build source.",
                "remediation": "Pick a save or an available default-V preset.",
            }

        if preset_rig:
            try:
                cc_override = load_preset(preset_rig)
            except NpvError as error:
                return {
                    "ok": False,
                    "error": error.user_message,
                    "remediation": error.remediation or "",
                }
            preset_overrides = req.get("cc_overrides") or {}
            if not isinstance(preset_overrides, dict):
                return {
                    "ok": False,
                    "error": "Preset appearance overrides must be an object.",
                    "remediation": "Return to Appearance and choose the options again.",
                }
            options = option_lists(
                load_part_index(cc_override.get("patch", "")),
                cc_override.get("body_rig", preset_rig),
                cc_override,
            )
            problems = validate_overrides(preset_overrides, options)
            problems.extend(
                _validate_garment_overrides(
                    preset_overrides,
                    cc_override.get("body_rig", preset_rig),
                )
            )
            if problems:
                return {
                    "ok": False,
                    "error": "; ".join(problems),
                    "remediation": "Return to Appearance and pick values from the dropdowns.",
                }
            cc_overrides, garments = _split_garment_overrides(preset_overrides)
            meta = {"npv_name": req["npv_name"], "preset_rig": preset_rig}
            save_path = None
            extra = {
                "cc_settings_override": cc_override,
                "cc_overrides": cc_overrides,
                "garments": garments,
            }
        else:
            meta = {"npv_name": req["npv_name"], "save_path": source_save_path}
            save_path = Path(source_save_path)
            stored_overrides = load_overrides(source_save_path)
            garment_values = {
                key: value for key, value in stored_overrides.items() if key.startswith("garment_")
            }
            if garment_values:
                try:
                    source_cc = parse_save_for_inspector(save_path)
                    rig = source_cc.get("body_rig", "pwa")
                except Exception:  # noqa: BLE001 - normal build reports parse errors later
                    rig = "pwa"
                problems = _validate_garment_overrides(stored_overrides, rig)
                if problems:
                    return {
                        "ok": False,
                        "error": "; ".join(problems),
                        "remediation": ("Return to Appearance and reselect the garment."),
                    }
            cc_overrides, garments = _split_garment_overrides(stored_overrides)
            extra = {
                "cc_overrides": cc_overrides,
                "garments": garments,
            }

        thumbnail_path = req.get("photomode_thumbnail")
        if not thumbnail_path:
            return {
                "ok": False,
                "error": "A Photo Mode thumbnail is required.",
                "remediation": "Return to Appearance and choose a portrait.",
            }
        try:
            thumbnail = validate_thumbnail(Path(thumbnail_path))
            meta["photomode_thumbnail"] = str(thumbnail.source)
            out_dir = Path(req["output_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "build_meta.json").write_text(
                json.dumps(meta),
                encoding="utf-8",
            )
        except OSError as e:
            return {
                "ok": False,
                "error": f"Cannot write to output directory: {e}",
                "remediation": "Check the output directory path and permissions.",
            }
        self._worker = BuildWorker(self._queue)
        self._worker.start(
            save_path=save_path,
            npv_name=req["npv_name"],
            output_dir=Path(req["output_dir"]),
            game_dir=Path(s.game_dir),
            template_cache=get_cache_dir() / "templates",
            clear_cache=bool(req.get("clear_cache", False)),
            resume=bool(req.get("resume", True)),
            photomode_thumbnail=thumbnail.source,
            **extra,
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
