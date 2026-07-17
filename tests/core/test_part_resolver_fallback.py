import logging

import pytest

import npv_build.part_resolver as pr
from npv_build.core.errors import NpvError, ToolError
from npv_build.wk_cli import WolvenKitError


def test_resolver_error_is_npv_error():
    assert issubclass(pr.ResolverError, NpvError)


def test_extract_recipe_hard_fails_on_tool_error(monkeypatch, tmp_path):
    """Recipe extraction reads the REQUIRED base-game archive
    (basegame_4_appearance.archive). Per spec ERR-2 (no degraded output), a
    ToolError here must propagate as ResolverError rather than being
    swallowed into a silent plain-part-list fallback.
    """

    def exploding_run_tool(argv, **kwargs):
        raise ToolError("corrupt archive", tool="WolvenKit.CLI")

    monkeypatch.setattr(pr, "run_tool", exploding_run_tool)

    game_dir = tmp_path / "Cyberpunk 2077"
    archive_dir = game_dir / "archive" / "pc" / "content"
    archive_dir.mkdir(parents=True)
    (archive_dir / "basegame_4_appearance.archive").write_bytes(b"not an archive")

    with pytest.raises(pr.ResolverError, match="basegame_4_appearance.archive"):
        pr.extract_recipe(game_dir, {"some/app/path.app": "some_appearance"}, verbosity=0)


def test_extract_recipe_hard_fails_on_wk_adapter_tool_error(tmp_path):
    """Same as test_extract_recipe_hard_fails_on_tool_error but drives the
    `wk`-adapter branch (extract_recipe(..., wk=fake_wk)) instead of the
    direct-subprocess branch, mirroring it 1:1. A WolvenKitError from the
    adapter's uncook_many() must also hard-fail as ResolverError, not be
    swallowed."""

    class ExplodingWk:
        def uncook_many(self, *args, **kwargs):
            raise WolvenKitError("corrupt archive", operation="uncook")

    game_dir = tmp_path / "Cyberpunk 2077"
    archive_dir = game_dir / "archive" / "pc" / "content"
    archive_dir.mkdir(parents=True)
    (archive_dir / "basegame_4_appearance.archive").write_bytes(b"not an archive")

    with pytest.raises(pr.ResolverError, match="basegame_4_appearance.archive"):
        pr.extract_recipe(
            game_dir,
            {"some/app/path.app": "some_appearance"},
            verbosity=0,
            wk=ExplodingWk(),
        )


def test_extract_recipe_resolver_error_forwards_tool_error_details(monkeypatch, tmp_path):
    """ResolverError wrapping a ToolError must forward the tool's `.details`
    (e.g. captured stderr tail) via ResolverError(..., details=...), and its
    message must include the ToolError's `.user_message`, so frontends can
    surface the underlying tool output instead of just the wrapper text."""

    def exploding_run_tool(argv, **kwargs):
        raise ToolError("corrupt archive", tool="WolvenKit.CLI", details="stderr: bad magic bytes")

    monkeypatch.setattr(pr, "run_tool", exploding_run_tool)

    game_dir = tmp_path / "Cyberpunk 2077"
    archive_dir = game_dir / "archive" / "pc" / "content"
    archive_dir.mkdir(parents=True)
    (archive_dir / "basegame_4_appearance.archive").write_bytes(b"not an archive")

    with pytest.raises(pr.ResolverError) as exc_info:
        pr.extract_recipe(game_dir, {"some/app/path.app": "some_appearance"}, verbosity=0)

    err = exc_info.value
    assert "corrupt archive" in err.user_message
    assert err.details == "stderr: bad magic bytes"


def test_extract_hair_components_skips_broken_mod_archive_with_warning(
    monkeypatch, tmp_path, caplog
):
    """Third-party mod archives are the sanctioned skip: ToolError while listing
    a mod archive -> warn + continue past it (not a crash)."""

    def exploding_run_tool(argv, **kwargs):
        raise ToolError("corrupt archive", tool="WolvenKit.CLI")

    monkeypatch.setattr(pr, "run_tool", exploding_run_tool)

    game_dir = tmp_path / "Cyberpunk 2077"
    mod_dir = game_dir / "archive" / "pc" / "mod"
    mod_dir.mkdir(parents=True)
    broken = mod_dir / "broken_hair_mod.archive"
    broken.write_bytes(b"not an archive")

    with caplog.at_level(logging.WARNING, logger="npv_build.part_resolver"):
        result = pr.extract_hair_components(game_dir, "fhair_test_style", verbosity=0)

    assert result == ([], None, None, None)
    assert any("broken_hair_mod" in rec.message for rec in caplog.records)
