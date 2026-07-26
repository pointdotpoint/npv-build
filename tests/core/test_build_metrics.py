from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

import npv_build.core.pipeline as pipeline
from npv_build.core.pipeline import BuildRequest, PipelineService
from scripts.benchmark_build import BenchmarkWorkspace


def test_cold_benchmark_clears_only_sentinel_owned_directories(tmp_path: Path) -> None:
    output_dir = tmp_path / "benchmark-output"
    cache_dir = tmp_path / "benchmark-cache"
    unrelated = tmp_path / "keep-me"
    unrelated.mkdir()
    (unrelated / "data").write_text("safe", encoding="utf-8")

    workspace = BenchmarkWorkspace(output_dir=output_dir, cache_dir=cache_dir)
    workspace.claim()
    (output_dir / "old").write_text("remove", encoding="utf-8")
    (cache_dir / "old").write_text("remove", encoding="utf-8")

    workspace.prepare("cold")

    assert not (output_dir / "old").exists()
    assert not (cache_dir / "old").exists()
    assert (unrelated / "data").read_text(encoding="utf-8") == "safe"


def test_build_result_reports_serializable_duration_for_every_stage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    thumbnail = tmp_path / "thumbnail.png"
    thumbnail.write_bytes(b"png")

    monkeypatch.setattr(
        "npv_build.core.pipeline.parse_save",
        lambda _path: {"body_rig": "pwa"},
    )
    monkeypatch.setattr(
        "npv_build.core.pipeline.resolve_assets",
        lambda *_args: {"body_rig": "pwa"},
    )
    monkeypatch.setattr(
        pipeline,
        "_make_wolvenkit",
        lambda _req, _cancel: object(),
    )

    def fake_assemble(req, _wk, mod_id, _resolved, _cc_settings, _thumbnail):
        archive_dir = req.output_dir / "archive" / "pc" / "mod"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / f"{mod_id}.archive").write_bytes(b"archive")

    monkeypatch.setattr(
        pipeline,
        "_run_assemble",
        fake_assemble,
    )
    monkeypatch.setattr(
        "npv_build.core.pipeline.write_amm_lua",
        lambda *_args, **_kwargs: None,
    )
    Image.new("RGB", (200, 200), "magenta").save(thumbnail)

    result = PipelineService().build(
        BuildRequest(
            save_path=None,
            output_dir=tmp_path / "output",
            game_dir=tmp_path / "game",
            template_cache=tmp_path / "cache",
            npv_name="Timing Test",
            cc_settings_override={
                "skin_tone": "01",
                "archetype": "pwa",
                "body_gender": "Female",
                "arms_gender": "Female",
            },
            photomode_thumbnail=thumbnail,
        )
    )

    assert set(result.stage_durations) == {
        "parse_save",
        "resolve_assets",
        "assemble",
        "emit_amm_lua",
        "emit_photomode",
        "package",
    }
    assert all(duration >= 0 for duration in result.stage_durations.values())
    json.dumps(result.stage_durations)

    resumed = PipelineService().build(
        BuildRequest(
            save_path=None,
            output_dir=tmp_path / "output",
            game_dir=tmp_path / "game",
            template_cache=tmp_path / "cache",
            npv_name="Timing Test",
            cc_settings_override={
                "skin_tone": "01",
                "archetype": "pwa",
                "body_gender": "Female",
                "arms_gender": "Female",
            },
            photomode_thumbnail=thumbnail,
            resume=True,
        )
    )
    assert resumed.stages_resumed
    assert set(resumed.stage_durations) == set(result.stage_durations)
    assert all(duration >= 0 for duration in resumed.stage_durations.values())
