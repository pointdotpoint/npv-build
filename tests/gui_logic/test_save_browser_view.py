from pathlib import Path

from npv_build.gui_logic.discovery import SaveEntry
from npv_build.gui_views.save_browser_view import build_rows


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
