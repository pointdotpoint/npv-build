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

# Full canonical depot paths. The basename above is AMBIGUOUS in
# basegame_4_appearance.archive — it also matches a stale base\characters\head\{rig}\
# revision (7 materials, h0_001 textures, no _dXX). We must restore materials from
# the canonical player_base_heads mesh, otherwise the baked head gets the wrong
# (skin-mod-incompatible) material set. Keep STOCK_HEAD_MESH for file discovery.
STOCK_HEAD_MESH_DEPOT = {
    "pwa": "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa_c__basehead\\h0_000_pwa_c__basehead.mesh",
    "pma": "base\\characters\\head\\player_base_heads\\player_man_average\\h0_000_pma_c__basehead\\h0_000_pma_c__basehead.mesh",
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
    """Restore stock head-mesh materials into the baked head mesh."""
    canonical_depot = STOCK_HEAD_MESH_DEPOT.get(body_rig, STOCK_HEAD_MESH_DEPOT["pwa"])
    _restore_part_materials(wk, baked_mesh_fs, canonical_depot, verbosity)


def _restore_part_materials(
    wk: WolvenKit,
    baked_mesh_fs: Path,
    canonical_depot: str,
    verbosity: int,
) -> None:
    """Copy material data from the canonical stock part mesh into the baked mesh.

    The Blender import --keep step strips localMaterialBuffer, appearances,
    and materialEntries. We serialize both, patch, and deserialize. Works for any
    morph-baked part (head h0_, skin-detail heb_) given its full canonical depot.
    """
    canonical_rel = canonical_depot.replace("\\", "/")
    # Anchored regex on the FULL canonical depot path so we never pick up the
    # stale base\characters\head\{rig}\ revision that shares the basename.
    canonical_regex = _re.escape(canonical_depot) + r"$"

    # 1. Scan for custom skin/complexion mod archives that override the head mesh in the pc/mod folder
    game_dir = wk.config.game_dir
    mod_archive_path = None
    if game_dir:
        mod_dir = game_dir / "archive" / "pc" / "mod"
        if mod_dir.exists():
            mod_archives = sorted(mod_dir.glob("*.archive"))
            # Pre-filter mod archives by keyword to avoid sequentially scanning hundreds of unrelated mods
            candidates = []
            for arch in mod_archives:
                if arch.name.startswith("my_v_"):
                    continue
                low = arch.name.lower()
                # Exclude accessories and unrelated cosmetic categories
                if any(x in low for x in ("holo", "plugin", "mask", "horn", "ear", "wing", "acc_", "hair", "tattoo", "jacket", "outfit", "boots", "frame", "dealer", "pose", "props", "cyberarm", "armleft", "flat_feet")):
                    continue
                if any(k in low for k in ("head", "face", "skin", "complexion", "vtk", "body", "basehead", "h0_000")):
                    candidates.append(arch)

            # Prioritize high-probability matches (VTK head overrides) to check them first
            high_priority = []
            low_priority = []
            for arch in candidates:
                low = arch.name.lower()
                if ("vtk" in low and "head" in low) or "basehead" in low or "h0_000" in low:
                    high_priority.append(arch)
                else:
                    low_priority.append(arch)
            
            ordered_candidates = high_priority + low_priority

            for arch in ordered_candidates:
                try:
                    matches = wk.list_archive(canonical_regex, archive=arch)
                    if matches:
                        mod_archive_path = arch
                        if verbosity > 0:
                            print(f"[Head] Found custom head mesh override in mod archive: {arch.name}")
                        break
                except Exception:
                    pass


    # Use the custom skin mod archive if found, otherwise fall back to base-game
    source_archive = mod_archive_path or wk.config.appearance_archive
    if verbosity > 0:
        print(f"[Head] Restoring head materials from archive: {source_archive.name}")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        wk.unbundle(canonical_regex, archive=source_archive, dest=td_path)
        # Select the canonical file by its full relative depot path, not by
        # basename — the stale revision shares the basename and must not win.
        canonical_fs = td_path / canonical_rel
        if canonical_fs.exists():
            stock_files = [canonical_fs]
        else:
            # Hard-fail policy: restoring from the wrong/absent stock head would
            # silently produce a head with mismatched skin materials.
            raise WolvenKitError(
                f"Canonical stock head mesh not found after unbundle: "
                f"{canonical_depot} (from {source_archive.name})",
                operation="restore head materials",
            )

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
    from .blender_module import (
        bake_face_mesh, HEAD_MORPHTARGET, HEB_MORPHTARGET, HEB_FACE_MESH,
    )

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

    # Also bake the heb_ skin-detail layer with the SAME face morphs. It shares
    # h0_'s 105 morphs; baked separately so it deforms identically and stops
    # overlapping the morphed head (doubled jaw/mouth). Non-fatal if unavailable.
    heb_mt = HEB_MORPHTARGET.get(body_rig, "")
    heb_mesh = HEB_FACE_MESH.get(body_rig, "")
    if heb_mt and heb_mesh:
        heb_baked_depot = f"base\\npv-build\\{mod_id}\\{mod_id}_heb.mesh"
        heb_baked_fs = build_dir / heb_baked_depot.replace("\\", "/")
        heb_result = bake_face_mesh(
            wk.config.game_dir, body_rig, face_morphs, heb_baked_fs, verbosity, wk=wk,
            mt_depot=heb_mt, mesh_depot=heb_mesh, stage_name="bake_heb",
        )
        if heb_result:
            _restore_part_materials(wk, heb_baked_fs, heb_mesh, verbosity)
            if verbosity > 0:
                print(f"[Head] baked heb_ layer: {heb_baked_depot}")
        elif verbosity > 0:
            print("[Head] heb_ bake skipped/failed; head may show overlap")

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
