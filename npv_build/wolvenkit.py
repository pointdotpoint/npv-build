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
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .wk_cli import WolvenKit, WolvenKitError
from .head_bake import bake_head, find_stock_head_part
from .clothing import resolve_clothing
from .config_editor import _MESH_COMPONENT_TYPES


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
        print(f"[npv-inject] $ {' '.join(cmd)}")

    stream = verbosity >= 2
    try:
        result = subprocess.run(
            cmd,
            stdout=None if stream else subprocess.PIPE,
            stderr=None if stream else subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        raise WolvenKitError(
            f"{INJECT_BINARY} not found. Build it with: dotnet build tools/npv-inject",
            operation="inject",
        )

    if result.returncode != 0:
        tail = ""
        if not stream:
            err = (result.stderr or "") + (result.stdout or "")
            tail = "\n" + err[-1500:]
        raise WolvenKitError(
            f"npv-inject failed (exit {result.returncode}).{tail}",
            operation="inject",
            exit_code=result.returncode,
        )


def _resolve_morphtarget_to_mesh(wk: WolvenKit, morphtarget_depot: str) -> str:
    basename = morphtarget_depot.replace("\\", "/").rsplit("/", 1)[-1]
    try:
        mt_data = wk.uncook_json(basename)
    except (WolvenKitError, FileNotFoundError):
        return ""
    return (mt_data.get("Data", {}).get("RootChunk", {})
            .get("baseMesh", {}).get("DepotPath", {}).get("$value", ""))


def _extract_part_components(
    wk: WolvenKit,
    part_ent_depot: str,
    verbosity: int,
) -> list[dict]:
    basename = part_ent_depot.replace("\\", "/").rsplit("/", 1)[-1]
    try:
        data = wk.uncook_json(basename)
    except (WolvenKitError, FileNotFoundError):
        return []

    chunks = (data.get("Data", {}).get("RootChunk", {})
              .get("compiledData", {}).get("Data", {}).get("Chunks", []))
    if not chunks:
        chunks = data.get("Data", {}).get("RootChunk", {}).get("components", [])

    result = []
    for c in chunks:
        ctype = c.get("$type", "")
        if ctype not in _MESH_COMPONENT_TYPES:
            continue
        name = c.get("name", {}).get("$value", "") if isinstance(c.get("name"), dict) else ""
        mesh = c.get("mesh", {}).get("DepotPath", {}).get("$value", "") if c.get("mesh") else ""
        ma = c.get("meshAppearance", {}).get("$value", "default") if c.get("meshAppearance") else "default"

        if ctype == "entMorphTargetSkinnedMeshComponent":
            mr = c.get("morphResource", {}).get("DepotPath", {}).get("$value", "") if c.get("morphResource") else ""
            if mr and not mesh:
                mesh = _resolve_morphtarget_to_mesh(wk, mr)
            if not mesh:
                continue
            ctype = "entSkinnedMeshComponent"
        elif not mesh:
            continue

        result.append({
            "comp_type": ctype,
            "name": name,
            "mesh": mesh,
            "appearance": ma,
        })
    return result


def _extract_ccxl_eye_components(
    game_dir: Path,
    cc_selections: list[dict],
    body_rig: str,
    verbosity: int,
) -> list[dict]:
    """Extract modded CCXL eye components (e.g. Sedth 3D Eyes) from mod archives.

    Detects CC labels matching *_eyes_r, *_eyes_l, *_eyes_r_glow, *_eyes_l_glow
    and resolves them to mesh components via the mod's .app files.
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
        return []

    suffix_to_app = {"_r": "eyes_r", "_l": "eyes_l", "_r_glow": "eyes_r_glow", "_l_glow": "eyes_l_glow"}
    label_to_app = {}
    for lbl in eye_labels:
        for suffix, app_stem in suffix_to_app.items():
            if lbl.endswith(suffix):
                label_to_app[lbl] = app_stem + ".app"
                break

    if not label_to_app:
        return []

    mod_dir = game_dir / "archive" / "pc" / "mod"
    if not mod_dir.exists():
        return []

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
        except Exception:
            continue

    if not target_archive:
        if verbosity > 0:
            print(f"[Eyes] modded eyes '{mod_prefix}' archive not found")
        return []

    if verbosity > 0:
        print(f"[Eyes] modded eyes from {target_archive.name}")

    components = []
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        app_names = set(label_to_app.values())
        alt = "|".join(re.escape(a) for a in app_names)
        regex = f"({alt})$"

        try:
            result = subprocess.run(
                ["WolvenKit.CLI", "uncook", "-p", str(target_archive), "-r", regex, "-o", str(td_path), "-s"],
                capture_output=True, text=True,
            )
        except Exception:
            return []

        # Also uncook morphtargets to resolve meshes
        subprocess.run(
            ["WolvenKit.CLI", "uncook", "-p", str(target_archive), "-r", r"\.morphtarget$", "-o", str(td_path), "-s"],
            capture_output=True, text=True,
        )

        mt_cache = {}
        for mt_json in td_path.rglob("*.morphtarget.json"):
            data = json.loads(mt_json.read_text())
            base_mesh = (data.get("Data", {}).get("RootChunk", {})
                         .get("baseMesh", {}).get("DepotPath", {}).get("$value", ""))
            mt_depot = str(mt_json.relative_to(td_path)).replace("/", "\\").replace(".json", "")
            mt_cache[mt_depot] = base_mesh

        for lbl, app_file in label_to_app.items():
            appearance_name = eye_labels.get(lbl, "")
            if not appearance_name:
                continue

            app_jsons = list(td_path.rglob(app_file + ".json"))
            if not app_jsons:
                continue

            data = json.loads(app_jsons[0].read_text())
            appearances = data.get("Data", {}).get("RootChunk", {}).get("appearances", [])
            for a in appearances:
                name = a.get("Data", {}).get("name", {}).get("$value", "")
                if name != appearance_name:
                    continue
                for c in a.get("Data", {}).get("components", []):
                    ctype = c.get("$type", "")
                    ma = c.get("meshAppearance", {}).get("$value", "default") if c.get("meshAppearance") else "default"
                    mesh = ""
                    if c.get("mesh"):
                        mesh = c["mesh"].get("DepotPath", {}).get("$value", "")
                    if not mesh and c.get("morphResource"):
                        mr = c["morphResource"].get("DepotPath", {}).get("$value", "")
                        mesh = mt_cache.get(mr, "")
                    if not mesh:
                        continue
                    comp_name = lbl.replace("_glow", "_g")
                    components.append({
                        "comp_type": "entSkinnedMeshComponent",
                        "name": comp_name,
                        "mesh": mesh,
                        "appearance": ma,
                        "source": f"modded eyes ({mod_prefix})",
                    })
                    if verbosity > 0:
                        print(f"[Eyes]   {comp_name}: {mesh.rsplit(chr(92), 1)[-1]} -> {ma}")
                break

    return components


def _apply_recipe_overrides(components: list[dict], recipe_overrides: list[dict]) -> list[dict]:
    """Process recipe material overrides. Modifies head component overrides
    to also target our baked head component name. Returns the fully prepared
    partsOverrides list to be written to the .app file."""
    import copy

    # 1. First, build the direct override_map for components where we can set appearance directly
    override_map = {}
    for ov in recipe_overrides:
        pr = ov.get("partResource", {}).get("DepotPath", {}).get("$value", "").lower()
        is_head_part = "appearances\\entity\\head\\h0_" in pr or "appearances/entity/head/h0_" in pr.replace("\\", "/")

        for co in ov.get("componentsOverrides", []):
            cn = co.get("componentName", {}).get("$value", "")
            ma = co.get("meshAppearance", {}).get("$value", "")
            if cn and ma:
                # Eyelashes shouldn't be set directly on the eyes component since eye color is also set there
                if ma.startswith("eyelashes__"):
                    continue

                # Alias stock head component overrides to our baked basehead component name
                if is_head_part and cn.startswith("MorphTargetSkinnedMesh"):
                    head_comp_names = [comp["name"] for comp in components if comp["name"].endswith("_basehead")]
                    for hname in head_comp_names:
                        override_map[hname] = ma

                override_map[cn] = ma

    # Apply direct appearances to inlined components
    for comp in components:
        name = comp.get("name", "")
        if name in override_map:
            comp["appearance"] = override_map[name]

    # 2. Prepare the partsOverrides list for the .app file.
    # We must preserve the original partResource paths and component overrides structure,
    # but we will inject the baked head component aliases for any head MorphTargetSkinnedMesh overrides.
    app_parts_overrides = []

    for ov in recipe_overrides:
        # Clone the override block to avoid modifying the original parsed asset_paths in-place
        ov_clone = copy.deepcopy(ov)
        pr = ov_clone.get("partResource", {}).get("DepotPath", {}).get("$value", "").lower()
        is_head_part = "appearances\\entity\\head\\h0_" in pr or "appearances/entity/head/h0_" in pr.replace("\\", "/")

        new_cos = []
        for co in ov_clone.get("componentsOverrides", []):
            new_cos.append(co)
            cn = co.get("componentName", {}).get("$value", "")

            # If it's a head part override targeting the stock MorphTargetSkinnedMesh,
            # duplicate it targeting our morph-baked custom head component name(s)
            if is_head_part and cn and cn.startswith("MorphTargetSkinnedMesh"):
                head_comp_names = [comp["name"] for comp in components if comp["name"].endswith("_basehead")]
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
) -> list[dict]:
    """Build the full mod: assemble components, inject into .app, pack .archive.

    Returns component spec list for diagnostics.
    """
    from .config_editor import build_app_template, build_ent_from_donor, NPC_BASE_ENT

    source_dir = out_dir / "source" / "archive"
    if source_dir.exists():
        shutil.rmtree(source_dir)
    source_dir.mkdir(parents=True, exist_ok=True)

    game_dir = wk.config.game_dir
    if not game_dir:
        raise WolvenKitError("game_dir required", operation="build_project")

    component_specs: list[dict] = []

    recipe_parts = asset_paths.get("recipe_parts", [])
    part_entities = asset_paths.get("part_entities", [])

    all_part_depots: set[str] = set()
    for pv in recipe_parts:
        dp = pv.get("resource", {}).get("DepotPath", {}).get("$value", "")
        if dp:
            all_part_depots.add(dp)
    for p in part_entities:
        all_part_depots.add(p)

    stock_head_depot = find_stock_head_part(asset_paths)

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

    if face_morphs and game_dir:
        try:
            result = bake_head(wk, mod_id, source_dir, body_rig, face_morphs, verbosity)
            if result:
                baked_mesh_depot = f"base\\npv-build\\{mod_id}\\{mod_id}_head.mesh"
        except Exception as e:
            print(f"[Head] face bake failed ({e}); using stock head.")

    if baked_mesh_depot:
        component_specs.append({
            "comp_type": "entSkinnedMeshComponent",
            "name": f"h0_000_{body_rig}_c__basehead",
            "mesh": baked_mesh_depot,
            "appearance": skin_tone,
            "source": "baked head (face morphs applied)",
        })
        if verbosity > 0:
            print(f"[Head] baked head component: h0_000_{body_rig}_c__basehead")

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
            seamfix_mesh = "base\\vtk\\femv_seamfix.mesh" if body_rig == "pwa" else "base\\vtk\\mase_seamfix.mesh"
            headpatch_mesh = "base\\vtk\\femv_vtk_headpatch.mesh" if body_rig == "pwa" else "base\\vtk\\mase_vtk_headpatch.mesh"
            
            component_specs.append({
                "comp_type": "entSkinnedMeshComponent",
                "name": "femv_vtk_headpatch",
                "mesh": headpatch_mesh,
                "appearance": skin_tone,
                "bind_to": "root",
                "source": "VTK headpatch (auto-injected)",
            })
            component_specs.append({
                "comp_type": "entSkinnedMeshComponent",
                "name": "femv_seamfix",
                "mesh": seamfix_mesh,
                "appearance": skin_tone,
                "bind_to": "root",
                "source": "VTK seamfix (auto-injected)",
            })
            if verbosity > 0:
                print(f"[Head] Auto-injected VTK headpatch and seamfix for rig {body_rig}")
    elif stock_head_depot:
        use_morph_fallback = bool(face_morphs)
        comps = _extract_part_components(wk, stock_head_depot, verbosity)
        if use_morph_fallback:
            from .blender_module import HEAD_MORPHTARGET, HEAD_FACE_MESH
            stock_mesh = HEAD_FACE_MESH.get(body_rig, "")
            stock_mt = HEAD_MORPHTARGET.get(body_rig, "")
            for c in comps:
                cname = c.get("name", "")
                if cname.startswith("h0_000_") and cname.endswith("_basehead"):
                    c["comp_type"] = "entMorphTargetSkinnedMeshComponent"
                    c["mesh"] = stock_mesh
                    c["graph"] = stock_mt  # Reused by C# injector for MorphResource
                    c["source"] = "stock morph target head (programmatic fallback)"
                    if verbosity > 0:
                        print(f"[Head] Programmatic morph fallback: {cname} using morphtarget {stock_mt}")
                else:
                    c["source"] = "stock head"
        else:
            for c in comps:
                c["source"] = "stock head"
        component_specs.extend(comps)
        if verbosity > 0:
            print(f"[Head] stock head: {len(comps)} component(s) (morph_fallback={use_morph_fallback})")

    # 2. Other part-ents (eyes, teeth, body, etc.)
    for dp in sorted(all_part_depots):
        if dp == stock_head_depot:
            continue
        comps = _extract_part_components(wk, dp, verbosity)
        for c in comps:
            c["source"] = dp.replace("\\", "/").rsplit("/", 1)[-1]
        if verbosity > 0 and comps:
            short = dp.rsplit("\\", 1)[-1]
            print(f"[Project]   {short}: {len(comps)} component(s)")
        component_specs.extend(comps)

    # 2b. Arms
    arms_mesh = {
        "pwa": "base\\characters\\common\\player_base_bodies\\player_female_average\\arms_hq\\a0_000_pwa_base_hq__full.mesh",
        "pma": "base\\characters\\common\\player_base_bodies\\player_male_average\\arms_hq\\a0_000_pma_base_hq__full.mesh",
    }
    if body_rig in arms_mesh:
        component_specs.append({
            "comp_type": "entSkinnedMeshComponent",
            "name": f"a0_000_{body_rig}_base_hq__full",
            "mesh": arms_mesh[body_rig],
            "appearance": "default",
            "source": "arms mesh",
        })
        if verbosity > 0:
            print(f"[Project]   arms: a0_000_{body_rig}_base_hq__full")

    # 2c. Seamfix
    seamfix_mesh = {
        "pwa": "base\\characters\\common\\player_base_bodies\\player_female_average\\t0_000_pwa_base__full_seamfix.mesh",
        "pma": "base\\characters\\common\\player_base_bodies\\player_male_average\\t0_000_pma_base__full_seamfix.mesh",
    }
    if body_rig in seamfix_mesh:
        component_specs.append({
            "comp_type": "entSkinnedMeshComponent",
            "name": f"t0_000_{body_rig}_base__full_seamfix",
            "mesh": seamfix_mesh[body_rig],
            "appearance": "default",
            "source": "seamfix",
        })

    # 2d. Modded CCXL eyes (e.g. Sedth 3D Eyes)
    cc_settings_data = {}
    cc_file = out_dir / "cc_settings.json"
    if cc_file.exists():
        cc_settings_data = json.loads(cc_file.read_text())
    if game_dir and cc_settings_data.get("selections"):
        eye_comps = _extract_ccxl_eye_components(
            game_dir, cc_settings_data["selections"], body_rig, verbosity)
        component_specs.extend(eye_comps)

    # 3. Hair components
    hair_components = asset_paths.get("hair_components", [])
    hair_color = asset_paths.get("hair_color", "")
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
                    component_specs.append({
                        "comp_type": "entAnimatedComponent",
                        "name": nm,
                        "graph": graph,
                        "rig": rig,
                        "source": "modded hair dangle",
                    })
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
            bind_target = "hair_dangle" if hair_has_dangle and "shadow" not in nm.lower() else "root"
            component_specs.append({
                "comp_type": "entSkinnedMeshComponent",
                "name": nm or f"hair_{len(component_specs)}",
                "mesh": mesh_dp,
                "appearance": ma,
                "bind_to": bind_target,
                "source": "modded hair",
            })
        if verbosity > 0:
            mesh_count = sum(1 for c in hair_components if c.get("$type") == "entSkinnedMeshComponent")
            print(f"[Project]   hair: {mesh_count} mesh + {'dangle' if hair_has_dangle else 'no dangle'}")

    # 4. Recipe material overrides
    runtime_overrides = _apply_recipe_overrides(component_specs, asset_paths.get("recipe_overrides", []))

    # 5. Skin tone — apply the early-resolved skin tone to default-appearance body parts
    for comp in component_specs:
        if comp.get("appearance") == "default":
            name = comp.get("name", "")
            if name.startswith(("t0_", "a0_", "i0_", "l0_")):
                comp["appearance"] = skin_tone
                if verbosity > 0:
                    print(f"[Project] Skin tone override: {name} -> {skin_tone}")

    # 6. Clothing
    component_specs.extend(resolve_clothing(body_rig, garment_overrides, verbosity))

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
        if "vagina" in genital_selection:
            component_specs = [c for c in component_specs if "penis" not in c.get("name", "")]
        elif "penis" in genital_selection:
            is_circumcised = "circumcised" in genital_selection
            component_specs = [
                c for c in component_specs
                if "vagina" not in c.get("name", "")
                and not (is_circumcised and c.get("name", "") == "i0_000_pwa_base__penis")
                and not (not is_circumcised and "circumcised" in c.get("name", ""))
            ]
    if verbosity > 0 and genital_selection:
        print(f"[Project] Genitals: {genital_selection.rsplit('__', 1)[0].rsplit('__', 1)[-1] if '__' in genital_selection else genital_selection}")

    if verbosity > 0:
        print(f"[Project] Total components: {len(component_specs)}")

    # --- Author .app template ---
    if runtime_overrides and verbosity > 0:
        for ro in runtime_overrides:
            part_name = ro.get("partResource", {}).get("DepotPath", {}).get("$value", "").replace("\\", "/").rsplit("/", 1)[-1]
            for co in ro.get("componentsOverrides", []):
                cname = co.get("componentName", {}).get("$value", "") if isinstance(co.get("componentName"), dict) else str(co.get("componentName", ""))
                mapp = co.get("meshAppearance", {}).get("$value", "") if isinstance(co.get("meshAppearance"), dict) else str(co.get("meshAppearance", ""))
                print(f"[Project] Runtime override ({part_name}): {cname} -> {mapp}")

    app_json = build_app_template(mod_id, parts_overrides=runtime_overrides)
    app_out = source_dir / "base" / "npv-build" / mod_id / f"{mod_id}.app.json"
    app_out.parent.mkdir(parents=True, exist_ok=True)
    app_out.write_text(json.dumps(app_json, indent=2))

    # --- Uncook donor .ent and .app ---
    donors_file = Path(__file__).parent / "data" / "donors" / f"{asset_paths.get('patch', '2.13')}.json"
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
    if verbosity > 0:
        print(f"[Project] NPV .ent based on {ent_basename}")

    ent_out = source_dir / "base" / "npv-build" / mod_id / f"{mod_id}.ent.json"
    ent_out.parent.mkdir(parents=True, exist_ok=True)
    ent_out.write_text(json.dumps(ent_json, indent=2))

    donor_app_depot = donor_cfg.get("app_path", "")
    app_basename = donor_app_depot.replace("\\", "/").rsplit("/", 1)[-1]
    donor_app_bins = [f for f in donor_stage.rglob(app_basename) if not f.name.endswith(".json")]
    donor_app_binary = donor_app_bins[0] if donor_app_bins else None
    if donor_app_binary and verbosity > 0:
        print(f"[Project] Donor .app for infrastructure: {app_basename}")

    # --- Cook JSON -> binary ---
    if verbosity > 0:
        print("[WolvenKit] Cooking JSON to binary...")
    wk.deserialize(source_dir)

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

    head_rig_base = "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa_c__basehead"
    if body_rig == "pma":
        head_rig_base = "base\\characters\\head\\player_base_heads\\player_male_average\\h0_000_pma_c__basehead"
    face_rig_path = f"{head_rig_base}\\h0_000_{body_rig}_c__basehead_skeleton.rig"
    facial_setup_path = f"{head_rig_base}\\h0_000_{body_rig}_c__basehead_rigsetup.facialsetup"
    face_graph_path = {
        "pwa": "base\\animations\\facial\\_facial_graphs\\player_woman_paperdoll_sermo.animgraph",
        "pma": "base\\animations\\facial\\_facial_graphs\\player_man_paperdoll_sermo.animgraph",
    }.get(body_rig, "base\\animations\\facial\\_facial_graphs\\player_woman_paperdoll_sermo.animgraph")

    if verbosity > 0:
        print(f"[npv-inject] Injecting {len(component_specs)} component(s)...")
    _inject_components(app_cooked, components_json, verbosity,
                       donor_app=donor_app_binary,
                       face_rig=face_rig_path,
                       facial_setup=facial_setup_path,
                       face_graph=face_graph_path,
                       hair_dangle_graph="skip" if hair_has_dangle else None)

    shutil.rmtree(donor_stage, ignore_errors=True)

    # --- Pack ---
    if verbosity > 0:
        print("[WolvenKit] Packing archive...")
    archive_dir = out_dir / "archive" / "pc" / "mod"
    archive_path = wk.pack(source_dir, dest=archive_dir)

    target = archive_dir / f"{mod_id}.archive"
    if not target.exists() and archive_path.name != f"{mod_id}.archive":
        archive_path.rename(target)

    return component_specs
