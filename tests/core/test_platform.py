from pathlib import Path

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
        lib2 / "steamapps" / "compatdata" / plat.GAME_STEAM_APPID / "pfx" / "drive_c"
        / "users" / "steamuser" / "Saved Games" / "CD Projekt Red" / "Cyberpunk 2077"
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


def test_candidate_save_dirs_windows_layout(tmp_path):
    d = _make_windows_save(tmp_path)
    dirs = plat.candidate_save_dirs(home=tmp_path / "home", steam_roots=[])
    assert d in dirs


def test_candidate_save_dirs_proton(tmp_path):
    steam, save, _ = _make_steam_tree(tmp_path)
    dirs = plat.candidate_save_dirs(home=tmp_path / "nohome", steam_roots=[steam])
    assert save in dirs


def test_find_game_dirs(tmp_path):
    steam, _, game = _make_steam_tree(tmp_path)
    assert plat.find_game_dirs(steam_roots=[steam]) == [game]


def test_missing_dirs_excluded(tmp_path):
    assert plat.candidate_save_dirs(home=tmp_path / "ghost", steam_roots=[]) == []
