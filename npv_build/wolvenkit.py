"""Build the WolvenKit project: assemble components, inject into .app, pack.

Depends on:
  - wk_cli.WolvenKit adapter for all CLI operations
  - head_bake module for face morph baking
  - clothing module for garment resolution
  - config_editor for .app/.ent template authoring
  - project_writer for npv_components.json serialisation
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from .clothing import resolve_clothing
from .config_editor import _MESH_COMPONENT_TYPES
from .core.app_inject import InjectError
from .core.app_inject import inject_components as _py_inject_components
from .core.errors import NpvError, ToolError
from .core.proc import run_tool
from .head_bake import find_stock_head_part, prepare_head, verify_morphtarget
from .wk_cli import WolvenKit, WolvenKitError

logger = logging.getLogger(__name__)

INJECT_BINARY = "npv-inject"


def _resolve_inject_binary() -> str:
    if shutil.which(INJECT_BINARY):
        return INJECT_BINARY
    tools_dir = Path(__file__).parent.parent / "tools" / "npv-inject"
    for candidate in [
        tools_dir / "bin" / "Release" / "net8.0" / INJECT_BINARY,
        tools_dir / "bin" / "Debug" / "net8.0" / INJECT_BINARY,
    ]:
        if candidate.exists():
            return str(candidate)
    return INJECT_BINARY


def _inject_components(
    app_path: Path,
    components_json: Path,
    verbosity: int,
    donor_app: Path | None = None,
    face_rig: str | None = None,
    facial_setup: str | None = None,
    face_graph: str | None = None,
    hair_dangle_graph: str | None = None,
) -> None:
    binary = _resolve_inject_binary()
    cmd = [binary, str(app_path), str(components_json)]
    if donor_app:
        cmd.extend(["--donor", str(donor_app)])
    if face_rig:
        cmd.extend(["--face-rig", face_rig])
    if facial_setup:
        cmd.extend(["--facial-setup", facial_setup])
    if face_graph:
        cmd.extend(["--face-graph", face_graph])
    if hair_dangle_graph == "skip":
        cmd.append("--skip-donor-hair-dangle")
    if verbosity >= 1:
        cmd.append("--verbose")
    if verbosity >= 2:
        logger.debug(f"[npv-inject] $ {' '.join(cmd)}")

    stream = verbosity >= 2
    try:
        result = run_tool(cmd, tool="npv-inject", timeout=120.0, logger=logger)
    except ToolError as e:
        if e.exit_code is None:
            raise WolvenKitError(
                f"{INJECT_BINARY} not found. Build it with: dotnet build tools/npv-inject",
                operation="inject",
            ) from e
        tail = ""
        if not stream:
            tail = "\n" + (e.details or "")
        raise WolvenKitError(
            f"npv-inject failed (exit {e.exit_code}).{tail}",
            operation="inject",
            exit_code=e.exit_code,
        ) from e

    if stream:
        if result.stdout:
            logger.debug(result.stdout)
        if result.stderr:
            logger.debug(result.stderr)


def _use_py_inject() -> bool:
    """Opt-in flag for the pure-Python WolvenKit round-trip injector.

    Default stays the .NET npv-inject tool until the in-game gate passes
    (M5 Task 7 / Task 8). Set NPV_PY_INJECT=1 to route through
    core.app_inject.inject_components instead.
    """
    return os.environ.get("NPV_PY_INJECT") == "1"


def _do_inject_components(
    wk: WolvenKit,
    app_path: Path,
    components_json: Path,
    verbosity: int,
    donor_app: Path | None = None,
    face_rig: str | None = None,
    facial_setup: str | None = None,
    face_graph: str | None = None,
    hair_dangle_graph: str | None = None,
) -> None:
    """Route to the Python or .NET component injector.

    NPV_PY_INJECT=1 selects the pure-Python WolvenKit round-trip
    (core.app_inject.inject_components). Default is the .NET npv-inject
    tool (_inject_components below) — unchanged until Task 7's in-game
    gate passes.
    """
    if _use_py_inject():
        try:
            _py_inject_components(
                wk,
                app_path,
                components_json,
                donor_app=donor_app,
                face_rig=face_rig,
                facial_setup=facial_setup,
                face_graph=face_graph,
                hair_dangle_graph=hair_dangle_graph,
            )
        except InjectError as e:
            raise WolvenKitError(
                f"Python component injection failed: {e.user_message}",
                operation="inject",
            ) from e
        return

    _inject_components(
        app_path,
        components_json,
        verbosity,
        donor_app=donor_app,
        face_rig=face_rig,
        facial_setup=facial_setup,
        face_graph=face_graph,
        hair_dangle_graph=hair_dangle_graph,
    )


def _resolve_morphtarget_to_mesh(
    wk: WolvenKit,
    morphtarget_depot: str,
    morph_json: dict[str, dict] | None = None,
) -> str:
    basename = morphtarget_depot.replace("\\", "/").rsplit("/", 1)[-1]
    mt_data = (morph_json or {}).get(basename)
    if mt_data is None:
        try:
            mt_data = wk.uncook_json(basename)
        except (WolvenKitError, FileNotFoundError):
            return ""
    return (
        mt_data.get("Data", {})
        .get("RootChunk", {})
        .get("baseMesh", {})
        .get("DepotPath", {})
        .get("$value", "")
    )


def _extract_part_components(
    wk: WolvenKit,
    part_ent_depot: str,
    verbosity: int,
    *,
    entity_json: dict[str, dict] | None = None,
    morph_json: dict[str, dict] | None = None,
) -> list[dict]:
    basename = part_ent_depot.replace("\\", "/").rsplit("/", 1)[-1]
    data = (entity_json or {}).get(basename)
    if data is None:
        try:
            data = wk.uncook_json(basename)
        except (WolvenKitError, FileNotFoundError):
            return []

    chunks = (
        data.get("Data", {})
        .get("RootChunk", {})
        .get("compiledData", {})
        .get("Data", {})
        .get("Chunks", [])
    )
    if not chunks:
        chunks = data.get("Data", {}).get("RootChunk", {}).get("components", [])

    result = []
    for c in chunks:
        ctype = c.get("$type", "")
        if ctype not in _MESH_COMPONENT_TYPES:
            continue
        name = c.get("name", {}).get("$value", "") if isinstance(c.get("name"), dict) else ""
        mesh = c.get("mesh", {}).get("DepotPath", {}).get("$value", "") if c.get("mesh") else ""
        ma = (
            c.get("meshAppearance", {}).get("$value", "default")
            if c.get("meshAppearance")
            else "default"
        )

        morph_resource = ""
        if ctype == "entMorphTargetSkinnedMeshComponent":
            mr = (
                c.get("morphResource", {}).get("DepotPath", {}).get("$value", "")
                if c.get("morphResource")
                else ""
            )
            if mr and not mesh:
                mesh = _resolve_morphtarget_to_mesh(wk, mr, morph_json)
            if not mesh:
                continue
            # Demoted to the neutral base mesh (baked-head design), but keep
            # the morphtarget path so eye components can be promoted back for
            # blink support (_split_stock_eye_for_glow).
            ctype = "entSkinnedMeshComponent"
            morph_resource = mr
        elif not mesh:
            continue

        entry = {
            "comp_type": ctype,
            "name": name,
            "mesh": mesh,
            "appearance": ma,
        }
        if morph_resource:
            entry["morph_resource"] = morph_resource
        if c.get("chunkMask"):
            entry["chunk_mask"] = str(c["chunkMask"])
        result.append(entry)
    return result


def _load_vanilla_hair_components(
    wk: WolvenKit,
    hair_ent_depot: str,
    *,
    entity_json: dict[str, dict] | None = None,
) -> list[dict]:
    """Uncook a vanilla hh_ part .ent and return its RAW chunks, in the same
    shape extract_hair_components yields for modded hair, so the hair section
    of build_project applies colour + dangle binding identically."""
    basename = hair_ent_depot.replace("\\", "/").rsplit("/", 1)[-1]
    data = (entity_json or {}).get(basename)
    if data is None:
        try:
            data = wk.uncook_json(basename)
        except (WolvenKitError, FileNotFoundError) as e:
            logger.warning(f"vanilla hair extraction failed ({e}); NPV will be bald.")
            return []
    rc = data.get("Data", {}).get("RootChunk", {})
    chunks = rc.get("compiledData", {}).get("Data", {}).get("Chunks", [])
    if not chunks:
        chunks = rc.get("components", [])
    return chunks


def _collect_prefetch_entity_depots(
    asset_paths: dict,
    stock_head_depot: str | None,
) -> set[str]:
    depots: set[str] = set()
    if stock_head_depot and stock_head_depot.lower().endswith(".ent"):
        depots.add(stock_head_depot)
    vanilla_hair = asset_paths.get("vanilla_hair_ent", "")
    if vanilla_hair and vanilla_hair.lower().endswith(".ent"):
        depots.add(vanilla_hair)
    for part in asset_paths.get("part_entities", []):
        if isinstance(part, str) and part.lower().endswith(".ent"):
            depots.add(part)
    for recipe_part in asset_paths.get("recipe_parts", []):
        depot = recipe_part.get("resource", {}).get("DepotPath", {}).get("$value", "")
        if depot and depot.lower().endswith(".ent"):
            depots.add(depot)
    return depots


def _component_chunks(data: dict) -> list[dict]:
    root = data.get("Data", {}).get("RootChunk", {})
    chunks = root.get("compiledData", {}).get("Data", {}).get("Chunks", [])
    return chunks or root.get("components", [])


def _prefetch_component_json(
    wk: WolvenKit,
    entity_depots: list[str] | set[str],
) -> tuple[dict[str, dict], dict[str, dict]]:
    if not hasattr(wk, "uncook_json_many"):
        return {}, {}
    entity_names = sorted(
        {
            depot.replace("\\", "/").rsplit("/", 1)[-1]
            for depot in entity_depots
            if depot.lower().endswith(".ent")
        }
    )
    if not entity_names:
        return {}, {}
    try:
        entity_json = wk.uncook_json_many(entity_names)
    except FileNotFoundError as error:
        entity_json = getattr(error, "results", {})

    morph_names: set[str] = set()
    for data in entity_json.values():
        for component in _component_chunks(data):
            morph_depot = component.get("morphResource", {}).get("DepotPath", {}).get("$value", "")
            if morph_depot:
                morph_names.add(morph_depot.replace("\\", "/").rsplit("/", 1)[-1])
    if not morph_names:
        return entity_json, {}
    try:
        morph_json = wk.uncook_json_many(sorted(morph_names))
    except FileNotFoundError as error:
        morph_json = getattr(error, "results", {})
    return entity_json, morph_json


def _resolve_garment_mesh(wk: WolvenKit, game_dir, name: str, verbosity: int) -> str:
    """Resolve an equipped garment component name to its .mesh depot path.

    The CET dump gives the garment component NAME (which equals the mesh basename,
    e.g. "t1_1g1_bswghfem_bodysuitsweater_01") but not a usable depot path — CET
    exposes the mesh only as a hash. We locate the real path by exact-basename
    search across the user's pc/mod archives first (modded garments), then the
    base-game appearance archive (vanilla garments). Component names include the
    rig token (pwa/pma) so the basename match is unambiguous across rig variants.

    Returns the depot path, or "" if not found.
    """
    import re as _re

    regex = r"\\" + _re.escape(name) + r"\.mesh$"

    # 1. pc/mod archives (modded garments). Match base game's mod scan style.
    if game_dir:
        mod_dir = game_dir / "archive" / "pc" / "mod"
        if mod_dir.exists():
            for arch in sorted(mod_dir.glob("*.archive")):
                if arch.name.startswith("my_v_") or arch.name == "archive.archive":
                    continue
                try:
                    matches = wk.list_archive(regex, archive=arch)
                except WolvenKitError:
                    matches = []
                if matches:
                    if len(matches) > 1:
                        logger.info(
                            f"[Clothing] '{name}': {len(matches)} matches in "
                            f"{arch.name}, using first: {matches[0]}"
                        )
                    return matches[0]

    # 2. base-game appearance archive (vanilla garments).
    try:
        matches = wk.list_archive(regex)  # defaults to appearance_archive
    except WolvenKitError:
        matches = []
    if matches:
        return matches[0]

    logger.warning(f"[Clothing] no mesh found for equipped garment '{name}'")
    return ""


def _resolve_equipped_clothing_meshes(
    wk: WolvenKit, game_dir, equipped: list, verbosity: int
) -> list:
    """Return a copy of the equipped-clothing list with each item's `mesh` set to a
    resolved depot path (by component name). Items whose mesh can't be resolved are
    dropped (they would otherwise inject an invalid/hashed mesh). The CET-supplied
    `mesh` (a hash like "hash:123ULL") is never trusted — always re-resolve by name.
    """
    if not equipped:
        return equipped or []
    resolved = []
    for item in equipped:
        name = item.get("name", "")
        if not name:
            continue
        mesh = item.get("mesh", "") or ""
        # Trust only a real depot path (contains a backslash and ends in .mesh).
        if not (mesh.lower().endswith(".mesh") and "\\" in mesh):
            mesh = _resolve_garment_mesh(wk, game_dir, name, verbosity)
        if not mesh:
            continue
        new_item = dict(item)
        new_item["mesh"] = mesh
        resolved.append(new_item)
        logger.info(
            f"[Clothing] resolved {item.get('slot') or '?'}: {name} -> "
            f"{mesh.rsplit(chr(92), 1)[-1]}"
        )
    return resolved


def _has_modded_ccxl_eyes(cc_selections: list[dict]) -> bool:
    """True if CC selections request modded CCXL eyes (e.g. Sedth 3D Eyes).

    When modded eyes are injected they REPLACE the stock he_ eye part; the stock
    eye must be suppressed or both irises render overlapping (doubled eyes).
    """
    for s in cc_selections or []:
        if s.get("slot") != "character_customization":
            continue
        lbl = s.get("label", "")
        raw = s.get("raw", "")
        if "_eyes_" in lbl and lbl not in ("eyes_color",) and raw and raw != "default":
            return True
    return False


def _ccxl_eye_components_from_app(
    app_data: dict,
    appearance_name: str,
    comp_name: str,
    mt_cache: dict[str, str],
    source: str,
) -> list[dict]:
    """Parse one CCXL eye .app: components of the named appearance -> specs.

    Carries the component's chunkMask — mod eye meshes bundle extra chunks
    (e.g. a built-in eyeball under a glow overlay) that the mask hides;
    rendering all chunks doubles the eyeball. An appearance name that doesn't
    exist in the .app (e.g. Sedth's w_cyber_00 = option off) yields [].
    """
    appearances = app_data.get("Data", {}).get("RootChunk", {}).get("appearances", [])
    components: list[dict] = []
    for a in appearances:
        name = a.get("Data", {}).get("name", {}).get("$value", "")
        if name != appearance_name:
            continue
        for c in a.get("Data", {}).get("components", []):
            ma = (
                c.get("meshAppearance", {}).get("$value", "default")
                if c.get("meshAppearance")
                else "default"
            )
            mesh = ""
            if c.get("mesh"):
                mesh = c["mesh"].get("DepotPath", {}).get("$value", "")
            mr = ""
            if c.get("morphResource"):
                mr = c["morphResource"].get("DepotPath", {}).get("$value", "")
            if not mesh and mr:
                mesh = mt_cache.get(mr, "")
            if not mesh:
                continue
            entry = {
                # Keep morph components as morph components: the morphtarget
                # carries blink correctives — a plain skinned mesh stays in
                # open-eye shape and pokes through closed eyelids.
                "comp_type": "entMorphTargetSkinnedMeshComponent"
                if mr
                else "entSkinnedMeshComponent",
                "name": comp_name,
                "mesh": mesh,
                "appearance": ma,
                "source": source,
            }
            if mr:
                entry["morph_resource"] = mr
            if c.get("chunkMask"):
                entry["chunk_mask"] = str(c["chunkMask"])
            components.append(entry)
        break
    return components


def _extract_ccxl_eye_components(
    game_dir: Path,
    cc_selections: list[dict],
    body_rig: str,
    verbosity: int,
) -> tuple[list[dict], bool]:
    """Extract modded CCXL eye components (e.g. Sedth 3D Eyes) from mod archives.

    Detects CC labels matching *_eyes_r, *_eyes_l, *_eyes_r_glow, *_eyes_l_glow
    and resolves them to mesh components via the mod's .app files.

    Returns (components, iris_replaced). iris_replaced is True only when a
    BASE (non-glow) eye selection actually produced components — a glow-only
    overlay does not replace the stock iris (e.g. Sedth base option
    w_cyber_00 = off, glow w_cyber_63 = on: the iris still comes from the
    stock he_ component on the mod's replacer mesh).
    """
    eye_labels = {}
    for s in cc_selections:
        if s.get("slot") != "character_customization":
            continue
        lbl = s.get("label", "")
        raw = s.get("raw", "")
        if "_eyes_" in lbl and lbl not in ("eyes_color",) and raw and raw != "default":
            eye_labels[lbl] = raw

    if not eye_labels:
        return [], False

    suffix_to_app = {
        "_r": "eyes_r",
        "_l": "eyes_l",
        "_r_glow": "eyes_r_glow",
        "_l_glow": "eyes_l_glow",
    }
    label_to_app = {}
    for lbl in eye_labels:
        for suffix, app_stem in suffix_to_app.items():
            if lbl.endswith(suffix):
                label_to_app[lbl] = app_stem + ".app"
                break

    if not label_to_app:
        return [], False

    mod_dir = game_dir / "archive" / "pc" / "mod"
    if not mod_dir.exists():
        return [], False

    # Find the archive containing these .app files by scanning .xl manifests
    # or checking archive contents. Use the first label's prefix as the mod name hint.
    first_label = next(iter(label_to_app))
    mod_prefix = first_label.rsplit("_eyes_", 1)[0]

    target_archive = None
    for xl_file in mod_dir.glob("*.xl"):
        try:
            content = xl_file.read_text(errors="replace")
            if mod_prefix in content.lower() and "eyes" in content.lower():
                archive_candidate = xl_file.with_suffix(".archive")
                if archive_candidate.exists():
                    target_archive = archive_candidate
                    break
        except OSError:
            continue

    if not target_archive:
        logger.info(f"[Eyes] modded eyes '{mod_prefix}' archive not found")
        return [], False

    logger.info(f"[Eyes] modded eyes from {target_archive.name}")

    components = []
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        app_names = set(label_to_app.values())
        alt = "|".join(re.escape(a) for a in app_names)
        regex = f"({alt})$"

        cmd = [
            "WolvenKit.CLI",
            "uncook",
            "-p",
            str(target_archive),
            "-r",
            regex,
            "-o",
            str(td_path),
            "-s",
        ]
        try:
            run_tool(cmd, tool="WolvenKit.CLI", timeout=600.0, logger=logger)
        except ToolError as e:
            raise WolvenKitError(
                f"Failed to uncook garment meshes from {target_archive.name}: {e.user_message}",
                operation="uncook",
                exit_code=e.exit_code if e.exit_code is not None else -1,
            ) from e

        # Also uncook morphtargets to resolve meshes
        run_tool(
            [
                "WolvenKit.CLI",
                "uncook",
                "-p",
                str(target_archive),
                "-r",
                r"\.morphtarget$",
                "-o",
                str(td_path),
                "-s",
            ],
            tool="WolvenKit.CLI",
            timeout=600.0,
            logger=logger,
        )

        mt_cache = {}
        for mt_json in td_path.rglob("*.morphtarget.json"):
            data = json.loads(mt_json.read_text())
            base_mesh = (
                data.get("Data", {})
                .get("RootChunk", {})
                .get("baseMesh", {})
                .get("DepotPath", {})
                .get("$value", "")
            )
            mt_depot = str(mt_json.relative_to(td_path)).replace("/", "\\").replace(".json", "")
            mt_cache[mt_depot] = base_mesh

        iris_replaced = False
        for lbl, app_file in label_to_app.items():
            appearance_name = eye_labels.get(lbl, "")
            if not appearance_name:
                continue

            app_jsons = list(td_path.rglob(app_file + ".json"))
            if not app_jsons:
                continue

            data = json.loads(app_jsons[0].read_text())
            comp_name = lbl.replace("_glow", "_g")
            comps = _ccxl_eye_components_from_app(
                data, appearance_name, comp_name, mt_cache, f"modded eyes ({mod_prefix})"
            )
            for c in comps:
                logger.info(
                    f"[Eyes]   {c['name']}: {c['mesh'].rsplit(chr(92), 1)[-1]} -> {c['appearance']}"
                )
            if comps and not lbl.endswith("_glow"):
                iris_replaced = True
            components.extend(comps)

    return components, iris_replaced


def _stock_eye_recipe_overrides(recipe_overrides: list[dict]) -> dict:
    """Collect the stock he_ eye part's iris and eyelash override rows.

    The player entity renders the he_ eye mesh via TWO component instances:
    an iris one (V's eye-color appearance, mask hiding the lash chunk) and a
    lash one (eyelashes__* appearance, mask hiding the iris chunks). Returns
    {iris_appearance, iris_chunk_mask, eyelash_appearance, eyelash_chunk_mask}
    ("" when a row is absent).
    """
    out = {
        "iris_appearance": "",
        "iris_chunk_mask": "",
        "eyelash_appearance": "",
        "eyelash_chunk_mask": "",
    }
    for ov in recipe_overrides:
        pr = ov.get("partResource", {}).get("DepotPath", {}).get("$value", "").lower()
        if "\\he_000_" not in pr and "/he_000_" not in pr:
            continue
        for co in ov.get("componentsOverrides", []):
            ma = co.get("meshAppearance", {}).get("$value", "")
            if not ma:
                continue
            mask = str(co.get("chunkMask") or "")
            if ma.startswith("eyelashes__"):
                if not out["eyelash_appearance"]:
                    out["eyelash_appearance"] = ma
                    out["eyelash_chunk_mask"] = mask
            elif not out["iris_appearance"]:
                out["iris_appearance"] = ma
                out["iris_chunk_mask"] = mask
    return out


def _split_stock_eye_for_glow(comps: list[dict], eye_ov: dict) -> list[dict]:
    """Split extracted stock-eye components into iris + lashes instances.

    Used when modded eyes are a glow-only OVERLAY (base option off): the stock
    he_ component must render both the iris (on the possibly mod-replaced
    mesh) and the lashes, each with its recipe mask — mirroring the player
    entity. Renamed with _iris/_lashes suffixes so the generic override_map
    (keyed by the original component name) doesn't clobber them.
    """
    out = []
    for c in comps:
        # Promote back to a morph component when the source was one: blink
        # correctives live in the morphtarget.
        if c.get("morph_resource"):
            c = dict(c)
            c["comp_type"] = "entMorphTargetSkinnedMeshComponent"
        iris = dict(c)
        iris["name"] = c["name"] + "_iris"
        if eye_ov.get("iris_appearance"):
            iris["appearance"] = eye_ov["iris_appearance"]
        if eye_ov.get("iris_chunk_mask"):
            iris["chunk_mask"] = eye_ov["iris_chunk_mask"]
        out.append(iris)

        if eye_ov.get("eyelash_appearance"):
            lashes = dict(c)
            lashes["name"] = c["name"] + "_lashes"
            lashes["appearance"] = eye_ov["eyelash_appearance"]
            if eye_ov.get("eyelash_chunk_mask"):
                lashes["chunk_mask"] = eye_ov["eyelash_chunk_mask"]
            out.append(lashes)
    return out


def _apply_body_tattoo(component_specs: list[dict], body_tattoo: dict | None) -> None:
    """Apply the save's body-tattoo appearance to the tx_ overlay component.

    The tx_ part .ent carries meshAppearance 'default'; the actual appearance
    is the save selection's raw value (skin-tone-keyed, e.g. w__01_ca_pale).
    """
    if not body_tattoo or not body_tattoo.get("appearance"):
        return
    for comp in component_specs:
        name = comp.get("name", "")
        if name.startswith("tx_") and "tattoo" in name:
            comp["appearance"] = body_tattoo["appearance"]
            logger.info(f"[Project] Body tattoo: {name} -> {body_tattoo['appearance']}")


def _apply_nail_color(component_specs: list[dict], nail_color: str) -> None:
    """Apply the selected mesh appearance to both curated arm nail meshes."""
    if not nail_color:
        return
    for comp in component_specs:
        name = comp.get("name", "")
        if name.endswith(("__nails_l", "__nails_r")):
            comp["appearance"] = nail_color
            logger.info(f"[Project] Nail color: {name} -> {nail_color}")


def _filter_genital_components(component_specs: list[dict], genital_selection: str) -> list[dict]:
    """Keep only the detachable genital meshes selected by character creation.

    The female base-body mesh supplies the default anatomy. ``genitals_none``
    therefore means that all detachable genital meshes must be removed.
    Inspect both component names and depot paths so renamed components cannot
    bypass the filter.
    """
    selection = genital_selection.lower()

    def identity(component: dict) -> str:
        return f"{component.get('name', '')} {component.get('mesh', '')}".lower()

    if "genitals_none" in selection:
        return [
            component
            for component in component_specs
            if "penis" not in identity(component) and "vagina" not in identity(component)
        ]

    if "vagina" in selection:
        return [component for component in component_specs if "penis" not in identity(component)]

    if "penis" in selection:
        is_circumcised = "circumcised" in selection
        filtered = []
        for component in component_specs:
            component_id = identity(component)
            if "vagina" in component_id:
                continue
            if is_circumcised and component.get("name", "").lower() == "i0_000_pwa_base__penis":
                continue
            if not is_circumcised and "circumcised" in component_id:
                continue
            filtered.append(component)
        return filtered

    return list(component_specs)


def _bake_lips_overlays(
    wk: WolvenKit,
    game_dir: Path,
    source_dir: Path,
    mod_id: str,
    body_rig: str,
    face_morphs: dict,
    component_specs: list[dict],
    verbosity: int,
) -> None:
    """Bake the makeup-lips overlay with V's face morphs and repoint it.

    The overlay is a stock unmorphed mesh; over the morph-baked head it
    renders a second pair of lips. Same design as the heb_ skin-detail layer:
    bake with the part's own morphtarget (shares the head's morph channels),
    restore materials, repoint the component. Stays a skinned mesh so it
    animates with the same face_rig bones as the baked head. Non-fatal: on
    bake failure the stock overlay is kept.
    """
    from . import blender_module, head_bake

    for comp in component_specs:
        if "makeup_lips" not in comp.get("name", "") or not comp.get("morph_resource"):
            continue
        stock_mesh = comp.get("mesh", "")
        lips_depot = f"base\\npv-build\\{mod_id}\\{mod_id}_lips.mesh"
        lips_fs = source_dir / lips_depot.replace("\\", "/")
        try:
            ok = blender_module.bake_face_mesh(
                game_dir,
                body_rig,
                face_morphs,
                lips_fs,
                verbosity,
                wk=wk,
                mt_depot=comp["morph_resource"],
                mesh_depot=stock_mesh,
                stage_name="bake_lips",
            )
            if ok:
                head_bake._restore_part_materials(wk, lips_fs, stock_mesh, verbosity)
        except (NpvError, OSError) as e:
            logger.warning(f"[Lips] overlay bake failed ({e}); keeping stock lips overlay")
            continue
        if ok:
            comp["mesh"] = lips_depot
            comp["source"] = "baked lips overlay (face morphs applied)"
            logger.info(f"[Lips] baked makeup lips overlay -> {lips_depot}")
        else:
            logger.warning("[Lips] overlay bake returned nothing; keeping stock lips overlay")


def _apply_recipe_overrides(
    components: list[dict], recipe_overrides: list[dict], modded_eyes: bool = False
) -> list[dict]:
    """Process recipe material overrides. Modifies head component overrides
    to also target our baked head component name. Returns the fully prepared
    partsOverrides list to be written to the .app file.

    modded_eyes: when True, the stock eye component renders ONLY eyelashes (the
    modded eyes supply the iris). The eyelash override is then KEPT (and the iris
    override on that same component dropped); otherwise the eyelash override is
    skipped so it doesn't clobber the iris color on the stock eye.
    """
    import copy

    # he_ eye part is the stock eye; its overrides land on a MorphTargetSkinnedMesh
    # component from a face_decals/he_ partResource.
    def _is_stock_eye(pr_lower: str) -> bool:
        return "\\he_000_" in pr_lower or "/he_000_" in pr_lower

    # 1. First, build the direct override_map for components where we can set
    # appearance (and the recipe's chunkMask, when present) directly
    override_map = {}
    for ov in recipe_overrides:
        pr = ov.get("partResource", {}).get("DepotPath", {}).get("$value", "").lower()
        is_head_part = (
            "appearances\\entity\\head\\h0_" in pr
            or "appearances/entity/head/h0_" in pr.replace("\\", "/")
        )
        is_stock_eye = _is_stock_eye(pr)

        for co in ov.get("componentsOverrides", []):
            cn = co.get("componentName", {}).get("$value", "")
            ma = co.get("meshAppearance", {}).get("$value", "")
            mask = co.get("chunkMask")
            if cn and ma:
                if ma.startswith("eyelashes__"):
                    # With modded eyes the stock eye renders lashes only -> keep
                    # the eyelash override. Without modded eyes it would clobber
                    # the iris color on the shared eye component -> skip it.
                    if not modded_eyes:
                        continue
                elif modded_eyes and is_stock_eye:
                    # Drop the iris/eye-color override on the stock eye when modded
                    # eyes supply the iris; the stock eye is eyelashes-only.
                    continue

                # Alias stock head component overrides to our baked basehead component name
                if is_head_part and cn.startswith("MorphTargetSkinnedMesh"):
                    head_comp_names = [
                        comp["name"] for comp in components if comp["name"].endswith("_basehead")
                    ]
                    for hname in head_comp_names:
                        override_map[hname] = (ma, mask)

                override_map[cn] = (ma, mask)

    # Apply direct appearances (and masks) to inlined components. The .app's
    # partsOverrides don't reach inlined components at runtime (no partsValues),
    # so the mask must live on the component itself.
    for comp in components:
        name = comp.get("name", "")
        if name in override_map:
            ma, mask = override_map[name]
            comp["appearance"] = ma
            if mask:
                comp["chunk_mask"] = str(mask)

    # 2. Prepare the partsOverrides list for the .app file.
    # We must preserve the original partResource paths and component overrides structure,
    # but we will inject the baked head component aliases for any head MorphTargetSkinnedMesh overrides.
    app_parts_overrides = []

    for ov in recipe_overrides:
        # Clone the override block to avoid modifying the original parsed asset_paths in-place
        ov_clone = copy.deepcopy(ov)
        pr = ov_clone.get("partResource", {}).get("DepotPath", {}).get("$value", "").lower()
        is_head_part = (
            "appearances\\entity\\head\\h0_" in pr
            or "appearances/entity/head/h0_" in pr.replace("\\", "/")
        )
        is_stock_eye = _is_stock_eye(pr)

        # Collapse duplicate overrides targeting the SAME component to the LAST
        # one. The CC recipe often lists a base makeup layer (e.g. yellow_01,
        # black_01) followed by V's chosen color (burgundy_19, black_31); emitting
        # both as partsOverrides stacks two decals on one mesh -> doubled lips /
        # doubled eye makeup in-game. Last wins, matching override_map above.
        # The stock eye carries BOTH an iris (double_eye_*) and an eyelashes__*
        # override on one component; keep the right one (lashes if modded eyes
        # supply the iris, else iris) so we don't stack iris+lashes or lose either.
        deduped_cos = {}
        for co in ov_clone.get("componentsOverrides", []):
            cn = co.get("componentName", {}).get("$value", "")
            ma = co.get("meshAppearance", {}).get("$value", "")
            if ma.startswith("eyelashes__"):
                if not modded_eyes:
                    continue
            elif modded_eyes and is_stock_eye:
                continue
            deduped_cos[cn] = co  # later entries overwrite earlier ones

        new_cos = []
        for co in deduped_cos.values():
            new_cos.append(co)
            cn = co.get("componentName", {}).get("$value", "")

            # If it's a head part override targeting the stock MorphTargetSkinnedMesh,
            # duplicate it targeting our morph-baked custom head component name(s)
            if is_head_part and cn and cn.startswith("MorphTargetSkinnedMesh"):
                head_comp_names = [
                    comp["name"] for comp in components if comp["name"].endswith("_basehead")
                ]
                for hname in head_comp_names:
                    co_dup = copy.deepcopy(co)
                    if isinstance(co_dup.get("componentName"), dict):
                        co_dup["componentName"]["$value"] = hname
                    else:
                        co_dup["componentName"] = hname
                    new_cos.append(co_dup)

        ov_clone["componentsOverrides"] = new_cos
        app_parts_overrides.append(ov_clone)

    return app_parts_overrides


def build_project(
    wk: WolvenKit,
    mod_id: str,
    out_dir: Path,
    asset_paths: dict,
    verbosity: int,
    garment_overrides: list[str] | None = None,
    skin_override: str | None = None,
    user_head_glb: Path | None = None,
    user_head_mesh: Path | None = None,
    user_heb_mesh: Path | None = None,
    restore_head_materials: bool = True,
    npv_name: str | None = None,
    photomode_thumbnail=None,
    artifact_cache=None,
) -> list[dict]:
    """Build the full mod: assemble components, inject into .app, pack .archive.

    Returns component spec list for diagnostics.
    """
    from .config_editor import NPC_BASE_ENT, build_app_template, build_ent_from_donor

    source_dir = out_dir / "source" / "archive"
    if source_dir.exists():
        shutil.rmtree(source_dir)
    source_dir.mkdir(parents=True, exist_ok=True)

    game_dir = wk.config.game_dir
    if not game_dir:
        raise WolvenKitError("game_dir required", operation="build_project")

    component_specs: list[dict] = []

    stock_head_depot = find_stock_head_part(asset_paths)
    vanilla_hair_ent = asset_paths.get("vanilla_hair_ent", "")
    prefetch_depots = _collect_prefetch_entity_depots(asset_paths, stock_head_depot)
    prefetched_entities, prefetched_morphs = _prefetch_component_json(wk, prefetch_depots)
    all_part_depots = set(prefetch_depots)
    if stock_head_depot:
        all_part_depots.discard(stock_head_depot)
    if vanilla_hair_ent:
        all_part_depots.discard(vanilla_hair_ent)

    # 0. Resolve skin tone early — prefer explicit --skin override, fall back to save's tone
    if skin_override:
        skin_tone = skin_override
    else:
        head_app_name = asset_paths.get("head_appearance_name", "")
        skin_tone = ""
        if "__" in head_app_name:
            skin_tone = head_app_name.rsplit("__", 1)[-1]
    if not skin_tone:
        skin_tone = "01_ca_pale"

    # 1. HEAD — baked or stock
    face_morphs = asset_paths.get("face_morphs", {})
    body_rig = asset_paths.get("body_rig", "pwa")
    baked_mesh_depot = None
    override = user_head_glb or user_head_mesh

    if (face_morphs or override) and game_dir:
        try:
            result = prepare_head(
                wk,
                mod_id,
                source_dir,
                body_rig,
                face_morphs,
                verbosity,
                user_glb=user_head_glb,
                user_mesh=user_head_mesh,
                user_heb_mesh=user_heb_mesh,
                restore_materials=restore_head_materials,
            )
            if result:
                baked_mesh_depot = f"base\\npv-build\\{mod_id}\\{mod_id}_head.mesh"
        except (NpvError, OSError) as e:
            logger.info(f"[Head] head preparation failed ({e}); using stock head.")

    if baked_mesh_depot:
        if user_head_glb:
            source_label = "user head GLB (imported)"
        elif user_head_mesh:
            source_label = "user head mesh (verbatim)"
        else:
            source_label = "baked head (face morphs applied)"

        component_specs.append(
            {
                "comp_type": "entSkinnedMeshComponent",
                "name": f"h0_000_{body_rig}_c__basehead",
                "mesh": baked_mesh_depot,
                "appearance": skin_tone,
                "source": source_label,
            }
        )
        logger.info(f"[Head] baked head component: h0_000_{body_rig}_c__basehead")

        # Auto-inject VTK seamfix and headpatch if VTK is installed in the game mods directory
        has_vtk = False
        if game_dir:
            mod_dir = game_dir / "archive" / "pc" / "mod"
            if mod_dir.exists():
                for arch in mod_dir.glob("*.archive"):
                    if "vtk" in arch.name.lower():
                        has_vtk = True
                        break

        if has_vtk:
            seamfix_mesh = (
                "base\\vtk\\femv_seamfix.mesh"
                if body_rig == "pwa"
                else "base\\vtk\\mase_seamfix.mesh"
            )
            headpatch_mesh = (
                "base\\vtk\\femv_vtk_headpatch.mesh"
                if body_rig == "pwa"
                else "base\\vtk\\mase_vtk_headpatch.mesh"
            )

            component_specs.append(
                {
                    "comp_type": "entSkinnedMeshComponent",
                    "name": "femv_vtk_headpatch",
                    "mesh": headpatch_mesh,
                    "appearance": skin_tone,
                    "bind_to": "root",
                    "source": "VTK headpatch (auto-injected)",
                }
            )
            component_specs.append(
                {
                    "comp_type": "entSkinnedMeshComponent",
                    "name": "femv_seamfix",
                    "mesh": seamfix_mesh,
                    "appearance": skin_tone,
                    "bind_to": "root",
                    "source": "VTK seamfix (auto-injected)",
                }
            )
            logger.info(f"[Head] Auto-injected VTK headpatch and seamfix for rig {body_rig}")
    elif stock_head_depot:
        use_morph_fallback = bool(face_morphs)
        comps = _extract_part_components(
            wk,
            stock_head_depot,
            verbosity,
            entity_json=prefetched_entities,
            morph_json=prefetched_morphs,
        )
        if use_morph_fallback:
            from .blender_module import HEAD_FACE_MESH, HEAD_MORPHTARGET

            stock_mesh = HEAD_FACE_MESH.get(body_rig, "")
            stock_mt = HEAD_MORPHTARGET.get(body_rig, "")
            for c in comps:
                cname = c.get("name", "")
                if cname.startswith("h0_000_") and cname.endswith("_basehead"):
                    c["comp_type"] = "entMorphTargetSkinnedMeshComponent"
                    c["mesh"] = stock_mesh
                    c["graph"] = stock_mt  # Reused by C# injector for MorphResource
                    c["source"] = "stock morph target head (programmatic fallback)"
                    logger.info(
                        f"[Head] Programmatic morph fallback: {cname} using morphtarget {stock_mt}"
                    )
                else:
                    c["source"] = "stock head"
        else:
            for c in comps:
                c["source"] = "stock head"
        component_specs.extend(comps)
        logger.info(
            f"[Head] stock head: {len(comps)} component(s) (morph_fallback={use_morph_fallback})"
        )

    # Load CC selections once — used to suppress the stock eye when modded eyes
    # are present (below) and to inject the modded eyes themselves (section 2d).
    cc_settings_data = {}
    cc_file = out_dir / "cc_settings.json"
    if cc_file.exists():
        cc_settings_data = json.loads(cc_file.read_text())
    cc_selections = cc_settings_data.get("selections", [])

    # Extract modded CCXL eye components up front (injected in section 2d).
    # modded_eyes is True only when the mod actually supplies a replacement
    # IRIS (base selection produced components). A glow-only overlay (base
    # option off, e.g. Sedth w_cyber_00) leaves the iris on the stock he_
    # component — suppressing it would leave a bare glow ring.
    ccxl_eye_comps: list[dict] = []
    modded_eyes = False
    if game_dir and cc_selections and _has_modded_ccxl_eyes(cc_selections):
        ccxl_eye_comps, modded_eyes = _extract_ccxl_eye_components(
            game_dir, cc_selections, body_rig, verbosity
        )
    ccxl_glow_only = bool(ccxl_eye_comps) and not modded_eyes

    # The player entity renders the stock he_ eye mesh via two component
    # instances — iris (eye-color appearance) and lashes (eyelashes__*) —
    # each with a chunkMask hiding the other's chunks.
    eye_ov = _stock_eye_recipe_overrides(asset_paths.get("recipe_overrides", []))
    eyelash_appearance = eye_ov["eyelash_appearance"]
    eyelash_chunk_mask = eye_ov["eyelash_chunk_mask"]

    # 2. Other part-ents (eyes, teeth, body, etc.)
    for dp in sorted(all_part_depots):
        if dp == stock_head_depot:
            continue
        comps = _extract_part_components(
            wk,
            dp,
            verbosity,
            entity_json=prefetched_entities,
            morph_json=prefetched_morphs,
        )
        # Modded CCXL eyes (Sedth) replace the stock he_ IRIS, but the stock eye
        # part also carries the eyelashes. Keep he_ rendering only the lashes
        # (eyelash appearance) instead of dropping it — else lashes disappear and
        # the iris would otherwise double up with the modded eyes.
        if modded_eyes and "\\he_000_" in dp:
            if eyelash_appearance:
                for c in comps:
                    c["appearance"] = eyelash_appearance
                    if eyelash_chunk_mask:
                        c["chunk_mask"] = eyelash_chunk_mask
                    c["source"] = dp.replace("\\", "/").rsplit("/", 1)[-1] + " (eyelashes only)"
                logger.info(
                    f"[Eyes] stock eye -> eyelashes only ({eyelash_appearance}); iris from modded eyes"
                )
                component_specs.extend(comps)
            else:
                logger.info(
                    f"[Eyes] skipping stock eye part {dp.rsplit(chr(92), 1)[-1]} (modded eyes, no eyelash appearance found)"
                )
            continue
        if ccxl_glow_only and "\\he_000_" in dp:
            split = _split_stock_eye_for_glow(comps, eye_ov)
            for c in split:
                c["source"] = dp.replace("\\", "/").rsplit("/", 1)[-1] + " (iris/lashes split)"
            logger.info(
                f"[Eyes] glow-only modded eyes: stock eye split into iris "
                f"({eye_ov['iris_appearance'] or 'extracted'}) + lashes "
                f"({eyelash_appearance or 'none'})"
            )
            component_specs.extend(split)
            continue
        for c in comps:
            c["source"] = dp.replace("\\", "/").rsplit("/", 1)[-1]
        if comps:
            short = dp.rsplit("\\", 1)[-1]
            logger.info(f"[Project]   {short}: {len(comps)} component(s)")
        component_specs.extend(comps)

    # 2a. Repoint the heb_ skin-detail layer to the morph-baked heb mesh.
    # _extract_part_components demotes heb_ (a morphtarget component) to its
    # NEUTRAL base mesh, which then overlaps the morphed h0_ head -> doubled
    # jaw/mouth. bake_head() also baked heb_ with V's morphs; point at it.
    if baked_mesh_depot and override:
        heb_baked_depot = f"base\\npv-build\\{mod_id}\\{mod_id}_heb.mesh"
        heb_baked_fs = source_dir / heb_baked_depot.replace("\\", "/")
        if heb_baked_fs.exists():
            for c in component_specs:
                if c.get("name", "").startswith("heb_000_") and c["name"].endswith("__basehead"):
                    c["mesh"] = heb_baked_depot
                    c["source"] = "user heb_ layer"
                    logger.info(f"[Head] repointed {c['name']} -> user heb mesh")
        else:
            component_specs[:] = [
                c
                for c in component_specs
                if not (
                    c.get("name", "").startswith("heb_000_") and c["name"].endswith("__basehead")
                )
            ]
            logger.info("[Head] no --heb-mesh with custom head; skin-detail layer omitted")
    elif baked_mesh_depot:
        heb_baked_depot = f"base\\npv-build\\{mod_id}\\{mod_id}_heb.mesh"
        heb_baked_fs = source_dir / heb_baked_depot.replace("\\", "/")
        if heb_baked_fs.exists():
            for c in component_specs:
                if c.get("name", "").startswith("heb_000_") and c["name"].endswith("__basehead"):
                    c["mesh"] = heb_baked_depot
                    c["source"] = "baked heb_ layer (face morphs applied)"
                    logger.info(f"[Head] repointed {c['name']} -> baked heb mesh")

    # 2a2. Bake the makeup-lips overlay with V's face morphs (same design as
    # heb_ above): the stock unmorphed overlay renders a second pair of lips
    # over the morph-baked head.
    if baked_mesh_depot and face_morphs and game_dir and not override:
        _bake_lips_overlays(
            wk, game_dir, source_dir, mod_id, body_rig, face_morphs, component_specs, verbosity
        )

    # 2b. Arms
    arms_mesh = {
        "pwa": "base\\characters\\common\\player_base_bodies\\player_female_average\\arms_hq\\a0_000_pwa_base_hq__full.mesh",
        "pma": "base\\characters\\common\\player_base_bodies\\player_male_average\\arms_hq\\a0_000_pma_base_hq__full.mesh",
    }
    if body_rig in arms_mesh:
        component_specs.append(
            {
                "comp_type": "entSkinnedMeshComponent",
                "name": f"a0_000_{body_rig}_base_hq__full",
                "mesh": arms_mesh[body_rig],
                "appearance": "default",
                "source": "arms mesh",
            }
        )
        logger.info(f"[Project]   arms: a0_000_{body_rig}_base_hq__full")

    # 2c. Seamfix
    seamfix_mesh = {
        "pwa": "base\\characters\\common\\player_base_bodies\\player_female_average\\t0_000_pwa_base__full_seamfix.mesh",
        "pma": "base\\characters\\common\\player_base_bodies\\player_male_average\\t0_000_pma_base__full_seamfix.mesh",
    }
    if body_rig in seamfix_mesh:
        component_specs.append(
            {
                "comp_type": "entSkinnedMeshComponent",
                "name": f"t0_000_{body_rig}_base__full_seamfix",
                "mesh": seamfix_mesh[body_rig],
                "appearance": "default",
                "source": "seamfix",
            }
        )

    # 2d. Modded CCXL eyes (e.g. Sedth 3D Eyes) — extracted before section 2:
    # full replacements suppress the stock iris; glow-only overlays layer on
    # top of the iris/lashes split above.
    component_specs.extend(ccxl_eye_comps)

    # 3. Hair components
    hair_components = asset_paths.get("hair_components", [])
    hair_color = asset_paths.get("hair_color", "")
    if not hair_components and vanilla_hair_ent:
        hair_components = _load_vanilla_hair_components(
            wk, vanilla_hair_ent, entity_json=prefetched_entities
        )
        short = vanilla_hair_ent.rsplit("\\", 1)[-1]
        logger.info(f"[Project]   vanilla hair: {short} ({len(hair_components)} chunk(s))")
    hair_has_dangle = False
    if hair_components:
        for c in hair_components:
            ctype = c.get("$type", "")
            nm_raw = c.get("name", {})
            nm = nm_raw.get("$value", "") if isinstance(nm_raw, dict) else str(nm_raw)

            if ctype == "entAnimatedComponent":
                graph = c.get("graph", {}).get("DepotPath", {}).get("$value", "")
                rig = c.get("rig", {}).get("DepotPath", {}).get("$value", "")
                if graph:
                    component_specs.append(
                        {
                            "comp_type": "entAnimatedComponent",
                            "name": nm,
                            "graph": graph,
                            "rig": rig,
                            "source": "modded hair dangle",
                        }
                    )
                    if nm == "hair_dangle":
                        hair_has_dangle = True
                continue

            if ctype != "entSkinnedMeshComponent":
                continue
            mesh_dp = c.get("mesh", {}).get("DepotPath", {}).get("$value", "")
            if not mesh_dp:
                continue
            if hair_color and "shadow" not in nm.lower():
                ma = hair_color
            else:
                ma = c.get("meshAppearance", {}).get("$value", "default")
            bind_target = (
                "hair_dangle" if hair_has_dangle and "shadow" not in nm.lower() else "root"
            )
            component_specs.append(
                {
                    "comp_type": "entSkinnedMeshComponent",
                    "name": nm or f"hair_{len(component_specs)}",
                    "mesh": mesh_dp,
                    "appearance": ma,
                    "bind_to": bind_target,
                    "source": "modded hair",
                }
            )
        mesh_count = sum(1 for c in hair_components if c.get("$type") == "entSkinnedMeshComponent")
        logger.info(
            f"[Project]   hair: {mesh_count} mesh + {'dangle' if hair_has_dangle else 'no dangle'}"
        )

    # 4. Recipe material overrides
    runtime_overrides = _apply_recipe_overrides(
        component_specs, asset_paths.get("recipe_overrides", []), modded_eyes=modded_eyes
    )

    # 5. Skin tone — apply the early-resolved skin tone to default-appearance body parts
    for comp in component_specs:
        if comp.get("appearance") == "default":
            name = comp.get("name", "")
            if name.startswith(("t0_", "a0_", "i0_", "l0_")):
                comp["appearance"] = skin_tone
                logger.info(f"[Project] Skin tone override: {name} -> {skin_tone}")

    # Nail meshes are part of the curated arms entity but use their own
    # appearance palette; apply this after the general body skin-tone pass.
    _apply_nail_color(component_specs, asset_paths.get("nail_color", ""))

    # 5a. Body tattoo — the tx_ overlay's appearance is the save's raw
    # selection (skin-tone-keyed, e.g. w__01_ca_pale), not 'default'.
    _apply_body_tattoo(component_specs, asset_paths.get("body_tattoo"))

    # 6. Clothing — resolve equipped garment meshes by name (CET gives only hashes)
    equipped_clothing = _resolve_equipped_clothing_meshes(
        wk, game_dir, asset_paths.get("equipped_clothing"), verbosity
    )
    component_specs.extend(
        resolve_clothing(
            body_rig, garment_overrides, equipped=equipped_clothing, verbosity=verbosity
        )
    )

    # 7. Genital filtering
    cc_settings = {}
    cc_file = out_dir / "cc_settings.json"
    if cc_file.exists():
        cc_settings = json.loads(cc_file.read_text())
    genital_selection = ""
    for s in cc_settings.get("selections", []):
        if s.get("label", "").startswith("genitals_"):
            genital_selection = s.get("raw", "")
            break
    if genital_selection:
        component_specs = _filter_genital_components(component_specs, genital_selection)
    if genital_selection:
        logger.info(
            f"[Project] Genitals: {genital_selection.rsplit('__', 1)[0].rsplit('__', 1)[-1] if '__' in genital_selection else genital_selection}"
        )

    logger.info(f"[Project] Total components: {len(component_specs)}")

    # --- Author .app template ---
    if runtime_overrides:
        for ro in runtime_overrides:
            part_name = (
                ro.get("partResource", {})
                .get("DepotPath", {})
                .get("$value", "")
                .replace("\\", "/")
                .rsplit("/", 1)[-1]
            )
            for co in ro.get("componentsOverrides", []):
                cname = (
                    co.get("componentName", {}).get("$value", "")
                    if isinstance(co.get("componentName"), dict)
                    else str(co.get("componentName", ""))
                )
                mapp = (
                    co.get("meshAppearance", {}).get("$value", "")
                    if isinstance(co.get("meshAppearance"), dict)
                    else str(co.get("meshAppearance", ""))
                )
                logger.info(f"[Project] Runtime override ({part_name}): {cname} -> {mapp}")

    app_json = build_app_template(mod_id, parts_overrides=runtime_overrides)
    app_out = source_dir / "base" / "npv-build" / mod_id / f"{mod_id}.app.json"
    app_out.parent.mkdir(parents=True, exist_ok=True)
    app_out.write_text(json.dumps(app_json, indent=2))

    # --- Uncook donor .ent and .app ---
    from .mapping import resolve_table_key

    donor_key = resolve_table_key(asset_paths.get("patch", "2.13"))
    donors_file = Path(__file__).parent / "data" / "donors" / f"{donor_key}.json"
    if not donors_file.exists():
        donors_file = Path(__file__).parent / "data" / "donors" / "2.13.json"
    donor_cfg = json.loads(donors_file.read_text()).get(body_rig, {})
    uncook_regex = donor_cfg.get("uncook_regex", "")

    donor_ent_depot = NPC_BASE_ENT.get(body_rig, NPC_BASE_ENT["pwa"])
    donor_stage = wk.uncook_many(uncook_regex, dest=source_dir / ".donor")

    ent_basename = donor_ent_depot.replace("\\", "/").rsplit("/", 1)[-1]
    donor_ent_files = list(donor_stage.rglob(ent_basename + ".json"))
    if not donor_ent_files:
        raise WolvenKitError(
            f"Could not uncook donor .ent {donor_ent_depot}",
            operation="uncook_donor",
        )
    donor_data = json.loads(donor_ent_files[0].read_text())
    ent_json = build_ent_from_donor(mod_id, donor_data, body_rig)
    logger.info(f"[Project] NPV .ent based on {ent_basename}")

    ent_out = source_dir / "base" / "npv-build" / mod_id / f"{mod_id}.ent.json"
    ent_out.parent.mkdir(parents=True, exist_ok=True)
    ent_out.write_text(json.dumps(ent_json, indent=2))

    donor_app_depot = donor_cfg.get("app_path", "")
    app_basename = donor_app_depot.replace("\\", "/").rsplit("/", 1)[-1]
    donor_app_bins = [f for f in donor_stage.rglob(app_basename) if not f.name.endswith(".json")]
    donor_app_binary = donor_app_bins[0] if donor_app_bins else None
    if donor_app_binary:
        logger.info(f"[Project] Donor .app for infrastructure: {app_basename}")

    # --- Cook JSON -> binary ---
    logger.info("[WolvenKit] Cooking JSON to binary...")
    wk.deserialize(source_dir)

    # Verify the baked morphtarget survived the JSON->binary cook with its
    # shapekeys intact (spec PC-6, guards WolvenKit issue #849 shape-key
    # loss, which typically drops SOME channels rather than all of them —
    # e.g. 105 -> 40). Only applies when a bake actually produced one;
    # user-supplied mesh/GLB overrides may not. The expected count is read
    # from the SOURCE (uncooked) morphtarget JSON that head_bake wrote
    # before this cook step — it carries the stock/full fixed channel set,
    # so the cooked result must match it exactly. The source JSON is still
    # on disk here; it's deleted a few lines below.
    morphtarget_cooked = source_dir / "base" / "npv-build" / mod_id / f"{mod_id}_morphs.morphtarget"
    if morphtarget_cooked.exists():
        morphtarget_source_json = morphtarget_cooked.parent / f"{morphtarget_cooked.name}.json"
        expected_targets = None
        if morphtarget_source_json.exists():
            try:
                source_data = json.loads(morphtarget_source_json.read_text(encoding="utf-8"))
                expected_targets = len(
                    source_data.get("Data", {}).get("RootChunk", {}).get("targets", [])
                )
            except (OSError, json.JSONDecodeError, AttributeError, TypeError) as e:
                logger.warning(
                    f"[Head] could not read source morphtarget JSON for expected "
                    f"target count ({e}); falling back to minimum-1 verification"
                )
        verify_morphtarget(wk, morphtarget_cooked, expected_targets=expected_targets)

    for p in list(source_dir.rglob("*.json")):
        p.unlink()
    for p in list(source_dir.rglob("*.buffer")):
        p.unlink()

    head_ent_cooked = source_dir / "base" / "characters" / "head" / f"{mod_id}_head.ent"
    if head_ent_cooked.exists():
        head_ent_cooked.unlink()

    # --- Inject components ---
    app_cooked = source_dir / "base" / "npv-build" / mod_id / f"{mod_id}.app"
    if not app_cooked.exists():
        raise WolvenKitError(
            f"Cooked .app not found: {app_cooked}",
            operation="inject",
        )

    components_json = out_dir / "npv_components.json"
    from .project_writer import write_components_json

    appearance_name = f"{mod_id}_appearance"
    write_components_json(component_specs, appearance_name, components_json)

    head_rig_base = (
        "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa_c__basehead"
    )
    if body_rig == "pma":
        head_rig_base = (
            "base\\characters\\head\\player_base_heads\\player_male_average\\h0_000_pma_c__basehead"
        )
    face_rig_path = f"{head_rig_base}\\h0_000_{body_rig}_c__basehead_skeleton.rig"
    facial_setup_path = f"{head_rig_base}\\h0_000_{body_rig}_c__basehead_rigsetup.facialsetup"
    face_graph_path = {
        "pwa": "base\\animations\\facial\\_facial_graphs\\player_woman_paperdoll_sermo.animgraph",
        "pma": "base\\animations\\facial\\_facial_graphs\\player_man_paperdoll_sermo.animgraph",
    }.get(
        body_rig, "base\\animations\\facial\\_facial_graphs\\player_woman_paperdoll_sermo.animgraph"
    )

    logger.info(f"[npv-inject] Injecting {len(component_specs)} component(s)...")
    _do_inject_components(
        wk,
        app_cooked,
        components_json,
        verbosity,
        donor_app=donor_app_binary,
        face_rig=face_rig_path,
        facial_setup=facial_setup_path,
        face_graph=face_graph_path,
        hair_dangle_graph="skip" if hair_has_dangle else None,
    )

    shutil.rmtree(donor_stage, ignore_errors=True)

    # Photo Mode must be authored while the unpacked source tree still exists.
    # Its dedicated entity/app intentionally diverge from the normal AMM
    # entity and are included in the same archive.
    if photomode_thumbnail is not None:
        from .photomode import author_photomode_assets

        author_photomode_assets(
            wk,
            source_dir=source_dir,
            mod_id=mod_id,
            npv_name=npv_name or mod_id,
            body_rig=body_rig,
            thumbnail=photomode_thumbnail,
            artifact_cache=artifact_cache,
        )

    # --- Pack ---
    logger.info("[WolvenKit] Packing archive...")
    archive_dir = out_dir / "archive" / "pc" / "mod"
    archive_path = wk.pack(source_dir, dest=archive_dir)

    target = archive_dir / f"{mod_id}.archive"
    if archive_path.name != f"{mod_id}.archive":
        # Always overwrite — a stale {mod_id}.archive from a prior build (the
        # mod_id is deterministic, so reinstalls reuse the name) must not shadow
        # the freshly packed archive, which wk.pack names after the source dir.
        if target.exists():
            target.unlink()
        archive_path.rename(target)

    return component_specs
