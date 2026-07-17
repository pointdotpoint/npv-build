import logging

import npv_build.part_resolver as pr
from npv_build.core.errors import NpvError, ToolError


def test_resolver_error_is_npv_error():
    assert issubclass(pr.ResolverError, NpvError)


def test_extract_recipe_skips_on_tool_error_with_warning(monkeypatch, tmp_path, caplog):
    """Recipe extraction (base-game archive, best-effort enhancement layer) is a
    sanctioned skip: ToolError -> warn + empty result. The caller (mapping.py)
    already treats a missing recipe as a graceful degrade to a plain part list,
    so this matches existing pipeline behavior rather than masking a required
    dependency failure.
    """

    def exploding_run_tool(argv, **kwargs):
        raise ToolError("corrupt archive", tool="WolvenKit.CLI")

    monkeypatch.setattr(pr, "run_tool", exploding_run_tool)

    game_dir = tmp_path / "Cyberpunk 2077"
    archive_dir = game_dir / "archive" / "pc" / "content"
    archive_dir.mkdir(parents=True)
    (archive_dir / "basegame_4_appearance.archive").write_bytes(b"not an archive")

    with caplog.at_level(logging.WARNING, logger="npv_build.part_resolver"):
        result = pr.extract_recipe(game_dir, {"some/app/path.app": "some_appearance"}, verbosity=0)

    assert result == {"parts": [], "overrides": []}
    assert any("basegame_4_appearance.archive" in rec.message for rec in caplog.records)


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
