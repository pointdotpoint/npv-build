"""Integration test for build_project — requires WolvenKit CLI + game dir."""

import os

import pytest

from npv_build.wk_cli import WolvenKitError
from npv_build.wolvenkit import _check_inject_binary_freshness

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
            "partResource": {
                "DepotPath": {
                    "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"
                }
            },
            "componentsOverrides": [
                {
                    "componentName": {"$value": "h0_000_pwa_c__basehead"},
                    "meshAppearance": {"$value": "01_ca_pale_d04"},
                }
            ],
        }
    ]

    parts_overrides = _apply_recipe_overrides(components, recipe_overrides)
    assert components[0]["appearance"] == "01_ca_pale_d04"
    assert len(parts_overrides) == 1
    assert (
        parts_overrides[0]["partResource"]["DepotPath"]["$value"]
        == "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"
    )
    assert len(parts_overrides[0]["componentsOverrides"]) == 1
    assert (
        parts_overrides[0]["componentsOverrides"][0]["componentName"]["$value"]
        == "h0_000_pwa_c__basehead"
    )
    assert (
        parts_overrides[0]["componentsOverrides"][0]["meshAppearance"]["$value"] == "01_ca_pale_d04"
    )

    # 2. Test alias remapping from stock MorphTargetSkinnedMesh7243
    components[0]["appearance"] = "default"
    recipe_overrides_alias = [
        {
            "partResource": {
                "DepotPath": {
                    "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"
                }
            },
            "componentsOverrides": [
                {
                    "componentName": {"$value": "MorphTargetSkinnedMesh7243"},
                    "meshAppearance": {"$value": "01_ca_pale_d04"},
                }
            ],
        }
    ]

    parts_overrides_alias = _apply_recipe_overrides(components, recipe_overrides_alias)
    assert components[0]["appearance"] == "01_ca_pale_d04"
    assert len(parts_overrides_alias) == 1
    assert (
        parts_overrides_alias[0]["partResource"]["DepotPath"]["$value"]
        == "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"
    )
    # Both stock MorphTargetSkinnedMesh7243 AND duplicated h0_000_pwa_c__basehead should be present!
    assert len(parts_overrides_alias[0]["componentsOverrides"]) == 2
    assert (
        parts_overrides_alias[0]["componentsOverrides"][0]["componentName"]["$value"]
        == "MorphTargetSkinnedMesh7243"
    )
    assert (
        parts_overrides_alias[0]["componentsOverrides"][0]["meshAppearance"]["$value"]
        == "01_ca_pale_d04"
    )
    assert (
        parts_overrides_alias[0]["componentsOverrides"][1]["componentName"]["$value"]
        == "h0_000_pwa_c__basehead"
    )
    assert (
        parts_overrides_alias[0]["componentsOverrides"][1]["meshAppearance"]["$value"]
        == "01_ca_pale_d04"
    )


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
            "partResource": {
                "DepotPath": {
                    "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\face_decals\\hx_000_pwa__basehead_makeup_lips_01.ent"
                }
            },
            "componentsOverrides": [
                {
                    "componentName": {"$value": "hx_000_pwa__basehead_makeup_lips_01"},
                    "meshAppearance": {"$value": "yellow_01"},
                },
                {
                    "componentName": {"$value": "hx_000_pwa__basehead_makeup_lips_01"},
                    "meshAppearance": {"$value": "burgundy_19"},
                },
            ],
        }
    ]

    parts_overrides = _apply_recipe_overrides(components, recipe_overrides)

    # inlined component takes the chosen (last) color
    assert components[0]["appearance"] == "burgundy_19"
    # partsOverrides must NOT carry both colors for the same component
    cos = parts_overrides[0]["componentsOverrides"]
    lip_cos = [
        c for c in cos if c["componentName"]["$value"] == "hx_000_pwa__basehead_makeup_lips_01"
    ]
    assert len(lip_cos) == 1, (
        f"expected one lip override, got {len(lip_cos)}: {[c['meshAppearance']['$value'] for c in lip_cos]}"
    )
    assert lip_cos[0]["meshAppearance"]["$value"] == "burgundy_19"


def test_apply_recipe_overrides_propagates_chunk_mask():
    """componentsOverrides carry per-style chunkMask (which studs of an
    earring mesh render, which chunks of the stock eye are iris vs lashes).
    Discarding it renders every chunk -> extra piercings, doubled eyeballs.
    The mask must land on the inlined component alongside the appearance."""
    from npv_build.wolvenkit import _apply_recipe_overrides

    components = [
        {"name": "i1_000_pwa__morphs_earring_01", "appearance": "default"},
        {"name": "a0_000_pwa_base_hq__full", "appearance": "default"},
    ]
    recipe_overrides = [
        {
            "partResource": {
                "DepotPath": {
                    "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\items\\i1_000_pwa_earring__basehead_01.ent"
                }
            },
            "componentsOverrides": [
                {
                    "componentName": {"$value": "i1_000_pwa__morphs_earring_01"},
                    "meshAppearance": {"$value": "silver"},
                    "chunkMask": "18446744073709549572",
                }
            ],
        }
    ]

    _apply_recipe_overrides(components, recipe_overrides)
    assert components[0]["appearance"] == "silver"
    assert components[0]["chunk_mask"] == "18446744073709549572"
    # No override for this component -> no mask key invented.
    assert "chunk_mask" not in components[1]


def test_apply_recipe_overrides_chunk_mask_reaches_baked_head_alias():
    """Head overrides aliased from the stock MorphTargetSkinnedMesh onto the
    baked basehead component must carry the chunkMask too."""
    from npv_build.wolvenkit import _apply_recipe_overrides

    components = [{"name": "h0_000_pwa_c__basehead", "appearance": "default"}]
    recipe_overrides = [
        {
            "partResource": {
                "DepotPath": {
                    "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"
                }
            },
            "componentsOverrides": [
                {
                    "componentName": {"$value": "MorphTargetSkinnedMesh7243"},
                    "meshAppearance": {"$value": "01_ca_pale_d04"},
                    "chunkMask": "18446744073709551613",
                }
            ],
        }
    ]

    _apply_recipe_overrides(components, recipe_overrides)
    assert components[0]["appearance"] == "01_ca_pale_d04"
    assert components[0]["chunk_mask"] == "18446744073709551613"


def _stock_eye_overrides():
    return [
        {
            "partResource": {
                "DepotPath": {
                    "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\face_decals\\he_000_pwa__basehead.ent"
                }
            },
            "componentsOverrides": [
                {
                    "componentName": {"$value": "MorphTargetSkinnedMesh3637"},
                    "meshAppearance": {"$value": "double_eye_black"},
                    "chunkMask": "18446744073709551614",
                },
                {
                    "componentName": {"$value": "MorphTargetSkinnedMesh3637"},
                    "meshAppearance": {"$value": "eyelashes__black_salt_n_pepper"},
                    "chunkMask": "18446744073709551609",
                },
            ],
        }
    ]


def test_stock_eye_lashes_only_when_modded_eyes():
    """With modded eyes supplying the iris, the stock eye renders ONLY eyelashes:
    keep the eyelash override, drop the iris (double_eye) override."""
    from npv_build.wolvenkit import _apply_recipe_overrides

    components = [{"name": "MorphTargetSkinnedMesh3637", "appearance": "default"}]
    parts = _apply_recipe_overrides(components, _stock_eye_overrides(), modded_eyes=True)

    eye_cos = [
        c
        for c in parts[0]["componentsOverrides"]
        if c["componentName"]["$value"] == "MorphTargetSkinnedMesh3637"
    ]
    assert len(eye_cos) == 1, [c["meshAppearance"]["$value"] for c in eye_cos]
    assert eye_cos[0]["meshAppearance"]["$value"] == "eyelashes__black_salt_n_pepper"
    assert components[0]["appearance"] == "eyelashes__black_salt_n_pepper"
    # The eyelash mask hides the iris chunks; without it the stock eye renders
    # a second eyeball under the modded iris.
    assert components[0]["chunk_mask"] == "18446744073709551609"


def test_stock_eye_iris_when_no_modded_eyes():
    """Without modded eyes the stock eye renders the iris; the eyelash override is
    skipped so it doesn't clobber the iris color on the shared eye component."""
    from npv_build.wolvenkit import _apply_recipe_overrides

    components = [{"name": "MorphTargetSkinnedMesh3637", "appearance": "default"}]
    parts = _apply_recipe_overrides(components, _stock_eye_overrides(), modded_eyes=False)

    eye_cos = [
        c
        for c in parts[0]["componentsOverrides"]
        if c["componentName"]["$value"] == "MorphTargetSkinnedMesh3637"
    ]
    assert len(eye_cos) == 1, [c["meshAppearance"]["$value"] for c in eye_cos]
    assert eye_cos[0]["meshAppearance"]["$value"] == "double_eye_black"
    assert components[0]["chunk_mask"] == "18446744073709551614"


def _sedth_glow_app_json():
    """Shape of a Sedth CCXL eye .app: morph components with chunkMask."""
    return {
        "Data": {
            "RootChunk": {
                "appearances": [
                    {
                        "Data": {
                            "name": {"$value": "w_cyber_63"},
                            "components": [
                                {
                                    "$type": "entMorphTargetSkinnedMeshComponent",
                                    "name": {"$value": "hx_000_pa__face_1_morphs"},
                                    "morphResource": {
                                        "DepotPath": {
                                            "$value": "sedth\\ccxl\\mesh\\ccxl_eyes_r_pwa_glow_eyes.morphtarget"
                                        }
                                    },
                                    "meshAppearance": {"$value": "eg_63"},
                                    "chunkMask": "9223372036854775803",
                                }
                            ],
                        }
                    }
                ]
            }
        }
    }


def test_ccxl_eye_components_from_app_carries_chunk_mask():
    """The mod's component chunkMask hides its built-in eyeball chunk; dropping
    it renders a second eyeball under the glow overlay."""
    from npv_build.wolvenkit import _ccxl_eye_components_from_app

    mt_cache = {
        "sedth\\ccxl\\mesh\\ccxl_eyes_r_pwa_glow_eyes.morphtarget": "sedth\\ccxl\\mesh\\ccxl_eyes_r_pwa_glow_eyes.mesh"
    }
    comps = _ccxl_eye_components_from_app(
        _sedth_glow_app_json(), "w_cyber_63", "sedth_eyes_r_g", mt_cache, "modded eyes (sedth)"
    )
    assert len(comps) == 1
    assert comps[0]["mesh"] == "sedth\\ccxl\\mesh\\ccxl_eyes_r_pwa_glow_eyes.mesh"
    assert comps[0]["appearance"] == "eg_63"
    assert comps[0]["chunk_mask"] == "9223372036854775803"


def test_ccxl_eye_components_stay_morph_components():
    """The mod defines its eye overlays as entMorphTargetSkinnedMeshComponent —
    the morphtarget carries the blink correctives. Demoting to a plain skinned
    mesh leaves the overlay in open-eye shape: eyeball visible through closed
    eyelids when the NPV blinks."""
    from npv_build.wolvenkit import _ccxl_eye_components_from_app

    mt_cache = {
        "sedth\\ccxl\\mesh\\ccxl_eyes_r_pwa_glow_eyes.morphtarget": "sedth\\ccxl\\mesh\\ccxl_eyes_r_pwa_glow_eyes.mesh"
    }
    comps = _ccxl_eye_components_from_app(
        _sedth_glow_app_json(), "w_cyber_63", "sedth_eyes_r_g", mt_cache, "modded eyes (sedth)"
    )
    assert comps[0]["comp_type"] == "entMorphTargetSkinnedMeshComponent"
    assert comps[0]["morph_resource"] == "sedth\\ccxl\\mesh\\ccxl_eyes_r_pwa_glow_eyes.morphtarget"


def test_ccxl_eye_components_from_app_missing_appearance_returns_empty():
    """w_cyber_00 ('off') doesn't exist in the mod .app -> no components."""
    from npv_build.wolvenkit import _ccxl_eye_components_from_app

    comps = _ccxl_eye_components_from_app(_sedth_glow_app_json(), "w_cyber_00", "x", {}, "src")
    assert comps == []


def _he_recipe_overrides():
    return [
        {
            "partResource": {
                "DepotPath": {
                    "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\he_000_pwa__basehead.ent"
                }
            },
            "componentsOverrides": [
                {
                    "componentName": {"$value": "MorphTargetSkinnedMesh3637"},
                    "meshAppearance": {"$value": "gradient_blue"},
                    "chunkMask": "18446744073709551614",
                }
            ],
        },
        {
            "partResource": {
                "DepotPath": {
                    "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\he_000_pwa__basehead.ent"
                }
            },
            "componentsOverrides": [
                {
                    "componentName": {"$value": "MorphTargetSkinnedMesh3637"},
                    "meshAppearance": {"$value": "eyelashes__black_carbon"},
                    "chunkMask": "18446744073709551609",
                }
            ],
        },
    ]


def test_stock_eye_recipe_overrides_finds_iris_and_lashes():
    from npv_build.wolvenkit import _stock_eye_recipe_overrides

    ov = _stock_eye_recipe_overrides(_he_recipe_overrides())
    assert ov["iris_appearance"] == "gradient_blue"
    assert ov["iris_chunk_mask"] == "18446744073709551614"
    assert ov["eyelash_appearance"] == "eyelashes__black_carbon"
    assert ov["eyelash_chunk_mask"] == "18446744073709551609"


def test_split_stock_eye_for_glow_produces_iris_and_lashes_components():
    """Glow-only modded eyes (iris NOT replaced, e.g. Sedth base = w_cyber_00
    'off' + glow overlay): the stock eye must render BOTH iris and lashes, as
    two components with the recipe's per-role masks — like the player entity."""
    from npv_build.wolvenkit import _split_stock_eye_for_glow, _stock_eye_recipe_overrides

    comps = [
        {
            "comp_type": "entSkinnedMeshComponent",
            "name": "MorphTargetSkinnedMesh3637",
            "mesh": "base\\x\\he_000_pwa_c__basehead.mesh",
            "appearance": "default",
        }
    ]
    eye_ov = _stock_eye_recipe_overrides(_he_recipe_overrides())
    out = _split_stock_eye_for_glow(comps, eye_ov)

    assert len(out) == 2
    iris = next(c for c in out if c["name"].endswith("_iris"))
    lashes = next(c for c in out if c["name"].endswith("_lashes"))
    assert iris["appearance"] == "gradient_blue"
    assert iris["chunk_mask"] == "18446744073709551614"
    assert lashes["appearance"] == "eyelashes__black_carbon"
    assert lashes["chunk_mask"] == "18446744073709551609"
    assert iris["mesh"] == lashes["mesh"] == "base\\x\\he_000_pwa_c__basehead.mesh"


def test_split_stock_eye_promotes_morph_components():
    """Stock eye comps that came from a morphtarget component must go back to
    entMorphTargetSkinnedMeshComponent so blink correctives animate them."""
    from npv_build.wolvenkit import _split_stock_eye_for_glow, _stock_eye_recipe_overrides

    comps = [
        {
            "comp_type": "entSkinnedMeshComponent",
            "name": "MorphTargetSkinnedMesh3637",
            "mesh": "base\\x\\he_000_pwa_c__basehead.mesh",
            "appearance": "default",
            "morph_resource": "base\\characters\\head\\player_base_heads\\player_female_average\\he_000_pwa__morphs.morphtarget",
        }
    ]
    out = _split_stock_eye_for_glow(comps, _stock_eye_recipe_overrides(_he_recipe_overrides()))
    for c in out:
        assert c["comp_type"] == "entMorphTargetSkinnedMeshComponent"
        assert c["morph_resource"].endswith("he_000_pwa__morphs.morphtarget")


def test_extract_part_components_keeps_morph_resource():
    """Morph components are demoted to skinned meshes (baked-head design), but
    the original morphtarget path must survive so eye components can be
    promoted back for blink support."""
    from npv_build.wolvenkit import _extract_part_components

    class FakeWk:
        def uncook_json(self, basename):
            return {
                "Data": {
                    "RootChunk": {
                        "components": [
                            {
                                "$type": "entMorphTargetSkinnedMeshComponent",
                                "name": {"$value": "MorphTargetSkinnedMesh3637"},
                                "mesh": {
                                    "DepotPath": {"$value": "base\\x\\he_000_pwa_c__basehead.mesh"}
                                },
                                "morphResource": {
                                    "DepotPath": {
                                        "$value": "base\\x\\he_000_pwa__morphs.morphtarget"
                                    }
                                },
                                "meshAppearance": {"$value": "default"},
                            },
                        ]
                    }
                }
            }

    comps = _extract_part_components(FakeWk(), "base\\x\\he_000_pwa__basehead.ent", 0)
    assert comps[0]["comp_type"] == "entSkinnedMeshComponent"
    assert comps[0]["morph_resource"] == "base\\x\\he_000_pwa__morphs.morphtarget"


def test_apply_body_tattoo_appearance():
    """The extracted tx_ tattoo overlay carries meshAppearance 'default'; the
    save's raw selection supplies the skin-tone-keyed appearance.

    The save stores that raw with a body-slot prefix ("w__01_ca_pale"), but the
    tattoo mesh's own appearances are unprefixed — verified by serializing
    tx_000_pwa_base__full_tattoo_02.mesh, which offers exactly:
    default, 01_ca_pale, 02_ca_limestone, 03_ca_senna, 04_ca_almond,
    05_bl_espresso, 06_bl_dark (+ _00_/_01_/_02_ sub-variants).
    Stamping the prefixed name names an appearance that does not exist, so the
    game falls back to no material and the tattoo is invisible.
    """
    from npv_build.wolvenkit import _apply_body_tattoo

    specs = [
        {"name": "tx_000_pwa_base__full_tattoo_02", "appearance": "default"},
        {"name": "t0_000_pwa_base__full", "appearance": "01_ca_pale"},
    ]
    _apply_body_tattoo(specs, {"shape": "02", "appearance": "w__01_ca_pale"})
    assert specs[0]["appearance"] == "01_ca_pale"
    assert specs[1]["appearance"] == "01_ca_pale"


def test_apply_body_tattoo_strips_only_the_body_slot_prefix():
    """Sub-variant tone names survive; an already-unprefixed value is untouched."""
    from npv_build.wolvenkit import _apply_body_tattoo

    specs = [{"name": "tx_000_pwa_base__full_tattoo_02", "appearance": "default"}]
    _apply_body_tattoo(specs, {"shape": "02", "appearance": "w__03_ca_senna_01_honey"})
    assert specs[0]["appearance"] == "03_ca_senna_01_honey"

    specs = [{"name": "tx_000_pwa_base__full_tattoo_02", "appearance": "default"}]
    _apply_body_tattoo(specs, {"shape": "02", "appearance": "03_ca_senna"})
    assert specs[0]["appearance"] == "03_ca_senna"

    # No tattoo -> no-op
    specs2 = [{"name": "tx_000_pwa_base__full_tattoo_02", "appearance": "default"}]
    _apply_body_tattoo(specs2, None)
    assert specs2[0]["appearance"] == "default"


def test_apply_nail_color_targets_both_nail_components_only():
    from npv_build.wolvenkit import _apply_nail_color

    specs = [
        {"name": "a0_000_pwa_base__nails_l", "appearance": "03_ca_senna"},
        {"name": "a0_000_pwa_base__nails_r", "appearance": "03_ca_senna"},
        {"name": "a0_000_pwa_base_hq__full", "appearance": "03_ca_senna"},
    ]

    _apply_nail_color(specs, "01_all_red__multilayer")

    assert specs[0]["appearance"] == "01_all_red__multilayer"
    assert specs[1]["appearance"] == "01_all_red__multilayer"
    assert specs[2]["appearance"] == "03_ca_senna"


def test_bake_lips_overlays_repoints_mesh(monkeypatch, tmp_path):
    """The makeup-lips overlay is a stock unmorphed mesh: over the morph-baked
    head it renders a second pair of lips. Bake it with the same face morphs
    (same design as the heb_ layer) and repoint the component."""
    import npv_build.blender_module as blender_module
    import npv_build.head_bake as head_bake
    from npv_build.wolvenkit import _bake_lips_overlays

    baked = {}

    def fake_bake(game_dir, rig, morphs, out_fs, verbosity, wk=None, **kw):
        baked["mt_depot"] = kw.get("mt_depot")
        baked["mesh_depot"] = kw.get("mesh_depot")
        out_fs.parent.mkdir(parents=True, exist_ok=True)
        out_fs.write_bytes(b"MESH")
        return True

    monkeypatch.setattr(blender_module, "bake_face_mesh", fake_bake)
    monkeypatch.setattr(head_bake, "_restore_part_materials", lambda *a, **k: None)

    specs = [
        {
            "comp_type": "entSkinnedMeshComponent",
            "name": "hx_000_pwa__basehead_makeup_lips_01",
            "mesh": "base\\x\\hx_000_pwa_c__basehead_makeup_lips_01.mesh",
            "appearance": "burgundy_06",
            "morph_resource": "base\\x\\hx_000_pwa__morphs_makeup_lips_01.morphtarget",
        },
        {
            "comp_type": "entSkinnedMeshComponent",
            "name": "hx_000_pwa__morphs_makeup_freckles_01",
            "mesh": "base\\x\\freckles.mesh",
            "appearance": "frecles_brown_10",
        },
    ]

    _bake_lips_overlays(
        wk=object(),
        game_dir=tmp_path,
        source_dir=tmp_path,
        mod_id="npv_test",
        body_rig="pwa",
        face_morphs={"mouth": "h013"},
        component_specs=specs,
        verbosity=0,
    )

    assert specs[0]["mesh"] == "base\\npv-build\\npv_test\\npv_test_lips.mesh"
    assert baked["mt_depot"] == "base\\x\\hx_000_pwa__morphs_makeup_lips_01.morphtarget"
    assert baked["mesh_depot"] == "base\\x\\hx_000_pwa_c__basehead_makeup_lips_01.mesh"
    # untouched: no morph_resource -> not a bake candidate
    assert specs[1]["mesh"] == "base\\x\\freckles.mesh"


def test_extract_part_components_carries_chunk_mask():
    """Components extracted from a part .ent keep their own chunkMask."""
    from npv_build.wolvenkit import _extract_part_components

    class FakeWk:
        def uncook_json(self, basename):
            return {
                "Data": {
                    "RootChunk": {
                        "components": [
                            {
                                "$type": "entSkinnedMeshComponent",
                                "name": {"$value": "i1_000_pwa__morphs_earring_01"},
                                "mesh": {"DepotPath": {"$value": "base\\x\\e1.mesh"}},
                                "meshAppearance": {"$value": "silver"},
                                "chunkMask": "18446744073709549572",
                            },
                            {
                                "$type": "entSkinnedMeshComponent",
                                "name": {"$value": "no_mask_comp"},
                                "mesh": {"DepotPath": {"$value": "base\\x\\e2.mesh"}},
                            },
                        ]
                    }
                }
            }

    comps = _extract_part_components(FakeWk(), "base\\x\\part.ent", 0)
    assert comps[0]["chunk_mask"] == "18446744073709549572"
    assert "chunk_mask" not in comps[1]


def test_filter_genital_components_removes_detachable_genitals_for_none():
    """Female ``genitals_none`` uses the anatomy already present on the base
    body, so neither detachable penis mesh may survive assembly."""
    from npv_build.wolvenkit import _filter_genital_components

    specs = [
        {
            "name": "t0_000_pwa_base__full",
            "mesh": r"base\characters\common\player_base_bodies\player_female_average"
            r"\t0_000_pwa_base__full.mesh",
        },
        {
            "name": "i0_000_pwa_base__penis",
            "mesh": r"base\characters\common\player_base_bodies\player_female_average"
            r"\genitals\i0_000_pwa_base__penis.mesh",
        },
        {
            "name": "i0_000_pwa_base__penis_circumcised",
            "mesh": r"base\characters\common\player_base_bodies\player_female_average"
            r"\genitals\i0_000_pwa_base__penis_circumcised.mesh",
        },
    ]

    filtered = _filter_genital_components(specs, "i0_000_pwa_base__genitals_none__03_ca_senna")

    assert [component["name"] for component in filtered] == ["t0_000_pwa_base__full"]


def test_asset_paths_carries_equipped_clothing():
    """resolve_assets surfaces cc_settings['clothing'] as asset_paths['equipped_clothing']
    so build_project can pass it to resolve_clothing."""
    from npv_build.mapping import resolve_assets

    cc = {
        "patch": "2.13",
        "body_rig": "pwa",
        "selections": [],
        "clothing": [
            {
                "name": "t1_x",
                "mesh": "base\\g\\t1_x.mesh",
                "appearance": "default",
                "slot": "inner_torso",
            },
        ],
    }
    ap = resolve_assets(cc, game_dir=None)
    assert ap["equipped_clothing"] == cc["clothing"]


def _fake_inject_tree(tmp_path, source_mtime, binary_mtime):
    project = tmp_path / "npv-inject"
    (project / "bin" / "Release" / "net8.0").mkdir(parents=True)
    source = project / "Program.cs"
    source.write_text("// source")
    os.utime(source, (source_mtime, source_mtime))
    binary = project / "bin" / "Release" / "net8.0" / "npv-inject"
    binary.write_bytes(b"\x7fELF")
    os.utime(binary, (binary_mtime, binary_mtime))
    return binary, project


def test_stale_inject_binary_hard_fails(tmp_path):
    """Source newer than the built binary must stop the build with a
    rebuild command, not fail later with a confusing component error."""
    binary, project = _fake_inject_tree(tmp_path, source_mtime=2000.0, binary_mtime=1000.0)
    with pytest.raises(WolvenKitError, match="dotnet build tools/npv-inject"):
        _check_inject_binary_freshness(binary, project)


def test_fresh_inject_binary_passes(tmp_path):
    binary, project = _fake_inject_tree(tmp_path, source_mtime=1000.0, binary_mtime=2000.0)
    _check_inject_binary_freshness(binary, project)  # must not raise


def test_freshness_check_skips_without_sources(tmp_path):
    """No .cs/.csproj sources next to the binary (e.g. stripped tree):
    nothing to compare, never block the build."""
    binary, project = _fake_inject_tree(tmp_path, source_mtime=2000.0, binary_mtime=1000.0)
    (project / "Program.cs").unlink()
    _check_inject_binary_freshness(binary, project)  # must not raise


def test_freshness_ignores_bin_and_obj_artifacts(tmp_path):
    """Build artifacts under bin/ and obj/ carry .cs files (AssemblyInfo);
    they are outputs, not sources, and must not trigger staleness."""
    binary, project = _fake_inject_tree(tmp_path, source_mtime=1000.0, binary_mtime=2000.0)
    obj_cs = project / "obj" / "Release" / "AssemblyInfo.cs"
    obj_cs.parent.mkdir(parents=True)
    obj_cs.write_text("// generated")
    os.utime(obj_cs, (3000.0, 3000.0))
    _check_inject_binary_freshness(binary, project)  # must not raise


def test_skin_tone_pass_skips_meshes_that_only_define_default():
    """The body skin-tone pass stamps the tone on default-appearance body
    parts, but the seamfix meshes define only 'default' — verified by
    serializing t0_000_pwa_base__full_seamfix.mesh, whose appearance list is
    exactly ['default']. Naming a missing appearance makes the game fall back
    to no material, the same defect that hid body tattoos."""
    from npv_build.wolvenkit import _apply_body_skin_tone

    specs = [
        {"name": "t0_000_pwa_base__full", "appearance": "default"},
        {"name": "t0_000_pwa_base__full_seamfix", "appearance": "default"},
        {"name": "a0_001_pwa_base_hq__full", "appearance": "default"},
        {"name": "femv_seamfix", "appearance": "default"},
    ]
    _apply_body_skin_tone(specs, "01_ca_pale")
    by_name = {s["name"]: s["appearance"] for s in specs}
    assert by_name["t0_000_pwa_base__full"] == "01_ca_pale"
    assert by_name["a0_001_pwa_base_hq__full"] == "01_ca_pale"
    # Seamfix meshes carry only 'default' — leave them alone.
    assert by_name["t0_000_pwa_base__full_seamfix"] == "default"
    assert by_name["femv_seamfix"] == "default"
