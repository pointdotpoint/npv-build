"""Guard: every component's meshAppearance must exist on its mesh.

The body-tattoo bug (fixed 2026-08-07) shipped because nothing checked the
appearance names a build writes against the names the meshes actually define.
The build stamped "w__01_ca_pale" — the save's raw, body-slot-prefixed value —
onto a mesh whose appearances are unprefixed, so the game fell back to no
material and the tattoo was invisible. Unit tests passed throughout: they
asserted the buggy value.

This test closes that gap for real builds by serializing each referenced mesh
and comparing. It needs a real game install plus a built NPV, so it skips
unless NPV_APPEARANCE_BUILD_DIR points at a build output directory.
"""

import json
import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _build_dir() -> Path:
    value = os.environ.get("NPV_APPEARANCE_BUILD_DIR", "")
    if not value:
        pytest.skip("NPV_APPEARANCE_BUILD_DIR not set (needs a real build output dir)")
    build = Path(value)
    if not (build / "npv_components.json").exists():
        pytest.skip(f"{build} has no npv_components.json")
    return build


def _mesh_appearances(wk, depot: str, stage: Path) -> set[str] | None:
    """Appearance names defined by a mesh, or None if it can't be read."""
    from npv_build.wk_cli import WolvenKitError

    extract_dir = stage / "extract"
    try:
        wk.extract(re.escape(depot), dest=extract_dir)
    except WolvenKitError:
        return None
    cr2w = extract_dir / Path(*depot.split("\\"))
    if not cr2w.exists():
        return None
    ser = stage / "ser" / cr2w.stem
    try:
        json_path = wk.serialize(cr2w, dest=ser)
    except WolvenKitError:
        return None
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    appearances = data.get("Data", {}).get("RootChunk", {}).get("appearances") or []
    names = set()
    for entry in appearances:
        name = (entry.get("Data") or entry).get("name")
        names.add(name.get("$value") if isinstance(name, dict) else name)
    return names


def test_component_appearances_exist_on_their_meshes(tmp_path, monkeypatch):
    from npv_build.config import load_config
    from npv_build.wk_cli import WolvenKit, WolvenKitConfig

    # The WolvenKit binary lives under the real cache dir, which conftest's
    # _isolate_user_dirs redirects away — restore it, as the render e2e does.
    monkeypatch.setenv("XDG_CACHE_HOME", str(Path.home() / ".cache"))

    build = _build_dir()
    # conftest's autouse _isolate_user_dirs redirects XDG_CONFIG_HOME, so
    # load_config() cannot see the real config from inside the suite — same
    # convention as test_appearance_render_e2e.py.
    game_dir = os.environ.get("NPV_GAME_DIR", "") or (load_config() or {}).get("game_dir", "")
    if not game_dir or not Path(game_dir).is_dir():
        pytest.skip("no valid game_dir (set NPV_GAME_DIR or configure game_dir)")

    wk = WolvenKit(WolvenKitConfig(game_dir=Path(game_dir)))
    components = json.loads((build / "npv_components.json").read_text())["components"]

    mismatches = []
    unreadable = []
    for comp in components:
        depot = comp.get("mesh") or ""
        wanted = comp.get("meshAppearance") or ""
        # Mod-scoped meshes are this build's own output and carry whatever the
        # baker wrote; only vanilla/mod-archive meshes have fixed appearances.
        if not wanted or not depot.endswith(".mesh") or depot.startswith("base\\npv-build\\"):
            continue
        available = _mesh_appearances(wk, depot, tmp_path / comp["name"])
        if available is None:
            unreadable.append(comp["name"])
            continue
        if wanted not in available:
            mismatches.append(f"{comp['name']}: wants {wanted!r}, mesh offers {sorted(available)}")

    # Unreadable meshes are not failures (some assets defeat WolvenKit's
    # exporter), but they are unchecked coverage — say so rather than let a
    # green run imply every component was verified.
    if unreadable:
        print(f"\nNOT CHECKED ({len(unreadable)} mesh(es) could not be read): {unreadable}")

    assert not mismatches, "appearance names not present on their meshes:\n" + "\n".join(mismatches)
