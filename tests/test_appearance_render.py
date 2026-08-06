import json
from pathlib import Path

import pytest

import npv_build.appearance_render as ar
from npv_build.core.errors import NpvError


def _build_dir(tmp_path, components):
    build = tmp_path / "build"
    build.mkdir()
    (build / "npv_components.json").write_text(
        json.dumps({"appearance_name": "x_appearance", "components": components})
    )
    return build


def test_render_appearance_writes_manifest_and_returns_pngs(monkeypatch, tmp_path):
    build = _build_dir(tmp_path, [])
    meshes = [{"glb": "/tmp/a.glb", "name": "head", "appearance": "01_ca_pale", "chunk_mask": ""}]
    monkeypatch.setattr(ar, "_gather_meshes", lambda wk, b, s, c: meshes)

    seen = {}

    def fake_blender(manifest_path, stage, verbosity):
        manifest = json.loads(manifest_path.read_text())
        seen.update(manifest)
        for view in manifest["views"]:
            Path(manifest["out_dir"], view["name"] + ".png").write_bytes(b"png")

    monkeypatch.setattr(ar, "_run_blender", fake_blender)

    pngs = ar.render_appearance(wk=object(), build_dir=build)

    assert [p.name for p in pngs] == ["full_front.png", "face_front.png", "face_34.png"]
    assert all(p.exists() for p in pngs)
    assert seen["meshes"] == meshes
    assert seen["materials"] == "clay"
    assert seen["resolution"] == [768, 1024]


def test_render_appearance_hard_fails_when_a_view_is_missing(monkeypatch, tmp_path):
    build = _build_dir(tmp_path, [])
    monkeypatch.setattr(ar, "_gather_meshes", lambda wk, b, s, c: [{"glb": "/tmp/a.glb", "name": "h", "appearance": "", "chunk_mask": ""}])
    monkeypatch.setattr(ar, "_run_blender", lambda m, s, v: None)  # renders nothing
    with pytest.raises(NpvError):
        ar.render_appearance(wk=object(), build_dir=build)


def test_gather_meshes_uses_local_mod_scoped_files(monkeypatch, tmp_path):
    depot = "base\\npv-build\\qa_x\\qa_x_head.mesh"
    build = _build_dir(tmp_path, [
        {"type": "entSkinnedMeshComponent", "name": "head", "mesh": depot,
         "meshAppearance": "01_ca_pale", "bindTo": "face_rig", "chunkMask": "42"},
    ])
    local = build / "source" / "archive" / "base" / "npv-build" / "qa_x" / "qa_x_head.mesh"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"cr2w")

    exported = []

    class FakeWk:
        def export(self, cr2w_file, *, dest):
            exported.append(Path(cr2w_file))
            glb = dest / (Path(cr2w_file).stem + ".glb")
            glb.write_bytes(b"glb")
            return glb

        def extract(self, regex, *, archive=None, dest=None):
            raise AssertionError("mod-scoped mesh must not hit game archives")

    stage = tmp_path / "stage"
    stage.mkdir()
    meshes = ar._gather_meshes(FakeWk(), build, stage, None)

    assert exported == [local]
    assert meshes == [{"glb": str(stage / "glb" / "0" / "qa_x_head.glb"),
                       "name": "head", "appearance": "01_ca_pale", "chunk_mask": "42"}]


def test_gather_meshes_extracts_base_game_depots(tmp_path):
    depot = "base\\characters\\garment\\t1_001_pwa_dress.mesh"
    build = _build_dir(tmp_path, [
        {"type": "entGarmentSkinnedMeshComponent", "name": "dress", "mesh": depot,
         "meshAppearance": "red", "bindTo": "root", "chunkMask": ""},
    ])

    class FakeWk:
        def extract(self, regex, *, archive=None, dest=None):
            target = dest / "base" / "characters" / "garment" / "t1_001_pwa_dress.mesh"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"cr2w")
            return dest

        def export(self, cr2w_file, *, dest):
            glb = dest / (Path(cr2w_file).stem + ".glb")
            glb.write_bytes(b"glb")
            return glb

    stage = tmp_path / "stage"
    stage.mkdir()
    meshes = ar._gather_meshes(FakeWk(), build, stage, None)
    assert meshes[0]["name"] == "dress" and meshes[0]["glb"].endswith("t1_001_pwa_dress.glb")


def test_gather_meshes_hard_fails_on_unlocatable_mesh(tmp_path):
    depot = "base\\npv-build\\qa_x\\missing.mesh"
    build = _build_dir(tmp_path, [
        {"type": "entSkinnedMeshComponent", "name": "head", "mesh": depot,
         "meshAppearance": "", "bindTo": "root", "chunkMask": ""},
    ])
    stage = tmp_path / "stage"
    stage.mkdir()
    with pytest.raises(NpvError, match="missing.mesh"):
        ar._gather_meshes(object(), build, stage, None)
