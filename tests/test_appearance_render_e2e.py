"""Golden-image regression for the appearance preview render.

Skips unless NPV_PREVIEW_BUILD_DIR points at a real build output dir on a
machine with the game + WolvenKit + Blender. Goldens live OUTSIDE the repo
(rendered pixels are CDPR-derivative) at ~/.cache/npv/preview_goldens/.
Bless new goldens with NPV_UPDATE_GOLDENS=1.
"""

import os
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

GOLDEN_DIR = Path.home() / ".cache" / "npv" / "preview_goldens"


def _build_dir():
    value = os.environ.get("NPV_PREVIEW_BUILD_DIR", "")
    if not value:
        pytest.skip("NPV_PREVIEW_BUILD_DIR not set (needs a real build output dir)")
    build = Path(value)
    if not (build / "npv_components.json").exists():
        pytest.skip(f"{build} has no npv_components.json")
    return build


def test_render_matches_goldens(tmp_path):
    from npv_build.appearance_render import render_appearance
    from npv_build.config import load_config
    from npv_build.core.image_diff import compare
    from npv_build.wk_cli import WolvenKit, WolvenKitConfig

    build = _build_dir()
    game_dir = (load_config() or {}).get("game_dir", "")
    if not game_dir or not Path(game_dir).is_dir():
        pytest.skip("no valid game_dir in config")

    wk = WolvenKit(WolvenKitConfig(game_dir=Path(game_dir)))
    pngs = render_appearance(wk, build, out_dir=tmp_path)

    if os.environ.get("NPV_UPDATE_GOLDENS") == "1":
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        for png in pngs:
            shutil.copy2(png, GOLDEN_DIR / png.name)
        pytest.skip(f"goldens updated at {GOLDEN_DIR}")

    missing = [p.name for p in pngs if not (GOLDEN_DIR / p.name).exists()]
    if missing:
        pytest.skip(f"goldens not blessed yet: {missing} (run with NPV_UPDATE_GOLDENS=1)")

    failures = {}
    for png in pngs:
        result = compare(png, GOLDEN_DIR / png.name)
        if not result["match"]:
            failures[png.name] = result["reason"]
    assert not failures, f"appearance drifted from goldens: {failures}"
