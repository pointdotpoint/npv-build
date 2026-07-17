"""Tests for the head_bake module."""

from npv_build.head_bake import _is_detail_layer_override, find_stock_head_part, swap_head_part


class TestFindStockHeadPart:
    def test_finds_from_recipe_parts(self):
        asset_paths = {
            "recipe_parts": [
                {
                    "resource": {
                        "DepotPath": {
                            "$value": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent"
                        }
                    }
                },
                {
                    "resource": {
                        "DepotPath": {"$value": "base\\characters\\garment\\some_garment.ent"}
                    }
                },
            ],
            "part_entities": [],
        }
        result = find_stock_head_part(asset_paths)
        assert result is not None
        assert "h0_" in result

    def test_finds_from_part_entities(self):
        asset_paths = {
            "recipe_parts": [],
            "part_entities": [
                "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent",
            ],
        }
        result = find_stock_head_part(asset_paths)
        assert result is not None

    def test_returns_none_when_no_head(self):
        asset_paths = {
            "recipe_parts": [],
            "part_entities": ["base\\characters\\garment\\pants.ent"],
        }
        assert find_stock_head_part(asset_paths) is None


class TestSwapHeadPart:
    def test_swaps_recipe_parts(self):
        asset_paths = {
            "recipe_parts": [
                {"resource": {"DepotPath": {"$value": "old_head.ent"}}},
            ],
            "recipe_overrides": [],
        }
        swap_head_part(asset_paths, "old_head.ent", "new_head.ent")
        assert asset_paths["recipe_parts"][0]["resource"]["DepotPath"]["$value"] == "new_head.ent"

    def test_swaps_recipe_overrides(self):
        asset_paths = {
            "recipe_parts": [],
            "recipe_overrides": [
                {
                    "partResource": {"DepotPath": {"$value": "old_head.ent"}},
                    "componentsOverrides": [
                        {"meshAppearance": {"$value": "01_ca_pale"}},
                        {"meshAppearance": {"$value": "01_ca_pale_d04"}},
                    ],
                },
            ],
        }
        swap_head_part(asset_paths, "old_head.ent", "new_head.ent")
        ov = asset_paths["recipe_overrides"][0]
        assert ov["partResource"]["DepotPath"]["$value"] == "new_head.ent"
        # Detail layer override (_d04) should be preserved
        assert len(ov["componentsOverrides"]) == 2
        assert ov["componentsOverrides"][0]["meshAppearance"]["$value"] == "01_ca_pale"
        assert ov["componentsOverrides"][1]["meshAppearance"]["$value"] == "01_ca_pale_d04"

    def test_noop_when_no_stock_head(self):
        asset_paths = {"recipe_parts": [], "recipe_overrides": []}
        swap_head_part(asset_paths, "", "new.ent")
        # No crash, no change


class TestIsDetailLayerOverride:
    def test_detects_d_suffix(self):
        assert _is_detail_layer_override({"meshAppearance": {"$value": "01_ca_pale_d04"}})

    def test_rejects_normal(self):
        assert not _is_detail_layer_override({"meshAppearance": {"$value": "01_ca_pale"}})

    def test_rejects_empty(self):
        assert not _is_detail_layer_override({})
