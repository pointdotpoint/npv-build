"""M2 T7 — current-patch (2.31) save support.

CDPR kept the save-format build (2310) and CC struct (v3=195) stable across
marketing patches 2.13 -> 2.31, so the existing decoder and asset tables serve
the current patch. These tests pin that: build 2310 resolves to the current
patch label and to asset/donor tables that exist on disk.
"""

from __future__ import annotations

import json
from importlib import resources

from npv_build.save_parser import detect_patch


def _save_versions() -> dict:
    return json.loads(resources.files("npv_build").joinpath("data/save_versions.json").read_text())


def test_build_2310_is_supported_and_labeled_current():
    versions = _save_versions()
    assert "2310" in versions
    # 2310 is the save-format build for the current patch line; label it as such.
    assert versions["2310"] == "2.31"


def test_detect_patch_returns_current_label_for_2310():
    assert detect_patch((269, 2310, 195)) == "2.31"


def test_current_patch_resolves_to_existing_tables():
    # 2.13->2.31 share the save format + game assets, so 2.31 resolves to the
    # vendored table key that has files on disk (no duplicated tables).
    from npv_build.mapping import resolve_table_key

    patch = _save_versions()["2310"]  # "2.31"
    table_key = resolve_table_key(patch)
    assert resources.files("npv_build").joinpath(f"data/mappings/{table_key}.json").is_file()
    assert resources.files("npv_build").joinpath(f"data/donors/{table_key}.json").is_file()


def test_resolve_table_key_identity_for_own_key():
    from npv_build.mapping import resolve_table_key

    # a patch whose tables exist directly resolves to itself
    assert resolve_table_key("2.13") == "2.13"


def test_current_donor_covers_both_body_rigs():
    from npv_build.mapping import resolve_table_key

    patch = _save_versions()["2310"]
    donors = json.loads(
        resources.files("npv_build")
        .joinpath(f"data/donors/{resolve_table_key(patch)}.json")
        .read_text()
    )
    for rig in ("pwa", "pma"):
        assert rig in donors, f"donor missing rig {rig}"
