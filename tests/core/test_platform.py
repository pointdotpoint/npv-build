from pathlib import Path

import pytest

from npv_build.core import platform as plat


def _make_windows_save(tmp_path: Path) -> Path:
    d = tmp_path / "home" / "Saved Games" / "CD Projekt Red" / "Cyberpunk 2077"
    d.mkdir(parents=True)
    return d


def _make_steam_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    steam = tmp_path / "steam"
    lib2 = tmp_path / "lib2"
    (steam / "steamapps").mkdir(parents=True)
    (lib2 / "steamapps").mkdir(parents=True)
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    vdf.write_text(
        '"libraryfolders"\n{\n'
        f'\t"0"\n\t{{\n\t\t"path"\t\t"{steam}"\n\t}}\n'
        f'\t"1"\n\t{{\n\t\t"path"\t\t"{lib2}"\n\t}}\n'
        "}\n",
        encoding="utf-8",
    )
    save = (
        lib2
        / "steamapps"
        / "compatdata"
        / plat.GAME_STEAM_APPID
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "Saved Games"
        / "CD Projekt Red"
        / "Cyberpunk 2077"
    )
    save.mkdir(parents=True)
    game = lib2 / "steamapps" / "common" / "Cyberpunk 2077"
    (game / "archive" / "pc" / "content").mkdir(parents=True)
    return steam, save, game


def test_is_valid_game_dir(tmp_path):
    assert not plat.is_valid_game_dir(tmp_path)
    (tmp_path / "archive" / "pc" / "content").mkdir(parents=True)
    assert plat.is_valid_game_dir(tmp_path)


def test_steam_libraries_parses_vdf(tmp_path):
    steam, _, _ = _make_steam_tree(tmp_path)
    libs = plat.steam_libraries(steam_roots=[steam])
    assert len(libs) == 2


def test_steam_libraries_unescapes_windows_backslash_path(tmp_path, monkeypatch):
    """VDF stores Windows paths with doubled backslashes (JSON-like escaping),
    e.g. "C:\\\\Games\\\\SteamLibrary". steam_libraries must unescape that to
    a single-backslash Path (C:\\Games\\SteamLibrary), not pass the doubled
    form through. The library-existence check (`(lib / "steamapps").is_dir()`)
    would always be False on Linux for a C:\\ path, so monkeypatch is_dir to
    make this a pure parsing test."""
    steam = tmp_path / "steam"
    (steam / "steamapps").mkdir(parents=True)
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    vdf.write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"C:\\\\Games\\\\SteamLibrary"\n\t}\n}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(plat.Path, "is_dir", lambda self: True)
    libs = plat.steam_libraries(steam_roots=[steam])
    assert len(libs) == 1
    assert str(libs[0]) == "C:\\Games\\SteamLibrary"


def test_candidate_save_dirs_windows_layout(tmp_path):
    d = _make_windows_save(tmp_path)
    dirs = plat.candidate_save_dirs(home=tmp_path / "home", steam_roots=[])
    assert d in dirs


def test_candidate_save_dirs_proton(tmp_path):
    steam, save, _ = _make_steam_tree(tmp_path)
    dirs = plat.candidate_save_dirs(home=tmp_path / "nohome", steam_roots=[steam])
    assert save in dirs


def test_steam_root_candidates_win32(monkeypatch):
    """On win32, steam_root_candidates checks a single Program Files (x86)
    candidate instead of the Linux/Steam-Deck triad. platform.py reads
    sys.platform at call time (module-level `import sys`, checked inside the
    function body), so monkeypatching sys.platform on the shared `sys`
    module is enough -- no need to patch the platform module's namespace."""
    monkeypatch.setattr(plat.sys, "platform", "win32")
    # Program Files (x86)/Steam does not exist on this (Linux) test machine,
    # so the non-existent-dir filter must drop it and return an empty list
    # without raising.
    assert plat.steam_root_candidates() == []


def test_steam_root_candidates_win32_finds_existing_candidate(monkeypatch):
    """When the win32 Program Files (x86)/Steam candidate's steamapps subdir
    exists, the candidate is returned. Uses the same is_dir monkeypatch seam
    as test_steam_libraries_unescapes_windows_backslash_path so the (Linux)
    test machine doesn't need a real C:\\ filesystem."""
    monkeypatch.setattr(plat.sys, "platform", "win32")
    monkeypatch.setattr(plat.Path, "is_dir", lambda self: True)
    result = plat.steam_root_candidates()
    assert result == [Path("C:/Program Files (x86)/Steam")]


def test_find_game_dirs(tmp_path):
    steam, _, game = _make_steam_tree(tmp_path)
    assert plat.find_game_dirs(steam_roots=[steam]) == [game]


def test_missing_dirs_excluded(tmp_path):
    assert plat.candidate_save_dirs(home=tmp_path / "ghost", steam_roots=[]) == []


def test_open_folder_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(plat.sys, "platform", "linux")
    calls = []
    monkeypatch.setattr(plat.subprocess, "Popen", lambda args, **kw: calls.append(args))
    plat.open_folder(tmp_path)
    assert calls == [["xdg-open", str(tmp_path)]]


def test_open_folder_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(plat.sys, "platform", "darwin")
    calls = []
    monkeypatch.setattr(plat.subprocess, "Popen", lambda args, **kw: calls.append(args))
    plat.open_folder(tmp_path)
    assert calls == [["open", str(tmp_path)]]


def test_open_folder_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(plat.sys, "platform", "win32")
    calls = []
    # os.startfile only exists on Windows; inject it so the attribute lookup resolves.
    monkeypatch.setattr(plat.os, "startfile", lambda p: calls.append(p), raising=False)
    plat.open_folder(tmp_path)
    assert calls == [str(tmp_path)]


def test_open_folder_missing_path_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(plat.subprocess, "Popen", lambda *a, **kw: pytest.fail("should not open"))
    with pytest.raises(FileNotFoundError):
        plat.open_folder(tmp_path / "does-not-exist")
