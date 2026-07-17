import os
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

_HAS_DISPLAY = bool(os.environ.get("DISPLAY"))


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


@pytest.mark.skipif(not _HAS_DISPLAY, reason="requires a display (headless environment)")
def test_modmanager_view_instantiates(tmp_path):
    import customtkinter as ctk

    from npv_build.gui_views.modmanager_view import ModManagerView

    out = tmp_path / "out"
    out.mkdir()
    _built_mod(out, "my_v_abc")
    game = _game(tmp_path / "game")

    root = ctk.CTk()
    try:
        view = ModManagerView(root, output_root=out, game_dir=game)
        root.update()
        assert view is not None
    finally:
        root.destroy()
