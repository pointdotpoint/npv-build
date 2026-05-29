"""Bake V's face morphs into a head mesh and author a mod-scoped morphtarget.

Owns its own staging directories. Takes a WolvenKit adapter instance for
all CLI operations.
"""
from __future__ import annotations

import json
import re as _re
import shutil
import tempfile
from pathlib import Path

from .wk_cli import WolvenKit, WolvenKitError


STOCK_HEAD_MESH = {
    "pwa": "h0_000_pwa_c__basehead.mesh",
    "pma": "h0_000_pma_c__basehead.mesh",
}


def find_stock_head_part(asset_paths: dict) -> str | None:
    """Find the head part .ent depot path in the recipe or part_entities."""
    for pv in asset_paths.get("recipe_parts", []):
        path = pv.get("resource", {}).get("DepotPath", {}).get("$value", "")
        if "appearances\\entity\\head\\h0_" in path:
            return path
    for p in asset_paths.get("part_entities", []):
        if "appearances\\entity\\head\\h0_" in p:
            return p
    return None


def swap_head_part(asset_paths: dict, stock_head: str, new_head: str) -> None:
    """Repoint recipe partsValues + partsOverrides from stock head to baked head.

    Strips _dXX detail-layer overrides that the baked mesh doesn't have.
    """
    if not stock_head:
        return
    for pv in asset_paths.get("recipe_parts", []):
        dp = pv.get("resource", {}).get("DepotPath", {})
        if dp.get("$value") == stock_head:
            dp["$value"] = new_head
    for ov in asset_paths.get("recipe_overrides", []):
        pr = ov.get("partResource", {}).get("DepotPath", {})
        if pr.get("$value") == stock_head:
            pr["$value"] = new_head


def _is_detail_layer_override(component_override: dict) -> bool:
    ma = component_override.get("meshAppearance", {}).get("$value", "")
    return bool(_re.search(r'_d\d{2}$', ma))


def _restore_head_materials(
    wk: WolvenKit,
    baked_mesh_fs: Path,
    body_rig: str,
    verbosity: int,
) -> None:
    """Copy material data from the stock head mesh into the baked mesh.

    The Blender import --keep step strips localMaterialBuffer, appearances,
    and materialEntries. We serialize both, patch, and deserialize.
    """
    basename = STOCK_HEAD_MESH.get(body_rig, STOCK_HEAD_MESH["pwa"])

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        wk.unbundle(_re.escape(basename) + r"$", dest=td_path)
        stock_files = list(td_path.rglob(basename))
        if not stock_files:
            return

        stock_json_dir = td_path / "stock_json"
        stock_json_dir.mkdir()
        stock_json_path = wk.serialize(stock_files[0], dest=stock_json_dir)
        stock_data = json.loads(stock_json_path.read_text())

        baked_json_dir = td_path / "baked_json"
        baked_json_dir.mkdir()
        baked_json_path = wk.serialize(baked_mesh_fs, dest=baked_json_dir)
        baked_data = json.loads(baked_json_path.read_text())

        stock_rc = stock_data.get("Data", {}).get("RootChunk", {})
        baked_rc = baked_data.get("Data", {}).get("RootChunk", {})

        for key in ("materialEntries", "appearances",
                    "localMaterialInstances", "preloadLocalMaterialInstances",
                    "externalMaterials", "preloadExternalMaterials",
                    "localMaterialBuffer"):
            if key in stock_rc:
                baked_rc[key] = stock_rc[key]

        patched_json = baked_json_dir / baked_json_path.name
        patched_json.write_text(json.dumps(baked_data, indent=2))

        # Copy stock mesh buffer files (material buffers)
        for buf in stock_json_path.parent.glob(
            stock_json_path.stem.replace(".mesh", "") + ".mesh.*.buffer"
        ):
            shutil.copy2(buf, baked_json_dir / buf.name.replace(
                stock_json_path.stem.replace(".mesh.json", ""),
                baked_json_path.stem.replace(".mesh.json", "")
            ))
        for buf in baked_mesh_fs.parent.glob(baked_mesh_fs.stem + ".*.buffer"):
            dest = baked_json_dir / buf.name
            if not dest.exists():
                shutil.copy2(buf, dest)

        wk.deserialize(patched_json)

        mat_count = len(stock_rc.get("materialEntries", []))
        if verbosity > 0:
            print(f"[Head] restored {mat_count} materials from stock head")


def bake_head(
    wk: WolvenKit,
    mod_id: str,
    build_dir: Path,
    body_rig: str,
    face_morphs: dict,
    verbosity: int = 0,
) -> bool | None:
    """Bake face morphs into head mesh and create mod-scoped morphtarget.

    Returns True on success, None on failure. Writes the baked mesh and
    morphtarget into build_dir at their depot paths.
    """
    from .blender_module import bake_face_mesh, HEAD_MORPHTARGET

    if not face_morphs:
        return None

    baked_mesh_depot = f"base\\npv-build\\{mod_id}\\{mod_id}_head.mesh"
    baked_mesh_fs = build_dir / baked_mesh_depot.replace("\\", "/")
    result = bake_face_mesh(
        wk.config.game_dir, body_rig, face_morphs, baked_mesh_fs, verbosity, wk=wk,
    )
    if not result:
        return None

    _restore_head_materials(wk, baked_mesh_fs, body_rig, verbosity)

    stock_mt_depot = HEAD_MORPHTARGET.get(body_rig, "")
    mt_depot = f"base\\npv-build\\{mod_id}\\{mod_id}_morphs.morphtarget"
    if not stock_mt_depot:
        return None

    mt_basename = stock_mt_depot.replace("\\", "/").rsplit("/", 1)[-1]
    try:
        mt_data = wk.uncook_json(mt_basename)
    except (WolvenKitError, FileNotFoundError):
        if verbosity > 0:
            print("[Head] could not uncook stock morphtarget")
        return None

    bm = mt_data.get("Data", {}).get("RootChunk", {}).get("baseMesh", {})
    bm_dp = bm.get("DepotPath", {})
    old_bm = bm_dp.get("$value", "")
    bm_dp["$value"] = baked_mesh_depot
    if verbosity > 0:
        print(f"[Head] morphtarget baseMesh: {old_bm} -> {baked_mesh_depot}")

    mt_json_fs = build_dir / (mt_depot.replace("\\", "/") + ".json")
    mt_json_fs.parent.mkdir(parents=True, exist_ok=True)
    mt_json_fs.write_text(json.dumps(mt_data, indent=2))

    if verbosity > 0:
        print(f"[Head] baked mesh: {baked_mesh_depot}")
        print(f"[Head] morphtarget: {mt_depot}")
    return True
