from __future__ import annotations

from npv_build.wolvenkit import (
    _collect_prefetch_entity_depots,
    _extract_part_components,
    _prefetch_component_json,
)


def _entity_json(number: int) -> dict:
    component = {
        "$type": "entMorphTargetSkinnedMeshComponent",
        "name": {"$value": f"part_{number}"},
        "morphResource": {
            "DepotPath": {"$value": f"base\\morph_{number}.morphtarget"}
        },
        "meshAppearance": {"$value": "default"},
        "chunkMask": str(100 + number),
    }
    return {"Data": {"RootChunk": {"components": [component]}}}


def _morph_json(number: int) -> dict:
    return {
        "Data": {
            "RootChunk": {
                "baseMesh": {"DepotPath": {"$value": f"base\\mesh_{number}.mesh"}}
            }
        }
    }


def test_prefetch_uses_one_entity_and_one_morphtarget_batch() -> None:
    calls: list[list[str]] = []

    class FakeWk:
        def uncook_json_many(self, filenames):
            calls.append(filenames)
            if filenames[0].endswith(".ent"):
                return {
                    filename: _entity_json(number)
                    for number, filename in enumerate(filenames)
                }
            return {
                filename: _morph_json(number)
                for number, filename in enumerate(filenames)
            }

    depots = [f"base\\part_{number}.ent" for number in range(10)]
    entities, morphs = _prefetch_component_json(FakeWk(), depots)

    assert len(calls) == 2
    assert len(entities) == 10
    assert len(morphs) == 10


def test_prefetch_collection_excludes_garment_meshes() -> None:
    asset_paths = {
        "part_entities": [
            r"base\body.ent",
            r"base\characters\garment\selected.mesh",
        ],
        "recipe_parts": [
            {"resource": {"DepotPath": {"$value": r"base\eyes.ent"}}},
            {"resource": {"DepotPath": {"$value": r"base\recipe.mesh"}}},
        ],
        "vanilla_hair_ent": r"base\hair.ent",
    }

    assert _collect_prefetch_entity_depots(asset_paths, r"base\head.ent") == {
        r"base\body.ent",
        r"base\eyes.ent",
        r"base\hair.ent",
        r"base\head.ent",
    }


def test_prefetched_component_output_matches_single_resource_path() -> None:
    entity = _entity_json(3)
    morph = _morph_json(3)

    class SingleWk:
        def uncook_json(self, filename):
            return morph if filename.endswith(".morphtarget") else entity

    class NoCallsWk:
        def uncook_json(self, _filename):
            raise AssertionError("prefetched JSON should avoid single-resource uncook")

    depot = r"base\part_3.ent"
    reference = _extract_part_components(SingleWk(), depot, 0)
    prefetched = _extract_part_components(
        NoCallsWk(),
        depot,
        0,
        entity_json={"part_3.ent": entity},
        morph_json={"morph_3.morphtarget": morph},
    )

    assert prefetched == reference
