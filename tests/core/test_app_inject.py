"""Unit tests for build_component_json (pure, per-component JSON builder)
and the donor-infrastructure handle-resolution helpers.

These test the piece of npv_build/core/app_inject.py most analogous to the
C# ComponentInjector.CreateComponent — in isolation, without WolvenKit.
The full inject_components() serialize->append->deserialize orchestration
is validated by the Task 7 desk diff (needs real WolvenKit), not a unit
test.
"""

from __future__ import annotations

import pytest

from npv_build.core.app_inject import (
    InjectError,
    _copy_infrastructure,
    _inline_handle_refs,
    build_component_json,
)


def test_build_component_mesh_type():
    spec = {
        "type": "entSkinnedMeshComponent",
        "name": "head",
        "mesh": r"base\x\head.mesh",
        "meshAppearance": "default",
        "bindTo": "root",
    }
    comp = build_component_json(spec)
    assert comp["Data"]["$type"] == "entSkinnedMeshComponent"
    assert comp["Data"]["name"]["$value"] == "head"
    assert comp["Data"]["parentTransform"]["Data"]["bindName"]["$value"] == "root"


def test_build_component_unknown_type_raises():
    with pytest.raises(InjectError):
        build_component_json(
            {
                "type": "entNotAComponent",
                "name": "x",
                "mesh": "",
                "meshAppearance": "",
                "bindTo": "root",
            }
        )


def test_build_component_missing_name_raises():
    with pytest.raises(InjectError):
        build_component_json(
            {
                "type": "entSkinnedMeshComponent",
                "mesh": "x.mesh",
                "meshAppearance": "default",
                "bindTo": "root",
            }
        )


def test_build_component_mesh_depot_path_set():
    spec = {
        "type": "entSkinnedMeshComponent",
        "name": "torso",
        "mesh": r"base\characters\common\t0_000.mesh",
        "meshAppearance": "01_ca_pale",
        "bindTo": "root",
    }
    comp = build_component_json(spec)
    data = comp["Data"]
    assert data["mesh"]["DepotPath"]["$value"] == r"base\characters\common\t0_000.mesh"
    assert data["meshAppearance"]["$value"] == "01_ca_pale"
    assert data["skinning"]["Data"]["bindName"]["$value"] == "root"


def test_build_component_garment_type_has_mesh_field():
    spec = {
        "type": "entGarmentSkinnedMeshComponent",
        "name": "garment_torso",
        "mesh": r"base\characters\garment\tank.mesh",
        "meshAppearance": "default",
        "bindTo": "root",
    }
    comp = build_component_json(spec)
    assert comp["Data"]["$type"] == "entGarmentSkinnedMeshComponent"
    assert comp["Data"]["mesh"]["DepotPath"]["$value"] == r"base\characters\garment\tank.mesh"


def test_build_component_morph_target_has_no_mesh_field():
    """entMorphTargetSkinnedMeshComponent has no `mesh` property on the
    RED4 type (WolvenKit/WolvenKit.RED4/Types/Classes/
    entMorphTargetSkinnedMeshComponent.cs) — only `morphResource`. A
    hand-authored `mesh` field on this type breaks WolvenKit's JSON
    deserializer (confirmed empirically during Task 7 attempt 2)."""
    spec = {
        "type": "entMorphTargetSkinnedMeshComponent",
        "name": "MorphTargetSkinnedMesh1",
        "morphResource": r"base\characters\head\my_v_morphs.morphtarget",
        "meshAppearance": "default",
        "bindTo": "face_rig",
    }
    comp = build_component_json(spec)
    data = comp["Data"]
    assert "mesh" not in data
    assert (
        data["morphResource"]["DepotPath"]["$value"]
        == r"base\characters\head\my_v_morphs.morphtarget"
    )
    assert data["parentTransform"]["Data"]["bindName"]["$value"] == "face_rig"
    assert data["skinning"]["Data"]["bindName"]["$value"] == "face_rig"


def test_build_component_animated_type():
    spec = {
        "type": "entAnimatedComponent",
        "name": "hair_dangle",
        "graph": r"base\anim\hair.animgraph",
        "rig": r"base\anim\hair.rig",
        "bindTo": "root",
    }
    comp = build_component_json(spec)
    data = comp["Data"]
    assert data["$type"] == "entAnimatedComponent"
    assert data["graph"]["DepotPath"]["$value"] == r"base\anim\hair.animgraph"
    assert data["rig"]["DepotPath"]["$value"] == r"base\anim\hair.rig"
    assert data["controlBinding"]["Data"]["bindName"]["$value"] == "root"


def test_build_component_defaults_bind_to_root():
    spec = {
        "type": "entSkinnedMeshComponent",
        "name": "x",
        "mesh": "x.mesh",
        "meshAppearance": "default",
    }
    comp = build_component_json(spec)
    assert comp["Data"]["parentTransform"]["Data"]["bindName"]["$value"] == "root"


# --- _inline_handle_refs / _copy_infrastructure --------------------------
#
# Regression coverage for a real bug caught during the Task 7 desk-diff gate:
# donor-copied infrastructure components (entAnimatedComponent, etc.) carry
# bare `{"HandleRefId": N}` fields (parentTransform, controlBinding) whose
# targets live ONLY in the donor's `compiledData.Data.Chunks[k]` — never in
# `components` itself. Copying the bare component into a fresh appearance
# without resolving those refs makes WolvenKit's deserializer fail outright
# on the dangling handle (confirmed empirically: JsonException on the
# unresolved HandleRefId). _inline_handle_refs fixes this by pulling the
# inline Data from the index-matched Chunks entry.


def test_inline_handle_refs_resolves_bare_handle_ref():
    comp = {
        "$type": "entAnimationSetupExtensionComponent",
        "name": {"$type": "CName", "$storage": "string", "$value": "man_face_base_animations"},
        "controlBinding": {"HandleRefId": "1"},
    }
    resolved_twin = {
        "$type": "entAnimationSetupExtensionComponent",
        "controlBinding": {
            "HandleId": "1",
            "Data": {
                "$type": "entAnimationControlBinding",
                "bindName": {"$type": "CName", "$storage": "string", "$value": "root"},
            },
        },
    }
    out = _inline_handle_refs(comp, resolved_twin)
    assert out["controlBinding"] == {
        "Data": {
            "$type": "entAnimationControlBinding",
            "bindName": {"$type": "CName", "$storage": "string", "$value": "root"},
        }
    }


def test_inline_handle_refs_leaves_already_inline_fields_untouched():
    comp = {
        "$type": "entSkinnedMeshComponent",
        "parentTransform": {"Data": {"$type": "entHardTransformBinding"}},
    }
    out = _inline_handle_refs(comp, {})
    assert out["parentTransform"] == {"Data": {"$type": "entHardTransformBinding"}}


def test_copy_infrastructure_resolves_donor_handle_refs():
    """End-to-end (minus WolvenKit) check that _copy_infrastructure produces
    self-contained components — no bare HandleRefId left pointing at a
    donor-only compiledData chunk."""
    source_appearance = {
        "components": [
            {
                "$type": "entAnimationSetupExtensionComponent",
                "name": {
                    "$type": "CName",
                    "$storage": "string",
                    "$value": "man_face_base_animations",
                },
                "controlBinding": {"HandleRefId": "1"},
            },
        ],
        "compiledData": {
            "Data": {
                "Chunks": [
                    {
                        "$type": "entAnimationSetupExtensionComponent",
                        "controlBinding": {
                            "HandleId": "1",
                            "Data": {
                                "$type": "entAnimationControlBinding",
                                "bindName": {
                                    "$type": "CName",
                                    "$storage": "string",
                                    "$value": "root",
                                },
                            },
                        },
                    }
                ]
            }
        },
    }
    target_appearance: dict = {"components": []}

    _copy_infrastructure(
        source_appearance,
        target_appearance,
        face_rig=None,
        facial_setup=None,
        face_graph=None,
        skip_donor_hair_dangle=False,
    )

    copied = target_appearance["components"][0]
    assert copied["controlBinding"] == {
        "Data": {
            "$type": "entAnimationControlBinding",
            "bindName": {"$type": "CName", "$storage": "string", "$value": "root"},
        }
    }


def test_copy_infrastructure_skips_hair_dangle_when_requested():
    source_appearance = {
        "components": [
            {
                "$type": "entAnimatedComponent",
                "name": {"$type": "CName", "$storage": "string", "$value": "hair_dangle"},
            },
            {
                "$type": "entAnimatedComponent",
                "name": {"$type": "CName", "$storage": "string", "$value": "breasts"},
            },
        ],
        "compiledData": {"Data": {"Chunks": [{}, {}]}},
    }
    target_appearance: dict = {"components": []}

    _copy_infrastructure(
        source_appearance,
        target_appearance,
        face_rig=None,
        facial_setup=None,
        face_graph=None,
        skip_donor_hair_dangle=True,
    )

    names = [c["name"]["$value"] for c in target_appearance["components"]]
    assert names == ["breasts"]


def test_copy_infrastructure_patches_face_rig_donor_overrides():
    source_appearance = {
        "components": [
            {
                "$type": "entAnimatedComponent",
                "name": {"$type": "CName", "$storage": "string", "$value": "face_rig"},
            },
        ],
        "compiledData": {"Data": {"Chunks": [{}]}},
    }
    target_appearance: dict = {"components": []}

    _copy_infrastructure(
        source_appearance,
        target_appearance,
        face_rig=r"base\test\custom.rig",
        facial_setup=r"base\test\custom.facialsetup",
        face_graph=r"base\test\custom.animgraph",
        skip_donor_hair_dangle=False,
    )

    copied = target_appearance["components"][0]
    assert copied["rig"]["DepotPath"]["$value"] == r"base\test\custom.rig"
    assert copied["facialSetup"]["DepotPath"]["$value"] == r"base\test\custom.facialsetup"
    assert copied["graph"]["DepotPath"]["$value"] == r"base\test\custom.animgraph"
