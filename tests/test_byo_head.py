import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from npv_build.cli import main
from npv_build.head_bake import _finalize_head, _get_glb_vertex_count


def test_cli_no_restore_without_head_mesh():
    # If --no-restore-head-materials is passed without --head-mesh
    with patch(
        "sys.argv", ["npv-build", "my_v", "--output", "out_dir", "--no-restore-head-materials"]
    ):
        with pytest.raises(SystemExit):
            main()


def test_cli_heb_without_head_flag():
    # If --heb-mesh is passed without --head-glb or --head-mesh
    with patch("sys.argv", ["npv-build", "my_v", "--output", "out_dir", "--heb-mesh", "foo.mesh"]):
        with pytest.raises(SystemExit):
            main()


def test_cli_both_head_flags():
    # If both --head-glb and --head-mesh are passed
    with patch(
        "sys.argv",
        [
            "npv-build",
            "my_v",
            "--output",
            "out_dir",
            "--head-glb",
            "foo.glb",
            "--head-mesh",
            "bar.mesh",
        ],
    ):
        with pytest.raises(SystemExit):
            main()


def test_cli_missing_head_glb():
    with patch(
        "sys.argv", ["npv-build", "my_v", "--output", "out_dir", "--head-glb", "nonexistent.glb"]
    ):
        with pytest.raises(SystemExit):
            main()


def test_cli_wrong_extension_head_glb(tmp_path):
    wrong_file = tmp_path / "wrong.mesh"
    wrong_file.write_text("dummy")
    with patch(
        "sys.argv", ["npv-build", "my_v", "--output", "out_dir", "--head-glb", str(wrong_file)]
    ):
        with pytest.raises(SystemExit):
            main()


@patch("npv_build.cli.PipelineService")
@patch("npv_build.cli.load_config")
def test_cli_valid_glb_override(mock_load_config, mock_pipeline_service_cls, tmp_path):
    mock_load_config.return_value = {"game_dir": "/dummy/game/dir"}
    valid_glb = tmp_path / "valid.glb"
    valid_glb.write_text("dummy")

    cc_json = tmp_path / "cc.json"
    cc_json.write_text("{}")

    mock_service = mock_pipeline_service_cls.return_value
    mock_service.build.return_value = MagicMock(output_dir="out_dir")

    with patch(
        "sys.argv",
        [
            "npv-build",
            "my_v",
            "--output",
            "out_dir",
            "--cc-json",
            str(cc_json),
            "--head-glb",
            str(valid_glb),
        ],
    ):
        main()

    mock_service.build.assert_called_once()
    req = mock_service.build.call_args[0][0]
    assert req.user_head_glb == valid_glb.resolve()


@patch("npv_build.head_bake._read_glb_json")
def test_get_glb_vertex_count(mock_read):
    mock_read.return_value = {
        "accessors": [{"count": 100}, {"count": 50}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }
    assert _get_glb_vertex_count(Path("dummy.glb")) == 100


@patch("npv_build.head_bake._restore_head_materials")
@patch("npv_build.head_bake._restore_part_materials")
def test_finalize_head_skips_materials(mock_restore_part, mock_restore_head, tmp_path):
    wk = MagicMock()
    wk.uncook_json.return_value = {
        "Data": {"RootChunk": {"baseMesh": {"DepotPath": {"$value": "old"}}}}
    }

    result = _finalize_head(
        wk=wk,
        mod_id="my_mod",
        build_dir=tmp_path,
        body_rig="pwa",
        baked_mesh_fs=tmp_path / "mesh.mesh",
        baked_mesh_depot="base\\npv-build\\my_mod\\my_mod_head.mesh",
        restore_materials=False,
    )

    assert result is True
    mock_restore_head.assert_not_called()
    mock_restore_part.assert_not_called()


@patch("npv_build.head_bake._restore_head_materials")
@patch("npv_build.head_bake._restore_part_materials")
def test_finalize_head_restores_materials(mock_restore_part, mock_restore_head, tmp_path):
    wk = MagicMock()
    wk.uncook_json.return_value = {
        "Data": {"RootChunk": {"baseMesh": {"DepotPath": {"$value": "old"}}}}
    }

    result = _finalize_head(
        wk=wk,
        mod_id="my_mod",
        build_dir=tmp_path,
        body_rig="pwa",
        baked_mesh_fs=tmp_path / "mesh.mesh",
        baked_mesh_depot="base\\npv-build\\my_mod\\my_mod_head.mesh",
        restore_materials=True,
    )

    assert result is True
    mock_restore_head.assert_called_once()


@patch("npv_build.wolvenkit.prepare_head")
@patch("npv_build.wolvenkit.find_stock_head_part")
@patch("npv_build.wolvenkit._inject_components")
def test_heb_dropped_with_override_no_heb_mesh(
    mock_inject, mock_find_stock, mock_prepare_head, tmp_path
):
    mock_prepare_head.return_value = True
    mock_find_stock.return_value = "base\\characters\\head\\stock.ent"

    wk = MagicMock()
    wk.config.game_dir = Path("/dummy/game")

    # Mock uncook_many to create the donor files with correct Header json
    def mock_uncook_many(regex, dest):
        p = Path(dest) / "judy.ent.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"Header": {"Name": "old"}, "Data": {"RootChunk": {"appearances": []}}})
        )
        return Path(dest)

    wk.uncook_many = mock_uncook_many

    # Mock deserialize to copy json -> binary
    def mock_deserialize(path):
        for p in list(Path(path).rglob("*.json")):
            cooked = p.with_suffix("")
            cooked.parent.mkdir(parents=True, exist_ok=True)
            cooked.write_text(p.read_text())

    wk.deserialize = mock_deserialize

    # We must also mock uncook_json to return a valid .ent / .app JSON structure
    wk.uncook_json.return_value = {
        "Header": {"Name": "old"},
        "Data": {"RootChunk": {"appearances": []}},
    }

    with patch("npv_build.wolvenkit._extract_part_components") as mock_extract:
        mock_extract.return_value = [
            {
                "name": "h0_000_pwa_c__basehead",
                "mesh": "stock_head.mesh",
                "comp_type": "entSkinnedMeshComponent",
                "appearance": "default",
            },
            {
                "name": "heb_000_pwa__basehead",
                "mesh": "stock_heb.mesh",
                "comp_type": "entSkinnedMeshComponent",
                "appearance": "default",
            },
        ]

        from npv_build.wolvenkit import build_project

        specs = build_project(
            wk=wk,
            mod_id="my_mod",
            out_dir=tmp_path,
            asset_paths={
                "body_rig": "pwa",
                "face_morphs": {},
                "recipe_parts": [
                    {"resource": {"DepotPath": {"$value": "base\\characters\\head\\heb.ent"}}}
                ],
            },
            verbosity=0,
            user_head_glb=Path("/dummy/head.glb"),
            user_head_mesh=None,
            user_heb_mesh=None,
        )

        heb_names = [c["name"] for c in specs if "heb_000_" in c.get("name", "")]
        assert len(heb_names) == 0


@patch("npv_build.wolvenkit.prepare_head")
@patch("npv_build.wolvenkit.find_stock_head_part")
@patch("npv_build.wolvenkit._inject_components")
def test_heb_repointed_with_override_and_heb_mesh(
    mock_inject, mock_find_stock, mock_prepare_head, tmp_path
):
    # Mock prepare_head to write the output heb mesh
    def mock_prep(wk, mod_id, build_dir, body_rig, face_morphs, verbosity, **kwargs):
        if kwargs.get("user_heb_mesh"):
            heb_file = Path(build_dir) / "base" / "npv-build" / mod_id / f"{mod_id}_heb.mesh"
            heb_file.parent.mkdir(parents=True, exist_ok=True)
            heb_file.write_text("dummy")
        return True

    mock_prepare_head.side_effect = mock_prep

    mock_find_stock.return_value = "base\\characters\\head\\stock.ent"

    wk = MagicMock()
    wk.config.game_dir = Path("/dummy/game")

    # Mock uncook_many to create the donor files with correct Header json
    def mock_uncook_many(regex, dest):
        p = Path(dest) / "judy.ent.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"Header": {"Name": "old"}, "Data": {"RootChunk": {"appearances": []}}})
        )
        return Path(dest)

    wk.uncook_many = mock_uncook_many

    # Mock deserialize to copy json -> binary
    def mock_deserialize(path):
        for p in list(Path(path).rglob("*.json")):
            cooked = p.with_suffix("")
            cooked.parent.mkdir(parents=True, exist_ok=True)
            cooked.write_text(p.read_text())

    wk.deserialize = mock_deserialize

    wk.uncook_json.return_value = {
        "Header": {"Name": "old"},
        "Data": {"RootChunk": {"appearances": []}},
    }

    with patch("npv_build.wolvenkit._extract_part_components") as mock_extract:
        mock_extract.return_value = [
            {
                "name": "h0_000_pwa_c__basehead",
                "mesh": "stock_head.mesh",
                "comp_type": "entSkinnedMeshComponent",
                "appearance": "default",
            },
            {
                "name": "heb_000_pwa__basehead",
                "mesh": "stock_heb.mesh",
                "comp_type": "entSkinnedMeshComponent",
                "appearance": "default",
            },
        ]

        from npv_build.wolvenkit import build_project

        specs = build_project(
            wk=wk,
            mod_id="my_mod",
            out_dir=tmp_path,
            asset_paths={
                "body_rig": "pwa",
                "face_morphs": {},
                "recipe_parts": [
                    {"resource": {"DepotPath": {"$value": "base\\characters\\head\\heb.ent"}}}
                ],
            },
            verbosity=0,
            user_head_glb=Path("/dummy/head.glb"),
            user_head_mesh=None,
            user_heb_mesh=Path("/dummy/heb.mesh"),
        )

        heb_components = [c for c in specs if "heb_000_" in c.get("name", "")]
        assert len(heb_components) == 1
        assert heb_components[0]["mesh"] == "base\\npv-build\\my_mod\\my_mod_heb.mesh"


@patch("npv_build.head_bake.shutil.copy2")
def test_dump_head_glb_produces_file(mock_copy, tmp_path):
    from npv_build.head_bake import dump_head_glb

    wk = MagicMock()
    from npv_build.blender_module import HEAD_FACE_MESH

    stock_head_depot = HEAD_FACE_MESH["pwa"]

    def mock_unbundle(regex, archive, dest):
        p = Path(dest) / stock_head_depot.replace("\\", "/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("dummy")

    wk.unbundle = mock_unbundle
    wk.export.return_value = tmp_path / "temp.glb"

    dest_path = tmp_path / "output.glb"
    dump_head_glb(wk, "pwa", dest_path, verbosity=0)

    mock_copy.assert_called_once_with(wk.export.return_value, dest_path)


@patch("npv_build.head_bake.dump_head_glb")
@patch("npv_build.orchestrator.parse_save")
def test_dump_head_glb_exits_without_building(mock_parse_save, mock_dump_head_glb, tmp_path):
    from npv_build.orchestrator import run_orchestrator

    with patch("npv_build.orchestrator.WolvenKit") as mock_wk_class:
        mock_wk = MagicMock()
        mock_wk_class.return_value = mock_wk

        res = run_orchestrator(
            save_path=None,
            npv_name="my_v",
            output_dir=tmp_path,
            game_dir=Path("/dummy/game"),
            template_cache=tmp_path / "cache",
            clear_cache=False,
            verbosity=0,
            dump_head_glb=tmp_path / "dump.glb",
        )

        assert res == str(tmp_path / "dump.glb")
        mock_dump_head_glb.assert_called_once_with(mock_wk, "pwa", tmp_path / "dump.glb", 0)
