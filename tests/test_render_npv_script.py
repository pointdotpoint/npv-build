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


def test_script_camera_faces_plus_y():
    """Regression guard for the live-gate finding (2026-08-06): WolvenKit glb
    exports face +Y, not -Y — confirmed by eye against a real render (camera
    on the -Y side showed the back of the character). If this flips back to
    -Y without a verified reason, every render will show the back again."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "math.cos(yaw) * dist, 0))" in text
    assert "-math.cos(yaw) * dist, 0))" not in text


def test_script_applies_clay_material_to_visible_meshes():
    """Regression guard: WolvenKit's materials-off glb export is a stub
    (pbrMetallicRoughness: {}), which glTF defaults to fully metallic + fully
    rough — with no environment lighting that renders near-black. Verified by
    eye against a real render before this fix landed."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "_apply_clay_material" in text
    assert 'inputs["Metallic"].default_value = 0.0' in text
