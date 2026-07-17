import pytest

from npv_build import cli
from npv_build.core.errors import NpvError


def test_new_flags_parse(monkeypatch, tmp_path, capsys):
    called = {}

    class FakeService:
        def build(self, req, on_event=None, cancel=None):
            called["resume"] = req.resume
            raise NpvError("stop here", remediation="do the thing")

    monkeypatch.setattr(cli, "PipelineService", FakeService)
    save = tmp_path / "sav.dat"
    save.write_bytes(b"x")
    argv = [
        str(save),
        "My V",
        "--output",
        str(tmp_path / "out"),
        "--game-dir",
        str(tmp_path),
        "--resume",
        "--log-file",
        str(tmp_path / "x.log"),
    ]
    with pytest.raises(SystemExit) as ei:
        cli.main(argv)
    assert ei.value.code == 1
    assert called["resume"] is True
    err = capsys.readouterr().err
    assert "stop here" in err
    assert "do the thing" in err
