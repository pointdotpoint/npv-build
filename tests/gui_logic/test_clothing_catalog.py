import json
import re
from pathlib import Path

import npv_build.gui_logic.clothing_catalog as clothing_catalog
from npv_build.gui_logic.clothing_catalog import (
    build_catalog,
    build_catalog_from_game,
    build_exact_catalog,
    load_catalog,
    save_catalog,
    slot_for_mesh,
)

MESHES = [
    (
        "base\\characters\\garment\\player_equipment\\torso\\"
        "t1_024_tshirt__sweater\\t1_024_pwa_tshirt__sweater.mesh"
    ),
    (
        "base\\characters\\garment\\player_equipment\\torso\\"
        "t1_024_tshirt__sweater\\t1_024_pma_tshirt__sweater.mesh"
    ),
    (
        "base\\characters\\garment\\player_equipment\\legs\\"
        "l1_012_pants__jeans_tight\\l1_012_pwa_pants__jeans_tight.mesh"
    ),
    # Decorative component: must never become a selectable garment.
    (
        "base\\characters\\garment\\player_equipment\\torso\\"
        "t1_024_tshirt__sweater\\t1_024_pwa_tshirt__sweater_collar.mesh"
    ),
]
CLOTHES = [
    {
        "command": 'Game.AddToInventory("Items.Tshirt_024_basic_01", 1)',
        "name": "SWEATER TSHIRT",
        "image": "/images/clothes/tshirt_sweater.jpg",
    },
    {
        "command": 'Game.AddToInventory("Items.Hat_99_rare", 1)',
        "name": "IMAGINARY UNMATCHABLE HAT ZZZZ",
        "image": "/images/clothes/hat.jpg",
    },
]


def test_build_catalog_joins_primary_mesh_and_flags_rigs():
    entries = build_catalog(MESHES, CLOTHES)
    sweater = next(e for e in entries if e["item_id"] == "Tshirt_024_basic_01")
    assert sweater["mesh"].endswith("t1_024_pwa_tshirt__sweater.mesh")
    assert sweater["mesh_pwa"].endswith("t1_024_pwa_tshirt__sweater.mesh")
    assert sweater["mesh_pma"].endswith("t1_024_pma_tshirt__sweater.mesh")
    assert sweater["buildable_pwa"] is True
    assert sweater["buildable_pma"] is True
    assert sweater["slot"] == "inner_torso"


def test_exact_catalog_preserves_item_mesh_appearance_and_child_components():
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "quicksave4_garment_case.json").read_text()
    )

    entries = build_exact_catalog(
        fixture["clothes"],
        fixture["item_records"],
        fixture["entity_documents"],
        fixture["app_documents"],
    )
    blue = next(entry for entry in entries if entry["item_id"] == "Shirt_01_basic_01")
    black = next(entry for entry in entries if entry["item_id"] == "Shirt_01_basic_02")
    expansion = next(entry for entry in entries if entry["item_id"] == "Q301_nusa_agent")

    assert blue["mesh_pwa"] == black["mesh_pwa"]
    assert blue["appearance_pwa"] == "blue_moro"
    assert black["appearance_pwa"] == "black_psycho"
    assert len(blue["components_pwa"]) == 1
    assert [component["appearance"] for component in black["components_pwa"]] == [
        "black_psycho",
        "black",
    ]
    assert blue["buildable_pwa"] is True
    assert blue["buildable_pma"] is False
    assert expansion["mesh_pwa"].startswith("ep1\\")
    assert expansion["appearance_pwa"] == "nusa_agent"
    assert expansion["buildable_pwa"] is True


def test_unjoined_items_grey_out_not_dropped():
    entries = build_catalog(MESHES, CLOTHES)
    hat = next(e for e in entries if e["item_id"] == "Hat_99_rare")
    assert hat["mesh"] is None
    assert hat["slot"] == "head"
    assert hat["buildable_pwa"] is False
    assert hat["buildable_pma"] is False


def test_slot_for_mesh_prefixes():
    assert slot_for_mesh("...\\t1_024_pwa_x.mesh") == "inner_torso"
    assert slot_for_mesh("...\\t2_010_pwa_x.mesh") == "outer_torso"
    assert slot_for_mesh("...\\l1_012_pwa_x.mesh") == "legs"
    assert slot_for_mesh("...\\s1_066_pwa_x.mesh") == "feet"
    assert slot_for_mesh("...\\h2_002_pwa_x.mesh") == "head"
    assert slot_for_mesh("...\\x1_001_pwa_x.mesh") == "other"


def test_cache_roundtrip_and_corruption_degrades_to_unbuilt(tmp_path):
    entries = build_catalog(MESHES, CLOTHES)
    cache = tmp_path / "nested" / "c.json"
    save_catalog(cache, entries)
    assert load_catalog(cache) == entries
    assert load_catalog(tmp_path / "missing.json") is None
    cache.write_text("{not json")
    assert load_catalog(cache) is None
    cache.write_text(json.dumps(entries))
    assert load_catalog(cache) is None


def test_cache_rejects_changed_source_fingerprint(tmp_path):
    cache = tmp_path / "catalog.json"
    entries = build_catalog(MESHES, CLOTHES)
    fingerprints = {"tweakdb": {"size": 10, "mtime_ns": 20}}
    save_catalog(cache, entries, source_fingerprints=fingerprints)

    assert load_catalog(cache, expected_fingerprints=fingerprints) == entries
    assert (
        load_catalog(
            cache,
            expected_fingerprints={"tweakdb": {"size": 11, "mtime_ns": 20}},
        )
        is None
    )


def test_build_catalog_from_game_follows_exact_graph_and_caches(tmp_path, monkeypatch):
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "quicksave4_garment_case.json").read_text()
    )
    game = tmp_path / "game"
    content = game / "archive" / "pc" / "content"
    content.mkdir(parents=True)
    (game / "archive" / "pc" / "ep1").mkdir(parents=True)
    entity_depot = "base\\gameplay\\items\\equipment\\player_inner_torso_item.ent"
    expansion_entity_depot = "ep1\\gameplay\\items\\equipment\\outfit\\player_outfit_item_ep1.ent"
    documents = {
        entity_depot: fixture["entity_documents"]["player_inner_torso_item"],
        expansion_entity_depot: fixture["entity_documents"]["player_outfit_item_ep1"],
        **fixture["app_documents"],
        **fixture["mesh_documents"],
    }

    class FakeWk:
        def __init__(self):
            self.calls = []

        def list_archive(self, pattern, *, archive):
            self.calls.append(("list", pattern, archive))
            return [depot for depot in documents if re.search(pattern, depot, re.IGNORECASE)]

        def uncook_many(self, pattern, *, archive, dest):
            self.calls.append(("uncook", pattern, archive))
            for depot, document in documents.items():
                if re.search(pattern, depot.replace("\\", "/").rsplit("/", 1)[-1]):
                    path = dest / (depot.replace("\\", "/") + ".json")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(document))

    clothes_path = tmp_path / "clothes.json"
    clothes_path.write_text(json.dumps(fixture["clothes"]))
    cache_path = tmp_path / "cache" / "catalog.json"
    wk = FakeWk()
    monkeypatch.setattr(
        clothing_catalog,
        "_load_item_records",
        lambda _game_dir, _clothes: fixture["item_records"],
    )

    entries = build_catalog_from_game(game, wk, clothes_path, cache_path)

    blue = next(entry for entry in entries if entry["item_id"] == "Shirt_01_basic_01")
    black = next(entry for entry in entries if entry["item_id"] == "Shirt_01_basic_02")
    expansion = next(entry for entry in entries if entry["item_id"] == "Q301_nusa_agent")
    assert blue["appearance_pwa"] == "blue_moro"
    assert black["appearance_pwa"] == "black_psycho"
    assert [component["name"] for component in black["components_pwa"]] == [
        "test_shirt",
        "test_shirt_cuff",
    ]
    assert blue["buildable_pwa"] is True
    assert black["buildable_pwa"] is True
    assert expansion["appearance_pwa"] == "nusa_agent"
    assert expansion["buildable_pwa"] is True
    assert load_catalog(cache_path) == entries
