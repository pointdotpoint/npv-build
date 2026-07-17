import logging
import queue
import shutil
import sys
import threading
from pathlib import Path

from .config import get_cache_dir
from .core.cancel import CancelToken
from .core.errors import NpvError, PipelineCancelled
from .core.logging_setup import CallbackHandler, configure_logging
from .core.pipeline import BuildRequest, PipelineService
from .save_parser import parse_save

logger = logging.getLogger(__name__)

# Stage list captured from the real PipelineService at import time. Tests
# monkeypatch the module-level `PipelineService` name (used to *instantiate*
# the service) with a fake that has no STAGES attribute, so progress mapping
# must not depend on that patchable name.
_STAGES = tuple(PipelineService.STAGES)

# Kwarg names the GUI passes to BuildWorker.start() that are not BuildRequest
# fields and must be stripped before constructing the request.
_NON_REQUEST_KWARGS = ("verbosity",)


def _request_kwargs(kwargs: dict) -> dict:
    """Map the GUI's build kwargs onto BuildRequest field names.

    The GUI's kwarg names already match BuildRequest's fields 1:1 (they were
    originally written for run_orchestrator's identically-named parameters).
    The one exception is `verbosity`, which BuildRequest has no field for
    (logging verbosity is now handled by configure_logging), so it is
    dropped here if present.
    """
    return {k: v for k, v in kwargs.items() if k not in _NON_REQUEST_KWARGS}


class BuildWorker:
    """Drives PipelineService.build() in a background thread."""

    def __init__(self, log_queue: queue.Queue):
        self.queue = log_queue
        self._thread: threading.Thread | None = None
        self._token: CancelToken | None = None

    def _make_token(self) -> CancelToken:
        return CancelToken()

    def start(self, **kwargs):
        self._token = self._make_token()
        self._thread = threading.Thread(target=self._run, kwargs=kwargs, daemon=True)
        self._thread.start()

    def cancel(self):
        if self._token is not None:
            self._token.cancel()

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self, **kwargs):
        stages = _STAGES

        def on_event(ev):
            if ev.kind == "stage_started":
                self.queue.put(("log", f"[{ev.stage}] {ev.message}\n"))
                self.queue.put(("progress", stages.index(ev.stage) / len(stages)))
            elif ev.kind in ("stage_completed", "stage_skipped"):
                self.queue.put(("progress", (stages.index(ev.stage) + 1) / len(stages)))
            elif ev.kind == "failed":
                self.queue.put(("log", f"[{ev.stage}] FAILED: {ev.message}\n"))

        handler = CallbackHandler(lambda line: self.queue.put(("log", line + "\n")))
        configure_logging(verbosity=2, extra_handler=handler)
        try:
            req = BuildRequest(resume=kwargs.pop("resume", False), **_request_kwargs(kwargs))
            result = PipelineService().build(req, on_event=on_event, cancel=self._token)
            self.queue.put(("done", result.output_dir))
        except PipelineCancelled:
            self.queue.put(("error", "Build cancelled."))
        except NpvError as e:
            msg = e.user_message + (f"\n{e.remediation}" if e.remediation else "")
            self.queue.put(("error", msg))
        except Exception as e:  # noqa: BLE001 - worker thread must survive to report to GUI queue
            logger.exception("Unexpected build failure")
            self.queue.put(("error", str(e)))


class InstallerWorker:
    """Executes auto_install_missing in a background thread."""

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            from .installer import auto_install_missing

            def progress_cb(msg, pct):
                self.log_queue.put(("log", f"{msg}\n"))
                self.log_queue.put(("progress", pct / 100.0))

            auto_install_missing(progress_cb)
            self.log_queue.put(("install_done", None))
        except Exception as e:  # noqa: BLE001 - worker thread must survive to report to GUI queue
            import traceback

            logger.exception("Unhandled error in installer worker thread")
            tb = traceback.format_exc()
            self.log_queue.put(("log", f"Traceback:\n{tb}"))
            self.log_queue.put(("install_error", str(e)))

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
    except OSError:
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
