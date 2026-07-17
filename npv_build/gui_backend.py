import queue
import shutil
import sys
import threading
from pathlib import Path

from .config import get_cache_dir
from .orchestrator import OrchestratorError, run_orchestrator
from .save_parser import parse_save


class LogRedirector:
    """Redirects stdout and stderr to a thread-safe queue."""

    def __init__(self, log_queue: queue.Queue):
        self.queue = log_queue

    def write(self, text: str):
        if text:
            self.queue.put(("log", text))

    def flush(self):
        pass


class BuildWorker:
    """Executes run_orchestrator in a background thread."""

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self._thread = None

    def start(self, **kwargs):
        self._thread = threading.Thread(target=self._run, kwargs=kwargs, daemon=True)
        self._thread.start()

    def _run(self, **kwargs):
        # Redirect standard outputs
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirector = LogRedirector(self.log_queue)
        sys.stdout = redirector
        sys.stderr = redirector

        try:
            # We set verbosity to 2 so subprocess calls print their details
            kwargs["verbosity"] = 2
            out_dir = run_orchestrator(**kwargs)
            self.log_queue.put(("done", out_dir))
        except OrchestratorError as e:
            self.log_queue.put(("error", f"[{e.module_name}] {str(e)}"))
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            self.log_queue.put(("log", f"Traceback:\n{tb}"))
            self.log_queue.put(("error", str(e)))
        finally:
            # Restore standard outputs
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


class InstallerWorker:
    """Executes auto_install_missing in a background thread."""

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirector = LogRedirector(self.log_queue)
        sys.stdout = redirector
        sys.stderr = redirector

        try:
            from .installer import auto_install_missing

            def progress_cb(msg, pct):
                self.log_queue.put(("log", f"{msg}\n"))
                self.log_queue.put(("progress", pct / 100.0))

            auto_install_missing(progress_cb)
            self.log_queue.put(("install_done", None))
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            self.log_queue.put(("log", f"Traceback:\n{tb}"))
            self.log_queue.put(("install_error", str(e)))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def check_dependencies(game_dir: Path | None) -> dict:
    """Check if the required external tools are available."""
    from .wolvenkit import _resolve_inject_binary

    tools_dir = get_cache_dir() / "tools"
    ext = ".exe" if sys.platform == "win32" else ""

    # WolvenKit.CLI
    wkit_binary = "WolvenKit.CLI"
    wkit_found = bool(shutil.which(wkit_binary))
    if not wkit_found:
        local_wkit = tools_dir / "wolvenkit" / f"WolvenKit.CLI{ext}"
        wkit_found = local_wkit.exists()

    # Blender
    blender_found = bool(shutil.which("blender") or shutil.which("org.blender.Blender"))
    if not blender_found:
        local_blender_dir = tools_dir / "blender"
        if local_blender_dir.exists():
            binary_name = f"blender{ext}"
            for path in local_blender_dir.rglob(binary_name):
                if path.is_file() and not path.is_symlink():
                    blender_found = True
                    break

    # npv-inject
    npv_inject_found = False
    try:
        inject_path = _resolve_inject_binary()
        if inject_path and (shutil.which(inject_path) or Path(inject_path).exists()):
            npv_inject_found = True
    except Exception:
        pass

    # Game Directory Verification
    game_dir_valid = False
    if game_dir:
        archive_path = game_dir / "archive" / "pc" / "content" / "basegame_4_appearance.archive"
        if archive_path.exists():
            game_dir_valid = True

    return {
        "wolvenkit": wkit_found,
        "blender": blender_found,
        "npv_inject": npv_inject_found,
        "game_dir_valid": game_dir_valid,
    }


def preview_save(save_path: Path) -> dict:
    """Parse save file and return summary. Raises SaveParserError on failure."""
    cc_settings = parse_save(save_path)
    return {
        "body_rig": cc_settings.get("body_rig", "Unknown"),
        "skin_tone": cc_settings.get("skin_tone", "Unknown"),
        "hair_style": cc_settings.get("hair", {}).get("style", "Unknown"),
        "hair_color": cc_settings.get("hair", {}).get("color", "Unknown"),
        "selections_count": len(cc_settings.get("selections", [])),
    }
