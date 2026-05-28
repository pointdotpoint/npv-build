from pathlib import Path
import shutil
import hashlib
import re

import json
from .save_parser import parse_save, SaveParserError
from .mapping import resolve_assets, MappingError
from .wk_cli import WolvenKit, WolvenKitConfig, WolvenKitError
from .wolvenkit import build_project

class OrchestratorError(Exception):
    def __init__(self, module_name, message):
        super().__init__(message)
        self.module_name = module_name

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

def compute_mod_id(npv_name: str, cc_settings: dict) -> str:
    slug = slugify(npv_name)
    canonical_json = json.dumps([npv_name, cc_settings], separators=(',', ':'), sort_keys=True)
    hash_digest = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()[:8]
    return f"{slug}_{hash_digest}"

def run_orchestrator(save_path: Path, npv_name: str, output_dir: Path, game_dir: Path, template_cache: Path, clear_cache: bool, verbosity: int, cc_json_path: Path = None, hair_override: str = None, skin_override: str = None, garments: list = None):
    # Construct WolvenKit CLI adapter
    wk_config = WolvenKitConfig(
        game_dir=game_dir,
        verbosity=verbosity,
    )
    wk = WolvenKit(wk_config)

    try:
        wk.check_version()
    except WolvenKitError as e:
        raise OrchestratorError(e.module_name, str(e))

    if clear_cache and template_cache.exists():
        shutil.rmtree(template_cache)

    # game_dir no longer required: NPV resources are authored from scratch and
    # reference base-game part .ents by depot path (resolved at game load).

    if verbosity > 0:
        print("[Orchestrator] Starting build process...")

    # Load CC settings: either from a CET-dumped JSON or from the save parser
    if cc_json_path is not None:
        if verbosity > 0:
            print(f"[CC Loader] Loading CC from {cc_json_path}...")
        try:
            with open(cc_json_path, "r") as f:
                cc_settings = json.load(f)
        except Exception as e:
            raise OrchestratorError("CC Loader", f"Failed to load --cc-json: {e}")
    else:
        if verbosity > 0:
            print("[Save Parser] Parsing save file...")
        try:
            cc_settings = parse_save(save_path)
        except SaveParserError as e:
            raise OrchestratorError(e.module_name, str(e))
        except Exception as e:
            raise OrchestratorError("Save Parser", f"Unexpected error: {e}")

    # Write cc_settings.json for diagnostics
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "cc_settings.json", "w") as f:
        json.dump(cc_settings, f, indent=2)

    # Mapping
    if verbosity > 0:
        print("[Mapping] Resolving asset paths...")
    try:
        asset_paths = resolve_assets(cc_settings, game_dir, hair_override=hair_override, garments=garments or [], wk=wk)
    except MappingError as e:
        raise OrchestratorError(e.module_name, str(e))
    except Exception as e:
        raise OrchestratorError("Mapping", f"Unexpected error: {e}")

    with open(output_dir / "asset_paths.json", "w") as f:
        json.dump(asset_paths, f, indent=2)


    # Compute deterministic Mod ID
    mod_id = compute_mod_id(npv_name, cc_settings)
    appearance_name = f"{mod_id}_appearance"
    app_depot = f"base\\npv-build\\{mod_id}\\{mod_id}.app"

    body_rig = asset_paths.get("body_rig", "pwa")
    ent_depot_path = f"base\\\\npv-build\\\\{mod_id}\\\\{mod_id}.ent"

    # AMM Lua Generator
    if verbosity > 0:
        print("[AMM Lua Generator] Generating LUA script...")

    ext_deps = asset_paths.get("external_dependencies", [])
    unresolved = asset_paths.get("unresolved", [])

    lua_comments = []
    if ext_deps:
        print("\n[Orchestrator] WARNING: External mod dependencies detected! These assets are not in the base game:")
        for dep in ext_deps:
            sel = dep.get("selection")
            reason = dep.get("reason")
            print(f"  - {sel}: {reason}")
            lua_comments.append(f"-- WARNING: External mod dependency: {sel} ({reason})")

    if unresolved:
        print("\n[Orchestrator] WARNING: Unresolved base-game selections (using sensible fallbacks):")
        for unr in unresolved:
            print(f"  - {unr}")
            lua_comments.append(f"-- WARNING: Unresolved selection (fallback used): {unr}")

    lua_comments_str = "\n".join(lua_comments) + "\n" if lua_comments else ""

    safe_display = npv_name.replace('"', '\\"')
    unique_id = mod_id.upper().replace("-", "_")

    # Use Judy's record for the puppet rig (animation, AI, locomotion) while
    # our .ent provides the appearance list (pointing at our .app). AMM should
    # use our .ent as the entity template and the record for puppet setup.
    record = '"Character.Judy"' if body_rig == "pwa" else '"Character.Viktor"'

    lua_code = f"""{lua_comments_str}return {{
  modder = "npv-build",
  unique_identifier = "{unique_id}",
  rig = "{body_rig}",
  entity_info = {{
    name = "{safe_display}",
    path = "{ent_depot_path}",
    record = {record},
    type = "Character",
    customName = true
  }},
  appearances = {{
    "{appearance_name}"
  }},
  attributes = nil
}}
"""
    
    # Build WolvenKit project (all binary assets, no archive packing)
    if verbosity > 0:
        print("[Project] Building WolvenKit project...")

    try:
        component_specs = build_project(wk, mod_id, output_dir, asset_paths, verbosity,
                                        garment_overrides=garments or [],
                                        skin_override=skin_override)
    except WolvenKitError as e:
        raise OrchestratorError(e.module_name, str(e))
    except Exception as e:
        raise OrchestratorError("WolvenKit Automation", f"Unexpected error: {e}")

    # AMM Lua
    lua_dir = output_dir / "bin" / "x64" / "plugins" / "cyber_engine_tweaks" / "mods" / "AppearanceMenuMod" / "Collabs" / "Custom Entities"
    lua_dir.mkdir(parents=True, exist_ok=True)
    lua_file = lua_dir / f"{mod_id}.lua"
    lua_file.write_text(lua_code, encoding="utf-8")

    if verbosity > 0:
        print(f"[Orchestrator] Mod built: {output_dir}")
        print(f"[Orchestrator] Components: {len(component_specs)}")
        print(f"[Orchestrator] Install: copy archive/ and bin/ to your game directory")

    return str(output_dir)
