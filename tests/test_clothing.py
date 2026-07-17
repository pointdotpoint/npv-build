"""Tests for the clothing module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from npv_build.clothing import resolve_clothing


@pytest.fixture
def mock_fallback(tmp_path):
    fallback = {
        "pwa": {
            "inner_torso": {
                "name": "t1_default_pwa",
                "mesh": "base\\garment\\t1_default_pwa.mesh",
                "appearance": "default",
            },
            "legs": {
                "name": "l1_default_pwa",
                "mesh": "base\\garment\\l1_default_pwa.mesh",
                "appearance": "default",
            },
        },
        "pma": {
            "inner_torso": {
                "name": "t1_default_pma",
                "mesh": "base\\garment\\t1_default_pma.mesh",
                "appearance": "default",
            },
        },
    }
    fallback_path = tmp_path / "fallback_outfit.json"
    fallback_path.write_text(json.dumps(fallback))
    return fallback_path


def test_resolve_clothing_defaults(mock_fallback):
    with patch("npv_build.clothing.Path") as MockPath:
        MockPath.__truediv__ = Path.__truediv__
        MockPath.return_value.__truediv__ = lambda self, other: mock_fallback.parent / other
        # Direct approach: patch the file reading
        # Simpler: just call with the real module but mock the data file

    # Test with the actual module, relying on the real fallback_outfit.json
    specs = resolve_clothing("pwa")
    assert len(specs) > 0
    assert all(s["comp_type"] == "entGarmentSkinnedMeshComponent" for s in specs)
    assert all("source" in s for s in specs)


def test_resolve_clothing_garment_override():
    specs = resolve_clothing(
        "pwa", garment_overrides=["base\\characters\\garment\\t1_097_pwa_tank.ent"]
    )
    names = [s["name"] for s in specs]
    assert "t1_097_pwa_tank" in names


def test_resolve_clothing_slot_detection():
    specs = resolve_clothing(
        "pwa",
        garment_overrides=[
            "base\\garment\\t2_jacket.ent",
            "base\\garment\\l1_pants.ent",
            "base\\garment\\s1_boots.ent",
        ],
    )
    sources = [s["source"] for s in specs]
    assert "clothing:outer_torso" in sources
    assert "clothing:legs" in sources
    assert "clothing:feet" in sources


def test_resolve_clothing_empty_overrides():
    specs_no = resolve_clothing("pwa", garment_overrides=[])
    specs_none = resolve_clothing("pwa", garment_overrides=None)
    assert len(specs_no) == len(specs_none)


def test_resolve_clothing_uses_equipped_outfit():
    equipped = [
        {
            "name": "t1_097_pwa_tank",
            "mesh": "base\\g\\t1_097_pwa_tank.mesh",
            "appearance": "red",
            "slot": "inner_torso",
        },
        {
            "name": "l1_055_pwa_pants",
            "mesh": "base\\g\\l1_055_pwa_pants.mesh",
            "appearance": "black",
            "slot": "legs",
        },
    ]
    specs = resolve_clothing("pwa", equipped=equipped)
    names = [s["name"] for s in specs]
    assert "t1_097_pwa_tank" in names
    assert "l1_055_pwa_pants" in names
    tank = next(s for s in specs if s["name"] == "t1_097_pwa_tank")
    assert tank["appearance"] == "red"
    assert tank["comp_type"] == "entGarmentSkinnedMeshComponent"
    assert "t1_024_pwa_tshirt__sweater" not in names


def test_resolve_clothing_equipped_keeps_both_torso_layers():
    equipped = [
        {
            "name": "t1_inner",
            "mesh": "base\\g\\t1_inner.mesh",
            "appearance": "default",
            "slot": "inner_torso",
        },
        {
            "name": "t2_outer",
            "mesh": "base\\g\\t2_outer.mesh",
            "appearance": "default",
            "slot": "outer_torso",
        },
    ]
    specs = resolve_clothing("pwa", equipped=equipped)
    names = [s["name"] for s in specs]
    assert "t1_inner" in names and "t2_outer" in names


def test_resolve_clothing_garment_override_beats_equipped():
    equipped = [
        {"name": "l1_old", "mesh": "base\\g\\l1_old.mesh", "appearance": "default", "slot": "legs"},
    ]
    specs = resolve_clothing(
        "pwa",
        garment_overrides=[
            "base\\garment\\l1_new_pwa.ent",
        ],
        equipped=equipped,
    )
    names = [s["name"] for s in specs]
    assert "l1_new_pwa" in names
    assert "l1_old" not in names


def test_resolve_clothing_empty_equipped_falls_back():
    specs_none = resolve_clothing("pwa", equipped=None)
    specs_empty = resolve_clothing("pwa", equipped=[])
    base = resolve_clothing("pwa")
    assert len(specs_none) == len(base)
    assert len(specs_empty) == len(base)
