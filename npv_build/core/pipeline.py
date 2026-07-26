"""Checkpointing pipeline service both frontends drive (spec CORE-1..4)."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .. import __version__
from ..gui_logic.appearance import apply_overrides
from ..mapping import resolve_assets
from ..photomode import (
    artifact_paths,
    photomode_helper_binary,
    runtime_dependency_status,
    validate_thumbnail,
    write_photomode_registration,
)
from ..save_parser import parse_save
from ..wk_cli import WolvenKit, WolvenKitConfig
from ..wolvenkit import build_project
from .artifact_cache import ArtifactCache
from .cancel import CancelToken
from .errors import NpvError
from .packaging import package_mod

logger = logging.getLogger(__name__)

MANIFEST_NAME = ".npv_manifest.json"
MANIFEST_FORMAT_VERSION = 2
STAGE_SCHEMAS = {
    "parse_save": 2,
    "resolve_assets": 2,
    "assemble": 2,
    "emit_amm_lua": 1,
    "emit_photomode": 1,
}


@dataclass
class BuildRequest:
    save_path: Path | None
    npv_name: str
    output_dir: Path
    game_dir: Path | None
    template_cache: Path
    clear_cache: bool = False
    cc_json_path: Path | None = None
    cc_settings_override: dict | None = None
    hair_override: str | None = None
    skin_override: str | None = None
    garments: list[str | dict] = field(default_factory=list)
    cc_overrides: dict = field(default_factory=dict)
    user_head_glb: Path | None = None
    user_head_mesh: Path | None = None
    user_heb_mesh: Path | None = None
    restore_head_materials: bool = True
    photomode_thumbnail: Path | None = None
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
    zip_path: str | None = None
    stage_durations: dict[str, float] = field(default_factory=dict)
    tool_stats: dict[str, int] = field(default_factory=dict)


def _make_wolvenkit(req: BuildRequest, cancel: CancelToken | None) -> WolvenKit:
    wk_config = WolvenKitConfig(
        game_dir=req.game_dir,
        verbosity=0,
        cancel=cancel,
        artifact_cache=ArtifactCache(req.template_cache),
    )
    return WolvenKit(wk_config)


def _run_parse(req: BuildRequest) -> dict:
    """Load CC settings. Replicates orchestrator.run_orchestrator's cc-json handling.

    File-based modes:
      save only            -> full CC from the save parser (fallback outfit)
      --cc-json only        -> full CC from the CET dump
      save AND --cc-json    -> CC from the save (head/face/hair are reliable only
                                there), with the dump's `clothing` overlaid so the
                                NPV wears V's equipped outfit. The CET dump cannot
                                reconstruct head CC, so we never let it replace it.

    A settings override is the sole source for a from-scratch preset build and
    cannot be combined with either file-based source.
    """
    sources = [
        source
        for source in (req.save_path, req.cc_json_path, req.cc_settings_override)
        if source is not None
    ]
    if len(sources) > 1 and req.cc_settings_override is not None:
        raise NpvError(
            "A preset build cannot also use a save or CC dump.",
            remediation="Provide exactly one CC source.",
        )
    if not sources:
        raise NpvError(
            "No CC source provided.",
            remediation="Provide a save file, a --cc-json dump, or a preset.",
        )
    if req.cc_settings_override is not None:
        logger.info("[CC Loader] Using preset CC settings (from-scratch build).")
        return copy.deepcopy(req.cc_settings_override)

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
    req: BuildRequest,
    wk: WolvenKit,
    mod_id: str,
    asset_paths: dict,
    cc_settings: dict,
    thumbnail,
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
        npv_name=req.npv_name,
        photomode_thumbnail=thumbnail,
        artifact_cache=wk.config.artifact_cache,
    )


def _hash_input(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stage_hash(stage: str, payload: object) -> str:
    return _hash_input([STAGE_SCHEMAS[stage], payload])


def _new_manifest() -> dict:
    return {
        "format_version": MANIFEST_FORMAT_VERSION,
        "producer_version": __version__,
        "stage_schemas": dict(STAGE_SCHEMAS),
        "stages": {},
    }


def _load_manifest(output_dir: Path) -> dict:
    manifest_path = output_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return _new_manifest()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _new_manifest()
    if (
        not isinstance(manifest, dict)
        or manifest.get("format_version") != MANIFEST_FORMAT_VERSION
        or not isinstance(manifest.get("stages"), dict)
    ):
        return _new_manifest()
    return manifest


def _write_manifest(output_dir: Path, manifest: dict) -> None:
    manifest["format_version"] = MANIFEST_FORMAT_VERSION
    manifest["producer_version"] = __version__
    manifest["stage_schemas"] = dict(STAGE_SCHEMAS)
    manifest_path = output_dir / MANIFEST_NAME
    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(manifest_path)


def _expected_assemble_artifacts(output_dir: Path, mod_id: str) -> list[str]:
    archive_dir = output_dir / "archive" / "pc" / "mod"
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
    return [
        str(archive_dir / f"{mod_id}.archive"),
        str(archive_dir / f"{mod_id}.archive.xl"),
        str(output_dir / "r6" / "tweaks" / "npv_build" / f"{mod_id}_photomode.yaml"),
        str(lua_dir / f"{mod_id}.lua"),
    ]


def _artifacts_are_nonempty(paths: object) -> bool:
    return (
        isinstance(paths, list)
        and bool(paths)
        and all(
            isinstance(path, str)
            and Path(path).is_file()
            and Path(path).stat().st_size > 0
            for path in paths
        )
    )


def _file_fingerprint(candidate: str | Path) -> dict:
    path = Path(candidate).expanduser()
    if not path.is_file():
        resolved = shutil.which(str(candidate))
        if resolved is None:
            return {"path": str(candidate), "missing": True}
        path = Path(resolved)
    path = path.resolve()
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _executable_fingerprint(candidate: str | Path) -> dict:
    fingerprint = {"executable": _file_fingerprint(candidate)}
    path = Path(candidate).expanduser()
    if path.is_file():
        companion = path.with_suffix(".dll")
        if companion.is_file():
            fingerprint["managed_dll"] = _file_fingerprint(companion)
    return fingerprint


def _assemble_tool_fingerprints(wk: WolvenKit) -> dict:
    # Unit-test doubles do not resolve external binaries. Their identity is
    # stable within a test; production WolvenKit instances include every tool
    # whose output is consumed by assembly.
    if not isinstance(wk, WolvenKit):
        return {"wolvenkit": {"test_double": type(wk).__name__}}

    from ..wolvenkit import _resolve_inject_binary

    return {
        "wolvenkit": _executable_fingerprint(wk.executable_path()),
        "npv_inject": _executable_fingerprint(_resolve_inject_binary()),
        "photomode_helper": _executable_fingerprint(photomode_helper_binary()),
    }


class PipelineService:
    STAGES = ("parse_save", "resolve_assets", "assemble", "emit_amm_lua", "emit_photomode")

    def build(
        self,
        req: BuildRequest,
        on_event: Callable[[PipelineEvent], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> BuildResult:
        stage_durations: dict[str, float] = {}
        stage_started_at: dict[str, float] = {}

        def emit(kind: str, stage: str | None, message: str) -> None:
            if stage is not None:
                if kind == "stage_started":
                    stage_started_at[stage] = time.perf_counter()
                elif kind in {"stage_completed", "stage_skipped", "failed"}:
                    started_at = stage_started_at.pop(stage, None)
                    if started_at is not None:
                        stage_durations[stage] = max(
                            0.0, time.perf_counter() - started_at
                        )
            if on_event is not None:
                on_event(PipelineEvent(kind=kind, stage=stage, message=message))

        if req.game_dir is None:
            raise NpvError(
                "No game directory configured",
                remediation="Set --game-dir or configure it in the GUI settings.",
            )
        req.output_dir.mkdir(parents=True, exist_ok=True)
        missing_runtime = [
            name
            for name, installed in runtime_dependency_status(req.game_dir).items()
            if not installed
        ]
        if missing_runtime:
            logger.warning(
                "[Photo Mode] Runtime dependencies not detected in this game install: %s",
                ", ".join(missing_runtime),
            )

        if req.clear_cache and req.template_cache.exists():
            shutil.rmtree(req.template_cache)

        manifest = _load_manifest(req.output_dir) if req.resume else _new_manifest()
        stage_manifest = manifest["stages"]

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
            parse_hash = _stage_hash(
                current_stage,
                [
                    str(req.save_path),
                    save_stat,
                    str(req.cc_json_path),
                    req.cc_settings_override,
                ]
            )
            prior = stage_manifest.get(current_stage)
            if req.resume and prior is not None and prior.get("input_hash") == parse_hash:
                cc_settings = prior["output"]
                stages_resumed.append(current_stage)
                emit(
                    "stage_skipped",
                    current_stage,
                    "Unchanged — reused previous output.",
                )
            else:
                cc_settings = _run_parse(req)
                stage_manifest[current_stage] = {
                    "input_hash": parse_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": cc_settings,
                }
                _write_manifest(req.output_dir, manifest)
                stages_run.append(current_stage)
                emit("stage_completed", current_stage, "Parsed CC settings.")

            # Apply GUI overrides to a copy; the checkpoint above stored the
            # raw parse so a later overrides change still resumes parse_save.
            if req.cc_overrides:
                cc_settings = apply_overrides(cc_settings, req.cc_overrides)

            # WolvenKit adapter is needed from here on.
            wk = _make_wolvenkit(req, cancel)

            # --- resolve_assets ---
            current_stage = "resolve_assets"
            emit("stage_started", current_stage, "Resolving asset paths...")
            if cancel is not None:
                cancel.raise_if_cancelled()

            resolve_hash = _stage_hash(
                current_stage, [cc_settings, req.hair_override, req.garments]
            )
            prior = stage_manifest.get(current_stage)
            if req.resume and prior is not None and prior.get("input_hash") == resolve_hash:
                asset_paths = prior["output"]
                stages_resumed.append(current_stage)
                emit(
                    "stage_skipped",
                    current_stage,
                    "Unchanged — reused previous output.",
                )
            else:
                asset_paths = resolve_assets(
                    cc_settings, req.game_dir, req.hair_override, req.garments, wk
                )
                stage_manifest[current_stage] = {
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
            if req.photomode_thumbnail is None:
                raise NpvError(
                    "A Photo Mode thumbnail is required.",
                    remediation="Choose a PNG, JPEG, or WebP image at least 200x200 pixels.",
                )
            thumbnail = validate_thumbnail(req.photomode_thumbnail)

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

            assemble_hash = _stage_hash(
                current_stage,
                [
                    asset_paths,
                    mod_id,
                    req.skin_override,
                    req.garments,
                    str(req.user_head_glb),
                    str(req.user_head_mesh),
                    str(req.user_heb_mesh),
                    req.restore_head_materials,
                    thumbnail.sha256,
                    _assemble_tool_fingerprints(wk),
                ]
            )
            prior = stage_manifest.get(current_stage)
            expected_artifacts = _expected_assemble_artifacts(req.output_dir, mod_id)
            prior_artifacts = prior.get("output") if prior else None
            if (
                req.resume
                and prior is not None
                and prior.get("input_hash") == assemble_hash
                and prior_artifacts == expected_artifacts
                and _artifacts_are_nonempty(prior_artifacts)
            ):
                stages_resumed.append(current_stage)
                emit(
                    "stage_skipped",
                    current_stage,
                    "Unchanged — reused previous output.",
                )
            else:
                _run_assemble(req, wk, mod_id, asset_paths, cc_settings, thumbnail)
                stage_manifest[current_stage] = {
                    "input_hash": assemble_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": expected_artifacts,
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
            lua_hash = _stage_hash(
                current_stage, [mod_id, req.npv_name, body_rig, asset_paths]
            )
            prior = stage_manifest.get(current_stage)
            lua_path_str = prior.get("output") if prior else None
            lua_exists = bool(lua_path_str) and Path(lua_path_str).exists()
            if (
                req.resume
                and prior is not None
                and prior.get("input_hash") == lua_hash
                and lua_exists
            ):
                stages_resumed.append(current_stage)
                emit(
                    "stage_skipped",
                    current_stage,
                    "Unchanged — reused previous output.",
                )
            else:
                lua_path = write_amm_lua(
                    mod_id, req.npv_name, body_rig, req.output_dir, asset_paths=asset_paths
                )
                stage_manifest[current_stage] = {
                    "input_hash": lua_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": str(lua_path),
                }
                _write_manifest(req.output_dir, manifest)
                stages_run.append(current_stage)
                emit("stage_completed", current_stage, "Wrote AMM lua script.")

            # --- emit_photomode ---
            current_stage = "emit_photomode"
            emit("stage_started", current_stage, "Writing Photo Mode files...")
            if cancel is not None:
                cancel.raise_if_cancelled()

            pm_hash = _stage_hash(
                current_stage, [mod_id, req.npv_name, body_rig, thumbnail.sha256]
            )
            prior = stage_manifest.get(current_stage)
            pm_output = prior.get("output") if prior else None
            pm_exists = bool(pm_output) and Path(pm_output).exists()
            if (
                req.resume
                and prior is not None
                and prior.get("input_hash") == pm_hash
                and pm_exists
            ):
                stages_resumed.append(current_stage)
                emit(
                    "stage_skipped",
                    current_stage,
                    "Unchanged — reused previous output.",
                )
            else:
                pm_paths = write_photomode_registration(
                    mod_id=mod_id,
                    npv_name=req.npv_name,
                    body_rig=body_rig,
                    output_dir=req.output_dir,
                    artifacts=artifact_paths(req.output_dir / "source" / "archive", mod_id),
                )
                stage_manifest[current_stage] = {
                    "input_hash": pm_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": str(pm_paths["tweak"]),
                }
                _write_manifest(req.output_dir, manifest)
                stages_run.append(current_stage)
                emit("stage_completed", current_stage, "Wrote Photo Mode files.")

            # --- package (post-stage, not checkpointed) ---
            # Packaging just re-zips the already-checkpointed archive/ + bin/
            # output of assemble/emit_amm_lua. It's cheap and deterministic, so
            # there's no resume benefit to tracking it in the manifest — always
            # re-run it after a successful build instead.
            current_stage = "package"
            emit("stage_started", current_stage, "Packaging mod zip...")
            if cancel is not None:
                cancel.raise_if_cancelled()

            zip_path = package_mod(req.output_dir, mod_id)
            emit("stage_completed", current_stage, f"Wrote mod zip to {zip_path}.")

        except Exception as e:
            emit("failed", current_stage, str(e))
            raise

        stats = getattr(wk, "stats", None)
        tool_stats = {
            "uncook_json_hits": int(getattr(stats, "cache_hits", 0)),
            "uncook_json_misses": int(getattr(stats, "cache_misses", 0)),
            "batched_uncook_processes": int(getattr(stats, "batch_processes", 0)),
            "batched_uncook_resources": int(getattr(stats, "batch_resources", 0)),
        }
        logger.info(
            "[Cache] uncook JSON: %d hits, %d misses",
            tool_stats["uncook_json_hits"],
            tool_stats["uncook_json_misses"],
        )
        logger.info(
            "[WolvenKit] batched uncook: %d processes, %d resources",
            tool_stats["batched_uncook_processes"],
            tool_stats["batched_uncook_resources"],
        )
        logger.info(
            "[Resume] reused %d/%d checkpointed stages",
            len(stages_resumed),
            len(self.STAGES),
        )
        emit("finished", None, "Build complete.")

        return BuildResult(
            output_dir=str(req.output_dir),
            mod_id=mod_id or "",
            stages_run=stages_run,
            stages_resumed=stages_resumed,
            zip_path=str(zip_path),
            stage_durations=stage_durations,
            tool_stats=tool_stats,
        )


# Imported at module level per the circular-import rule: orchestrator.py imports
# pipeline lazily (inside run_orchestrator's body), so pipeline is free to import
# orchestrator.write_amm_lua at module load time.
from ..orchestrator import write_amm_lua  # noqa: E402
