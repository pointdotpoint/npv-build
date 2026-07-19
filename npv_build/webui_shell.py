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
