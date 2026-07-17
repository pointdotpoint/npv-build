import zipfile

import pytest

from npv_build.core.errors import PackagingError
from npv_build.core.packaging import package_mod


def _make_build_tree(tmp_path, mod_id="my_v_abc123"):
    out = tmp_path / "out"
    archive_dir = out / "archive" / "pc" / "mod"
    archive_dir.mkdir(parents=True)
    (archive_dir / f"{mod_id}.archive").write_bytes(b"archive-bytes")

    lua_dir = (
        out
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
    (lua_dir / f"{mod_id}.lua").write_text("-- amm lua")

    return out


def test_zip_contains_archive_at_game_relative_path(tmp_path):
    out = _make_build_tree(tmp_path)
    zip_path = package_mod(out, "my_v_abc123")

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "archive/pc/mod/my_v_abc123.archive" in names


def test_zip_includes_lua_and_excludes_byproducts(tmp_path):
    out = _make_build_tree(tmp_path)
    (out / "source").mkdir()
    (out / "source" / "junk").write_text("junk")
    (out / "cc_settings.json").write_text("{}")
    (out / "asset_paths.json").write_text("{}")
    (out / "npv_components.json").write_text("{}")
    (out / "logs").mkdir()
    (out / "logs" / "build.log").write_text("log")
    (out / ".npv_manifest.json").write_text("{}")

    zip_path = package_mod(out, "my_v_abc123")

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

    expected_lua = (
        "bin/x64/plugins/cyber_engine_tweaks/mods/AppearanceMenuMod/"
        "Collabs/Custom Entities/my_v_abc123.lua"
    )
    assert expected_lua in names
    assert not any(n.startswith("source/") for n in names)
    assert not any(n.startswith("logs/") for n in names)
    for excluded in (
        "cc_settings.json",
        "asset_paths.json",
        "npv_components.json",
        ".npv_manifest.json",
    ):
        assert excluded not in names


def test_default_zip_path_is_output_dir_slash_mod_id(tmp_path):
    out = _make_build_tree(tmp_path)
    zip_path = package_mod(out, "my_v_abc123")
    assert zip_path == out / "my_v_abc123.zip"


def test_packaging_is_deterministic_across_calls(tmp_path):
    out = _make_build_tree(tmp_path)
    zip_path = package_mod(out, "my_v_abc123", zip_path=tmp_path / "one.zip")
    first_bytes = zip_path.read_bytes()
    with zipfile.ZipFile(zip_path) as zf:
        first_names = zf.namelist()

    zip_path2 = package_mod(out, "my_v_abc123", zip_path=tmp_path / "two.zip")
    second_bytes = zip_path2.read_bytes()
    with zipfile.ZipFile(zip_path2) as zf:
        second_names = zf.namelist()

    assert first_names == second_names
    assert first_bytes == second_bytes


def test_raises_packaging_error_when_no_archive_present(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(PackagingError):
        package_mod(out, "my_v_abc123")
