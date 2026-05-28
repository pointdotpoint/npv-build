"""Integration test for build_project — requires WolvenKit CLI + game dir."""
import json
import os
import pytest
from pathlib import Path

GAME_DIR = os.environ.get("NPV_GAME_DIR", "")
SKIP_REASON = "Set NPV_GAME_DIR to run integration tests"


@pytest.mark.skipif(not GAME_DIR, reason=SKIP_REASON)
def test_build_project_produces_expected_files(tmp_path):
    from npv_build.wolvenkit import build_project

    asset_paths = {
        "part_entities": [
            r"base\characters\common\player_base_bodies\appearances\entity\t0_000_pwa_base__full.ent",
            r"base\characters\common\player_base_bodies\appearances\entity\a0_000_pwa_base__full.ent",
        ],
        "recipe_parts": [],
        "recipe_overrides": [],
        "face_morphs": {},
        "hair_components": [],
        "body_rig": "pwa",
        "_game_dir": GAME_DIR,
    }
    component_specs = build_project("test_int", tmp_path, asset_paths, verbosity=0)
    app = tmp_path / "source" / "archive" / "base" / "characters" / "appearances" / "test_int.app"
    assert app.exists(), f"Cooked .app not found at {app}"
    ent = tmp_path / "source" / "archive" / "base" / "characters" / "entities" / "test_int.ent"
    assert ent.exists(), f"Cooked .ent not found at {ent}"
    assert isinstance(component_specs, list)
    assert len(component_specs) > 0
    for spec in component_specs:
        assert "comp_type" in spec
        assert "name" in spec
