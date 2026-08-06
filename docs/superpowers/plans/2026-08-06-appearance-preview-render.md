# Appearance Preview Render + Golden Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a built NPV's full appearance (head, hair, garments, tattoo overlays) to deterministic PNGs headlessly in Blender — no game launch — and add golden-image comparison so appearance regressions become automated checks.

**Architecture:** A built NPV's `<output>/npv_components.json` lists every mesh component with depot path, appearance, and chunk mask; mod-scoped meshes already sit uncooked in `<output>/source/archive/`. A new `appearance_render.py` gathers those meshes (WolvenKit `extract`+`export` for base-game depots), writes a JSON manifest, and invokes a new pure-bpy `render_npv.py` through the existing `blender_module` command seams (`_blender_cmd()`/`_run()`). Deterministic camera/lighting/resolution make renders diffable; `core/image_diff.py` (Pillow RMS) compares against local goldens. A bridge method + My NPVs button expose it in the GUI. A front-loaded spike decides the materials tier: CP77 Blender add-on shaders if headlessly automatable, grey-clay geometry otherwise (still catches missing hair/clothes/parts; skin/hair color validation then waits on the add-on).

**Tech Stack:** Python 3.11, Blender 4.x headless (pure bpy baseline; CP77 IO Suite add-on optional per spike), WolvenKit CLI adapter (`wk_cli.WolvenKit`), Pillow (already a dependency), pytest, vanilla-JS web UI.

**Supersedes:** `docs/superpowers/plans/2026-07-17-face-preview.md` (head-only, targeted the retired customtkinter GUI). Its research conclusions stand: scraping is infeasible, `screenshot.png` is a scene snapshot, rendering the real meshes is the only reliable signal.

## Global Constraints

- Gates for every task: `uv run ruff check .` clean and `uv run pytest -q` fully green (baseline at plan time: 511 passed / 4 skipped; e2e/golden tests must skip cleanly on machines without game data).
- **No CDPR bytes in the repo — this includes rendered pixels.** Preview PNGs and golden images are derivative of game assets: they are NEVER committed. Goldens live at `~/.cache/npv/preview_goldens/`; previews go under the user's build output dir. Repo gets code, tests, and synthetic test images only.
- Depot paths use Windows backslashes (`base\characters\...`) even on Linux; convert to OS separators only when touching the filesystem.
- Hard-fail policy: a mesh that cannot be located or exported raises `NpvError` naming the depot path — never render a silently incomplete character.
  - **AMENDED at Task 7 live gate (2026-08-06):** hard-fail applies to *mod-scoped* meshes (`base\npv-build\...` — the build's own output; missing = broken build). Components whose depots resolve externally (game/mod archives at runtime, e.g. `base\vtk\...`) are best-effort: WolvenKit provably cannot export some of them at all (`femv_vtk_headpatch.mesh` returns a clean `false` from the classic mesh exporter), so a strict hard-fail would kill previews for any VTK-referencing build. Skips must be LOUD, never silent: recorded per-component in `render_report.json` next to the PNGs ({name, depot, reason}) plus one summary warning log. The preview is thereby explicitly labeled incomplete rather than quietly missing parts.
- Bridge (`webui_api.py`) methods never raise into JS — structured `{"ok": False, "error", "remediation"}` dicts.
- Blender is invoked only via `blender_module._blender_cmd()` + `_run()` (flatpak-aware, timeout, `BlenderError`); scripts are copied into the stage dir before running (flatpak read access — same pattern as `bake_head.py` at blender_module.py:214).
- Rendering is opt-in (button / explicit call): first render costs many WolvenKit exports (~tens of seconds to minutes); never render automatically while listing.
- Determinism: fixed camera, lights, resolution, film settings; no wall-clock or randomness in the render path.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## File Structure

- `npv_build/data/blender/render_npv.py` (new) — pure-bpy, manifest-driven: import N glbs, apply chunk-mask submesh visibility, LOD filter, camera+lights per view, render PNGs.
- `npv_build/appearance_render.py` (new) — `render_appearance(wk, build_dir, ...)`: gather meshes → export glbs → manifest → Blender → verify PNGs. Sibling of `head_bake.py`/`blender_module.py` (top-level, owns a WolvenKit adapter).
- `npv_build/core/image_diff.py` (new) — pure Pillow: `rms_diff`, `compare`.
- `npv_build/webui_api.py` (modify) — `render_npv_preview(output_dir)` bridge method.
- `npv_build/webui/js/library.js` + `index.html` + `app.css` (modify) — "Render preview" action on a My NPVs entry, inline image strip.
- `tests/test_render_npv_script.py`, `tests/test_appearance_render.py`, `tests/core/test_image_diff.py`, `tests/test_appearance_render_e2e.py` (new), `tests/test_webui_api.py` + `tests/webui_smoke/` (extend).
- `docs/research/2026-08-06-cp77-addon-headless.md` (new, Task 1 output).

---

### Task 1: SPIKE — CP77 add-on headless automation + material export probe

**This is a research spike, not TDD.** Time-box: stop and write up as soon as each question has a definite answer. Its output is a decision document that Task 2/3 read; no production code.

**Files:**
- Create: `docs/research/2026-08-06-cp77-addon-headless.md`

**Interfaces:**
- Consumes: the cached Blender (`~/.cache/npv/tools/blender/` or PATH — see `blender_module._blender_cmd()`), the WolvenKit adapter, a real built NPV at `~/npv_builds/QuickSave-0/` (meshes under `source/archive/base/npv-build/...`).
- Produces: a written MATERIALS decision — `"addon"` or `"clay"` — plus, if addon: the add-on release URL + sha256, the headless install command, and the exact bpy import call that loads a mesh with materials. Task 2's script and Task 3's manifest honor the decision.

- [ ] **Step 1: Probe WolvenKit material export.** Run `uv run python` snippets against the real install: export one built mesh (e.g. `~/npv_builds/QuickSave-0/source/archive/base/npv-build/quicksave_0_110a165e/quicksave_0_110a165e_head.mesh`) via `wk.export(mesh, dest=scratch)` and inspect what lands next to the `.glb` (a `.Material.json`? embedded textures? nothing?). Also try WolvenKit CLI `export --help` for material/texture flags and record what this WolvenKit version supports.

- [ ] **Step 2: Probe the CP77 add-on.** Find the current Cyberpunk Blender add-on release (WolvenKit org, "Cyberpunk-Blender-add-on" / CP77 IO Suite) compatible with the cached Blender's version. Download the zip to scratch, install headlessly:

```bash
blender --background --python-expr "import bpy; bpy.ops.preferences.addon_install(filepath='<zip>'); bpy.ops.preferences.addon_enable(module='<module-name>'); bpy.ops.wm.save_userpref()"
```

Then, in a second headless run, attempt its glb+material import operator on the Step 1 export and check the resulting scene has non-empty material node trees. Record the exact operator name and required inputs (many add-on importers want the WolvenKit *project* layout — note whatever it demands).

- [ ] **Step 3: Decide and document.** Write `docs/research/2026-08-06-cp77-addon-headless.md` with: what WolvenKit export emits, whether the add-on installs+imports headlessly, the MATERIALS decision (`addon` only if BOTH probes pass end-to-end without interactive steps), the artifacts (URL, sha256, operator name), and what the clay tier can/cannot validate (can: presence/placement/silhouette of every part; cannot: skin tone, hair color, material variants). If the decision is `clay`, list the concrete blocker(s) so a future task can revisit.

- [ ] **Step 4: Commit**

```bash
git add docs/research/2026-08-06-cp77-addon-headless.md
git commit -m "docs(research): CP77 add-on headless automation spike

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Blender render script (`data/blender/render_npv.py`)

**Files:**
- Create: `npv_build/data/blender/render_npv.py`
- Test: `tests/test_render_npv_script.py` (static/AST — the script only runs inside Blender)

**Interfaces:**
- Consumes: Task 1's MATERIALS decision (if `addon`, add an `elif manifest.get("materials") == "addon":` import branch using the spike's recorded operator; the clay path below is always the fallback).
- Produces: a script runnable as `blender --background --python render_npv.py -- <manifest.json>` where the manifest is:

```json
{
  "meshes": [{"glb": "/abs/path.glb", "name": "t1_dress", "appearance": "red", "chunk_mask": "9223372036854775807"}],
  "views": [
    {"name": "full_front", "framing": "body", "yaw_deg": 0},
    {"name": "face_front", "framing": "face", "yaw_deg": 0},
    {"name": "face_34", "framing": "face", "yaw_deg": 35}
  ],
  "resolution": [768, 1024],
  "materials": "clay",
  "out_dir": "/abs/out"
}
```

  It writes `out_dir/<view name>.png` for every view. Task 3 generates this manifest; keep field names exactly as above.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_render_npv_script.py
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
```

- [ ] **Step 2: RED** — `uv run pytest tests/test_render_npv_script.py -q` → file not found.

- [ ] **Step 3: Implement** `npv_build/data/blender/render_npv.py`:

```python
"""Blender headless render of an assembled NPV: manifest in, PNGs out.

Run via:
  blender --background --python render_npv.py -- <manifest.json>

Pure bpy baseline ("clay" materials). Imports every glb listed in the
manifest, hides submeshes masked out by the component's chunkMask, keeps
only LOD 1 geometry, then renders each requested view with a fixed
camera/light rig. Deterministic by construction: no randomness, no clock.
WolvenKit glb naming convention: objects are "submesh_NN_LOD_M".
"""

import json
import math
import re
import sys

import bpy
import mathutils

_SUBMESH_RE = re.compile(r"submesh_(\d+)_LOD_(\d+)", re.IGNORECASE)


def _manifest():
    argv = sys.argv
    idx = argv.index("--")
    with open(argv[idx + 1], encoding="utf-8") as f:
        return json.load(f)


def _apply_chunk_mask(imported_objects, chunk_mask):
    """Hide submeshes whose bit is cleared; drop every LOD but 1."""
    try:
        mask = int(chunk_mask) if chunk_mask else -1
    except ValueError:
        mask = -1
    kept = []
    for obj in imported_objects:
        if obj.type != "MESH":
            continue
        m = _SUBMESH_RE.search(obj.name)
        if m:
            index, lod = int(m.group(1)), int(m.group(2))
            if lod != 1 or (mask >= 0 and not (mask >> index) & 1):
                obj.hide_render = True
                obj.hide_set(True)
                continue
        kept.append(obj)
    return kept


def _scene_bounds(objs):
    points = []
    for obj in objs:
        points.extend(obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box)
    lo = mathutils.Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = mathutils.Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return lo, hi


def _add_camera(name, location, look_at):
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    direction = look_at - location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def _add_lights(center, dist):
    for name, offset, energy in (
        ("key", (dist, -dist, dist), 1200),
        ("fill", (-dist, -dist, 0), 450),
        ("rim", (0, dist, dist), 600),
    ):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.size = dist
        obj = bpy.data.objects.new(name, light)
        obj.location = center + mathutils.Vector(offset)
        bpy.context.scene.collection.objects.link(obj)


def _pick_engine():
    try:
        engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    except Exception:
        engines = set()
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"


def main():
    manifest = _manifest()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    visible = []
    for entry in manifest["meshes"]:
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=entry["glb"])
        imported = [o for o in bpy.context.scene.objects if o not in before]
        visible.extend(_apply_chunk_mask(imported, entry.get("chunk_mask", "")))
    if not visible:
        raise SystemExit("render_npv: no visible mesh after import/masking")

    lo, hi = _scene_bounds(visible)
    center = (lo + hi) / 2.0
    height = hi.z - lo.z
    # Face region: top ~15% of the character's height.
    face_center = mathutils.Vector((center.x, center.y, lo.z + height * 0.925))

    _add_lights(center, height * 1.5)

    scene = bpy.context.scene
    scene.render.engine = _pick_engine()
    scene.render.resolution_x, scene.render.resolution_y = manifest["resolution"]
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"

    for view in manifest["views"]:
        framing = view["framing"]
        target = face_center if framing == "face" else center
        dist = height * (0.55 if framing == "face" else 1.8)
        yaw = math.radians(view.get("yaw_deg", 0))
        # Camera on -Y side (glb convention: character faces -Y); yaw orbits it.
        offset = mathutils.Vector((math.sin(yaw) * dist, -math.cos(yaw) * dist, 0))
        cam = _add_camera(f"cam_{view['name']}", target + offset, target)
        scene.camera = cam
        scene.render.filepath = f"{manifest['out_dir']}/{view['name']}.png"
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
```

(If Task 1 decided `addon`, add the material branch: after each glb import, when `manifest["materials"] == "addon"`, invoke the spike's recorded operator/setup instead of leaving imported materials as-is. Keep the clay path as the fallback when the operator errors — log to stderr and continue clay rather than dying, since geometry validation still has value. The camera's `-Y` facing and the 0.925 face-height factor are the empirical unknowns — Task 7 verifies against real renders and adjusts; note any change in your report.)

- [ ] **Step 4: GREEN** — `uv run pytest tests/test_render_npv_script.py -q`

- [ ] **Step 5: Full gate + commit**

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/data/blender/render_npv.py tests/test_render_npv_script.py
git commit -m "feat(preview): manifest-driven Blender render script for assembled NPVs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `appearance_render.py` orchestration

**Files:**
- Create: `npv_build/appearance_render.py`
- Test: `tests/test_appearance_render.py`

**Interfaces:**
- Consumes: `wk_cli.WolvenKit` adapter (`extract(regex, *, archive=None, dest)`, `export(cr2w_file, *, dest) -> Path`); `blender_module._blender_cmd()` and `blender_module._run(cmd, verbosity, error_prefix)`; `core.errors.NpvError`; `core.cancel.CancelToken` (optional param, `raise_if_cancelled()` between stages); build output layout: `<build_dir>/npv_components.json` (`{"appearance_name", "components": [{"type","name","mesh","meshAppearance","bindTo","chunkMask",...}]}`) and mod-scoped uncooked meshes at `<build_dir>/source/archive/<depot>`.
- Produces (Tasks 5/7 call this):

```python
DEFAULT_VIEWS = (
    {"name": "full_front", "framing": "body", "yaw_deg": 0},
    {"name": "face_front", "framing": "face", "yaw_deg": 0},
    {"name": "face_34", "framing": "face", "yaw_deg": 35},
)

def render_appearance(wk, build_dir: Path, out_dir: Path | None = None, *,
                      views=DEFAULT_VIEWS, resolution=(768, 1024),
                      materials="clay", verbosity=0, cancel=None) -> list[Path]
```

  Returns the rendered PNG paths (one per view, in `out_dir`, default `<build_dir>/preview/`). Module-level seams for tests: `_gather_meshes(wk, build_dir, stage, cancel) -> list[dict]` (manifest `meshes` entries) and `_run_blender(manifest_path: Path, stage: Path, verbosity: int) -> None`.

- [ ] **Step 1: Write the failing tests** (mock both seams — no real WolvenKit/Blender):

```python
# tests/test_appearance_render.py
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
```

- [ ] **Step 2: RED** — `uv run pytest tests/test_appearance_render.py -q` → module not found.

- [ ] **Step 3: Implement** `npv_build/appearance_render.py`:

  - `_gather_meshes(wk, build_dir, stage, cancel)`: read `npv_components.json`; for each component whose `mesh` ends `.mesh` or `.morphtarget` (skip others), dedupe by depot preserving first-seen component metadata, then locate the CR2W file:
    - depot starts with `base\npv-build\` → `build_dir / "source" / "archive" / Path(*depot.split("\\"))`; `NpvError` naming the depot if missing (hard-fail policy).
    - otherwise → `wk.extract(re.escape(depot), dest=stage / "extract")`, then the file is at `stage / "extract" / Path(*depot.split("\\"))`; `NpvError` naming the depot if extraction produced nothing.
    - Export each to its own numbered subdir (`stage / "glb" / str(i)`) via `wk.export(cr2w, dest=...)` — per-mesh subdirs because `export` returns the first `*.glb` glob in `dest`.
    - Call `cancel.raise_if_cancelled()` per component when `cancel` is not None.
    - Return `[{"glb": str(glb), "name": comp["name"], "appearance": comp.get("meshAppearance", ""), "chunk_mask": comp.get("chunkMask", "")}]`.
  - `_run_blender(manifest_path, stage, verbosity)`: copy `data/blender/render_npv.py` into `stage` (flatpak-readable, same as blender_module.py:214), then `blender_module._run(blender_module._blender_cmd() + ["--background", "--python", str(local_script), "--", str(manifest_path)], verbosity, "RenderFailed")`.
  - `render_appearance(...)`: stage dir via `tempfile.mkdtemp` under the user's home cache (`~/.cache/npv/render_stage/` — flatpak Blender can read `$HOME`, not `/tmp`); default `out_dir = build_dir / "preview"`, mkdir; write the manifest (schema from Task 2, `resolution` as a list); call the two seams; verify every `out_dir/<view>.png` exists else `NpvError("RenderFailed: view <name> missing", remediation=...)`; clean the stage dir in a `finally`; return the PNG paths in view order.

- [ ] **Step 4: GREEN** — `uv run pytest tests/test_appearance_render.py -q`

- [ ] **Step 5: Full gate + commit**

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/appearance_render.py tests/test_appearance_render.py
git commit -m "feat(preview): render_appearance orchestration (components -> glbs -> Blender PNGs)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `core/image_diff.py` + golden e2e test

**Files:**
- Create: `npv_build/core/image_diff.py`
- Create: `tests/core/test_image_diff.py`
- Create: `tests/test_appearance_render_e2e.py`

**Interfaces:**
- Consumes: Pillow (existing dependency); `render_appearance` (Task 3) in the e2e test.
- Produces:

```python
def rms_diff(a: Path, b: Path) -> float          # RMS over RGBA channels, 0.0..255.0; inf on dimension mismatch
def compare(candidate: Path, golden: Path, threshold: float = 3.0) -> dict
# -> {"match": bool, "rms": float, "reason": str}   reason "" on match,
#    "dimension mismatch" or f"rms {rms:.2f} > threshold {threshold}" otherwise
```

  Golden policy (binding, from Global Constraints): goldens live at `~/.cache/npv/preview_goldens/<view>.png`, never in the repo. The e2e test renders a real build and compares; `NPV_UPDATE_GOLDENS=1` blesses current renders as the new goldens.

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/core/test_image_diff.py
from PIL import Image

from npv_build.core.image_diff import compare, rms_diff


def _png(path, color, size=(32, 32)):
    Image.new("RGBA", size, color).save(path)
    return path


def test_identical_images_match(tmp_path):
    a = _png(tmp_path / "a.png", (120, 30, 200, 255))
    b = _png(tmp_path / "b.png", (120, 30, 200, 255))
    assert rms_diff(a, b) == 0.0
    assert compare(a, b) == {"match": True, "rms": 0.0, "reason": ""}


def test_small_noise_within_threshold(tmp_path):
    a = _png(tmp_path / "a.png", (100, 100, 100, 255))
    b = _png(tmp_path / "b.png", (102, 100, 99, 255))
    result = compare(a, b, threshold=3.0)
    assert result["match"] is True and 0 < result["rms"] < 3.0


def test_wrong_color_fails(tmp_path):
    a = _png(tmp_path / "a.png", (10, 10, 10, 255))
    b = _png(tmp_path / "b.png", (200, 200, 200, 255))
    result = compare(a, b, threshold=3.0)
    assert result["match"] is False and result["reason"].startswith("rms ")


def test_dimension_mismatch_fails(tmp_path):
    a = _png(tmp_path / "a.png", (0, 0, 0, 255), size=(32, 32))
    b = _png(tmp_path / "b.png", (0, 0, 0, 255), size=(16, 16))
    assert rms_diff(a, b) == float("inf")
    assert compare(a, b) == {"match": False, "rms": float("inf"), "reason": "dimension mismatch"}
```

- [ ] **Step 2: RED → implement** `npv_build/core/image_diff.py`:

```python
"""Golden-image comparison for appearance previews. Pure Pillow, no repo goldens."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops


def rms_diff(a: Path, b: Path) -> float:
    """Root-mean-square pixel difference over RGBA, 0.0..255.0.

    Returns +inf when dimensions differ — resizing would hide layout bugs.
    """
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != ib.size:
            return float("inf")
        diff = ImageChops.difference(ia.convert("RGBA"), ib.convert("RGBA"))
        histogram = diff.histogram()
    total_sq = 0
    count = 0
    for channel in range(4):
        for value, n in enumerate(histogram[channel * 256:(channel + 1) * 256]):
            total_sq += n * value * value
            count += n
    return math.sqrt(total_sq / count) if count else 0.0


def compare(candidate: Path, golden: Path, threshold: float = 3.0) -> dict:
    rms = rms_diff(candidate, golden)
    if rms == float("inf"):
        return {"match": False, "rms": rms, "reason": "dimension mismatch"}
    if rms > threshold:
        return {"match": False, "rms": rms, "reason": f"rms {rms:.2f} > threshold {threshold}"}
    return {"match": True, "rms": rms, "reason": ""}
```

- [ ] **Step 3: GREEN** — `uv run pytest tests/core/test_image_diff.py -q`

- [ ] **Step 4: Write the e2e golden test** (skips cleanly everywhere except a machine with a real build; runs render + compare when armed):

```python
# tests/test_appearance_render_e2e.py
"""Golden-image regression for the appearance preview render.

Skips unless NPV_PREVIEW_BUILD_DIR points at a real build output dir on a
machine with the game + WolvenKit + Blender. Goldens live OUTSIDE the repo
(rendered pixels are CDPR-derivative) at ~/.cache/npv/preview_goldens/.
Bless new goldens with NPV_UPDATE_GOLDENS=1.
"""

import os
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

GOLDEN_DIR = Path.home() / ".cache" / "npv" / "preview_goldens"


def _build_dir():
    value = os.environ.get("NPV_PREVIEW_BUILD_DIR", "")
    if not value:
        pytest.skip("NPV_PREVIEW_BUILD_DIR not set (needs a real build output dir)")
    build = Path(value)
    if not (build / "npv_components.json").exists():
        pytest.skip(f"{build} has no npv_components.json")
    return build


def test_render_matches_goldens(tmp_path):
    from npv_build.appearance_render import render_appearance
    from npv_build.config import load_config
    from npv_build.core.image_diff import compare
    from npv_build.wk_cli import WolvenKit, WolvenKitConfig

    build = _build_dir()
    game_dir = (load_config() or {}).get("game_dir", "")
    if not game_dir or not Path(game_dir).is_dir():
        pytest.skip("no valid game_dir in config")

    wk = WolvenKit(WolvenKitConfig(game_dir=Path(game_dir)))
    pngs = render_appearance(wk, build, out_dir=tmp_path)

    if os.environ.get("NPV_UPDATE_GOLDENS") == "1":
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        for png in pngs:
            shutil.copy2(png, GOLDEN_DIR / png.name)
        pytest.skip(f"goldens updated at {GOLDEN_DIR}")

    missing = [p.name for p in pngs if not (GOLDEN_DIR / p.name).exists()]
    if missing:
        pytest.skip(f"goldens not blessed yet: {missing} (run with NPV_UPDATE_GOLDENS=1)")

    failures = {}
    for png in pngs:
        result = compare(png, GOLDEN_DIR / png.name)
        if not result["match"]:
            failures[png.name] = result["reason"]
    assert not failures, f"appearance drifted from goldens: {failures}"
```

  (Verified: `npv_build.config.load_config() -> dict` exists (config.py:39) and returns `{}` when no config file — the `(load_config() or {}).get(...)` guard above handles both.)

- [ ] **Step 5: Verify skip behavior + full gate** — `uv run pytest tests/test_appearance_render_e2e.py -q` collects and SKIPS (env var unset). Then `uv run ruff check . && uv run pytest -q` (skip count rises by 1).

- [ ] **Step 6: Commit**

```bash
git add npv_build/core/image_diff.py tests/core/test_image_diff.py tests/test_appearance_render_e2e.py
git commit -m "feat(preview): golden-image diff + env-gated e2e regression test

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Bridge method `render_npv_preview`

**Files:**
- Modify: `npv_build/webui_api.py`
- Test: `tests/test_webui_api.py` (extend)

**Interfaces:**
- Consumes: `render_appearance` (Task 3 — import at module level in `webui_api.py` so tests can monkeypatch `npv_build.webui_api.render_appearance`); `load_settings` (already imported there); `WolvenKit`/`WolvenKitConfig` from `wk_cli`; `NpvError`.
- Produces: bridge method

```python
def render_npv_preview(self, output_dir: str) -> dict
# success: {"ok": True, "images": [{"view": "full_front", "path": "/abs/full_front.png",
#                                   "data_url": "data:image/png;base64,..."}, ...]}
# failure: {"ok": False, "error": "...", "remediation": "..."}
```

  Also: if the My NPVs listing payload (`list_mods` bridge response) does not already expose each entry's build output dir, add an `output_dir` field to it (derived the same way `build_meta.json` is found at webui_api.py:712 — `archive_path.parents[3]`), so the frontend can pass it back. Task 6 relies on `output_dir` being present in the listing.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_webui_api.py
def test_render_npv_preview_returns_data_urls(monkeypatch, tmp_path):
    from PIL import Image

    import npv_build.webui_api as api_mod

    build = tmp_path / "build"
    build.mkdir()
    (build / "npv_components.json").write_text("{}")
    pngs = []
    for name in ("full_front", "face_front", "face_34"):
        p = build / "preview" / f"{name}.png"
        p.parent.mkdir(exist_ok=True)
        Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(p)
        pngs.append(p)

    monkeypatch.setattr(api_mod, "render_appearance", lambda wk, build_dir, **k: pngs)

    class FakeSettings:
        game_dir = str(tmp_path)

    monkeypatch.setattr(api_mod, "load_settings", lambda: FakeSettings())

    result = api_mod.WebUiApi().render_npv_preview(str(build))
    assert result["ok"] is True
    assert [i["view"] for i in result["images"]] == ["full_front", "face_front", "face_34"]
    assert all(i["data_url"].startswith("data:image/png;base64,") for i in result["images"])


def test_render_npv_preview_maps_npv_error(monkeypatch, tmp_path):
    import npv_build.webui_api as api_mod
    from npv_build.core.errors import NpvError

    def boom(wk, build_dir, **k):
        raise NpvError("blender missing", remediation="install blender")

    monkeypatch.setattr(api_mod, "render_appearance", boom)

    class FakeSettings:
        game_dir = str(tmp_path)

    monkeypatch.setattr(api_mod, "load_settings", lambda: FakeSettings())

    result = api_mod.WebUiApi().render_npv_preview(str(tmp_path))
    assert result["ok"] is False and "blender missing" in result["error"]
    assert result["remediation"] == "install blender"


def test_render_npv_preview_requires_game_dir(monkeypatch, tmp_path):
    import npv_build.webui_api as api_mod

    class FakeSettings:
        game_dir = ""

    monkeypatch.setattr(api_mod, "load_settings", lambda: FakeSettings())
    result = api_mod.WebUiApi().render_npv_preview(str(tmp_path))
    assert result["ok"] is False and result["remediation"]
```

  (Verified: `webui_api.py` imports `load_settings` at module level (line 46), so `monkeypatch.setattr(api_mod, "load_settings", ...)` works exactly as written.)

- [ ] **Step 2: RED → implement** `render_npv_preview` in `webui_api.py`: guard `settings.game_dir` (structured error with remediation "Set the game directory in Settings" when empty/invalid), build `wk = WolvenKit(WolvenKitConfig(game_dir=Path(settings.game_dir)))`, call `render_appearance(wk, Path(output_dir))`, base64-encode each PNG into `data_url`, return the success dict. `except NpvError` → `{"ok": False, "error": e.user_message, "remediation": e.remediation or ""}`; `except Exception  # noqa: BLE001 - bridge boundary must not raise into JS` → `{"ok": False, "error": str(e), "remediation": ""}`. Add `output_dir` to the mod-listing payload if absent.

- [ ] **Step 3: GREEN** — `uv run pytest tests/test_webui_api.py -k render_npv_preview -q`

- [ ] **Step 4: Full gate + commit**

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/webui_api.py tests/test_webui_api.py
git commit -m "feat(webui): render_npv_preview bridge — headless appearance render to data URLs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: My NPVs "Render preview" UI

**Files:**
- Modify: `npv_build/webui/js/library.js` (and `index.html`/`app.css` as needed)
- Modify: `tests/webui_smoke/mock_api.js`
- Test: `tests/webui_smoke/test_webui_smoke.py` (extend)

**Interfaces:**
- Consumes: bridge `render_npv_preview(output_dir)` and the listing's `output_dir` field (Task 5). Frontend API convention: `window.__mockApi`-aware `Api.call()` (see `webui/js/api.js`); smoke tests drive the page against `tests/webui_smoke/mock_api.js`.
- Produces: each My NPVs entry gains a "Render preview" action (`.btn-render-preview`); clicking shows an in-card busy state ("Rendering…", button disabled), then an image strip (`.preview-strip` with one `<img class="preview-img">` per view, `src` = the returned data URLs), or the standard error affordance with the remediation text on failure. Re-clicking re-renders (bridge call is idempotent).

- [ ] **Step 1: Extend the mock API** — in `tests/webui_smoke/mock_api.js`, add (a 1×1 red PNG data URL literal):

```js
render_npv_preview: async (outputDir) => ({
  ok: true,
  images: [
    { view: "full_front", path: "/out/x/preview/full_front.png",
      data_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==" },
    { view: "face_front", path: "/out/x/preview/face_front.png",
      data_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==" },
  ],
})
```

  and ensure the mock's mod-listing payload includes `output_dir` on at least one entry (mirror however the existing mock lists mods).

- [ ] **Step 2: Write the failing smoke test** (follow the file's existing pattern — `webui_server` fixture, `sync_playwright`, `page.goto`):

```python
def test_library_render_preview_shows_images(webui_server):
    """My NPVs entry -> Render preview -> image strip appears from bridge data URLs."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(webui_server)
        page.click("#nav-library")
        page.wait_for_selector(".btn-render-preview")
        page.click(".btn-render-preview")
        page.wait_for_selector(".preview-strip .preview-img")
        images = page.eval_on_selector_all(".preview-strip .preview-img", "els => els.map(e => e.src)")
        assert len(images) == 2 and all(src.startswith("data:image/png") for src in images)
        browser.close()
```

- [ ] **Step 3: RED → implement** the button + handler in `library.js`: on click, disable the button and set its label to "Rendering…", `await Api.call("render_npv_preview", entry.output_dir)`, then either inject/replace the entry's `.preview-strip` with the returned images or surface `error` + `remediation` via the library view's existing error affordance; always restore the button state. Match the file's existing DOM-building style (no frameworks).

- [ ] **Step 4: GREEN** — `uv run pytest tests/webui_smoke/test_webui_smoke.py -k render_preview -q`, then the whole smoke file.

- [ ] **Step 5: Full gate + commit**

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/webui/js/library.js npv_build/webui/index.html npv_build/webui/app.css tests/webui_smoke/mock_api.js tests/webui_smoke/test_webui_smoke.py
git commit -m "feat(webui): Render preview action on My NPVs entries

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

  (Stage only the files you actually touched.)

---

### Task 7: Live gate — real render, camera truth, golden bless

**Files:** possibly `npv_build/data/blender/render_npv.py` (camera/framing fixes only) + a ledger/report note. This proves the feature on this machine; it cannot run in CI.

**Interfaces:**
- Consumes: everything above; the real build at `~/npv_builds/QuickSave-0` (or any current build with `npv_components.json`), the configured game dir, cached WolvenKit + Blender.

- [ ] **Step 1: Real render.**

```bash
uv run python -c "
from pathlib import Path
from npv_build.appearance_render import render_appearance
from npv_build.wk_cli import WolvenKit, WolvenKitConfig
from npv_build.config import load_config
cfg = load_config()
wk = WolvenKit(WolvenKitConfig(game_dir=Path(cfg['game_dir'])))
pngs = render_appearance(wk, Path.home() / 'npv_builds' / 'QuickSave-0')
for p in pngs: print(p, p.stat().st_size, 'bytes')
"
```

  (Adjust the config access to the real loader API, as in Task 4. Record wall-clock for the first render and note whether the WolvenKit artifact cache made repeat renders faster.)

- [ ] **Step 2: Eyeball loop.** Read each PNG as an image. Verify: `full_front` shows a full character facing the camera wearing the expected outfit with hair; `face_front`/`face_34` frame the face. Known empirical unknowns to fix here if wrong (edit `render_npv.py`, re-render, repeat): camera side (`-Y` vs `+Y`), face-height factor (0.925), framing distances, chunk-mask visibility (body poking through garments means mask bits or submesh naming need adjustment — dump imported object names to stderr to diagnose). Keep static tests green through any edit.

- [ ] **Step 3: GUI proof.** Launch the QA harness (pattern in memory: HTTP server + bridge to the real `WebUiApi`, driven by Playwright) or `uv run npv-build-gui`, open My NPVs, click "Render preview" on the built NPV, confirm the strip renders real images.

- [ ] **Step 4: Bless goldens + prove the regression gate.**

```bash
NPV_PREVIEW_BUILD_DIR=~/npv_builds/QuickSave-0 NPV_UPDATE_GOLDENS=1 uv run pytest tests/test_appearance_render_e2e.py -q   # blesses
NPV_PREVIEW_BUILD_DIR=~/npv_builds/QuickSave-0 uv run pytest tests/test_appearance_render_e2e.py -q                        # must PASS against goldens
```

  Confirm goldens landed in `~/.cache/npv/preview_goldens/` and NOT in the repo (`git status` clean of PNGs).

- [ ] **Step 5: Full gate + commit** any render-script fixes:

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/data/blender/render_npv.py
git commit -m "fix(preview): camera/framing corrections from live render gate

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

  (Skip the commit if Step 2 needed no changes.) Report must state: renders verified by eye, golden round-trip proven, GUI button works, and the MATERIALS tier actually used.

---

## After all tasks

- Update `docs/ROADMAP.md`: move "Face preview" out of **Not started**, replaced by a shipped line pointing at this plan; note the golden-image regression workflow (env vars `NPV_PREVIEW_BUILD_DIR` / `NPV_UPDATE_GOLDENS`).
- If Task 1 decided `clay`, add a ROADMAP follow-up line: "Preview materials tier — revisit CP77 add-on when <recorded blocker> changes."

## Exit Criteria

- A built NPV renders to deterministic full-body + face PNGs headlessly, with chunk masks honored (no body-through-clothes).
- Golden round-trip proven live: bless → re-render → compare passes; goldens and previews exist only outside the repo.
- My NPVs has a working opt-in "Render preview" action with busy/error states, smoke-tested against the mock API.
- Full suite + ruff green; the e2e golden test skips cleanly on machines without `NPV_PREVIEW_BUILD_DIR`.
