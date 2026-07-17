"""Checkpointing pipeline service both frontends drive (spec CORE-1..4)."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..mapping import resolve_assets
from ..save_parser import parse_save
from ..wk_cli import WolvenKit, WolvenKitConfig
from ..wolvenkit import build_project
from .cancel import CancelToken

logger = logging.getLogger(__name__)

MANIFEST_NAME = ".npv_manifest.json"


@dataclass
class BuildRequest:
    save_path: Path | None
    npv_name: str
    output_dir: Path
    game_dir: Path
    template_cache: Path
    clear_cache: bool = False
    cc_json_path: Path | None = None
    hair_override: str | None = None
    skin_override: str | None = None
    garments: list[str] = field(default_factory=list)
    user_head_glb: Path | None = None
    user_head_mesh: Path | None = None
    user_heb_mesh: Path | None = None
    restore_head_materials: bool = True
    resume: bool = False


@dataclass(frozen=True)
class PipelineEvent:
    kind: str  # "stage_started" | "stage_completed" | "stage_skipped" | "failed" | "finished"
    stage: str | None
    message: str


@dataclass
class BuildResult:
    output_dir: str
    mod_id: str
    stages_run: list[str]
    stages_resumed: list[str]


def _make_wolvenkit(req: BuildRequest, cancel: CancelToken | None) -> WolvenKit:
    wk_config = WolvenKitConfig(game_dir=req.game_dir, verbosity=0, cancel=cancel)
    return WolvenKit(wk_config)


def _run_parse(req: BuildRequest) -> dict:
    """Load CC settings. Replicates orchestrator.run_orchestrator's cc-json handling.

    Three modes:
      save only            -> full CC from the save parser (fallback outfit)
      --cc-json only        -> full CC from the CET dump
      save AND --cc-json    -> CC from the save (head/face/hair are reliable only
                                there), with the dump's `clothing` overlaid so the
                                NPV wears V's equipped outfit. The CET dump cannot
                                reconstruct head CC, so we never let it replace it.
    """
    dump_data = None
    if req.cc_json_path is not None:
        logger.info(f"[CC Loader] Loading CC dump from {req.cc_json_path}...")
        with open(req.cc_json_path) as f:
            dump_data = json.load(f)

    if req.save_path is not None:
        logger.info("[Save Parser] Parsing save file...")
        cc_settings = parse_save(req.save_path)
        # Overlay ONLY the equipped clothing from the dump onto the save CC.
        if dump_data is not None:
            clothing = dump_data.get("clothing", [])
            cc_settings["clothing"] = clothing
            logger.info(
                f"[CC Loader] Overlaid {len(clothing)} equipped garment(s) "
                "from the CET dump onto the save CC."
            )
    else:
        # --cc-json only: the dump is the sole CC source.
        cc_settings = dump_data

    return cc_settings


def _run_assemble(
    req: BuildRequest, wk: WolvenKit, mod_id: str, asset_paths: dict, cc_settings: dict
) -> list[dict]:
    return build_project(
        wk,
        mod_id,
        req.output_dir,
        asset_paths,
        0,
        garment_overrides=req.garments,
        skin_override=req.skin_override,
        user_head_glb=req.user_head_glb,
        user_head_mesh=req.user_head_mesh,
        user_heb_mesh=req.user_heb_mesh,
        restore_head_materials=req.restore_head_materials,
    )


def _hash_input(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_manifest(output_dir: Path) -> dict:
    manifest_path = output_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_manifest(output_dir: Path, manifest: dict) -> None:
    manifest_path = output_dir / MANIFEST_NAME
    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(manifest_path)


class PipelineService:
    STAGES = ("parse_save", "resolve_assets", "assemble", "emit_amm_lua")

    def build(
        self,
        req: BuildRequest,
        on_event: Callable[[PipelineEvent], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> BuildResult:
        def emit(kind: str, stage: str | None, message: str) -> None:
            if on_event is not None:
                on_event(PipelineEvent(kind=kind, stage=stage, message=message))

        req.output_dir.mkdir(parents=True, exist_ok=True)

        if req.clear_cache and req.template_cache.exists():
            shutil.rmtree(req.template_cache)

        manifest = _load_manifest(req.output_dir) if req.resume else {}

        stages_run: list[str] = []
        stages_resumed: list[str] = []

        cc_settings: dict | None = None
        asset_paths: dict | None = None
        mod_id: str | None = None
        wk: WolvenKit | None = None

        current_stage: str | None = None
        try:
            # --- parse_save ---
            current_stage = "parse_save"
            emit("stage_started", current_stage, "Parsing save / CC data...")
            if cancel is not None:
                cancel.raise_if_cancelled()

            save_stat = None
            if req.save_path is not None and req.save_path.exists():
                st = req.save_path.stat()
                save_stat = [st.st_size, st.st_mtime]
            parse_hash = _hash_input(
                [str(req.save_path), save_stat, str(req.cc_json_path)]
            )
            prior = manifest.get(current_stage)
            if req.resume and prior is not None and prior.get("input_hash") == parse_hash:
                cc_settings = prior["output"]
                stages_resumed.append(current_stage)
                emit("stage_skipped", current_stage, "Unchanged, skipping.")
            else:
                cc_settings = _run_parse(req)
                manifest[current_stage] = {
                    "input_hash": parse_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": cc_settings,
                }
                _write_manifest(req.output_dir, manifest)
                stages_run.append(current_stage)
                emit("stage_completed", current_stage, "Parsed CC settings.")

            # WolvenKit adapter is needed from here on.
            wk = _make_wolvenkit(req, cancel)

            # --- resolve_assets ---
            current_stage = "resolve_assets"
            emit("stage_started", current_stage, "Resolving asset paths...")
            if cancel is not None:
                cancel.raise_if_cancelled()

            resolve_hash = _hash_input([cc_settings, req.hair_override, req.garments])
            prior = manifest.get(current_stage)
            if req.resume and prior is not None and prior.get("input_hash") == resolve_hash:
                asset_paths = prior["output"]
                stages_resumed.append(current_stage)
                emit("stage_skipped", current_stage, "Unchanged, skipping.")
            else:
                asset_paths = resolve_assets(
                    cc_settings, req.game_dir, req.hair_override, req.garments, wk
                )
                manifest[current_stage] = {
                    "input_hash": resolve_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": asset_paths,
                }
                _write_manifest(req.output_dir, manifest)
                stages_run.append(current_stage)
                emit("stage_completed", current_stage, "Resolved asset paths.")

            # mod_id is derived, not a stage input/output, but needed downstream.
            from ..orchestrator import compute_mod_id

            mod_id = compute_mod_id(req.npv_name, cc_settings)

            # --- assemble ---
            current_stage = "assemble"
            emit("stage_started", current_stage, "Assembling WolvenKit project...")
            if cancel is not None:
                cancel.raise_if_cancelled()

            # build_project reads cc_settings.json / asset_paths.json from out_dir
            # directly (wolvenkit.py: cc_selections for modded-eye suppression,
            # genital_selection for genital component filtering). Write them
            # unconditionally here — not gated on resolve_assets actually having
            # run this call — so a resumed build that skipped resolve_assets (and
            # therefore never re-wrote these files this process) still has them
            # on disk before build_project runs.
            with open(req.output_dir / "cc_settings.json", "w") as f:
                json.dump(cc_settings, f, indent=2)
            with open(req.output_dir / "asset_paths.json", "w") as f:
                json.dump(asset_paths, f, indent=2)

            assemble_hash = _hash_input(
                [
                    asset_paths,
                    mod_id,
                    req.skin_override,
                    req.garments,
                    str(req.user_head_glb),
                    str(req.user_head_mesh),
                    str(req.user_heb_mesh),
                    req.restore_head_materials,
                ]
            )
            prior = manifest.get(current_stage)
            archive_dir = req.output_dir / "archive" / "pc" / "mod"
            archive_exists = archive_dir.exists() and any(archive_dir.iterdir())
            if (
                req.resume
                and prior is not None
                and prior.get("input_hash") == assemble_hash
                and archive_exists
            ):
                stages_resumed.append(current_stage)
                emit("stage_skipped", current_stage, "Unchanged, skipping.")
            else:
                _run_assemble(req, wk, mod_id, asset_paths, cc_settings)
                manifest[current_stage] = {
                    "input_hash": assemble_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": None,
                }
                _write_manifest(req.output_dir, manifest)
                stages_run.append(current_stage)
                emit("stage_completed", current_stage, "Assembled mod project.")

            # --- emit_amm_lua ---
            current_stage = "emit_amm_lua"
            emit("stage_started", current_stage, "Writing AMM lua script...")
            if cancel is not None:
                cancel.raise_if_cancelled()

            body_rig = asset_paths.get("body_rig", "pwa")
            lua_hash = _hash_input([mod_id, req.npv_name, body_rig, asset_paths])
            prior = manifest.get(current_stage)
            lua_path_str = prior.get("output") if prior else None
            lua_exists = bool(lua_path_str) and Path(lua_path_str).exists()
            if (
                req.resume
                and prior is not None
                and prior.get("input_hash") == lua_hash
                and lua_exists
            ):
                stages_resumed.append(current_stage)
                emit("stage_skipped", current_stage, "Unchanged, skipping.")
            else:
                lua_path = write_amm_lua(
                    mod_id, req.npv_name, body_rig, req.output_dir, asset_paths=asset_paths
                )
                manifest[current_stage] = {
                    "input_hash": lua_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": str(lua_path),
                }
                _write_manifest(req.output_dir, manifest)
                stages_run.append(current_stage)
                emit("stage_completed", current_stage, "Wrote AMM lua script.")

        except Exception as e:
            emit("failed", current_stage, str(e))
            raise

        emit("finished", None, "Build complete.")

        return BuildResult(
            output_dir=str(req.output_dir),
            mod_id=mod_id or "",
            stages_run=stages_run,
            stages_resumed=stages_resumed,
        )


# Imported at module level per the circular-import rule: orchestrator.py imports
# pipeline lazily (inside run_orchestrator's body), so pipeline is free to import
# orchestrator.write_amm_lua at module load time.
from ..orchestrator import write_amm_lua  # noqa: E402
