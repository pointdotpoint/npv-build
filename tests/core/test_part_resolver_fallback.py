import json
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


def test_extract_hair_components_resolves_generic_ccxl_from_aggregate_mod_directory(tmp_path):
    game_dir = tmp_path / "Cyberpunk 2077"
    mod_dir = game_dir / "archive" / "pc" / "mod"
    mod_dir.mkdir(parents=True)
    (mod_dir / "#B1W_CCXL_S2-g.archive").write_bytes(b"archive")
    (mod_dir / "b1whair003ccxl.archive.xl").write_text(
        "resource:\n"
        "  scope:\n"
        "    player_wa_hair.app:\n"
        "      - b1w\\\\ccxl\\\\hair003\\\\appearances\\\\b1w_003_wa.app\n"
        "      - b1w\\\\ccxl\\\\hair003\\\\appearances\\\\fpp\\\\b1w_003_wa_fpp.app\n"
    )
    depot = r"b1w\ccxl\hair003\appearances\b1w_003_wa.app"

    class FakeWk:
        def __init__(self):
            self.listed = []
            self.uncooked_from = None

        def list_archive(self, pattern, *, archive):
            self.listed.append(archive)
            return [depot] if archive == mod_dir else []

        def uncook_many(self, pattern, *, archive, dest):
            self.uncooked_from = archive
            output = dest / (depot.replace("\\", "/") + ".json")
            output.parent.mkdir(parents=True)
            output.write_text(
                json.dumps(
                    {
                        "Data": {
                            "RootChunk": {
                                "appearances": [
                                    {
                                        "Data": {
                                            "name": {"$value": "default"},
                                            "compiledData": {
                                                "Data": {
                                                    "Chunks": [
                                                        {
                                                            "$type": "entSkinnedMeshComponent",
                                                            "name": {"$value": "b1w003"},
                                                        }
                                                    ]
                                                }
                                            },
                                        }
                                    }
                                ]
                            }
                        }
                    }
                )
            )

    wk = FakeWk()

    components, source, app_depot, appearance = pr.extract_hair_components(
        game_dir, "b1w_003_wa", body_rig="pwa", wk=wk
    )

    assert wk.listed[0] == mod_dir
    assert wk.uncooked_from == mod_dir
    assert app_depot == depot
    assert source == "b1whair003ccxl.archive.xl"
    assert appearance == "default"
    assert components[0]["name"]["$value"] == "b1w003"


def test_hair_registration_status_finds_saved_ccxl_dependency(tmp_path):
    mod_dir = tmp_path / "archive" / "pc" / "mod"
    mod_dir.mkdir(parents=True)
    (mod_dir / "b1whair003ccxl.archive.xl").write_text(
        "resource:\n"
        "  - b1w\\ccxl\\hair003\\appearances\\b1w_003_wa.app\n"
        "  - b1w\\ccxl\\hair003\\appearances\\fpp\\b1w_003_wa_fpp.app\n"
    )

    assert pr.hair_registration_status(tmp_path, "b1w_003_wa") == {
        "state": "registered",
        "selection_label": "b1w_003_wa",
        "depot": r"b1w\ccxl\hair003\appearances\b1w_003_wa.app",
        "source": "b1whair003ccxl.archive.xl",
    }


def test_exact_hair_ranking_prefers_tpp_requested_rig_and_non_cyberware():
    basename = "shared_hair.app"
    paths = [
        r"mods\pwa\fpp\shared_hair.app",
        r"mods\pma\tpp\shared_hair.app",
        r"mods\pwa\cyberware\shared_hair.app",
        r"mods\pwa\tpp\shared_hair.app",
    ]

    assert pr._select_exact_hair_path(paths, basename, "pwa") == (r"mods\pwa\tpp\shared_hair.app")


def test_exact_hair_ranking_rejects_equal_best_tie():
    assert (
        pr._select_exact_hair_path(
            [
                r"author_a\pwa\tpp\shared_hair.app",
                r"author_b\pwa\tpp\shared_hair.app",
            ],
            "shared_hair.app",
            "pwa",
        )
        is None
    )


def test_archive_xl_sidecar_never_derives_archive_archive(tmp_path):
    game_dir = tmp_path / "Cyberpunk 2077"
    mod_dir = game_dir / "archive" / "pc" / "mod"
    mod_dir.mkdir(parents=True)
    archive = mod_dir / "b1whair003ccxl.archive"
    archive.write_bytes(b"archive")
    (mod_dir / "b1whair003ccxl.archive.xl").write_text(
        "resource:\n  - b1w\\\\ccxl\\\\hair003\\\\appearances\\\\b1w_003_wa.app\n"
    )
    depot = r"b1w\ccxl\hair003\appearances\b1w_003_wa.app"

    class FakeWk:
        def __init__(self):
            self.archives = []

        def list_archive(self, pattern, *, archive):
            self.archives.append(archive)
            if archive == mod_dir:
                return []
            return [depot] if archive == archive_path else []

        def uncook_many(self, pattern, *, archive, dest):
            output = dest / (depot.replace("\\", "/") + ".json")
            output.parent.mkdir(parents=True)
            output.write_text(
                json.dumps(
                    {
                        "Data": {
                            "RootChunk": {
                                "appearances": [
                                    {
                                        "Data": {
                                            "name": {"$value": "default"},
                                            "compiledData": {"Data": {"Chunks": []}},
                                        }
                                    }
                                ]
                            }
                        }
                    }
                )
            )

    archive_path = archive
    wk = FakeWk()
    pr.extract_hair_components(
        game_dir,
        "b1w_003_wa",
        body_rig="pwa",
        wk=wk,
    )

    assert archive_path in wk.archives
    assert all(path.name != "b1whair003ccxl.archive.archive" for path in wk.archives)
