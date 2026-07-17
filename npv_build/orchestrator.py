import hashlib
import json
import logging
import re
from pathlib import Path

from .mapping import MappingError
from .save_parser import SaveParserError, parse_save
from .wk_cli import WolvenKit, WolvenKitConfig, WolvenKitError

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    def __init__(self, module_name, message):
        super().__init__(message)
        self.module_name = module_name


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def compute_mod_id(npv_name: str, cc_settings: dict) -> str:
    slug = slugify(npv_name)
    canonical_json = json.dumps([npv_name, cc_settings], separators=(",", ":"), sort_keys=True)
    hash_digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{hash_digest}"


def write_amm_lua(
    mod_id: str,
    npv_name: str,
    body_rig: str,
    output_dir: Path,
    asset_paths: dict | None = None,
) -> Path:
    """Generate the AppearanceMenuMod Lua entry for this mod and write it to disk.

    When `asset_paths` is provided, restores the original orchestrator behavior:
    a leading `-- WARNING` comment block (and matching `logger.warning` calls) for
    any external mod dependencies or unresolved base-game selections recorded in
    `asset_paths["external_dependencies"]` / `asset_paths["unresolved"]`.
    """
    appearance_name = f"{mod_id}_appearance"
    ent_depot_path = f"base\\\\npv-build\\\\{mod_id}\\\\{mod_id}.ent"

    ext_deps = (asset_paths or {}).get("external_dependencies", [])
    unresolved = (asset_paths or {}).get("unresolved", [])

    lua_comments = []
    if ext_deps:
        logger.warning(
            "\n[Orchestrator] External mod dependencies detected! These assets are not in the base game:"
        )
        for dep in ext_deps:
            sel = dep.get("selection")
            reason = dep.get("reason")
            logger.warning(f"  - {sel}: {reason}")
            lua_comments.append(f"-- WARNING: External mod dependency: {sel} ({reason})")

    if unresolved:
        logger.warning(
            "\n[Orchestrator] Unresolved base-game selections (using sensible fallbacks):"
        )
        for unr in unresolved:
            logger.warning(f"  - {unr}")
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

    lua_dir = (
        output_dir
        / "bin"
        / "x64"
        / "plugins"
        / "cyber_engine_tweaks"
        / "mods"
        / "AppearanceMenuMod"
        / "Collabs"
        / "Custom Entities"
    )
    lua_dir.mkdir(parents=True, exist_ok=True)
    lua_file = lua_dir / f"{mod_id}.lua"
    lua_file.write_text(lua_code, encoding="utf-8")
    return lua_file


def run_orchestrator(
    save_path: Path,
    npv_name: str,
    output_dir: Path,
    game_dir: Path,
    template_cache: Path,
    clear_cache: bool,
    verbosity: int,
    cc_json_path: Path = None,
    hair_override: str = None,
    skin_override: str = None,
    garments: list = None,
    user_head_glb: Path = None,
    user_head_mesh: Path = None,
    user_heb_mesh: Path = None,
    restore_head_materials: bool = True,
    dump_head_glb: Path = None,
):
    # Construct WolvenKit CLI adapter
    wk_config = WolvenKitConfig(
        game_dir=game_dir,
        verbosity=verbosity,
    )
    wk = WolvenKit(wk_config)

    try:
        wk.check_version()
    except WolvenKitError as e:
        raise OrchestratorError(e.module_name, str(e)) from e

    if dump_head_glb:
        from .head_bake import dump_head_glb as _dump_head_glb

        body_rig = "pwa"
        if cc_json_path:
            try:
                with open(cc_json_path) as f:
                    dump_data_for_rig = json.load(f)
                body_rig = dump_data_for_rig.get("body_rig", "pwa")
            except (OSError, json.JSONDecodeError):
                pass
        elif save_path:
            try:
                cc_tmp = parse_save(save_path)
                body_rig = cc_tmp.get("body_rig", "pwa")
            except SaveParserError:
                pass
        if body_rig == "pwa" and not (cc_json_path or save_path):
            logger.info("[Head] using default body rig 'pwa' for head dump")
        _dump_head_glb(wk, body_rig, dump_head_glb, verbosity)
        return str(dump_head_glb)

    # Delegate the actual build to the checkpointing pipeline service.
    # Imported here (not at module top) to avoid a circular import: pipeline
    # imports write_amm_lua from this module at its own module level.
    from .core.pipeline import BuildRequest, PipelineService

    req = BuildRequest(
        save_path=save_path,
        npv_name=npv_name,
        output_dir=output_dir,
        game_dir=game_dir,
        template_cache=template_cache,
        clear_cache=clear_cache,
        cc_json_path=cc_json_path,
        hair_override=hair_override,
        skin_override=skin_override,
        garments=garments or [],
        user_head_glb=user_head_glb,
        user_head_mesh=user_head_mesh,
        user_heb_mesh=user_heb_mesh,
        restore_head_materials=restore_head_materials,
    )

    # NOTE: run_orchestrator does not pass a `cancel` token to PipelineService
    # today, so PipelineCancelled cannot actually be raised here yet. If/when
    # cancel wiring is added to this function, PipelineCancelled must NOT be
    # caught by the blanket `except Exception` below and re-wrapped as
    # OrchestratorError — callers need to distinguish "cancelled" from "failed".
    try:
        result = PipelineService().build(req)
    except (MappingError, SaveParserError, WolvenKitError) as e:
        raise OrchestratorError(e.module_name, str(e)) from e
    except OrchestratorError:
        raise
    except Exception as e:
        logger.debug("Traceback:", exc_info=True)
        raise OrchestratorError("Pipeline", f"Unexpected error: {e}") from e

    logger.info(f"[Orchestrator] Mod built: {result.output_dir}")
    logger.info("[Orchestrator] Install: copy archive/ and bin/ to your game directory")

    return result.output_dir
