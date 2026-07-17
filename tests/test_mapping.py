import pytest

from npv_build.mapping import MappingError, resolve_assets


def test_resolve_assets_valid():
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "selections": [
            {
                "slot": "head",
                "prefix": "h0",
                "index": 0,
                "rig": "pwa",
                "group": "basehead",
                "variant": "01_ca_pale",
                "raw": "h0_000_pwa__basehead__01_ca_pale",
                "cname_hash": 1234567,
            },
            {
                "slot": "eyes",
                "prefix": "he",
                "index": 0,
                "rig": "pwa",
                "group": "basehead",
                "variant": "14_gradient_grey",
                "raw": "he_000_pwa__basehead__14_gradient_grey",
                "cname_hash": 7654321,
            },
            {
                "slot": "hairs",
                "prefix": "fhair",
                "index": 0,
                "rig": "",
                "group": "miyavivi_twistup_soft",
                "variant": "",
                "raw": "fhair_miyavivi_twistup_soft",
                "cname_hash": 0,
            },
        ],
    }

    assets = resolve_assets(cc_settings)

    assert assets["patch"] == "2.13"
    assert assets["body_rig"] == "pwa"
    assert (
        assets["head_app"]
        == "base\\characters\\head\\player_base_heads\\appearances\\head\\h0_000__basehead.app"
    )
    assert assets["head_appearance_name"] == "h0_000_pwa__basehead__01_ca_pale"

    # Assert part_entities lists head preset parts, body base, and arms
    assert any("h0_000_pwa__basehead.ent" in p for p in assets["part_entities"])
    assert any("he_000_pwa__basehead.ent" in p for p in assets["part_entities"])
    assert any("ht_000_pwa__basehead.ent" in p for p in assets["part_entities"])
    assert any("heb_000_pwa__basehead.ent" in p for p in assets["part_entities"])
    assert any("t0_000_pwa_base__full.ent" in p for p in assets["part_entities"])
    assert any("a0_000_pwa_base__full.ent" in p for p in assets["part_entities"])

    # Assert fhair registered as external dependency
    assert len(assets["external_dependencies"]) == 1
    assert assets["external_dependencies"][0]["selection"] == "fhair_miyavivi_twistup_soft"


def test_resolve_assets_missing_patch():
    with pytest.raises(MappingError):
        resolve_assets({})
