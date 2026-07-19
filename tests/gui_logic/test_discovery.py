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


def test_patch_detected_from_header(tmp_path):
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1]))
    from conftest import _build_synth_save_bytes

    d = tmp_path / "RealSave"
    d.mkdir()
    (d / "sav.dat").write_bytes(_build_synth_save_bytes(build=2310))
    [e] = list_saves([tmp_path])
    assert e.patch == "2.31"


def test_patch_none_for_unreadable_header(tmp_path):
    # Garbage sav.dat: still listed (preview will explain), badge just absent.
    _make_save(tmp_path, "Broken")
    [e] = list_saves([tmp_path])
    assert e.patch is None


def test_entry_for_path_builds_single_entry(tmp_path):
    from npv_build.gui_logic.discovery import entry_for_path

    d = _make_save(tmp_path, "PickedSave")
    e = entry_for_path(d / "sav.dat")
    assert e.name == "PickedSave"
    assert e.path == d / "sav.dat"
    assert e.patch is None  # garbage header -> no badge, still usable
