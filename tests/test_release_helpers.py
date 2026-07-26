from pathlib import Path

import pytest

from scripts.build_release_helpers import _remove_foreign_native_assets, publish_helper


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
        (output / executable_name).touch()
        (output / "helper.pdb").touch()
        (output / "foreign.dylib").touch()
        (output / "managed.dll").touch()

    monkeypatch.setattr("scripts.build_release_helpers.subprocess.run", fake_run)

    executable = publish_helper(repo, tmp_path / "out", "npv-photomode", rid)

    assert executable.name == executable_name
    assert calls[0][1]["check"] is True
    command = calls[0][0]
    assert "--self-contained" in command
    assert "-p:PublishSingleFile=false" in command
    _remove_foreign_native_assets(executable.parent, rid)
    assert not (executable.parent / "foreign.dylib").exists()
    assert (executable.parent / "managed.dll").exists()


def test_publish_helper_rejects_missing_project(tmp_path):
    with pytest.raises(FileNotFoundError, match="Missing helper project"):
        publish_helper(tmp_path, tmp_path / "out", "npv-inject", "linux-x64")
