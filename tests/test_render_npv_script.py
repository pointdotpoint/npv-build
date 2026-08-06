import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "npv_build" / "data" / "blender" / "render_npv.py"


def test_script_parses():
    ast.parse(SCRIPT.read_text(encoding="utf-8"))


def test_script_takes_manifest_after_dashdash():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'argv.index("--")' in text and "manifest" in text


def test_script_handles_chunk_mask_and_lod():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "chunk_mask" in text and "submesh" in text
    assert "LOD" in text  # keeps LOD 1 only


def test_script_renders_every_view_deterministically():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "bpy.ops.render.render" in text and "write_still=True" in text
    assert "views" in text and "yaw_deg" in text
    for banned in ("random", "time.time", "datetime"):
        assert banned not in text
