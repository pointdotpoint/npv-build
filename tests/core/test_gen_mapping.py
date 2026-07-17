from npv_build.gen_mapping import (
    diff_mapping,
    extract_index_head_paths,
    format_report,
    mapping_report,
)


def test_diff_finds_missing_and_unmapped():
    mapping_paths = {r"base\characters\head\a.ent", r"base\characters\head\gone.ent"}
    index_paths = {r"base\characters\head\a.ent", r"base\characters\head\new.ent"}
    missing, unmapped = diff_mapping(mapping_paths, index_paths)
    assert missing == {r"base\characters\head\gone.ent"}
    assert unmapped == {r"base\characters\head\new.ent"}


def test_diff_mapping_no_drift():
    paths = {r"base\characters\head\a.ent", r"base\characters\head\b.ent"}
    missing, unmapped = diff_mapping(paths, paths)
    assert missing == set()
    assert unmapped == set()


def test_diff_mapping_backslash_literal_no_normalization():
    # A forward-slash variant of the same logical path must NOT be treated as
    # a match -- depot paths are backslash-literal, no normalization.
    mapping_paths = {r"base\characters\head\a.ent"}
    index_paths = {"base/characters/head/a.ent"}
    missing, unmapped = diff_mapping(mapping_paths, index_paths)
    assert missing == mapping_paths
    assert unmapped == index_paths


def test_diff_mapping_empty_inputs():
    missing, unmapped = diff_mapping(set(), set())
    assert missing == set()
    assert unmapped == set()


def test_extract_index_head_paths_excludes_hair_and_tattoo_and_item_stems():
    # Real part_ents shapes observed in the 2.13 game index: hair (hh_),
    # tattoo/scar (hx_), facial hair (hb_), and item/earring (i1_) .ent files
    # all live under player_base_heads alongside baseheads, but are never
    # referenced by head_preset_parts -- they must not appear as candidates.
    index = {
        "part_ents": {
            "hh_044_pma__hairs_140_fpp": (
                r"base\characters\head\player_base_heads\appearances\entity"
                r"\hairs\fpp\hh_044_pma__hairs_140_fpp.ent"
            ),
            "hx_000_pwa__tattoo_09": (
                r"base\characters\head\player_base_heads\appearances\entity"
                r"\tattoo\hx_000_pwa__tattoo_09.ent"
            ),
            "hb_000_pma__fu_manchu": (
                r"base\characters\head\player_base_heads\appearances\entity"
                r"\facial_hairs\hb_000_pma__fu_manchu.ent"
            ),
            "i1_000_pwa_earring__basehead_04": (
                r"base\characters\head\player_base_heads\appearances\entity"
                r"\items\i1_000_pwa_earring__basehead_04.ent"
            ),
        }
    }
    assert extract_index_head_paths(index) == set()


def test_extract_index_head_paths_includes_basehead_family_stems():
    # The four prefixes actually present in data/mappings/2.13.json's
    # head_preset_parts: h0_/he_/ht_ (head dir) and heb_ (face_decals dir).
    index = {
        "part_ents": {
            "h0_000_pwa__basehead": (
                r"base\characters\head\player_base_heads\appearances\entity"
                r"\head\h0_000_pwa__basehead.ent"
            ),
            "he_000_pwa__basehead": (
                r"base\characters\head\player_base_heads\appearances\entity"
                r"\head\he_000_pwa__basehead.ent"
            ),
            "ht_000_pwa__basehead": (
                r"base\characters\head\player_base_heads\appearances\entity"
                r"\head\ht_000_pwa__basehead.ent"
            ),
            "heb_000_pwa__basehead": (
                r"base\characters\head\player_base_heads\appearances\entity"
                r"\face_decals\heb_000_pwa__basehead.ent"
            ),
        }
    }
    assert extract_index_head_paths(index) == set(index["part_ents"].values())


def test_mapping_report_composes_extract_and_diff(monkeypatch):
    import npv_build.gen_mapping as gm

    fake_mapping = {
        "pwa": {
            "head_preset_parts": {
                "00": [
                    r"base\characters\head\player_base_heads\appearances\entity\head\h0_000_pwa__basehead.ent",
                    r"base\characters\head\player_base_heads\appearances\entity\head\gone_pwa.ent",
                ]
            },
            "body_part": r"base\characters\common\player_base_bodies\appearances\entity\t0_000_pwa_base__full.ent",
            "arms_part": r"base\characters\common\player_base_bodies\appearances\entity\a0_000_pwa_base__full.ent",
            "hair_part": {},
        },
        "pma": {
            "head_preset_parts": {
                "00": [
                    r"base\characters\head\player_base_heads\appearances\entity\head\h0_000_pma__basehead.ent",
                ]
            },
            "body_part": r"base\characters\common\player_base_bodies\appearances\entity\t0_000_pma_base__full.ent",
            "arms_part": r"base\characters\common\player_base_bodies\appearances\entity\a0_000_pma_base__full.ent",
            "hair_part": {},
        },
    }
    # body_part/arms_part are intentionally NOT covered by the index (they
    # live outside player_base_heads) -- they must be excluded from the diff
    # entirely, not counted as "checked" or flagged "missing".

    fake_index = {
        "part_ents": {
            "h0_000_pwa__basehead": r"base\characters\head\player_base_heads\appearances\entity\head\h0_000_pwa__basehead.ent",
            "h0_000_pma__basehead": r"base\characters\head\player_base_heads\appearances\entity\head\h0_000_pma__basehead.ent",
            # A new, unmapped basehead-family entry -- a genuine candidate.
            "h0_001_pwa__basehead": r"base\characters\head\player_base_heads\appearances\entity\head\h0_001_pwa__basehead.ent",
            # A hair .ent under the same player_base_heads tree -- structurally
            # never covered by head_preset_parts, so must NOT surface as a
            # candidate (this is the false-positive noise being filtered out).
            "hh_044_pma__hairs_140_fpp": r"base\characters\head\player_base_heads\appearances\entity\hairs\fpp\hh_044_pma__hairs_140_fpp.ent",
        },
        "head_apps": {},
        "app_appearances": {},
    }

    monkeypatch.setattr(gm, "_load_mapping", lambda patch: fake_mapping)
    monkeypatch.setattr(gm, "_load_index", lambda game_dir, patch, wk: fake_index)

    report = mapping_report(game_dir="/fake/game", mapping_patch="2.13")

    assert report["missing_assets"] == [
        r"base\characters\head\player_base_heads\appearances\entity\head\gone_pwa.ent"
    ]
    assert report["unmapped_candidates"] == [
        r"base\characters\head\player_base_heads\appearances\entity\head\h0_001_pwa__basehead.ent"
    ]
    assert report["checked"] == 3  # 2 pwa head_preset_parts + 1 pma head_preset_parts


def test_mapping_report_output_is_sorted_lists(monkeypatch):
    import npv_build.gen_mapping as gm

    fake_mapping = {
        "pwa": {
            "head_preset_parts": {
                "00": [
                    r"base\characters\head\z_last.ent",
                    r"base\characters\head\a_first.ent",
                ]
            },
            "body_part": None,
            "arms_part": None,
            "hair_part": {},
        }
    }
    fake_index = {"part_ents": {}, "head_apps": {}, "app_appearances": {}}

    monkeypatch.setattr(gm, "_load_mapping", lambda patch: fake_mapping)
    monkeypatch.setattr(gm, "_load_index", lambda game_dir, patch, wk: fake_index)

    report = mapping_report(game_dir="/fake/game", mapping_patch="2.13")

    assert report["missing_assets"] == sorted(report["missing_assets"])
    assert report["unmapped_candidates"] == sorted(report["unmapped_candidates"])


def test_format_report_contains_counts():
    report = {
        "missing_assets": [r"base\characters\head\gone.ent"],
        "unmapped_candidates": [r"base\characters\head\new.ent"],
        "checked": 10,
    }
    text = format_report(report)
    assert "missing" in text.lower()
    assert "unmapped" in text.lower()
    assert "gone.ent" in text
    assert "new.ent" in text
    assert "10" in text
