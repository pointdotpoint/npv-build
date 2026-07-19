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
    # pywebview forces its QT backend under KDE (KDE_FULL_SESSION), which we
    # don't ship; WebKitGTK's DMA-BUF renderer crashes on NVIDIA + Wayland.
    os.environ.setdefault("PYWEBVIEW_GUI", "gtk")
    os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")


def _probe_webkitgtk() -> None:
    """Import the WebKitGTK GI bindings pywebview's GTK backend needs.
    Raises on any missing piece (gi itself, or the WebKit2 typelib)."""
    import gi

    try:
        gi.require_version("WebKit2", "4.1")
    except ValueError:
        gi.require_version("WebKit2", "4.0")
    from gi.repository import WebKit2  # noqa: F401


def check_webview_runtime(platform: str | None = None) -> str | None:
    """Return an install hint when the platform's webview runtime is missing,
    or None when the GUI can start. Windows uses the built-in WebView2
    (preinstalled on Win 10/11), so only Linux needs a real probe."""
    platform = sys.platform if platform is None else platform
    if not platform.startswith("linux"):
        return None
    try:
        _probe_webkitgtk()
    except Exception as e:  # noqa: BLE001 - any failure means "can't render"
        return (
            f"WebKitGTK runtime not found ({e}).\n"
            "npv-build-gui needs it to render the interface on Linux.\n"
            "  Debian/Ubuntu: sudo apt install gir1.2-webkit2-4.1\n"
            "  Fedora:        sudo dnf install webkit2gtk4.1\n"
            "  Arch:          sudo pacman -S webkit2gtk-4.1\n"
            "Then reinstall Python bindings if needed: uv sync --extra gui"
        )
    return None


def main() -> int:
    _linux_env_defaults()
    try:
        import webview
    except ImportError:
        print(
            "npv-build-gui needs pywebview (and WebKitGTK on Linux).\n"
            "Install with: uv sync --extra gui\n"
            "On Debian/Ubuntu also: sudo apt install gir1.2-webkit2-4.1",
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
