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
    monkeypatch.setattr(ar, "_gather_meshes", lambda wk, b, s, c, progress=None: (meshes, []))

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
    monkeypatch.setattr(
        ar,
        "_gather_meshes",
        lambda wk, b, s, c, progress=None: (
            [{"glb": "/tmp/a.glb", "name": "h", "appearance": "", "chunk_mask": ""}],
            [],
        ),
    )
    monkeypatch.setattr(ar, "_run_blender", lambda m, s, v: None)  # renders nothing
    with pytest.raises(NpvError):
        ar.render_appearance(wk=object(), build_dir=build)


def test_render_appearance_writes_render_report_with_skips(monkeypatch, tmp_path):
    build = _build_dir(tmp_path, [])
    meshes = [{"glb": "/tmp/a.glb", "name": "head", "appearance": "", "chunk_mask": ""}]
    skipped = [{"name": "femv_vtk_headpatch", "depot": "base\\vtk\\femv_vtk_headpatch.mesh",
                "reason": "export failed: boom"}]
    monkeypatch.setattr(ar, "_gather_meshes", lambda wk, b, s, c, progress=None: (meshes, skipped))

    def fake_blender(manifest_path, stage, verbosity):
        manifest = json.loads(manifest_path.read_text())
        for view in manifest["views"]:
            Path(manifest["out_dir"], view["name"] + ".png").write_bytes(b"png")

    monkeypatch.setattr(ar, "_run_blender", fake_blender)

    out_dir = tmp_path / "out"
    ar.render_appearance(wk=object(), build_dir=build, out_dir=out_dir)

    report = json.loads((out_dir / "render_report.json").read_text())
    assert report == {"skipped": skipped}


def test_render_appearance_writes_empty_render_report_when_nothing_skipped(monkeypatch, tmp_path):
    build = _build_dir(tmp_path, [])
    meshes = [{"glb": "/tmp/a.glb", "name": "head", "appearance": "", "chunk_mask": ""}]
    monkeypatch.setattr(ar, "_gather_meshes", lambda wk, b, s, c, progress=None: (meshes, []))

    def fake_blender(manifest_path, stage, verbosity):
        manifest = json.loads(manifest_path.read_text())
        for view in manifest["views"]:
            Path(manifest["out_dir"], view["name"] + ".png").write_bytes(b"png")

    monkeypatch.setattr(ar, "_run_blender", fake_blender)

    out_dir = tmp_path / "out"
    ar.render_appearance(wk=object(), build_dir=build, out_dir=out_dir)

    report = json.loads((out_dir / "render_report.json").read_text())
    assert report == {"skipped": []}


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
        def export(self, cr2w_file, *, dest, with_materials=True):
            exported.append(Path(cr2w_file))
            glb = dest / (Path(cr2w_file).stem + ".glb")
            glb.write_bytes(b"glb")
            return glb

        def extract(self, regex, *, archive=None, dest=None):
            raise AssertionError("mod-scoped mesh must not hit game archives")

    stage = tmp_path / "stage"
    stage.mkdir()
    meshes, skipped = ar._gather_meshes(FakeWk(), build, stage, None)

    assert exported == [local]
    assert meshes == [{"glb": str(stage / "glb" / "0" / "qa_x_head.glb"),
                       "name": "head", "appearance": "01_ca_pale", "chunk_mask": "42"}]
    assert skipped == []


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

        def export(self, cr2w_file, *, dest, with_materials=True):
            glb = dest / (Path(cr2w_file).stem + ".glb")
            glb.write_bytes(b"glb")
            return glb

    stage = tmp_path / "stage"
    stage.mkdir()
    meshes, skipped = ar._gather_meshes(FakeWk(), build, stage, None)
    assert meshes[0]["name"] == "dress" and meshes[0]["glb"].endswith("t1_001_pwa_dress.glb")
    assert skipped == []


def test_gather_meshes_hard_fails_on_unlocatable_mod_scoped_mesh(tmp_path):
    depot = "base\\npv-build\\qa_x\\missing.mesh"
    build = _build_dir(tmp_path, [
        {"type": "entSkinnedMeshComponent", "name": "head", "mesh": depot,
         "meshAppearance": "", "bindTo": "root", "chunkMask": ""},
    ])
    stage = tmp_path / "stage"
    stage.mkdir()
    with pytest.raises(NpvError, match="missing.mesh"):
        ar._gather_meshes(object(), build, stage, None)


def test_gather_meshes_soft_skips_unlocatable_external_mesh(tmp_path):
    """A non-mod-scoped depot missing from every archive is recorded, not raised —
    unlike a mod-scoped miss, which always means the build itself is broken."""
    depot = "base\\vtk\\femv_vtk_headpatch.mesh"
    build = _build_dir(tmp_path, [
        {"type": "entSkinnedMeshComponent", "name": "femv_vtk_headpatch", "mesh": depot,
         "meshAppearance": "", "bindTo": "root", "chunkMask": ""},
    ])

    class FakeConfig:
        game_dir = None

    class FakeWk:
        config = FakeConfig()

        def extract(self, regex, *, archive=None, dest=None):
            return dest  # nothing extracted, no matter which archive

        def export(self, cr2w_file, *, dest, with_materials=True):
            raise AssertionError("should never reach export for an unlocatable mesh")

    stage = tmp_path / "stage"
    stage.mkdir()
    meshes, skipped = ar._gather_meshes(FakeWk(), build, stage, None)

    assert meshes == []
    assert skipped == [{
        "name": "femv_vtk_headpatch",
        "depot": depot,
        "reason": "mesh not found in game or mod archives",
    }]


def test_gather_meshes_hard_fails_on_unexportable_mod_scoped_mesh(tmp_path):
    """A located mod-scoped mesh (the build's own output) that fails to export
    is a hard failure, not a soft skip — unlike an external depot's export
    failure (test_gather_meshes_soft_skips_unexportable_mesh below), a
    mod-scoped export failure always means the build itself is broken, same
    as a mod-scoped mesh that can't be located at all
    (test_gather_meshes_hard_fails_on_unlocatable_mod_scoped_mesh above)."""
    depot = "base\\npv-build\\qa_x\\qa_x_head.mesh"
    build = _build_dir(tmp_path, [
        {"type": "entSkinnedMeshComponent", "name": "head", "mesh": depot,
         "meshAppearance": "", "bindTo": "root", "chunkMask": ""},
    ])
    local = build / "source" / "archive" / "base" / "npv-build" / "qa_x" / "qa_x_head.mesh"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"cr2w")

    from npv_build.wk_cli import WolvenKitError

    class FakeWk:
        def export(self, cr2w_file, *, dest, with_materials=True):
            raise WolvenKitError("export failed: boom", operation="export")

        def extract(self, regex, *, archive=None, dest=None):
            raise AssertionError("mod-scoped mesh must not hit game archives")

    stage = tmp_path / "stage"
    stage.mkdir()
    with pytest.raises(NpvError, match="qa_x_head.mesh"):
        ar._gather_meshes(FakeWk(), build, stage, None)


def test_gather_meshes_soft_skips_unexportable_mesh(tmp_path):
    """A located mesh that WolvenKit's exporter rejects is recorded, not raised —
    confirmed live against femv_vtk_headpatch.mesh, which returns a clean `false`
    from WolvenKit's classic mesh exporter with no exception."""
    depot = "base\\characters\\garment\\t1_001_pwa_dress.mesh"
    build = _build_dir(tmp_path, [
        {"type": "entGarmentSkinnedMeshComponent", "name": "dress", "mesh": depot,
         "meshAppearance": "red", "bindTo": "root", "chunkMask": ""},
    ])

    from npv_build.wk_cli import WolvenKitError

    class FakeWk:
        def extract(self, regex, *, archive=None, dest=None):
            target = dest / "base" / "characters" / "garment" / "t1_001_pwa_dress.mesh"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"cr2w")
            return dest

        def export(self, cr2w_file, *, dest, with_materials=True):
            raise WolvenKitError("export failed: boom", operation="export")

    stage = tmp_path / "stage"
    stage.mkdir()
    meshes, skipped = ar._gather_meshes(FakeWk(), build, stage, None)

    assert meshes == []
    assert len(skipped) == 1
    assert skipped[0]["name"] == "dress"
    assert skipped[0]["depot"] == depot
    assert "export failed" in skipped[0]["reason"]


def test_gather_meshes_reports_per_component_progress(tmp_path):
    """Each component export reports (message, current, total) so the GUI can
    show a live counter during the slow WolvenKit export phase."""
    depots = {
        "head": "base\\npv-build\\qa_x\\qa_x_head.mesh",
        "dress": "base\\npv-build\\qa_x\\qa_x_dress.mesh",
    }
    build = _build_dir(
        tmp_path,
        [
            {"type": "entSkinnedMeshComponent", "name": name, "mesh": depot,
             "meshAppearance": "", "bindTo": "root", "chunkMask": ""}
            for name, depot in depots.items()
        ],
    )
    for depot in depots.values():
        local = build / "source" / "archive" / Path(*depot.split("\\"))
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b"cr2w")

    class FakeWk:
        def export(self, cr2w_file, *, dest, with_materials=True):
            glb = dest / (Path(cr2w_file).stem + ".glb")
            glb.write_bytes(b"glb")
            return glb

    calls = []
    stage = tmp_path / "stage"
    stage.mkdir()
    ar._gather_meshes(FakeWk(), build, stage, None, progress=lambda m, c, t: calls.append((m, c, t)))

    assert calls == [("Exporting head", 1, 2), ("Exporting dress", 2, 2)]


def test_render_appearance_reports_blender_phase_progress(monkeypatch, tmp_path):
    build = _build_dir(tmp_path, [])
    meshes = [{"glb": "/tmp/a.glb", "name": "head", "appearance": "", "chunk_mask": ""}]
    monkeypatch.setattr(ar, "_gather_meshes", lambda wk, b, s, c, progress=None: (meshes, []))

    def fake_blender(manifest_path, stage, verbosity):
        manifest = json.loads(manifest_path.read_text())
        for view in manifest["views"]:
            Path(manifest["out_dir"], view["name"] + ".png").write_bytes(b"png")

    monkeypatch.setattr(ar, "_run_blender", fake_blender)

    calls = []
    ar.render_appearance(
        wk=object(), build_dir=build, progress=lambda m, c, t: calls.append((m, c, t))
    )

    assert calls[-1] == ("Rendering views in Blender", 1, 1)
