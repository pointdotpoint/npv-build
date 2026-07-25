import json

import pytest

from npv_build.core.errors import NpvError
from npv_build.gui_logic import presets


def test_list_presets_reports_availability(monkeypatch, tmp_path):
    monkeypatch.setattr(presets, "_preset_dir", lambda: tmp_path)
    (tmp_path / "default_v_pwa.json").write_text(
        json.dumps({"body_rig": "pwa"}),
        encoding="utf-8",
    )

    assert presets.list_presets() == [
        {"rig": "pwa", "available": True},
        {"rig": "pma", "available": False},
    ]


def test_load_preset_roundtrip_and_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(presets, "_preset_dir", lambda: tmp_path)
    (tmp_path / "default_v_pwa.json").write_text(
        json.dumps({"body_rig": "pwa"}),
        encoding="utf-8",
    )

    assert presets.load_preset("pwa")["body_rig"] == "pwa"
    with pytest.raises(NpvError):
        presets.load_preset("pma")
    with pytest.raises(NpvError):
        presets.load_preset("weird")


def test_load_preset_reports_corrupt_json(monkeypatch, tmp_path):
    monkeypatch.setattr(presets, "_preset_dir", lambda: tmp_path)
    (tmp_path / "default_v_pwa.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(NpvError, match="corrupt"):
        presets.load_preset("pwa")


@pytest.mark.parametrize("rig", ["pwa", "pma"])
def test_vendored_preset_structure(rig):
    """Guard the real vendored files once the user generates them."""
    path = presets.preset_path(rig)
    if not path.exists():
        pytest.skip(f"preset for {rig} not vendored yet (user-gated data)")

    cc = json.loads(path.read_text(encoding="utf-8"))
    assert cc["body_rig"] == rig
    assert cc["selections"], "preset must carry the full default CC selections"
    for key in ("patch", "skin", "hair", "face_morphs"):
        assert key in cc
