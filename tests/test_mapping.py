import json
from pathlib import Path

import pytest

from npv_build.core.errors import MappingResolutionError
from npv_build.mapping import MappingError, resolve_assets
from npv_build.part_resolver import get_mock_index


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


def test_resolve_assets_uses_explicit_generic_ccxl_hair(monkeypatch, tmp_path):
    from npv_build import part_resolver

    selections = json.loads(
        (Path(__file__).parent / "fixtures" / "quicksave4_hair_selections.json").read_text()
    )
    for selection in selections:
        selection.update(
            {
                "prefix": "",
                "index": 0,
                "rig": "",
                "group": "",
                "variant": "",
            }
        )
    monkeypatch.setattr(
        part_resolver,
        "get_or_create_index",
        lambda *args, **kwargs: get_mock_index(),
    )
    resolved = []

    def fake_extract(game_dir, selection_label, body_rig, verbosity=0, wk=None):
        resolved.append((selection_label, body_rig))
        return (
            [{"$type": "entSkinnedMeshComponent"}],
            "#B1W_CCXL_S2-g.archive",
            r"b1w\ccxl\hair003\appearances\b1w_003_wa.app",
            "default",
        )

    monkeypatch.setattr(part_resolver, "extract_hair_components", fake_extract)
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "selections": selections,
        "hair": {
            "kind": "modded",
            "selection_label": "b1w_003_wa",
            "mesh_appearance": "teal_ombre",
            "style_id": "b1w_003_wa",
            "raw": "b1w_003_wa",
            "vanilla_style": 0,
        },
    }

    assets = resolve_assets(cc_settings, game_dir=tmp_path)

    assert resolved == [("b1w_003_wa", "pwa")]
    assert assets["hair_app"].endswith(r"b1w_003_wa.app")
    assert assets["hair_color"] == "teal_ombre"
    assert assets["external_dependencies"] == [
        {
            "selection": "b1w_003_wa",
            "reason": "modded hair from #B1W_CCXL_S2-g.archive (must stay installed)",
        }
    ]


def test_selected_modded_hair_must_resolve_instead_of_silently_building_bald(monkeypatch, tmp_path):
    from npv_build import part_resolver

    monkeypatch.setattr(
        part_resolver,
        "get_or_create_index",
        lambda *args, **kwargs: get_mock_index(),
    )
    monkeypatch.setattr(
        part_resolver,
        "extract_hair_components",
        lambda *args, **kwargs: ([], None, None, None),
    )
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "selections": [],
        "hair": {
            "kind": "modded",
            "selection_label": "b1w_003_wa",
            "mesh_appearance": "teal_ombre",
            "style_id": "b1w_003_wa",
            "raw": "b1w_003_wa",
            "vanilla_style": 0,
        },
    }

    with pytest.raises(MappingResolutionError, match="b1w_003_wa") as exc_info:
        resolve_assets(cc_settings, game_dir=tmp_path)

    assert "reinstall" in exc_info.value.remediation.casefold()


def test_unknown_selected_hair_record_blocks_build_instead_of_building_bald(
    monkeypatch,
):
    from npv_build import part_resolver

    monkeypatch.setattr(
        part_resolver,
        "get_or_create_index",
        lambda *args, **kwargs: get_mock_index(),
    )
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "selections": [],
        "hair": {
            "kind": "unknown",
            "selection_label": "mystery_ccxl_hair",
            "mesh_appearance": "",
            "style_id": "",
            "raw": "",
            "vanilla_style": 0,
        },
    }

    with pytest.raises(MappingResolutionError, match="mystery_ccxl_hair") as exc_info:
        resolve_assets(cc_settings)

    assert "reselect" in exc_info.value.remediation.casefold()


def test_resolve_assets_body_tattoo():
    """A body_tattoo_NN selection (slot TPP_Body/character_creation, raw =
    skin-tone-keyed appearance like w__01_ca_pale) must add the tx_ overlay
    part and record the appearance for the assembler."""
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
                "cname_hash": 1,
            },
            {
                "slot": "TPP_Body",
                "prefix": "",
                "index": 0,
                "rig": "",
                "group": "01_ca_pale",
                "variant": "",
                "raw": "w__01_ca_pale",
                "label": "body_tattoo_02",
                "cname_hash": 2,
            },
            {
                "slot": "FPP_Body",
                "prefix": "",
                "index": 0,
                "rig": "",
                "group": "01_ca_pale",
                "variant": "",
                "raw": "w__01_ca_pale",
                "label": "fpp_body_tattoo_02",
                "cname_hash": 3,
            },
        ],
    }

    assets = resolve_assets(cc_settings)

    assert assets["body_tattoo"] == {"shape": "02", "appearance": "w__01_ca_pale"}
    tx = [p for p in assets["part_entities"] if "tx_000_pwa_base__full_tattoo_02.ent" in p]
    assert len(tx) == 1, assets["part_entities"]


def test_resolve_assets_no_body_tattoo():
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
                "cname_hash": 1,
            },
        ],
    }
    assets = resolve_assets(cc_settings)
    assert assets.get("body_tattoo") is None
    assert not any("full_tattoo" in p for p in assets["part_entities"])


def test_resolve_assets_missing_patch():
    with pytest.raises(MappingError):
        resolve_assets({})


def test_unresolved_only_tracks_canonical_visual_selections(monkeypatch):
    """Runtime slots and choices with another resolution path are not failures."""
    from npv_build import part_resolver

    earring = "i0_000_pwa__earring__07_pearl"
    index = get_mock_index()
    index["appearance_to_app"] = {
        earring: [
            "base\\characters\\head\\player_base_heads\\appearances\\head\\"
            "piercings\\i0_000__earring_11.app"
        ]
    }
    monkeypatch.setattr(part_resolver, "get_or_create_index", lambda *a, **k: index)

    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "selections": [
            {
                "slot": "TPP",
                "prefix": "n0",
                "index": 0,
                "group": "neck",
                "raw": "n0_000_pwa_fpp__neck__03_ca_senna",
            },
            {
                "slot": "character_customization",
                "label": "piercings_11",
                "prefix": "i0",
                "index": 0,
                "group": "earring",
                "raw": earring,
            },
            {
                "slot": "character_customization",
                "label": "hair_color_cyberware_01",
                "prefix": "",
                "index": 0,
                "group": "",
                "raw": "15_pink_magenta",
            },
            {
                "slot": "character_customization",
                "label": "nails_color_tpp",
                "prefix": "a0",
                "index": 0,
                "group": "nails_01_all_black",
                "raw": "a0_000_pwa_base__nails_01_all_black__multilayer",
            },
        ],
    }

    assets = resolve_assets(cc_settings)

    assert assets["unresolved"] == []


def test_unknown_canonical_visual_selection_is_unresolved(monkeypatch):
    from npv_build import part_resolver

    monkeypatch.setattr(part_resolver, "get_or_create_index", lambda *a, **k: get_mock_index())
    unknown = "zz_999_pwa__unknown_feature__default"
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "selections": [
            {
                "slot": "character_customization",
                "label": "unknown_feature_01",
                "prefix": "zz",
                "index": 999,
                "group": "unknown_feature",
                "raw": unknown,
            }
        ],
    }

    assets = resolve_assets(cc_settings)

    assert assets["unresolved"] == [unknown]


def test_resolve_assets_carries_selected_nail_appearance(monkeypatch):
    from npv_build import part_resolver

    monkeypatch.setattr(part_resolver, "get_or_create_index", lambda *a, **k: get_mock_index())
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "nails": {"appearance": "01_all_red__multilayer"},
        "selections": [],
    }

    assets = resolve_assets(cc_settings)

    assert assets["nail_color"] == "01_all_red__multilayer"


def test_resolve_assets_body_tattoo_follows_effective_skin_tone():
    """When cc_settings carries a skin tone (e.g. after a skin_tone override),
    the tattoo appearance must be re-keyed to that tone, not the save's
    original tone embedded in the selection raw."""
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "skin": {"tone_id": "03_ca_senna"},
        "selections": [
            {
                "slot": "head",
                "prefix": "h0",
                "index": 0,
                "rig": "pwa",
                "group": "basehead",
                "variant": "01_ca_pale",
                "raw": "h0_000_pwa__basehead__01_ca_pale",
                "cname_hash": 1,
            },
            {
                "slot": "TPP_Body",
                "prefix": "",
                "index": 0,
                "rig": "",
                "group": "01_ca_pale",
                "variant": "",
                "raw": "w__01_ca_pale",
                "label": "body_tattoo_02",
                "cname_hash": 2,
            },
        ],
    }

    assets = resolve_assets(cc_settings)

    assert assets["body_tattoo"] == {"shape": "02", "appearance": "w__03_ca_senna"}


def test_resolve_assets_body_tattoo_keeps_raw_without_skin_tone():
    """No skin tone in cc_settings (or empty) -> tattoo raw passes through."""
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "skin": {"tone_id": ""},
        "selections": [
            {
                "slot": "TPP_Body",
                "prefix": "",
                "index": 0,
                "rig": "",
                "group": "01_ca_pale",
                "variant": "",
                "raw": "w__01_ca_pale",
                "label": "body_tattoo_02",
                "cname_hash": 2,
            },
        ],
    }

    assets = resolve_assets(cc_settings)

    assert assets["body_tattoo"]["appearance"] == "w__01_ca_pale"
