"""cc_overrides apply after the parse checkpoint and change the mod id."""
import pytest

from npv_build.core.pipeline import BuildRequest, PipelineService


def _req(tmp_path, overrides):
    return BuildRequest(
        save_path=tmp_path / "sav.dat", npv_name="V", output_dir=tmp_path / "o",
        game_dir=tmp_path, template_cache=tmp_path / "tc",
        cc_overrides=overrides,
    )


def test_overrides_reach_resolve_and_mod_id(monkeypatch, tmp_path, synth_save_2310):
    seen = {}

    def fake_resolve(cc, game_dir, hair_override, garments, wk):
        seen["cc"] = cc
        raise RuntimeError("stop after resolve")  # don't run the real assemble

    monkeypatch.setattr("npv_build.core.pipeline.resolve_assets", fake_resolve)
    req = _req(tmp_path, {"skin_tone": "03_ca_medium"})
    req.save_path = synth_save_2310
    with pytest.raises(RuntimeError):
        PipelineService().build(req)
    assert seen["cc"]["skin"]["tone_id"] == "03_ca_medium"


def test_parse_checkpoint_stores_unmodified_cc(monkeypatch, tmp_path, synth_save_2310):
    import json

    def fake_resolve(cc, *a, **k):
        raise RuntimeError("stop")

    monkeypatch.setattr("npv_build.core.pipeline.resolve_assets", fake_resolve)
    req = _req(tmp_path, {"skin_tone": "03_ca_medium"})
    req.save_path = synth_save_2310
    with pytest.raises(RuntimeError):
        PipelineService().build(req)
    manifest = json.loads((req.output_dir / ".npv_manifest.json").read_text())
    stored = manifest["parse_save"]["output"]
    assert stored["skin"]["tone_id"] != "03_ca_medium"  # checkpoint = raw parse


def test_unknown_override_slot_fails_the_build(tmp_path, synth_save_2310):
    req = _req(tmp_path, {"bogus_slot": "x"})
    req.save_path = synth_save_2310
    with pytest.raises(ValueError):
        PipelineService().build(req)
