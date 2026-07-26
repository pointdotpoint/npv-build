"""The build pipeline must emit photomode files as a checkpointed stage.

We test the stage wiring in isolation by driving the same helpers the stage
uses, rather than running a full WolvenKit build. The stage's contract: after
a successful build, the TweakXL yaml and .archive.xl exist under output_dir.
"""

from npv_build.photomode import artifact_paths, write_photomode_registration


def test_emit_photomode_produces_files_under_output(tmp_path):
    # Mirror what the emit_photomode stage does with in-scope build data.
    out = write_photomode_registration(
        mod_id="myv_abc123",
        npv_name="My V",
        body_rig="pwa",
        output_dir=tmp_path,
        artifacts=artifact_paths(tmp_path / "source" / "archive", "myv_abc123"),
    )
    assert (tmp_path / "r6" / "tweaks" / "npv_build" / "myv_abc123_photomode.yaml").exists()
    assert (tmp_path / "archive" / "pc" / "mod" / "myv_abc123.archive.xl").exists()
    assert out["tweak"].exists() and out["xl"].exists()


def test_pipeline_imports_write_photomode_registration():
    from npv_build.core import pipeline

    assert hasattr(pipeline, "write_photomode_registration")
