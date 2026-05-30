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
    assert len(parts_overrides) == 1
    assert parts_overrides[0]["partResource"]["DepotPath"]["$value"] == "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"
    assert len(parts_overrides[0]["componentsOverrides"]) == 1
    assert parts_overrides[0]["componentsOverrides"][0]["componentName"]["$value"] == "h0_000_pwa_c__basehead"
    assert parts_overrides[0]["componentsOverrides"][0]["meshAppearance"]["$value"] == "01_ca_pale_d04"

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
    assert len(parts_overrides_alias) == 1
    assert parts_overrides_alias[0]["partResource"]["DepotPath"]["$value"] == "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"
    # Both stock MorphTargetSkinnedMesh7243 AND duplicated h0_000_pwa_c__basehead should be present!
    assert len(parts_overrides_alias[0]["componentsOverrides"]) == 2
    assert parts_overrides_alias[0]["componentsOverrides"][0]["componentName"]["$value"] == "MorphTargetSkinnedMesh7243"
    assert parts_overrides_alias[0]["componentsOverrides"][0]["meshAppearance"]["$value"] == "01_ca_pale_d04"
    assert parts_overrides_alias[0]["componentsOverrides"][1]["componentName"]["$value"] == "h0_000_pwa_c__basehead"
    assert parts_overrides_alias[0]["componentsOverrides"][1]["meshAppearance"]["$value"] == "01_ca_pale_d04"


def test_apply_recipe_overrides_dedupes_duplicate_component_appearances():
    """Two overrides for the SAME component (CC base layer + chosen color) must
    collapse to the chosen (last) one. Emitting both produces overlapping decal
    layers in-game: doubled lips / doubled eye makeup."""
    from npv_build.wolvenkit import _apply_recipe_overrides

    components = [
        {"name": "hx_000_pwa__basehead_makeup_lips_01", "appearance": "default"},
    ]
    recipe_overrides = [
        {
            "partResource": {"DepotPath": {"$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\face_decals\\hx_000_pwa__basehead_makeup_lips_01.ent"}},
            "componentsOverrides": [
                {"componentName": {"$value": "hx_000_pwa__basehead_makeup_lips_01"}, "meshAppearance": {"$value": "yellow_01"}},
                {"componentName": {"$value": "hx_000_pwa__basehead_makeup_lips_01"}, "meshAppearance": {"$value": "burgundy_19"}},
            ],
        }
    ]

    parts_overrides = _apply_recipe_overrides(components, recipe_overrides)

    # inlined component takes the chosen (last) color
    assert components[0]["appearance"] == "burgundy_19"
    # partsOverrides must NOT carry both colors for the same component
    cos = parts_overrides[0]["componentsOverrides"]
    lip_cos = [c for c in cos if c["componentName"]["$value"] == "hx_000_pwa__basehead_makeup_lips_01"]
    assert len(lip_cos) == 1, f"expected one lip override, got {len(lip_cos)}: {[c['meshAppearance']['$value'] for c in lip_cos]}"
    assert lip_cos[0]["meshAppearance"]["$value"] == "burgundy_19"


def _stock_eye_overrides():
    return [
        {
            "partResource": {"DepotPath": {"$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\face_decals\\he_000_pwa__basehead.ent"}},
            "componentsOverrides": [
                {"componentName": {"$value": "MorphTargetSkinnedMesh3637"}, "meshAppearance": {"$value": "double_eye_black"}},
                {"componentName": {"$value": "MorphTargetSkinnedMesh3637"}, "meshAppearance": {"$value": "eyelashes__black_salt_n_pepper"}},
            ],
        }
    ]


def test_stock_eye_lashes_only_when_modded_eyes():
    """With modded eyes supplying the iris, the stock eye renders ONLY eyelashes:
    keep the eyelash override, drop the iris (double_eye) override."""
    from npv_build.wolvenkit import _apply_recipe_overrides

    components = [{"name": "MorphTargetSkinnedMesh3637", "appearance": "default"}]
    parts = _apply_recipe_overrides(components, _stock_eye_overrides(), modded_eyes=True)

    eye_cos = [c for c in parts[0]["componentsOverrides"]
               if c["componentName"]["$value"] == "MorphTargetSkinnedMesh3637"]
    assert len(eye_cos) == 1, [c["meshAppearance"]["$value"] for c in eye_cos]
    assert eye_cos[0]["meshAppearance"]["$value"] == "eyelashes__black_salt_n_pepper"
    assert components[0]["appearance"] == "eyelashes__black_salt_n_pepper"


def test_stock_eye_iris_when_no_modded_eyes():
    """Without modded eyes the stock eye renders the iris; the eyelash override is
    skipped so it doesn't clobber the iris color on the shared eye component."""
    from npv_build.wolvenkit import _apply_recipe_overrides

    components = [{"name": "MorphTargetSkinnedMesh3637", "appearance": "default"}]
    parts = _apply_recipe_overrides(components, _stock_eye_overrides(), modded_eyes=False)

    eye_cos = [c for c in parts[0]["componentsOverrides"]
               if c["componentName"]["$value"] == "MorphTargetSkinnedMesh3637"]
    assert len(eye_cos) == 1, [c["meshAppearance"]["$value"] for c in eye_cos]
    assert eye_cos[0]["meshAppearance"]["$value"] == "double_eye_black"


