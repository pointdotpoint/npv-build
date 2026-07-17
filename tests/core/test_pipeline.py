import json

import pytest

import npv_build.core.pipeline as pl
from npv_build.core.cancel import CancelToken
from npv_build.core.errors import PipelineCancelled
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
    monkeypatch.setattr(
        pl, "_run_assemble", lambda req, wk, mod_id, asset_paths, cc: calls.append("assemble")
    )
    monkeypatch.setattr(
        pl,
        "write_amm_lua",
        lambda mod_id, npv_name, body_rig, output_dir, **kw: (
            calls.append("emit_amm_lua") or output_dir / "x.lua"
        ),
    )
    return calls


def _req(tmp_path, **kw) -> BuildRequest:
    save = tmp_path / "sav.dat"
    if not save.exists():  # keep mtime stable across calls — parse_save's input hash includes it
        save.write_bytes(b"fake")
    out = tmp_path / "out"
    defaults = dict(
        save_path=save,
        npv_name="My V",
        output_dir=out,
        game_dir=tmp_path,
        template_cache=tmp_path / "cache",
    )
    defaults.update(kw)
    return BuildRequest(**defaults)


def test_runs_all_stages_in_order(fake_stages, tmp_path):
    result = PipelineService().build(_req(tmp_path))
    assert fake_stages == ["parse_save", "resolve_assets", "assemble", "emit_amm_lua"]
    assert result.stages_run == list(PipelineService.STAGES)
    manifest = json.loads((tmp_path / "out" / ".npv_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == set(PipelineService.STAGES)


def test_events_emitted(fake_stages, tmp_path):
    events = []
    PipelineService().build(_req(tmp_path), on_event=events.append)
    kinds = [e.kind for e in events]
    assert kinds.count("stage_started") == 4
    assert kinds.count("stage_completed") == 4
    assert kinds[-1] == "finished"


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


def test_resume_reruns_on_changed_input(fake_stages, tmp_path):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()
    req2 = _req(tmp_path, hair_override="hair_02", resume=True)
    svc.build(req2)
    assert "resolve_assets" in fake_stages  # input hash changed -> re-run


def test_cancel_before_stage(fake_stages, tmp_path):
    token = CancelToken()
    token.cancel()
    with pytest.raises(PipelineCancelled):
        PipelineService().build(_req(tmp_path), cancel=token)
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

    def fake_assemble(req, wk, mod_id, asset_paths, cc):
        cc_file = req.output_dir / "cc_settings.json"
        asset_file = req.output_dir / "asset_paths.json"
        seen["cc_exists"] = cc_file.exists()
        seen["asset_exists"] = asset_file.exists()
        seen["cc_content"] = json.loads(cc_file.read_text()) if cc_file.exists() else None
        seen["asset_content"] = json.loads(asset_file.read_text()) if asset_file.exists() else None

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
