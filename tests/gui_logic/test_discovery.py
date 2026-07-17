from pathlib import Path

from npv_build.gui_logic.discovery import SaveEntry, list_saves


def _make_save(root: Path, name: str, with_thumb: bool = False) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "sav.dat").write_bytes(b"\x00")
    if with_thumb:
        (d / "screenshot.png").write_bytes(b"\x89PNG")
    return d


def test_lists_saves_newest_first(tmp_path):
    import os

    a = _make_save(tmp_path, "AutoSave-1")
    b = _make_save(tmp_path, "QuickSave-2")
    # make b newer deterministically
    os.utime(a / "sav.dat", (1000, 1000))
    os.utime(b / "sav.dat", (2000, 2000))
    entries = list_saves([tmp_path])
    assert [e.name for e in entries] == ["QuickSave-2", "AutoSave-1"]
    assert all(isinstance(e, SaveEntry) for e in entries)


def test_thumbnail_detected_when_present(tmp_path):
    _make_save(tmp_path, "WithThumb", with_thumb=True)
    [e] = list_saves([tmp_path])
    assert e.thumbnail is not None and e.thumbnail.name == "screenshot.png"


def test_no_thumbnail_is_none(tmp_path):
    _make_save(tmp_path, "NoThumb")
    [e] = list_saves([tmp_path])
    assert e.thumbnail is None


def test_ignores_dirs_without_savdat(tmp_path):
    (tmp_path / "not_a_save").mkdir()
    assert list_saves([tmp_path]) == []
