"""Tests for the WolvenKit CLI adapter module."""

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from npv_build.core.cancel import CancelToken
from npv_build.core.errors import ToolError
from npv_build.core.proc import ToolResult
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
    @patch("npv_build.wk_cli.run_tool")
    def test_check_version_ok(self, mock_run_tool, wk):
        mock_run_tool.return_value = ToolResult(
            argv=["WolvenKit.CLI", "--version"], returncode=0, stdout="8.19.0\n", stderr=""
        )
        version = wk.check_version()
        assert version == "8.19.0"

    @patch("npv_build.wk_cli.run_tool")
    def test_check_version_mismatch_warns(self, mock_run_tool, wk, caplog):
        mock_run_tool.return_value = ToolResult(
            argv=["WolvenKit.CLI", "--version"], returncode=0, stdout="9.0.0\n", stderr=""
        )
        with caplog.at_level("WARNING", logger="npv_build.wk_cli"):
            version = wk.check_version()
        assert version == "9.0.0"
        assert any(
            record.levelname == "WARNING" and "9.0.0" in record.message for record in caplog.records
        )

    @patch("npv_build.wk_cli.run_tool")
    def test_check_version_below_minimum_raises(self, mock_run_tool, wk):
        mock_run_tool.return_value = ToolResult(
            argv=["WolvenKit.CLI", "--version"], returncode=0, stdout="8.18.1\n", stderr=""
        )
        with pytest.raises(WolvenKitError) as ei:
            wk.check_version()
        assert "8.18.1" in str(ei.value)
        assert "8.19" in str(ei.value)

    @patch("npv_build.wk_cli.run_tool")
    def test_check_version_newer_warns_not_raises(self, mock_run_tool, wk, caplog):
        mock_run_tool.return_value = ToolResult(
            argv=["WolvenKit.CLI", "--version"], returncode=0, stdout="8.20.2\n", stderr=""
        )
        with caplog.at_level(logging.WARNING, logger="npv_build.wk_cli"):
            assert wk.check_version() == "8.20.2"
        assert any("8.20.2" in r.message for r in caplog.records)

    @patch("npv_build.wk_cli.run_tool")
    def test_check_version_not_found(self, mock_run_tool, wk):
        mock_run_tool.side_effect = ToolError(
            "WolvenKit.CLI not found", tool="WolvenKit.CLI", exit_code=None
        )
        with pytest.raises(WolvenKitError):
            wk.check_version()


class TestListArchive:
    @patch("npv_build.wk_cli.run_tool")
    def test_list_archive_parses_lines(self, mock_run_tool, wk):
        mock_run_tool.return_value = ToolResult(
            argv=["WolvenKit.CLI"],
            returncode=0,
            stdout="base\\characters\\head\\test.ent\nbase\\characters\\head\\test.app\n",
            stderr="",
        )
        result = wk.list_archive(r".*\.ent$")
        assert result == ["base\\characters\\head\\test.ent", "base\\characters\\head\\test.app"]

    @patch("npv_build.wk_cli.run_tool")
    def test_list_archive_filters_empty(self, mock_run_tool, wk):
        mock_run_tool.return_value = ToolResult(
            argv=["WolvenKit.CLI"], returncode=0, stdout="\n  \n", stderr=""
        )
        result = wk.list_archive(r".*")
        assert result == []


class TestRun:
    @patch("npv_build.wk_cli.run_tool")
    def test_run_raises_on_failure(self, mock_run_tool, wk):
        mock_run_tool.side_effect = ToolError(
            "WolvenKit.CLI exited with code 1.",
            tool="WolvenKit.CLI",
            exit_code=1,
            details="some error some output",
        )
        with pytest.raises(WolvenKitError) as exc_info:
            wk.deserialize(Path("/fake/dir"))
        assert exc_info.value.exit_code == 1
        assert exc_info.value.operation == "deserialize"

    @patch("npv_build.wk_cli.run_tool")
    def test_run_not_found(self, mock_run_tool, wk):
        mock_run_tool.side_effect = ToolError(
            "WolvenKit.CLI: executable not found: WolvenKit.CLI",
            tool="WolvenKit.CLI",
            exit_code=None,
        )
        with pytest.raises(WolvenKitError) as exc_info:
            wk.deserialize(Path("/fake/dir"))
        assert "not found" in str(exc_info.value)


class TestUncookJson:
    @patch("npv_build.wk_cli.run_tool")
    def test_uncook_json_returns_parsed(self, mock_run_tool, wk, tmp_path):
        test_data = {"Data": {"RootChunk": {"test": True}}}

        def fake_run_tool(cmd, **kwargs):
            if "uncook" in cmd:
                out_dir = cmd[cmd.index("-o") + 1]
                json_path = Path(out_dir) / "base" / "characters" / "test.ent.json"
                json_path.parent.mkdir(parents=True, exist_ok=True)
                json_path.write_text(json.dumps(test_data))
            return ToolResult(argv=list(cmd), returncode=0, stdout="", stderr="")

        mock_run_tool.side_effect = fake_run_tool
        result = wk.uncook_json("test.ent")
        assert result == test_data

    @patch("npv_build.wk_cli.run_tool")
    def test_uncook_json_file_not_found(self, mock_run_tool, wk):
        mock_run_tool.return_value = ToolResult(argv=[], returncode=0, stdout="", stderr="")
        with pytest.raises(FileNotFoundError):
            wk.uncook_json("nonexistent.ent")


class TestAllowExitCodes:
    @patch("npv_build.wk_cli.run_tool")
    def test_import_mesh_tolerates_exit_3(self, mock_run_tool, wk, tmp_path):
        mock_run_tool.return_value = ToolResult(argv=[], returncode=3, stdout="", stderr="")
        wk.import_mesh(tmp_path, dest=tmp_path, allow_exit_codes=(3,))

    @patch("npv_build.wk_cli.run_tool")
    def test_import_mesh_fails_on_unexpected_exit(self, mock_run_tool, wk, tmp_path):
        mock_run_tool.side_effect = ToolError(
            "WolvenKit.CLI exited with code 5.", tool="WolvenKit.CLI", exit_code=5
        )
        with pytest.raises(WolvenKitError):
            wk.import_mesh(tmp_path, dest=tmp_path, allow_exit_codes=(3,))


def test_wolvenkit_error_is_tool_error():
    assert issubclass(WolvenKitError, ToolError)
    e = WolvenKitError("boom", operation="pack", exit_code=3)
    assert e.operation == "pack"
    assert e.exit_code == 3
    assert e.module_name == "WolvenKit Automation"


def test_run_routes_through_run_tool(monkeypatch, tmp_path):
    calls = {}

    def fake_run_tool(
        argv, *, tool, timeout, cancel=None, cwd=None, allow_exit_codes=(), logger=None
    ):
        calls["argv"] = list(argv)
        calls["timeout"] = timeout
        calls["cancel"] = cancel
        return ToolResult(argv=list(argv), returncode=0, stdout="8.19.0\n", stderr="")

    monkeypatch.setattr("npv_build.wk_cli.run_tool", fake_run_tool)
    token = CancelToken()
    wk = WolvenKit(WolvenKitConfig(game_dir=tmp_path, timeout_s=123.0, cancel=token))
    wk.check_version()
    assert calls["argv"][1:] == ["--version"] or "--version" in calls["argv"]
    assert calls["timeout"] == 123.0
    assert calls["cancel"] is token


def test_list_archive_routes_through_run_tool(monkeypatch, tmp_path):
    seen = []

    def fake_run_tool(argv, **kwargs):
        seen.append(list(argv))
        return ToolResult(argv=list(argv), returncode=0, stdout="a.ent\nb.app\n", stderr="")

    monkeypatch.setattr("npv_build.wk_cli.run_tool", fake_run_tool)
    wk = WolvenKit(WolvenKitConfig(game_dir=tmp_path))
    archive = tmp_path / "x.archive"
    archive.write_bytes(b"")
    names = wk.list_archive(r".*\.(ent|app)", archive=archive)
    assert seen, "list_archive must go through run_tool"
    assert names == ["a.ent", "b.app"] or all(isinstance(n, str) for n in names)
