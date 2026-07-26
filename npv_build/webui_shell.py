"""pywebview entry point for the npv-build GUI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .webui_api import WebUiApi


def webui_dir() -> Path:
    return Path(__file__).parent / "webui"


def _linux_env_defaults() -> None:
    if not sys.platform.startswith("linux"):
        return
    # The release bundle ships Qt WebEngine as one coherent GUI runtime.
    # Mixing bundled GTK/PyGObject with host WebKitGTK is not ABI-safe across
    # Linux distributions.
    os.environ.setdefault("PYWEBVIEW_GUI", "qt")


def _probe_qt_webengine() -> None:
    """Import the Qt WebEngine widget pywebview's Linux backend needs."""
    from qtpy.QtWebEngineWidgets import QWebEngineView  # noqa: F401


def check_webview_runtime(platform: str | None = None) -> str | None:
    """Return an install hint when the platform's webview runtime is missing,
    or None when the GUI can start. Windows uses the built-in WebView2
    (preinstalled on Win 10/11), so only Linux needs a real probe."""
    platform = sys.platform if platform is None else platform
    if not platform.startswith("linux"):
        return None
    try:
        _probe_qt_webengine()
    except Exception as e:  # noqa: BLE001 - any failure means "can't render"
        return (
            f"Qt WebEngine runtime not found ({e}).\n"
            "npv-build-gui needs PyQt6-WebEngine to render the interface on Linux.\n"
            "Reinstall the GUI dependencies with: uv sync --extra gui"
        )
    return None


def main() -> int:
    _linux_env_defaults()
    try:
        import webview
    except ImportError:
        print(
            "npv-build-gui needs pywebview (and Qt WebEngine on Linux).\n"
            "Install with: uv sync --extra gui\n"
            "Release packages include the Linux Qt runtime.",
            file=sys.stderr,
        )
        return 1
    hint = check_webview_runtime()
    if hint:
        print(hint, file=sys.stderr)
        return 1
    webview.create_window(
        "NPV Build",
        url=str(webui_dir() / "index.html"),
        js_api=WebUiApi(),
        width=1200,
        height=800,
        min_size=(900, 600),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
