from pathlib import Path

import pytest

from scripts.build_release_helpers import (
    _assert_stj_not_clobbered,
    _remove_foreign_native_assets,
    helper_output_dir,
    publish_helper,
)


@pytest.mark.parametrize(
    ("rid", "executable_name"),
    [("linux-x64", "npv-photomode"), ("win-x64", "npv-photomode.exe")],
)
def test_publish_helper_builds_expected_self_contained_binary(
    monkeypatch, tmp_path, rid, executable_name
):
    repo = tmp_path / "repo"
    project = repo / "tools" / "npv-photomode" / "npv-photomode.csproj"
    project.parent.mkdir(parents=True)
    project.touch()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        output = Path(command[command.index("-o") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / executable_name).touch()
        (output / "helper.pdb").touch()
        (output / "foreign.dylib").touch()
        (output / "managed.dll").touch()

    monkeypatch.setattr("scripts.build_release_helpers.subprocess.run", fake_run)

    out_root = tmp_path / "out"
    executable = publish_helper(repo, out_root, "npv-photomode", rid)

    assert executable.name == executable_name
    # Isolated subdir — not the shared root.
    assert executable.parent == helper_output_dir(out_root, "npv-photomode")
    assert executable.parent != out_root
    assert calls[0][1]["check"] is True
    command = calls[0][0]
    assert "--self-contained" in command
    assert "-p:PublishSingleFile=false" in command
    assert not (executable.parent / "foreign.dylib").exists()
    assert (executable.parent / "managed.dll").exists()


def test_publish_helper_rejects_missing_project(tmp_path):
    with pytest.raises(FileNotFoundError, match="Missing helper project"):
        publish_helper(tmp_path, tmp_path / "out", "npv-inject", "linux-x64")


def test_helpers_do_not_share_one_flat_output_dir(monkeypatch, tmp_path):
    """Regression: publishing all helpers into one folder clobbered STJ 9.x."""
    repo = tmp_path / "repo"
    for name in ("npv-inject", "npv-photomode", "npv-tweakdb"):
        p = repo / "tools" / name / f"{name}.csproj"
        p.parent.mkdir(parents=True)
        p.touch()

    def fake_run(command, **kwargs):
        output = Path(command[command.index("-o") + 1])
        output.mkdir(parents=True, exist_ok=True)
        helper = output.name
        exe = f"{helper}.exe" if "win-x64" in command else helper
        (output / exe).touch()
        # Simulate inject/photomode shipping small STJ 9 vs tweakdb large STJ 8.
        size = 1_400_000 if helper == "npv-tweakdb" else 640_000
        (output / "System.Text.Json.dll").write_bytes(b"\0" * size)
        if helper != "npv-tweakdb":
            (output / f"{helper}.deps.json").write_text(
                '{"libraries": {"System.Text.Json/9.0.2": {}}}'
            )
        else:
            (output / f"{helper}.deps.json").write_text('{"libraries": {}}')

    monkeypatch.setattr("scripts.build_release_helpers.subprocess.run", fake_run)

    out = tmp_path / "helpers"
    out.mkdir()
    paths = [
        publish_helper(repo, out, h, "linux-x64")
        for h in (
            "npv-inject",
            "npv-photomode",
            "npv-tweakdb",
        )
    ]
    # Distinct directories
    parents = {p.parent for p in paths}
    assert len(parents) == 3
    # Inject kept its small (9.x-sized) STJ; not overwritten by tweakdb.
    inject_stj = out / "npv-inject" / "System.Text.Json.dll"
    tweak_stj = out / "npv-tweakdb" / "System.Text.Json.dll"
    assert inject_stj.stat().st_size == 640_000
    assert tweak_stj.stat().st_size == 1_400_000
    _assert_stj_not_clobbered(out / "npv-inject")


def test_assert_stj_not_clobbered_detects_framework_overwrite(tmp_path):
    d = tmp_path / "npv-inject"
    d.mkdir()
    (d / "npv-inject.deps.json").write_text('{"libraries": {"System.Text.Json/9.0.2": {}}}')
    (d / "System.Text.Json.dll").write_bytes(b"\0" * 1_476_944)
    with pytest.raises(RuntimeError, match="clobber"):
        _assert_stj_not_clobbered(d)


def test_remove_foreign_native_assets_recursive(tmp_path):
    nested = tmp_path / "sub"
    nested.mkdir()
    (nested / "libfoo.so").write_text("x")
    (nested / "keep.dll").write_text("x")
    _remove_foreign_native_assets(tmp_path, "win-x64")
    assert not (nested / "libfoo.so").exists()
    assert (nested / "keep.dll").exists()
