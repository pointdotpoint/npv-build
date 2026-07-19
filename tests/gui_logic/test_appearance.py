import copy

import pytest

from npv_build.gui_logic.appearance import (
    EDITABLE_SLOTS,
    apply_overrides,
    inspector_rows,
    option_lists,
    validate_overrides,
)


def _cc():
    return {
        "patch": "2.31", "body_rig": "pwa",
        "selections": [
            {"slot": "character_customization", "label": "eyes_color",
             "raw": "he_000_pwa__basehead__11_gradient_blue",
             "variant": "11_gradient_blue", "rig": "pwa", "group": "basehead",
             "prefix": "he", "index": 0, "cname_hash": 1},
            {"slot": "character_customization", "label": "winona_2_hair",
             "raw": "51_succulent", "variant": "", "rig": "", "group": "",
             "prefix": "", "index": 0, "cname_hash": 2},
        ],
        "head": {"preset_id": 0, "raw": "h0_000_pwa__basehead__01_ca_pale"},
        "eyes": {"raw": "he_000_pwa__basehead__11_gradient_blue"},
        "teeth": {"raw": "female_ht_000__basehead"},
        "skin": {"tone_id": "01_ca_pale"},
        "hair": {"style_id": "winona_2", "raw": "winona_2_hair"},
        "overlays": [],
        "face_morphs": {"ear": "h035", "eyes": "h091", "jaw": "h114",
                        "mouth": "h013", "nose": "h042"},
    }


OPTIONS = {
    "skin_tone": ["01_ca_pale", "02_ca_limestone", "03_ca_medium"],
    "hair_style": ["hh_040_pwa__morrigan", "hh_041_pwa__bob"],
    "hair_color": ["03_ginger_copper", "51_succulent", "06_black_carbon"],
    "eye_color": ["01_black", "11_gradient_blue", "21_green"],
}


def test_rows_cover_editable_and_readonly():
    rows = inspector_rows(_cc(), OPTIONS, {})
    by_id = {r["slot_id"]: r for r in rows}
    for slot in EDITABLE_SLOTS:
        assert by_id[slot]["editable"] is True
        assert by_id[slot]["options"]
    assert by_id["skin_tone"]["value_raw"] == "01_ca_pale"
    assert by_id["hair_style"]["value_raw"] == "winona_2"
    assert by_id["hair_color"]["value_raw"] == "51_succulent"
    assert by_id["eye_color"]["value_raw"] == "11_gradient_blue"
    # Read-only rows exist and are locked
    assert by_id["body_rig"]["editable"] is False
    assert by_id["face_morph_eyes"]["editable"] is False
    assert by_id["face_morph_eyes"]["value_raw"] == "h091"


def test_rows_editable_without_option_list_degrades_to_readonly():
    rows = inspector_rows(_cc(), {}, {})
    by_id = {r["slot_id"]: r for r in rows}
    assert by_id["hair_style"]["editable"] is False  # no options -> locked


def test_rows_use_display_names_with_raw_fallback():
    rows = inspector_rows(_cc(), OPTIONS, {"skin_tone": "Skin tone"})
    by_id = {r["slot_id"]: r for r in rows}
    assert by_id["skin_tone"]["label"] == "Skin tone"
    assert by_id["hair_color"]["label"] == "hair_color"  # fallback = slot_id


def test_apply_overrides_is_pure_and_targets_the_right_fields():
    cc = _cc()
    before = copy.deepcopy(cc)
    out = apply_overrides(cc, {
        "skin_tone": "03_ca_medium",
        "hair_style": "hh_041_pwa__bob",
        "hair_color": "06_black_carbon",
        "eye_color": "21_green",
    })
    assert cc == before  # input untouched
    assert out["skin"]["tone_id"] == "03_ca_medium"
    assert out["hair"]["style_id"] == "hh_041_pwa__bob"
    hair_sel = next(s for s in out["selections"] if s["label"].endswith("_hair"))
    assert hair_sel["raw"] == "06_black_carbon"
    assert out["eyes"]["raw"] == "he_000_pwa__basehead__21_green"
    eye_sel = next(s for s in out["selections"] if s["label"] == "eyes_color")
    assert eye_sel["raw"] == "he_000_pwa__basehead__21_green"
    assert eye_sel["variant"] == "21_green"


def test_apply_overrides_empty_is_identity_copy():
    cc = _cc()
    out = apply_overrides(cc, {})
    assert out == cc and out is not cc


def test_apply_overrides_unknown_slot_raises():
    with pytest.raises(ValueError):
        apply_overrides(_cc(), {"nose_shape": "x"})


def _cc_without_hair_color_selection():
    cc = _cc()
    cc["selections"] = [s for s in cc["selections"] if s["label"] != "winona_2_hair"]
    cc["hair"] = {"style_id": "winona_2", "raw": "winona_2_hair"}
    return cc


def test_apply_overrides_hair_color_without_selection_raises():
    with pytest.raises(ValueError):
        apply_overrides(_cc_without_hair_color_selection(), {"hair_color": "x"})


def test_rows_hair_color_with_empty_value_is_locked_even_with_options():
    rows = inspector_rows(_cc_without_hair_color_selection(), OPTIONS, {})
    by_id = {r["slot_id"]: r for r in rows}
    assert by_id["hair_color"]["value_raw"] == ""
    assert by_id["hair_color"]["editable"] is False


def test_apply_overrides_hair_mod_emulates_ccxl_save():
    """hair_mod: <token> must reshape cc.hair exactly like a save that used
    that CCXL hair — mapping.resolve_assets' CCXL branch keys off
    hair.raw.endswith('_hair') + hair.style_id (see research note
    2026-07-19-ccxl-hair-input.md)."""
    out = apply_overrides(_cc(), {"hair_mod": "edie"})
    assert out["hair"] == {"style_id": "edie", "raw": "edie_hair"}


def test_apply_overrides_hair_mod_wins_over_hair_style():
    # UI keeps them mutually exclusive, but the transform must still be
    # deterministic if both arrive: hair_mod wins regardless of dict order.
    out = apply_overrides(_cc(), {"hair_style": "hh_041_pwa__bob",
                                  "hair_mod": "edie"})
    assert out["hair"] == {"style_id": "edie", "raw": "edie_hair"}


def test_validate_overrides_reports_bad_values():
    problems = validate_overrides({"skin_tone": "nope"}, OPTIONS)
    assert problems and "skin_tone" in problems[0]
    assert validate_overrides({"skin_tone": "03_ca_medium"}, OPTIONS) == []
    # Unknown slot is a problem, not a crash
    assert validate_overrides({"bogus": "x"}, OPTIONS)


def test_validate_overrides_hair_mod_token():
    # hair_mod has no options list — any non-empty token passes, empty fails.
    assert validate_overrides({"hair_mod": "edie"}, OPTIONS) == []
    assert validate_overrides({"hair_mod": ""}, OPTIONS)


INDEX = {
    "part_ents": {
        "hh_040_pwa__morrigan": "base\\...\\hh_040_pwa__morrigan.ent",
        "hh_041_pwa__bob": "base\\...\\hh_041_pwa__bob.ent",
        "hh_044_pma__hairs_140": "base\\...\\hh_044_pma__hairs_140.ent",
        "hh_044_pma__hairs_140_fpp": "base\\...\\hh_044_pma__hairs_140_fpp.ent",
        "hx_000_pwa__tattoo_09": "base\\...\\hx_000_pwa__tattoo_09.ent",
    },
    "app_appearances": {
        "base\\x\\he_000_pwa__basehead.app": [
            "he_000_pwa__basehead__01_black", "he_000_pwa__basehead__11_gradient_blue"],
        "base\\x\\h0_000_pwa__basehead.app": [
            "h0_000_pwa__basehead__01_ca_pale", "h0_000_pwa__basehead__03_ca_medium"],
        "base\\x\\hh_040_pwa.app": ["03_ginger_copper", "51_succulent"],
    },
}


def test_option_lists_derivation():
    opts = option_lists(INDEX, "pwa")
    assert opts["hair_style"] == ["hh_040_pwa__morrigan", "hh_041_pwa__bob"]
    assert opts["eye_color"] == ["01_black", "11_gradient_blue"]
    assert opts["skin_tone"] == ["01_ca_pale", "03_ca_medium"]
    assert opts["hair_color"] == ["03_ginger_copper", "51_succulent"]


def test_option_lists_other_rig_and_empty_index():
    opts = option_lists(INDEX, "pma")
    assert opts["hair_style"] == ["hh_044_pma__hairs_140"]  # no _fpp
    assert option_lists({}, "pwa") == {}
    assert option_lists(None, "pwa") == {}


# Real-shape fixture: app basenames WITHOUT rig (rig only embedded in the
# appearance names), matching the actual part-resolver index shape rather
# than the synthetic INDEX above. Includes a decoy app that must not match.
INDEX2 = {
    "part_ents": {},
    "app_appearances": {
        "base\\x\\he_000__basehead.app": [
            "he_000_pwa__basehead__11_gradient_blue",
            "he_000_pwa__basehead__01_black",
            "he_000_pma__basehead__21_green",
        ],
        "base\\x\\h0_000__basehead.app": [
            "h0_000_pwa__basehead__01_ca_pale",
            "h0_000_pwa__basehead__03_ca_medium",
        ],
        # Decoy: must NOT be matched as the exact skin_tone app for pwa.
        "base\\x\\h0_000__basehead_face_rig.app": [
            "h0_000_pwa__basehead_face_rig__99_should_not_appear",
        ],
    },
}


def test_option_lists_rigless_app_basename_fallback():
    opts = option_lists(INDEX2, "pwa")
    assert opts["eye_color"] == ["01_black", "11_gradient_blue"]
    assert opts["skin_tone"] == ["01_ca_pale", "03_ca_medium"]
    assert "99_should_not_appear" not in opts.get("skin_tone", [])
    # No hh_* apps/parts at all -> hair_style/hair_color absent or fall back,
    # but the decoy must not leak into any option list.
    for values in opts.values():
        assert "99_should_not_appear" not in values


def test_option_lists_hair_color_falls_back_to_vendored_list_when_index_has_no_hh_apps():
    import json
    from pathlib import Path

    vendored = json.loads(
        (Path(__file__).parents[2] / "npv_build" / "data" / "hair_colors.json").read_text()
    )
    opts = option_lists(INDEX2, "pwa")
    assert opts["hair_color"] == vendored
    assert opts["hair_color"] != []


def test_option_lists_empty_index_still_returns_empty_dict_with_fallback_present():
    # Fallback must never fire when there's no index at all.
    assert option_lists({}, "pwa") == {}
    assert option_lists(None, "pwa") == {}
