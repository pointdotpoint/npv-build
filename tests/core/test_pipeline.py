import json
from pathlib import Path

import pytest
from PIL import Image

import npv_build.core.pipeline as pl
from npv_build.core.cancel import CancelToken
from npv_build.core.errors import NpvError, PipelineCancelled
from npv_build.core.pipeline import BuildRequest, PipelineService


@pytest.fixture
def fake_stages(monkeypatch, tmp_path):
    calls: list[str] = []
    monkeypatch.setattr(pl, "_make_wolvenkit", lambda req, cancel: object())
    monkeypatch.setattr(
        pl,
        "parse_save",
        lambda p: calls.append("parse_save") or {"patch": "2.13", "body_rig": "pwa"},
    )
    monkeypatch.setattr(
        pl,
        "resolve_assets",
        lambda cc, game_dir, hair_override, garments, wk: (
            calls.append("resolve_assets") or {"head": "x"}
        ),
    )

    def fake_assemble(req, wk, mod_id, asset_paths, cc, thumbnail):
        calls.append("assemble")
        # Real build_project produces the installable archive; packaging
        # (which runs after emit_amm_lua) requires it to exist.
        arch_dir = req.output_dir / "archive" / "pc" / "mod"
        arch_dir.mkdir(parents=True, exist_ok=True)
        (arch_dir / f"{mod_id}.archive").write_bytes(b"fake-archive")

    monkeypatch.setattr(pl, "_run_assemble", fake_assemble)

    def fake_write_amm(mod_id, npv_name, body_rig, output_dir, **kw):
        calls.append("emit_amm_lua")
        path = (
            output_dir
            / "bin"
            / "x64"
            / "plugins"
            / "cyber_engine_tweaks"
            / "mods"
            / "AppearanceMenuMod"
            / "Collabs"
            / "Custom Entities"
            / f"{mod_id}.lua"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("return {}", encoding="utf-8")
        return path

    monkeypatch.setattr(pl, "write_amm_lua", fake_write_amm)
    return calls


def _req(tmp_path, **kw) -> BuildRequest:
    save = tmp_path / "sav.dat"
    if not save.exists():  # keep mtime stable across calls — parse_save's input hash includes it
        save.write_bytes(b"fake")
    out = tmp_path / "out"
    thumbnail = tmp_path / "thumbnail.png"
    if not thumbnail.exists():
        Image.new("RGB", (200, 200), "magenta").save(thumbnail)
    defaults = dict(
        save_path=save,
        npv_name="My V",
        output_dir=out,
        game_dir=tmp_path,
        template_cache=tmp_path / "cache",
        photomode_thumbnail=thumbnail,
    )
    defaults.update(kw)
    return BuildRequest(**defaults)


def test_runs_all_stages_in_order(fake_stages, tmp_path):
    result = PipelineService().build(_req(tmp_path))
    assert fake_stages == ["parse_save", "resolve_assets", "assemble", "emit_amm_lua"]
    assert result.stages_run == list(PipelineService.STAGES)


def test_build_result_zip_path_populated(fake_stages, tmp_path):
    result = PipelineService().build(_req(tmp_path))
    assert result.zip_path == str(tmp_path / "out" / result.mod_id) + ".zip"
    assert Path(result.zip_path).exists()
    manifest = json.loads((tmp_path / "out" / ".npv_manifest.json").read_text(encoding="utf-8"))
    assert manifest["format_version"] == 2
    assert manifest["producer_version"] == "2.0.2"
    assert set(manifest["stage_schemas"]) == set(PipelineService.STAGES)
    assert set(manifest["stages"]) == set(PipelineService.STAGES)


def test_events_emitted(fake_stages, tmp_path):
    events = []
    PipelineService().build(_req(tmp_path), on_event=events.append)
    kinds = [e.kind for e in events]
    # 5 checkpointed stages + the post-stage packaging step.
    assert kinds.count("stage_started") == 6
    assert kinds.count("stage_completed") == 6
    assert kinds[-1] == "finished"


def test_build_logs_one_cache_batch_and_resume_summary(fake_stages, tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr(pl.logger, "info", lambda message, *args: messages.append(message % args))

    PipelineService().build(_req(tmp_path))

    assert sum(message.startswith("[Cache]") for message in messages) == 1
    assert sum(message.startswith("[WolvenKit] batched uncook:") for message in messages) == 1
    assert sum(message.startswith("[Resume]") for message in messages) == 1


def test_resume_skips_unchanged_stages(fake_stages, tmp_path, monkeypatch):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()
    # archive artifact must exist for assemble skip
    arch = tmp_path / "out" / "archive" / "pc" / "mod"
    arch.mkdir(parents=True, exist_ok=True)
    (arch / "fake.archive").write_bytes(b"a")
    result = svc.build(_req(tmp_path, resume=True))
    assert "parse_save" not in fake_stages
    assert "resolve_assets" not in fake_stages
    assert result.stages_resumed  # at least one stage skipped


def test_identical_request_with_valid_artifacts_skips_all_checkpointed_stages(
    fake_stages, tmp_path
):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()

    result = svc.build(_req(tmp_path, resume=True))

    assert fake_stages == []
    assert result.stages_resumed == list(PipelineService.STAGES)


def test_zero_byte_expected_archive_forces_assemble_rerun(fake_stages, tmp_path):
    svc = PipelineService()
    first = svc.build(_req(tmp_path))
    fake_stages.clear()
    archive = tmp_path / "out" / "archive" / "pc" / "mod" / f"{first.mod_id}.archive"
    archive.write_bytes(b"")

    result = svc.build(_req(tmp_path, resume=True))

    assert "assemble" in fake_stages
    assert "assemble" in result.stages_run


def test_changed_tool_fingerprint_forces_assemble_rerun(fake_stages, tmp_path, monkeypatch):
    fingerprint = {"wolvenkit": {"path": "/tool", "size": 1, "mtime_ns": 1}}
    monkeypatch.setattr(
        pl,
        "_assemble_tool_fingerprints",
        lambda _wk: fingerprint.copy(),
        raising=False,
    )
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()
    fingerprint["wolvenkit"] = {"path": "/tool", "size": 2, "mtime_ns": 2}

    result = svc.build(_req(tmp_path, resume=True))

    assert "assemble" in fake_stages
    assert "assemble" in result.stages_run


def test_changed_assemble_schema_forces_only_assemble_and_dependents(
    fake_stages, tmp_path, monkeypatch
):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()
    monkeypatch.setitem(
        pl.STAGE_SCHEMAS,
        "assemble",
        pl.STAGE_SCHEMAS["assemble"] + 1,
    )

    result = svc.build(_req(tmp_path, resume=True))

    assert "parse_save" in result.stages_resumed
    assert "resolve_assets" in result.stages_resumed
    assert "assemble" in result.stages_run


def test_resume_reruns_on_changed_input(fake_stages, tmp_path):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()
    req2 = _req(tmp_path, garments=["base/test/changed.mesh"], resume=True)
    result = svc.build(req2)
    assert "parse_save" in result.stages_resumed
    assert "resolve_assets" in fake_stages  # input hash changed -> re-run
    assert "assemble" in fake_stages


def test_garment_appearance_is_part_of_checkpoint_hash(fake_stages, tmp_path):
    shared = {
        "item_id": "Shirt_01_basic_01",
        "name": "TEST SHIRT",
        "slot": "inner_torso",
        "mesh": "base/test/t1_035_pwa_shirt.mesh",
        "appearance": "blue_moro",
        "components": [
            {
                "mesh": "base/test/t1_035_pwa_shirt.mesh",
                "appearance": "blue_moro",
            }
        ],
        "source_kind": "catalog",
    }
    service = PipelineService()
    service.build(_req(tmp_path, garments=[shared]))
    fake_stages.clear()

    changed = {
        **shared,
        "item_id": "Shirt_01_basic_02",
        "appearance": "black_psycho",
        "components": [
            {
                **shared["components"][0],
                "appearance": "black_psycho",
            }
        ],
    }
    service.build(_req(tmp_path, garments=[changed], resume=True))

    assert "resolve_assets" in fake_stages
    assert "assemble" in fake_stages


def test_changed_thumbnail_reruns_assemble_and_photomode_only(fake_stages, tmp_path):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()
    changed_thumbnail = tmp_path / "changed-thumbnail.png"
    Image.new("RGB", (200, 200), "cyan").save(changed_thumbnail)

    result = svc.build(_req(tmp_path, photomode_thumbnail=changed_thumbnail, resume=True))

    assert "parse_save" in result.stages_resumed
    assert "resolve_assets" in result.stages_resumed
    assert "assemble" in result.stages_run
    assert "emit_photomode" in result.stages_run


def test_changed_name_reruns_mod_id_dependent_stages(fake_stages, tmp_path):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()

    result = svc.build(_req(tmp_path, npv_name="Renamed V", resume=True))

    assert "parse_save" in result.stages_resumed
    assert "resolve_assets" in result.stages_resumed
    assert {"assemble", "emit_amm_lua", "emit_photomode"} <= set(result.stages_run)


@pytest.mark.parametrize(
    "manifest_text",
    [
        '{"parse_save": {"input_hash": "legacy"}}',
        "{not-json",
        '{"format_version": 99, "stages": {}}',
    ],
)
def test_legacy_corrupt_or_future_manifest_is_a_clean_miss(fake_stages, tmp_path, manifest_text):
    req = _req(tmp_path, resume=True)
    req.output_dir.mkdir(parents=True, exist_ok=True)
    (req.output_dir / pl.MANIFEST_NAME).write_text(manifest_text, encoding="utf-8")

    result = PipelineService().build(req)

    assert result.stages_run == list(PipelineService.STAGES)


def test_cancel_before_stage(fake_stages, tmp_path):
    token = CancelToken()
    token.cancel()
    with pytest.raises(PipelineCancelled):
        PipelineService().build(_req(tmp_path), cancel=token)
    assert fake_stages == []


def test_build_raises_actionable_error_when_game_dir_none(fake_stages, tmp_path):
    """game_dir is Path | None (e.g. GUI settings not configured yet). Rather
    than blowing up deep in WolvenKitConfig/resolve_assets with an opaque
    TypeError, PipelineService.build must guard at the top and raise an
    NpvError with remediation telling the user how to fix it."""
    req = _req(tmp_path, game_dir=None)
    with pytest.raises(NpvError) as exc_info:
        PipelineService().build(req)
    assert "game dir" in exc_info.value.user_message.lower()
    assert exc_info.value.remediation
    # Must fail before any stage runs.
    assert fake_stages == []


def test_failed_event_on_stage_error(fake_stages, tmp_path, monkeypatch):
    def boom(cc, game_dir, hair_override, garments, wk):
        raise RuntimeError("resolver died")

    monkeypatch.setattr(pl, "resolve_assets", boom)
    events = []
    with pytest.raises(RuntimeError):
        PipelineService().build(_req(tmp_path), on_event=events.append)
    assert any(e.kind == "failed" and e.stage == "resolve_assets" for e in events)


def test_cc_settings_and_asset_paths_json_written_before_assemble(
    fake_stages, tmp_path, monkeypatch
):
    # build_project (invoked inside _run_assemble) reads cc_settings.json and
    # asset_paths.json directly from output_dir via `open(...)` — not via any
    # in-memory argument. If the pipeline stops writing these files, build_project's
    # modded-eye suppression and genital-component filtering silently no-op. Assert
    # the files exist with the expected content at the moment _run_assemble runs.
    seen = {}

    def fake_assemble(req, wk, mod_id, asset_paths, cc, thumbnail):
        cc_file = req.output_dir / "cc_settings.json"
        asset_file = req.output_dir / "asset_paths.json"
        seen["cc_exists"] = cc_file.exists()
        seen["asset_exists"] = asset_file.exists()
        seen["cc_content"] = json.loads(cc_file.read_text()) if cc_file.exists() else None
        seen["asset_content"] = json.loads(asset_file.read_text()) if asset_file.exists() else None
        arch_dir = req.output_dir / "archive" / "pc" / "mod"
        arch_dir.mkdir(parents=True, exist_ok=True)
        (arch_dir / f"{mod_id}.archive").write_bytes(b"fake-archive")

    monkeypatch.setattr(pl, "_run_assemble", fake_assemble)

    PipelineService().build(_req(tmp_path))

    assert seen["cc_exists"], "cc_settings.json must exist on disk before build_project runs"
    assert seen["asset_exists"], "asset_paths.json must exist on disk before build_project runs"
    assert seen["cc_content"] == {"patch": "2.13", "body_rig": "pwa"}
    assert seen["asset_content"] == {"head": "x"}

    # Also still present after the full build (not deleted by a later stage).
    out = tmp_path / "out"
    assert json.loads((out / "cc_settings.json").read_text()) == {
        "patch": "2.13",
        "body_rig": "pwa",
    }
    assert json.loads((out / "asset_paths.json").read_text()) == {"head": "x"}


def test_cc_settings_json_rewritten_on_resume_even_if_resolve_assets_skipped(fake_stages, tmp_path):
    # Simulate the resume path: resolve_assets is skipped (cached), but
    # build_project must still find cc_settings.json / asset_paths.json on disk
    # for THIS process invocation, since it re-reads them fresh each run.
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()

    out = tmp_path / "out"
    # Simulate a fresh process: delete the diagnostic JSON files that a prior
    # process run would have written, but keep the manifest + archive artifact
    # so resolve_assets/assemble are eligible to be skipped on resume.
    (out / "cc_settings.json").unlink()
    (out / "asset_paths.json").unlink()
    arch = out / "archive" / "pc" / "mod"
    arch.mkdir(parents=True, exist_ok=True)
    (arch / "fake.archive").write_bytes(b"a")

    svc.build(_req(tmp_path, resume=True))

    assert "resolve_assets" not in fake_stages  # confirms it really was skipped
    assert (out / "cc_settings.json").exists()
    assert (out / "asset_paths.json").exists()


def test_emit_amm_lua_includes_external_dependency_warning(fake_stages, tmp_path, monkeypatch):
    from npv_build.orchestrator import write_amm_lua as real_write_amm_lua

    monkeypatch.setattr(pl, "write_amm_lua", real_write_amm_lua)
    asset_paths_with_dep = {
        "head": "x",
        "body_rig": "pwa",
        "external_dependencies": [
            {"selection": "fhair_02", "reason": "modded hair not in base game"},
        ],
        "unresolved": [],
    }
    monkeypatch.setattr(
        pl,
        "resolve_assets",
        lambda cc, game_dir, hair_override, garments, wk: asset_paths_with_dep,
    )

    result = PipelineService().build(_req(tmp_path))

    lua_dir = (
        tmp_path
        / "out"
        / "bin"
        / "x64"
        / "plugins"
        / "cyber_engine_tweaks"
        / "mods"
        / "AppearanceMenuMod"
        / "Collabs"
        / "Custom Entities"
    )
    lua_files = list(lua_dir.glob("*.lua"))
    assert len(lua_files) == 1
    lua_text = lua_files[0].read_text(encoding="utf-8")
    assert (
        "-- WARNING: External mod dependency: fhair_02 (modded hair not in base game)" in lua_text
    )
    assert result.mod_id
