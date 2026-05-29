import json
from pathlib import Path
from npv_build.project_writer import write_components_json, write_readme


def test_components_json_structure(tmp_path):
    specs = [
        {"comp_type": "entMorphTargetSkinnedMeshComponent",
         "name": "MorphTargetSkinnedMesh7243",
         "mesh": "base\\characters\\head\\my_head.mesh",
         "appearance": "01_ca_pale",
         "morph_resource": "base\\characters\\head\\my_morphs.morphtarget",
         "source": "baked head"},
        {"comp_type": "entSkinnedMeshComponent",
         "name": "hair_1",
         "mesh": "base\\hair\\mesh.mesh",
         "appearance": "molten_marmalade",
         "source": "modded hair"},
    ]
    out = tmp_path / "npv_components.json"
    write_components_json(specs, "my_npv_abc_appearance", out)
    data = json.loads(out.read_text())
    assert data["appearance_name"] == "my_npv_abc_appearance"
    assert len(data["components"]) == 2
    c0 = data["components"][0]
    assert c0["type"] == "entMorphTargetSkinnedMeshComponent"
    assert c0["name"] == "MorphTargetSkinnedMesh7243"
    assert c0["meshAppearance"] == "01_ca_pale"
    assert c0["morphResource"] == "base\\characters\\head\\my_morphs.morphtarget"
    assert c0["bindTo"] == "face_rig"
    assert c0["source"] == "baked head"
    c1 = data["components"][1]
    assert "morphResource" not in c1


def test_readme_contains_key_sections(tmp_path):
    out = tmp_path / "README_GUI_STEPS.md"
    write_readme("my_npv_abc", "my_npv_abc_appearance", out)
    text = out.read_text()
    assert "WolvenKit" in text
    assert "my_npv_abc.app" in text
    assert "my_npv_abc_appearance" in text
    assert "parentTransform" in text
    assert "bindName" in text
    assert "root" in text
    assert "Pack" in text


def test_readme_mentions_component_json(tmp_path):
    out = tmp_path / "README_GUI_STEPS.md"
    write_readme("x", "x_appearance", out)
    text = out.read_text()
    assert "npv_components.json" in text
