"""Tests for the WolvenKit CLI adapter module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from npv_build.wk_cli import WolvenKit, WolvenKitConfig, WolvenKitError


@pytest.fixture
def wk():
    config = WolvenKitConfig(
        game_dir=Path("/fake/game"),
        cli_binary="WolvenKit.CLI",
        verbosity=0,
    )
    return WolvenKit(config)


class TestWolvenKitConfig:
    def test_appearance_archive_path(self):
        cfg = WolvenKitConfig(game_dir=Path("/game"))
        assert cfg.appearance_archive == Path(
            "/game/archive/pc/content/basegame_4_appearance.archive"
        )

    def test_appearance_archive_no_game_dir(self):
        cfg = WolvenKitConfig()
        with pytest.raises(WolvenKitError):
            _ = cfg.appearance_archive

    def test_frozen(self):
        cfg = WolvenKitConfig(game_dir=Path("/game"))
        with pytest.raises(AttributeError):
            cfg.verbosity = 2


class TestCheckVersion:
    @patch("npv_build.wk_cli.subprocess.run")
    def test_check_version_ok(self, mock_run, wk):
        mock_run.return_value = MagicMock(stdout="8.18.1\n", returncode=0)
        version = wk.check_version()
        assert version == "8.18.1"

    @patch("npv_build.wk_cli.subprocess.run")
    def test_check_version_mismatch_warns(self, mock_run, wk, capsys):
        mock_run.return_value = MagicMock(stdout="9.0.0\n", returncode=0)
        version = wk.check_version()
        assert version == "9.0.0"
        assert "Warning" in capsys.readouterr().err

    @patch("npv_build.wk_cli.subprocess.run")
    def test_check_version_not_found(self, mock_run, wk):
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(WolvenKitError):
            wk.check_version()


class TestListArchive:
    @patch("npv_build.wk_cli.subprocess.run")
    def test_list_archive_parses_lines(self, mock_run, wk):
        mock_run.return_value = MagicMock(
            stdout="base\\characters\\head\\test.ent\nbase\\characters\\head\\test.app\n",
            returncode=0,
        )
        result = wk.list_archive(r".*\.ent$")
        assert result == ["base\\characters\\head\\test.ent", "base\\characters\\head\\test.app"]

    @patch("npv_build.wk_cli.subprocess.run")
    def test_list_archive_filters_empty(self, mock_run, wk):
        mock_run.return_value = MagicMock(stdout="\n  \n", returncode=0)
        result = wk.list_archive(r".*")
        assert result == []


class TestRun:
    @patch("subprocess.run")
    def test_run_raises_on_failure(self, mock_run, wk):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="some output",
            stderr="some error",
        )
        with pytest.raises(WolvenKitError) as exc_info:
            wk.deserialize(Path("/fake/dir"))
        assert exc_info.value.exit_code == 1
        assert exc_info.value.operation == "deserialize"

    @patch("subprocess.run")
    def test_run_not_found(self, mock_run, wk):
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(WolvenKitError) as exc_info:
            wk.deserialize(Path("/fake/dir"))
        assert "not found" in str(exc_info.value)


class TestUncookJson:
    @patch("subprocess.run")
    def test_uncook_json_returns_parsed(self, mock_run, wk, tmp_path):
        test_data = {"Data": {"RootChunk": {"test": True}}}

        def fake_run(cmd, **kwargs):
            if "uncook" in cmd:
                out_dir = cmd[cmd.index("-o") + 1]
                json_path = Path(out_dir) / "base" / "characters" / "test.ent.json"
                json_path.parent.mkdir(parents=True, exist_ok=True)
                json_path.write_text(json.dumps(test_data))
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run
        result = wk.uncook_json("test.ent")
        assert result == test_data

    @patch("subprocess.run")
    def test_uncook_json_file_not_found(self, mock_run, wk):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        with pytest.raises(FileNotFoundError):
            wk.uncook_json("nonexistent.ent")


class TestAllowExitCodes:
    @patch("subprocess.run")
    def test_import_mesh_tolerates_exit_3(self, mock_run, wk, tmp_path):
        mock_run.return_value = MagicMock(returncode=3, stdout="", stderr="")
        wk.import_mesh(tmp_path, dest=tmp_path, allow_exit_codes=(3,))

    @patch("subprocess.run")
    def test_import_mesh_fails_on_unexpected_exit(self, mock_run, wk, tmp_path):
        mock_run.return_value = MagicMock(returncode=5, stdout="", stderr="")
        with pytest.raises(WolvenKitError):
            wk.import_mesh(tmp_path, dest=tmp_path, allow_exit_codes=(3,))
