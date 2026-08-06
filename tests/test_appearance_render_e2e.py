"""Golden-image regression for the appearance preview render.

Skips unless NPV_PREVIEW_BUILD_DIR points at a real build output dir on a
machine with the game + WolvenKit + Blender. Goldens live OUTSIDE the repo
(rendered pixels are CDPR-derivative) at ~/.cache/npv/preview_goldens/.
Bless new goldens with NPV_UPDATE_GOLDENS=1.

Game dir: prefers NPV_GAME_DIR (same convention as test_build_project.py's
integration test) over the user's real config.toml, because the autouse
_isolate_user_dirs fixture in conftest.py redirects XDG_CONFIG_HOME to an
empty tmp dir for every test — load_config() alone can never see the real
config inside the suite, so this test would always skip without the env var.

Cache dir: this test also restores the real XDG_CACHE_HOME (mirroring the
Playwright-browsers workaround already applied in conftest.py's
_isolate_user_dirs). Without it, blender_module._blender_cmd() cannot see
the auto-downloaded Blender binary cached under ~/.cache/npv/tools/blender/
and silently falls back to `flatpak run org.blender.Blender`. Flatpak's
/tmp is a private per-sandbox tmpfs even under a filesystem=host override,
so a render with out_dir under pytest's tmp_path (which lives under /tmp)
"succeeds" (exit 0) while writing PNGs the host process can never see —
discovered 2026-08-06 live-gate run, see task-7-report.md. out_dir is kept
under ~/.cache/npv/ for the same reason: it's the one location every
Blender invocation (cached binary, PATH binary, or flatpak) can reach.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_REAL_CACHE_DIR = Path.home() / ".cache"
GOLDEN_DIR = _REAL_CACHE_DIR / "npv" / "preview_goldens"


def _build_dir():
    value = os.environ.get("NPV_PREVIEW_BUILD_DIR", "")
    if not value:
        pytest.skip("NPV_PREVIEW_BUILD_DIR not set (needs a real build output dir)")
    build = Path(value)
    if not (build / "npv_components.json").exists():
        pytest.skip(f"{build} has no npv_components.json")
    return build


def test_render_matches_goldens(monkeypatch):
    from npv_build.appearance_render import render_appearance
    from npv_build.config import load_config
    from npv_build.core.image_diff import compare
    from npv_build.wk_cli import WolvenKit, WolvenKitConfig

    build = _build_dir()
    game_dir = os.environ.get("NPV_GAME_DIR", "") or (load_config() or {}).get("game_dir", "")
    if not game_dir or not Path(game_dir).is_dir():
        pytest.skip("no valid game_dir (set NPV_GAME_DIR or configure game_dir)")

    monkeypatch.setenv("XDG_CACHE_HOME", str(_REAL_CACHE_DIR))

    render_root = _REAL_CACHE_DIR / "npv" / "e2e_render_out"
    render_root.mkdir(parents=True, exist_ok=True)
    out_dir = Path(tempfile.mkdtemp(dir=render_root))
    try:
        wk = WolvenKit(WolvenKitConfig(game_dir=Path(game_dir)))
        pngs = render_appearance(wk, build, out_dir=out_dir)

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
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
