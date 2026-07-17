# Face Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the GUI save browser an **opt-in "Generate face preview"** action that renders the character's baked head to a PNG headlessly in Blender, so the user can see a real face (not just the unreliable in-game `screenshot.png`) before committing to a full build.

**Architecture:** Reuse the existing bake pipeline (WolvenKit uncook → export head morphtarget to .glb → Blender applies V's shapekeys → `baked.glb`). Add one new Blender render script + a `render_preview()` orchestration that stops after the baked head glb and renders it to PNG with a simple camera/3-point light setup. This is **opt-in per save** (real cost: the uncook+bake chain, ~tens of seconds), NOT automatic-on-list — the research established that's the only reliable face-preview path (scraping is infeasible; `screenshot.png` is a scene snapshot, not a face).

**Tech Stack:** Blender 4.x/5.x headless (bpy, EEVEE), the WolvenKit adapter, the existing `head_bake`/`blender_module` pipeline, customtkinter, pytest.

## Why this design (from research, 2026-07-17)

- **Scraping a hosted preview image is infeasible** — a real user's character never keys to any catalogued preset image, and Nexus ToS forbids scraping. Dead end.
- **`screenshot.png`** (already shown as the save-browser thumbnail) is the *scene* V was in at save time — often not a face, user-editable, untrustworthy as a character preview.
- **Rendering the baked head in Blender is the only real face signal.** The pipeline already produces the baked head glb; a single-frame EEVEE render of it is cheap (seconds) *once the mesh exists* — the cost is the upstream uncook+bake chain (needs game install + WolvenKit + Blender), so it must be a deliberate per-save action, not automatic.

## Global Constraints

- Python 3.11 floor; run via `uv run`. Gates every task: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`.
- No CDPR bytes in repo. The render script is pure `bpy` (the existing `bake_head.py` sets the precedent — pure bpy, no addons).
- Blender is invoked via the existing `blender_module` adapter (absolute-path resolution per M5 SEC-3 once that lands; until then the current resolution).
- Preview is OPT-IN per save — never rendered automatically for every save in the browser list.
- Reuse `head_bake`/`blender_module` — do NOT fork the bake pipeline. The preview stops after the baked head glb; it does not pack an archive.
- GUI logic stays testable: the orchestration (`render_preview`) is a `core`-layer function unit-tested with a mocked Blender/WolvenKit; only the button wiring lives in the view.
- Errors surface as `NpvError` (user_message + remediation) — no raw tracebacks in the GUI (GUI-8).

## File Structure

- `npv_build/data/blender/render_head.py` (new) — pure-bpy script: import a head .glb, set up camera + 3-point light framing the face, render one PNG.
- `npv_build/core/face_preview.py` (new) — `render_preview(wk, save_path, game_dir, out_png, cache_dir) -> Path`: runs uncook → export → bake (reusing the pipeline) → render_head.py → returns the PNG path. Plus a cache keyed on the save's CC hash so re-previewing the same save is instant.
- `npv_build/gui_views/save_browser_view.py` (modify) — add a "Generate face preview" button per selected save that calls `render_preview` on a worker thread and swaps the thumbnail to the rendered face.
- `npv_build/gui_backend.py` (modify) — a `PreviewWorker` (mirrors `BuildWorker`: thread + queue) so the render doesn't block the GUI and is cancellable.

## Plan Roadmap

Plan of 6 tasks. Order: T1 render script → T2 render_preview orchestration (mocked-Blender tested) → T3 preview cache → T4 PreviewWorker (threaded, cancellable) → T5 GUI button wiring → T6 real-render gate + milestone. T1-T3 are pipeline/core (unit-testable); T4-T5 are GUI; T6 is the real Blender render proof on this machine.

---

### Task 1: Blender head-render script (`data/blender/render_head.py`)

**Files:**
- Create: `npv_build/data/blender/render_head.py`
- Test: `tests/core/test_render_head_script.py` (static/AST checks — the script only runs inside Blender)

**Interfaces:**
- Consumes: nothing (standalone bpy script).
- Produces: a script runnable as `blender --background --python render_head.py -- <in.glb> <out.png>` that imports the glb, frames the head, and writes one PNG. Task 2 invokes it.

- [ ] **Step 1: Write the failing test** (the script can't run outside Blender, so test its structure statically — it must parse, define the argv contract, use EEVEE, write to the out path):

```python
# tests/core/test_render_head_script.py
import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "npv_build" / "data" / "blender" / "render_head.py"


def test_script_parses():
    ast.parse(SCRIPT.read_text(encoding="utf-8"))


def test_script_reads_two_cli_args_after_dashdash():
    text = SCRIPT.read_text(encoding="utf-8")
    # contract: argv after "--" is [in_glb, out_png]
    assert 'sys.argv' in text and '"--"' in text
    assert "in_glb" in text and "out_png" in text


def test_script_renders_still_to_out_path():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "render.filepath" in text or "filepath = out_png" in text
    assert "bpy.ops.render.render" in text and "write_still=True" in text
```

- [ ] **Step 2: RED** — `uv run pytest tests/core/test_render_head_script.py -q` → file not found.

- [ ] **Step 3: Implement** `npv_build/data/blender/render_head.py`:

```python
"""Blender headless render: one PNG of a head .glb, framed on the face.

Run via:
  blender --background --python render_head.py -- <in.glb> <out.png>

Pure bpy, no addons. Imports the glb (a baked head mesh), places a camera in
front of the face with 3-point lighting, and renders a single EEVEE frame.
Tested against Blender 4.x/5.x.
"""

import sys

import bpy


def _args():
    argv = sys.argv
    idx = argv.index("--")
    in_glb, out_png = argv[idx + 1], argv[idx + 2]
    return in_glb, out_png


def main():
    in_glb, out_png = _args()

    # clean scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=in_glb)

    # find the head mesh + its bounds
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("render_head: no mesh in glb")
    head = meshes[0]
    bpy.context.view_layer.objects.active = head

    # frame: camera in front (+Y toward face is glb convention), slightly above
    import mathutils

    bbox = [head.matrix_world @ mathutils.Vector(c) for c in head.bound_box]
    center = sum(bbox, mathutils.Vector()) / 8.0
    height = max(v.z for v in bbox) - min(v.z for v in bbox)
    dist = height * 2.2

    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = center + mathutils.Vector((0, -dist, height * 0.15))
    # point camera at the upper-head/face
    look = center + mathutils.Vector((0, 0, height * 0.2))
    direction = look - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    # 3-point lighting
    for name, loc, energy in (
        ("key", (dist, -dist, dist), 800),
        ("fill", (-dist, -dist, 0), 300),
        ("rim", (0, dist, dist), 400),
    ):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = dist
        lo = bpy.data.objects.new(name, ld)
        lo.location = center + mathutils.Vector(loc)
        bpy.context.scene.collection.objects.link(lo)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in _engines() else "BLENDER_EEVEE"
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = out_png
    bpy.ops.render.render(write_still=True)


def _engines():
    try:
        return {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    except Exception:
        return set()


if __name__ == "__main__":
    main()
```

(Note: EEVEE engine identifier differs between Blender 4.2 `BLENDER_EEVEE` and 5.x `BLENDER_EEVEE_NEXT` — the `_engines()` guard picks the available one. The `+Y`/`-Y` facing may need flipping in Task 6's real render — the camera-direction is the one thing to verify against a real render and adjust; note this in the report.)

- [ ] **Step 4: GREEN** — `uv run pytest tests/core/test_render_head_script.py -q`

- [ ] **Step 5: Commit** — `git add npv_build/data/blender/render_head.py tests/core/test_render_head_script.py && git commit -m "feat(preview): Blender headless head-render script"`

---

### Task 2: `render_preview` orchestration (`core/face_preview.py`)

**Files:**
- Create: `npv_build/core/face_preview.py`
- Test: `tests/core/test_face_preview.py`

**Interfaces:**
- Consumes: WolvenKit adapter, the existing bake pipeline (`head_bake`/`blender_module` — the same uncook→export→bake steps a build uses, stopping at the baked glb), `blender_module`'s Blender invocation, `NpvError`.
- Produces: `render_preview(wk, save_path: Path, game_dir: Path, out_png: Path, cache_dir: Path, cancel=None) -> Path` — parses the save, resolves+uncooks+exports the head morphtarget, bakes V's morphs into the head glb (reusing the pipeline), then invokes `render_head.py` on that glb, returns `out_png`. Raises `NpvError`/`BlenderError` on failure. The seams (`_parse`, `_bake_head_glb`, `_render`) are module-level for mock-testing.

- [ ] **Step 1: Read the bake pipeline** to find the exact call sequence a build uses to produce the baked head glb (`blender_module.bake_face_mesh` and `head_bake` — identify the function that yields `baked.glb` and stop there; the preview does NOT need the WolvenKit re-import or the pack). Document the reused entry points in your report.

- [ ] **Step 2: Write the failing tests** (mock the seams — no real Blender/WolvenKit):

```python
# tests/core/test_face_preview.py
from pathlib import Path

import pytest

import npv_build.core.face_preview as fp
from npv_build.core.errors import NpvError


def test_render_preview_calls_bake_then_render(monkeypatch, tmp_path):
    calls = []
    baked = tmp_path / "baked.glb"
    baked.write_bytes(b"glb")
    out = tmp_path / "preview.png"

    monkeypatch.setattr(fp, "_parse", lambda save_path: calls.append("parse") or {"patch": "2.31", "body_rig": "pwa"})
    monkeypatch.setattr(fp, "_bake_head_glb", lambda wk, cc, game_dir, cache_dir, cancel: calls.append("bake") or baked)
    monkeypatch.setattr(fp, "_render", lambda glb, png, cancel: calls.append("render") or png.write_bytes(b"png"))

    result = fp.render_preview(wk=object(), save_path=tmp_path / "s.dat", game_dir=tmp_path, out_png=out, cache_dir=tmp_path)
    assert result == out and out.exists()
    assert calls == ["parse", "bake", "render"]


def test_render_preview_bake_failure_propagates(monkeypatch, tmp_path):
    monkeypatch.setattr(fp, "_parse", lambda save_path: {"patch": "2.31", "body_rig": "pwa"})
    def boom(*a, **k):
        raise NpvError("bake failed", remediation="check blender")
    monkeypatch.setattr(fp, "_bake_head_glb", boom)
    with pytest.raises(NpvError):
        fp.render_preview(wk=object(), save_path=tmp_path / "s.dat", game_dir=tmp_path, out_png=tmp_path / "o.png", cache_dir=tmp_path)
```

- [ ] **Step 3: RED → implement** `face_preview.py` with `_parse` (calls `save_parser.parse_save`), `_bake_head_glb` (reuses the pipeline's uncook→export→bake to produce the baked head glb — the real entry points found in Step 1), `_render` (invokes `render_head.py` via `blender_module`'s Blender runner), and `render_preview` orchestrating them with `cancel.raise_if_cancelled()` between stages.

- [ ] **Step 4: GREEN** — `uv run pytest tests/core/test_face_preview.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(preview): render_preview orchestration (bake head glb -> render PNG)"`

---

### Task 3: Preview cache (keyed on CC hash)

**Files:**
- Modify: `npv_build/core/face_preview.py` (cache lookup/store)
- Test: `tests/core/test_face_preview.py` (extend)

**Interfaces:**
- Consumes: `render_preview` (T2), `compute_mod_id`/a CC hash (orchestrator has the hashing).
- Produces: `render_preview` checks `cache_dir / f"{cc_hash}.png"` first — if present, returns it without re-baking; else renders and stores it there. Re-previewing the same save is instant.

- [ ] **Step 1: Write the failing test**

```python
def test_render_preview_uses_cache(monkeypatch, tmp_path):
    import npv_build.core.face_preview as fp

    cc = {"patch": "2.31", "body_rig": "pwa"}
    monkeypatch.setattr(fp, "_parse", lambda save_path: cc)
    # pre-seed the cache with the CC hash
    cache = tmp_path / "cache"
    cache.mkdir()
    cached = cache / (fp._cc_hash(cc) + ".png")
    cached.write_bytes(b"cached-png")

    bake_calls = []
    monkeypatch.setattr(fp, "_bake_head_glb", lambda *a, **k: bake_calls.append(1))
    result = fp.render_preview(wk=object(), save_path=tmp_path / "s.dat", game_dir=tmp_path, out_png=tmp_path / "o.png", cache_dir=cache)
    assert result == cached and not bake_calls  # cache hit -> no bake
```

- [ ] **Step 2: RED → implement** `_cc_hash(cc_settings) -> str` (stable hash of the CC dict, reuse the orchestrator's `compute_mod_id` hashing pattern) and the cache short-circuit in `render_preview`.

- [ ] **Step 3: GREEN** — `uv run pytest tests/core/test_face_preview.py -q`

- [ ] **Step 4: Commit** — `git commit -m "feat(preview): cache rendered previews by CC hash"`

---

### Task 4: `PreviewWorker` (threaded, cancellable)

**Files:**
- Modify: `npv_build/gui_backend.py`
- Test: `tests/gui_logic/test_preview_worker.py`

**Interfaces:**
- Consumes: `render_preview` (T2), `CancelToken` (M1), the queue-tuple pattern.
- Produces: `PreviewWorker` mirroring `BuildWorker` — `__init__(log_queue)`, `start(**kwargs)`, `cancel()`, `is_alive`, posting `("preview_done", png_path)` / `("preview_error", msg)` on the queue. Runs `render_preview` off the main thread so the GUI stays responsive.

- [ ] **Step 1: Write the failing tests** (mock render_preview):

```python
# tests/gui_logic/test_preview_worker.py
import queue as queue_mod

from npv_build import gui_backend
from npv_build.core.errors import NpvError


def _drain(q):
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue_mod.Empty:
            return items


def test_preview_worker_success(monkeypatch, tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"x")
    monkeypatch.setattr(gui_backend, "render_preview", lambda **k: png)
    q = queue_mod.Queue()
    w = gui_backend.PreviewWorker(q)
    w.start(save_path=tmp_path / "s.dat", game_dir=tmp_path, out_png=png, cache_dir=tmp_path)
    w._thread.join(timeout=10)
    assert ("preview_done", str(png)) in _drain(q)


def test_preview_worker_error(monkeypatch, tmp_path):
    def boom(**k):
        raise NpvError("no blender", remediation="install blender")
    monkeypatch.setattr(gui_backend, "render_preview", boom)
    q = queue_mod.Queue()
    w = gui_backend.PreviewWorker(q)
    w.start(save_path=tmp_path / "s.dat", game_dir=tmp_path, out_png=tmp_path / "p.png", cache_dir=tmp_path)
    w._thread.join(timeout=10)
    errs = [v for k, v in _drain(q) if k == "preview_error"]
    assert errs and "no blender" in errs[0]
```

- [ ] **Step 2: RED → implement** `PreviewWorker` (copy `BuildWorker`'s thread+token structure; `_run` calls `render_preview`, posts `preview_done`/`preview_error`; `NpvError` → user_message+remediation; blanket except with the sanctioned `# noqa: BLE001 - GUI event loop must survive`). Import `render_preview` at module level so it's monkeypatchable.

- [ ] **Step 3: GREEN** — `uv run pytest tests/gui_logic/test_preview_worker.py -q`

- [ ] **Step 4: Commit** — `git commit -m "feat(gui): PreviewWorker — threaded, cancellable face-preview render"`

---

### Task 5: GUI button wiring (save browser)

**Files:**
- Modify: `npv_build/gui_views/save_browser_view.py`
- Test: `tests/gui_logic/test_save_browser_view.py` (extend — logic only + headless smoke)

**Interfaces:**
- Consumes: `PreviewWorker` (T4).
- Produces: the save browser gains a "Generate face preview" button on the selected save; clicking it starts a `PreviewWorker`, shows a spinner/"Rendering…" state, and on `preview_done` swaps that save's thumbnail to the rendered PNG (via the existing guarded `CTkImage` load — which now handles bad images from T2 of M4). On `preview_error`, shows the error via the host's error affordance (no traceback).

- [ ] **Step 1: Write the failing test** (the pure bit: the view exposes a public `request_preview(entry, on_done, on_error)` seam that starts the worker and routes results — test the seam with a fake worker, no real render):

```python
# append to tests/gui_logic/test_save_browser_view.py
def test_request_preview_routes_done(monkeypatch, tmp_path):
    from npv_build.gui_views import save_browser_view as sbv

    # a fake worker that immediately posts preview_done
    class FakeWorker:
        def __init__(self, q): self.q = q
        def start(self, **k): self.q.put(("preview_done", str(k["out_png"])))
        @property
        def is_alive(self): return False
    monkeypatch.setattr(sbv, "PreviewWorker", FakeWorker)
    # the pure router: given a queue drain, calls on_done with the png
    done = []
    sbv.route_preview_event(("preview_done", "/x/p.png"), on_done=done.append, on_error=lambda m: None)
    assert done == ["/x/p.png"]
```

- [ ] **Step 2: RED → implement** `route_preview_event(event, on_done, on_error)` (pure dispatch) + the button + worker wiring + poll loop in the view (mirror `BuildView`'s poll pattern). The thumbnail swap reuses the existing `_load_thumbnail` guarded path.

- [ ] **Step 3: GREEN + headless smoke** — `uv run pytest tests/gui_logic/test_save_browser_view.py -q` + the save-browser smoke still builds.

- [ ] **Step 4: Commit** — `git commit -m "feat(gui): Generate face preview button in save browser (spec: opt-in preview)"`

---

### Task 6: Real-render gate + milestone

**Files:** none new — this is the proof that it actually renders a face on this machine.

- [ ] **Step 1: Real render.** On this machine (game install + WolvenKit 8.19 + Blender in cache), run `render_preview` against the real 2.31 save end-to-end and produce a PNG:

```
uv run python -c "
from pathlib import Path
from npv_build.wk_cli import WolvenKit, WolvenKitConfig
from npv_build.core.face_preview import render_preview
wk = WolvenKit(WolvenKitConfig(game_dir=Path('/home/pdp/.local/share/Steam/steamapps/common/Cyberpunk 2077')))
save = Path('/home/pdp/.local/share/Steam/steamapps/compatdata/1091500/pfx/drive_c/users/steamuser/Saved Games/CD Projekt Red/Cyberpunk 2077/ManualSave-0/sav.dat')
out = render_preview(wk=wk, save_path=save, game_dir=wk.config.game_dir, out_png=Path('/tmp/claude-1000/face_preview.png'), cache_dir=Path('/tmp/claude-1000/preview_cache'))
print('rendered:', out, out.stat().st_size, 'bytes')
"
```

- [ ] **Step 2: Inspect the PNG.** Open `/tmp/claude-1000/face_preview.png` (Read it as an image). Verify it shows a head/face, not an empty frame or the back of the head. **If the camera faces the wrong way** (back of head, or empty), flip the camera `-Y`/`+Y` in `render_head.py` (the documented Task-1 uncertainty) and re-render until the face is visible. Record the final camera orientation.

- [ ] **Step 3: Cache proof.** Re-run the same render command — the second run must hit the cache (near-instant, no Blender invocation). Confirm via timing/log.

- [ ] **Step 4: Milestone gate** — full suite + ruff check + ruff format --check green; push branch; CI green (the render itself isn't in CI — it needs the game install — but the unit tests + gui-smoke are).

- [ ] **Step 5: Commit** any camera-orientation fix + a note in the report with the rendered-PNG dimensions and that a real face was produced.

---

## Exit Criteria

- `render_head.py` renders a head glb to PNG headlessly; `render_preview` orchestrates uncook→bake→render and caches by CC hash.
- A real face PNG is produced from the 2.31 save on this machine (verified by eye — a face, not an empty/back-of-head frame).
- The save browser has an opt-in "Generate face preview" button that renders off-thread (PreviewWorker), swaps the thumbnail, and surfaces errors without tracebacks.
- Re-previewing the same save hits the cache (instant).
- Unit tests + GUI smoke green in CI; the real render is a manual/local gate (needs the game install).

## Notes

- **Dependency on M5 SEC-3:** if M5's absolute-path tool resolution lands first, `_render` uses the resolved Blender path; otherwise it uses `blender_module`'s current resolution. Either works — this plan doesn't block on M5.
- **This is genuinely opt-in.** Do not add automatic preview rendering to `list_saves` or the browser's initial population — the cost (uncook+bake) is too high for a passive list. The button is the only trigger.
- **Camera orientation is the one empirical unknown** (glb facing convention) — Task 6 Step 2 resolves it against a real render; everything else is deterministic.
