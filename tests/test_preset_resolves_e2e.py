"""Guard that every vendored preset resolves through the live game mapping."""

import json
from pathlib import Path

import pytest

from npv_build.gui_logic.presets import RIGS, preset_path
from npv_build.gui_logic.settings import load_settings
from npv_build.mapping import resolve_assets


@pytest.mark.e2e
@pytest.mark.parametrize("rig", RIGS)
def test_preset_resolves_cleanly(rig):
    path = preset_path(rig)
    if not path.exists():
        pytest.skip(f"preset for {rig} not vendored yet")

    settings = load_settings()
    if not settings.game_dir:
        pytest.skip("no game_dir configured")

    cc = json.loads(path.read_text(encoding="utf-8"))
    asset_paths = resolve_assets(cc, Path(settings.game_dir), None, [], None)
    assert not asset_paths.get("unresolved"), asset_paths.get("unresolved")
