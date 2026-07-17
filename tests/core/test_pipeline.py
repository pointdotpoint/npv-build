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
    monkeypatch.setattr(pl, "parse_save", lambda p: calls.append("parse_save") or {"patch": "2.13", "body_rig": "pwa"})
    monkeypatch.setattr(
        pl, "resolve_assets",
        lambda cc, game_dir, hair_override, garments, wk: calls.append("resolve_assets") or {"head": "x"},
    )
    monkeypatch.setattr(pl, "_run_assemble", lambda req, wk, mod_id, asset_paths, cc: calls.append("assemble"))
    monkeypatch.setattr(pl, "write_amm_lua", lambda mod_id, npv_name, body_rig, output_dir: calls.append("emit_amm_lua") or output_dir / "x.lua")
    return calls


def _req(tmp_path, **kw) -> BuildRequest:
    save = tmp_path / "sav.dat"
    if not save.exists():  # keep mtime stable across calls — parse_save's input hash includes it
        save.write_bytes(b"fake")
    out = tmp_path / "out"
    defaults = dict(
        save_path=save, npv_name="My V", output_dir=out, game_dir=tmp_path,
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
