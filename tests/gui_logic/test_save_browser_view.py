import os
from pathlib import Path

import pytest

from npv_build.gui_logic.discovery import SaveEntry
from npv_build.gui_views.save_browser_view import build_rows

_HAS_DISPLAY = bool(os.environ.get("DISPLAY"))


def test_build_rows_shape():
    e = SaveEntry(
        path=Path("/x/QuickSave-1/sav.dat"), name="QuickSave-1", mtime=1000.0, thumbnail=None
    )
    [row] = build_rows([e])
    assert row["name"] == "QuickSave-1"
    assert row["path"] == e.path
    assert "timestamp" in row  # human-readable
    assert row["has_thumb"] is False


def test_build_rows_empty():
    assert build_rows([]) == []


def test_build_rows_has_thumb_true():
    e = SaveEntry(
        path=Path("/x/WithThumb/sav.dat"),
        name="WithThumb",
        mtime=2000.0,
        thumbnail=Path("/x/WithThumb/screenshot.png"),
    )
    [row] = build_rows([e])
    assert row["has_thumb"] is True


def test_build_rows_timestamp_matches_entry_mtime():
    from datetime import datetime

    e = SaveEntry(path=Path("/x/A/sav.dat"), name="A", mtime=1_600_000_000.0, thumbnail=None)
    [row] = build_rows([e])
    assert row["timestamp"] == datetime.fromtimestamp(e.mtime).strftime("%Y-%m-%d %H:%M:%S")


@pytest.mark.skipif(not _HAS_DISPLAY, reason="requires a display (headless environment)")
def test_load_thumbnail_truncated_png_returns_fallback_no_raise(tmp_path):
    """Regression test: Image.open() is lazy and only reads the PNG header, so a
    truncated-but-header-valid screenshot.png passes Image.open() but fails later
    on pixel decode. _load_thumbnail must force an eager decode inside its guard
    and return None instead of letting the OSError escape.
    """
    # Build a header-valid PNG with truncated pixel data.
    from io import BytesIO

    import customtkinter as ctk
    from PIL import Image

    from npv_build.gui_views.save_browser_view import SaveBrowserView

    buf = BytesIO()
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(buf, format="PNG")
    full_bytes = buf.getvalue()
    truncated_path = tmp_path / "screenshot.png"
    truncated_path.write_bytes(full_bytes[: len(full_bytes) // 2])

    root = ctk.CTk()
    try:
        view = SaveBrowserView(root, lambda p: None, save_dirs=[])
        result = view._load_thumbnail(truncated_path)
        assert result is None
    finally:
        root.destroy()


@pytest.mark.skipif(not _HAS_DISPLAY, reason="requires a display (headless environment)")
def test_save_browser_view_renders_row_with_truncated_thumbnail_without_crashing(tmp_path):
    """End-to-end regression test: a save row whose screenshot.png is truncated
    must render (with no thumbnail) instead of crashing the whole save list.
    The original bug surfaced inside CTkButton.__init__ -> _draw -> _update_image,
    outside of _load_thumbnail's try/except, so this exercises the full row build.
    """
    from io import BytesIO

    import customtkinter as ctk
    from PIL import Image

    from npv_build.gui_views.save_browser_view import SaveBrowserView

    save_dir = tmp_path / "SaveWithBadThumb"
    save_dir.mkdir()
    (save_dir / "sav.dat").write_bytes(b"fake")

    buf = BytesIO()
    Image.new("RGBA", (64, 64), (0, 255, 0, 255)).save(buf, format="PNG")
    full_bytes = buf.getvalue()
    (save_dir / "screenshot.png").write_bytes(full_bytes[: len(full_bytes) // 2])

    root = ctk.CTk()
    try:
        view = SaveBrowserView(root, lambda p: None, save_dirs=[tmp_path])
        root.update()
        assert view is not None
    finally:
        root.destroy()
