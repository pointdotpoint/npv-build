"""Guard that every vendored preset resolves through the live game mapping."""

import json
import os
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

    # tests/conftest.py isolates XDG config for every test, so the real GUI
    # setting is intentionally invisible under pytest. Let an explicit e2e
    # path opt into the live install; retain load_settings() for standalone
    # use where that isolation fixture is absent.
    game_dir = os.environ.get("NPV_E2E_GAME_DIR")
    if not game_dir:
        game_dir = load_settings().game_dir
    if not game_dir:
        pytest.skip("no game_dir configured (set NPV_E2E_GAME_DIR)")

    cc = json.loads(path.read_text(encoding="utf-8"))
    asset_paths = resolve_assets(cc, Path(game_dir), None, [], None)
    assert not asset_paths.get("unresolved"), asset_paths.get("unresolved")
