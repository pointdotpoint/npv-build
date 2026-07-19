from pathlib import Path

import pytest

from npv_build.core.errors import InstallError
from npv_build.gui_logic.modmanager import (
    ModEntry,
    game_mod_dir,
    install_mod,
    list_mods,
    uninstall_mod,
)


def _built_mod(root: Path, mod_id: str) -> Path:
    d = root / mod_id
    (d / "archive" / "pc" / "mod").mkdir(parents=True)
    (d / "archive" / "pc" / "mod" / f"{mod_id}.archive").write_bytes(b"A")
    lua_dir = (
        d
        / "bin"
        / "x64"
        / "plugins"
        / "cyber_engine_tweaks"
        / "mods"
        / "AppearanceMenuMod"
        / "Collabs"
        / "Custom Entities"
    )
    lua_dir.mkdir(parents=True)
    (lua_dir / f"{mod_id}.lua").write_text("return {}", encoding="utf-8")
    return d


def _add_photomode_files(mod_root: Path, mod_id: str) -> None:
    mod_dir = mod_root / "archive" / "pc" / "mod"
    (mod_dir / f"{mod_id}_photomode.archive.xl").write_text("resource:", encoding="utf-8")
    tweaks = mod_root / "r6" / "tweaks" / "npv_build"
    tweaks.mkdir(parents=True)
    (tweaks / f"{mod_id}_photomode.yaml").write_text("x: 1", encoding="utf-8")


def _game(tmp_path: Path) -> Path:
    (tmp_path / "archive" / "pc" / "mod").mkdir(parents=True)
    return tmp_path


def test_list_and_install_roundtrip(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    _built_mod(out, "my_v_abc")
    game = _game(tmp_path / "game")

    mods = list_mods(out, game)
    assert len(mods) == 1 and mods[0].mod_id == "my_v_abc" and mods[0].installed is False

    install_mod(mods[0], game)
    assert (game_mod_dir(game) / "my_v_abc.archive").is_file()
    assert list_mods(out, game)[0].installed is True

    uninstall_mod(mods[0], game)
    assert not (game_mod_dir(game) / "my_v_abc.archive").exists()


def test_install_copies_full_payload_including_photomode(tmp_path):
    """Install must carry ALL payload files (photomode .archive.xl and r6 tweaks
    yaml), not just archive + lua. Regression: GUI QA found photomode files
    silently missing after install."""
    out = tmp_path / "out"
    out.mkdir()
    mod_root = _built_mod(out, "my_v_abc")
    _add_photomode_files(mod_root, "my_v_abc")
    game = _game(tmp_path / "game")

    entry = list_mods(out, game)[0]
    install_mod(entry, game)

    assert (game / "archive" / "pc" / "mod" / "my_v_abc_photomode.archive.xl").is_file()
    assert (game / "r6" / "tweaks" / "npv_build" / "my_v_abc_photomode.yaml").is_file()

    uninstall_mod(entry, game)
    assert not (game / "archive" / "pc" / "mod" / "my_v_abc_photomode.archive.xl").exists()
    assert not (game / "r6" / "tweaks" / "npv_build" / "my_v_abc_photomode.yaml").exists()
    # archive + lua removed too
    assert not (game_mod_dir(game) / "my_v_abc.archive").exists()


def test_list_mods_reports_built_at(tmp_path):
    import os

    out = tmp_path / "out"
    out.mkdir()
    mod_root = _built_mod(out, "my_v_abc")
    archive = mod_root / "archive" / "pc" / "mod" / "my_v_abc.archive"
    os.utime(archive, (1000, 1234.5))
    game = _game(tmp_path / "game")
    [entry] = list_mods(out, game)
    assert entry.built_at == 1234.5


def test_delete_mod_removes_output_and_installed_files(tmp_path):
    from npv_build.gui_logic.modmanager import delete_mod

    out = tmp_path / "out"
    out.mkdir()
    mod_root = _built_mod(out, "my_v_abc")
    _add_photomode_files(mod_root, "my_v_abc")
    game = _game(tmp_path / "game")
    entry = list_mods(out, game)[0]
    install_mod(entry, game)

    delete_mod(entry, game)
    assert not mod_root.exists()
    assert not (game_mod_dir(game) / "my_v_abc.archive").exists()
    assert not (game / "r6" / "tweaks" / "npv_build" / "my_v_abc_photomode.yaml").exists()
    assert list_mods(out, game) == []


def test_install_missing_source_raises(tmp_path):
    game = _game(tmp_path / "game")
    ghost = ModEntry(
        mod_id="x",
        archive_path=tmp_path / "nope.archive",
        lua_path=tmp_path / "nope.lua",
        installed=False,
    )
    with pytest.raises(InstallError):
        install_mod(ghost, game)


def test_install_permission_denied_raises_install_error(tmp_path, monkeypatch):
    """A read-only/permission-denied game dir must surface as InstallError, not
    a bare OSError/PermissionError (GUI-8: no raw tracebacks in the UI)."""
    import shutil as shutil_mod

    out = tmp_path / "out"
    out.mkdir()
    _built_mod(out, "my_v_abc")
    game = _game(tmp_path / "game")
    entry = list_mods(out, game)[0]

    def _raise(*args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(shutil_mod, "copy2", _raise)

    with pytest.raises(InstallError):
        install_mod(entry, game)


def test_uninstall_permission_denied_raises_install_error(tmp_path, monkeypatch):
    """Same guarantee for uninstall_mod: OSError during unlink becomes InstallError."""
    out = tmp_path / "out"
    out.mkdir()
    _built_mod(out, "my_v_abc")
    game = _game(tmp_path / "game")
    entry = list_mods(out, game)[0]
    install_mod(entry, game)
    entry = list_mods(out, game)[0]
    assert entry.installed is True

    def _raise(self, *args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(Path, "unlink", _raise)

    with pytest.raises(InstallError):
        uninstall_mod(entry, game)
