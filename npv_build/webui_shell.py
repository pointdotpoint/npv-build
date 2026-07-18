"""pywebview entry point for the npv-build GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from .webui_api import WebUiApi


def webui_dir() -> Path:
    return Path(__file__).parent / "webui"


def main() -> int:
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
