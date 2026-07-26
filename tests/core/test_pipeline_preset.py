import json

import pytest

from npv_build.core.errors import NpvError
from npv_build.core.pipeline import BuildRequest, PipelineService, _run_parse

CC = {
    "patch": "2.31",
    "body_rig": "pma",
    "selections": [],
    "head": {},
    "eyes": {},
    "teeth": {},
    "skin": {"tone_id": "01"},
    "hair": {"style_id": "x"},
    "overlays": [],
    "face_morphs": {},
}


def _req(tmp_path, **kwargs):
    return BuildRequest(
        save_path=None,
        npv_name="V",
        output_dir=tmp_path / "o",
        game_dir=tmp_path,
        template_cache=tmp_path / "tc",
        **kwargs,
    )


def test_run_parse_returns_copy_of_override(tmp_path):
    req = _req(tmp_path, cc_settings_override=CC)
    out = _run_parse(req)
    assert out == CC
    assert out is not CC
    assert out["skin"] is not CC["skin"]


def test_override_is_exclusive_with_save(tmp_path, synth_save_2310):
    req = _req(tmp_path, cc_settings_override=CC)
    req.save_path = synth_save_2310
    with pytest.raises(NpvError):
        _run_parse(req)


def test_override_is_exclusive_with_cc_json(tmp_path):
    req = _req(
        tmp_path,
        cc_json_path=tmp_path / "cc.json",
        cc_settings_override=CC,
    )
    with pytest.raises(NpvError):
        _run_parse(req)


def test_no_cc_source_is_an_error(tmp_path):
    with pytest.raises(NpvError):
        _run_parse(_req(tmp_path))


def test_preset_build_resumes_parse_stage(monkeypatch, tmp_path):
    def stop_after_parse(*args, **kwargs):
        raise RuntimeError("stop")

    monkeypatch.setattr("npv_build.core.pipeline.resolve_assets", stop_after_parse)
    req = _req(tmp_path, cc_settings_override=CC)
    with pytest.raises(RuntimeError, match="stop"):
        PipelineService().build(req)

    req2 = _req(tmp_path, cc_settings_override=CC, resume=True)
    events = []
    with pytest.raises(RuntimeError, match="stop"):
        PipelineService().build(req2, on_event=events.append)

    manifest = json.loads((tmp_path / "o" / ".npv_manifest.json").read_text())
    assert manifest["stages"]["parse_save"]["output"]["body_rig"] == "pma"
    assert any(
        event.kind == "stage_skipped" and event.stage == "parse_save"
        for event in events
    )


def test_changed_preset_invalidates_parse_checkpoint(monkeypatch, tmp_path):
    def stop_after_parse(*args, **kwargs):
        raise RuntimeError("stop")

    monkeypatch.setattr("npv_build.core.pipeline.resolve_assets", stop_after_parse)
    with pytest.raises(RuntimeError, match="stop"):
        PipelineService().build(_req(tmp_path, cc_settings_override=CC))

    changed = {**CC, "body_rig": "pwa"}
    events = []
    with pytest.raises(RuntimeError, match="stop"):
        PipelineService().build(
            _req(tmp_path, cc_settings_override=changed, resume=True),
            on_event=events.append,
        )

    manifest = json.loads((tmp_path / "o" / ".npv_manifest.json").read_text())
    assert manifest["stages"]["parse_save"]["output"]["body_rig"] == "pwa"
    assert any(
        event.kind == "stage_completed" and event.stage == "parse_save"
        for event in events
    )
