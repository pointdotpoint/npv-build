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


def test_apply_recipe_overrides():
    from npv_build.wolvenkit import _apply_recipe_overrides

    components = [
        {"name": "h0_000_pwa_c__basehead", "appearance": "default"},
        {"name": "a0_000_pwa_base_hq__full", "appearance": "default"},
    ]
    
    # 1. Test direct component override
    recipe_overrides = [
        {
            "partResource": {"DepotPath": {"$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"}},
            "componentsOverrides": [
                {
                    "componentName": {"$value": "h0_000_pwa_c__basehead"},
                    "meshAppearance": {"$value": "01_ca_pale_d04"},
                }
            ]
        }
    ]

    parts_overrides = _apply_recipe_overrides(components, recipe_overrides)
    assert components[0]["appearance"] == "01_ca_pale_d04"
    assert not parts_overrides

    # 2. Test alias remapping from stock MorphTargetSkinnedMesh7243
    components[0]["appearance"] = "default"
    recipe_overrides_alias = [
        {
            "partResource": {"DepotPath": {"$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"}},
            "componentsOverrides": [
                {
                    "componentName": {"$value": "MorphTargetSkinnedMesh7243"},
                    "meshAppearance": {"$value": "01_ca_pale_d04"},
                }
            ]
        }
    ]

    parts_overrides_alias = _apply_recipe_overrides(components, recipe_overrides_alias)
    assert components[0]["appearance"] == "01_ca_pale_d04"
    assert not parts_overrides_alias

