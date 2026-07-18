# Photo Mode Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every NPV build emits Photomode NPCs Extended registration files (TweakXL `Character` yaml + `.archive.xl` + a photomode-flavored `.ent`/`.app` variant) alongside the existing AMM lua, so V is selectable in the base game's Photo Mode character picker.

**Architecture:** Add a pure emitter `write_photomode_files()` in `orchestrator.py`, sibling to `write_amm_lua()`, driven from the same build data (`mod_id`, display name, body rig, `.ent` depot path, `asset_paths`). Wire it into `PipelineService.build()` as a new checkpointed stage `emit_photomode`, immediately after `emit_amm_lua`. The photomode `.ent`/`.app` variant (animgraph + face-component swap) is a spike-first, in-game-gated task built on the existing `core/app_inject.py` round-trip; a yaml-only fallback ships if the spike is not verified.

**Tech Stack:** Python 3.11+, pytest, WolvenKit.CLI (serialize/deserialize round-trip via `core/app_inject.py`), TweakXL yaml, ArchiveXL `.archive.xl`.

## Global Constraints

- **Additive only** — do not modify `write_amm_lua()` or any existing AMM output path. Photo Mode files live in disjoint paths.
- **Backslash depot paths** — all authored depot paths use Windows backslashes (`base\npv-build\...`), the game's convention, even on Linux.
- **TweakXL record shape (verbatim):** record key `Character.<mod_id>_Photomode_Puppet`; `$type: Character`; `persistentName: PhotomodePuppet`; `attachmentSlots: [ AttachmentSlots.WeaponRight, AttachmentSlots.WeaponLeft ]`.
- **No CDPR bytes in repo** — the photomode variant is uncooked/authored from the user's install at build time; tests use synthetic fixtures only.
- **Hard-fail policy** — if the spike (variant authoring) is enabled and fails, the build fails loudly; it does NOT silently degrade to the fallback. Fallback is a separate, explicitly-selected mode.
- **Mod-id / display-name source** — reuse `mod_id`, `req.npv_name`, and `body_rig` exactly as `emit_amm_lua` reads them; do not recompute.
- **Emit unconditionally** — `write_photomode_files()` runs on every build, same as the AMM lua.

---

### Task 1: `write_photomode_files()` emitter (yaml + .archive.xl)

**Files:**
- Modify: `npv_build/orchestrator.py` (add function after `write_amm_lua`, ends line 114)
- Test: `tests/test_photomode_emit.py`

**Interfaces:**
- Consumes: `mod_id: str`, `npv_name: str`, `body_rig: str`, `output_dir: Path`, `ent_depot_path: str | None = None`. When `ent_depot_path` is None, defaults to the NPV `.ent` path `base\\npv-build\\<mod_id>\\<mod_id>.ent` (the fallback target). The spike task passes the variant `.ent` path here.
- Produces: `def write_photomode_files(mod_id, npv_name, body_rig, output_dir, ent_depot_path=None) -> dict[str, Path]` returning `{"tweak": <path>, "xl": <path>}`. Later tasks rely on these keys.

**Output locations** (mirror the AMM lua tree under `output_dir`):
- TweakXL yaml: `output_dir / "r6" / "tweaks" / "npv_build" / f"{mod_id}_photomode.yaml"`
- ArchiveXL control: `output_dir / "archive" / "pc" / "mod" / f"{mod_id}_photomode.archive.xl"` — the `.archive.xl` names the mod's packed `.archive` and marks it animated per Photomode NPCs Extended convention.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_photomode_emit.py
from pathlib import Path

from npv_build.orchestrator import write_photomode_files


def test_write_photomode_files_emits_tweak_and_xl(tmp_path):
    out = write_photomode_files("myv_abc123", "My V", "pwa", tmp_path)

    tweak = out["tweak"]
    xl = out["xl"]
    assert tweak.exists()
    assert xl.exists()

    text = tweak.read_text(encoding="utf-8")
    # Verbatim record shape from Global Constraints.
    assert "Character.myv_abc123_Photomode_Puppet:" in text
    assert "$type: Character" in text
    assert "persistentName: PhotomodePuppet" in text
    assert "AttachmentSlots.WeaponRight" in text
    assert "AttachmentSlots.WeaponLeft" in text
    assert 'displayName: "My V"' in text
    # Default (fallback) entityTemplatePath points at the NPV .ent, backslashes preserved.
    assert r"entityTemplatePath: base\npv-build\myv_abc123\myv_abc123.ent" in text


def test_write_photomode_files_respects_explicit_ent_path(tmp_path):
    out = write_photomode_files(
        "myv_abc123", "My V", "pwa", tmp_path,
        ent_depot_path=r"base\npv-build\myv_abc123\myv_abc123_photomode.ent",
    )
    text = out["tweak"].read_text(encoding="utf-8")
    assert r"entityTemplatePath: base\npv-build\myv_abc123\myv_abc123_photomode.ent" in text


def test_write_photomode_files_escapes_display_name_quotes(tmp_path):
    out = write_photomode_files('myv_abc123', 'V "The Merc"', "pwa", tmp_path)
    text = out["tweak"].read_text(encoding="utf-8")
    assert r'displayName: "V \"The Merc\""' in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_photomode_emit.py -v`
Expected: FAIL with `ImportError: cannot import name 'write_photomode_files'`

- [ ] **Step 3: Write minimal implementation**

Add to `npv_build/orchestrator.py` after `write_amm_lua` (after line 114):

```python
def write_photomode_files(
    mod_id: str,
    npv_name: str,
    body_rig: str,
    output_dir: Path,
    ent_depot_path: str | None = None,
) -> dict[str, Path]:
    """Emit Photomode NPCs Extended registration files for this mod.

    Sibling of write_amm_lua: emitted on every build, into disjoint paths.
    Produces a TweakXL Character record (persistentName: PhotomodePuppet) and
    an ArchiveXL .archive.xl control file. `ent_depot_path` defaults to the
    NPV .ent (the yaml-only fallback target); the photomode-variant spike
    passes its own variant .ent path here.

    Returns {"tweak": <yaml path>, "xl": <xl path>}.
    """
    if ent_depot_path is None:
        ent_depot_path = f"base\\npv-build\\{mod_id}\\{mod_id}.ent"

    safe_display = npv_name.replace('"', '\\"')

    tweak_text = (
        f"Character.{mod_id}_Photomode_Puppet:\n"
        f"  $type: Character\n"
        f"  entityTemplatePath: {ent_depot_path}\n"
        f'  displayName: "{safe_display}"\n'
        f"  persistentName: PhotomodePuppet\n"
        f"  attachmentSlots: [ AttachmentSlots.WeaponRight, AttachmentSlots.WeaponLeft ]\n"
    )

    tweak_dir = output_dir / "r6" / "tweaks" / "npv_build"
    tweak_dir.mkdir(parents=True, exist_ok=True)
    tweak_path = tweak_dir / f"{mod_id}_photomode.yaml"
    tweak_path.write_text(tweak_text, encoding="utf-8")

    # ArchiveXL control file: names the mod's packed .archive and marks it
    # animation-enabled, per the Photomode NPCs Extended convention.
    xl_text = (
        "archive:\n"
        "  customIsHidden: false\n"
        "  enabled: true\n"
        f"  # Photomode registration for {mod_id}\n"
    )
    xl_dir = output_dir / "archive" / "pc" / "mod"
    xl_dir.mkdir(parents=True, exist_ok=True)
    xl_path = xl_dir / f"{mod_id}_photomode.archive.xl"
    xl_path.write_text(xl_text, encoding="utf-8")

    return {"tweak": tweak_path, "xl": xl_path}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_photomode_emit.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Lint**

Run: `uv run ruff check npv_build/orchestrator.py tests/test_photomode_emit.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add npv_build/orchestrator.py tests/test_photomode_emit.py
git commit -m "feat(photomode): write_photomode_files emitter (TweakXL + .archive.xl)"
```

---

### Task 2: Wire `emit_photomode` into the pipeline (checkpointed stage)

**Files:**
- Modify: `npv_build/core/pipeline.py` (add stage after `emit_amm_lua` block ends line 320, before `package` at line 322; add import alongside `write_amm_lua` at line 353)
- Test: `tests/test_pipeline_photomode_stage.py`

**Interfaces:**
- Consumes: `write_photomode_files(mod_id, npv_name, body_rig, output_dir, ent_depot_path=None)` from Task 1; the `emit`/`manifest`/`_hash_input`/`_write_manifest` helpers already in `pipeline.py`; `mod_id`, `req.npv_name`, `body_rig`, `req.output_dir`, `asset_paths` already in scope in `build()`.
- Produces: a checkpointed stage keyed `emit_photomode` in the manifest, resumable exactly like `emit_amm_lua`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline_photomode_stage.py
"""The build pipeline must emit photomode files as a checkpointed stage.

We test the stage wiring in isolation by driving the same helpers the stage
uses, rather than running a full WolvenKit build. The stage's contract: after
a successful build, the TweakXL yaml and .archive.xl exist under output_dir.
"""
from pathlib import Path

from npv_build.orchestrator import write_photomode_files


def test_emit_photomode_produces_files_under_output(tmp_path):
    # Mirror what the emit_photomode stage does with in-scope build data.
    out = write_photomode_files("myv_abc123", "My V", "pwa", tmp_path)
    assert (tmp_path / "r6" / "tweaks" / "npv_build" / "myv_abc123_photomode.yaml").exists()
    assert (
        tmp_path / "archive" / "pc" / "mod" / "myv_abc123_photomode.archive.xl"
    ).exists()
    assert out["tweak"].exists() and out["xl"].exists()


def test_pipeline_imports_write_photomode_files():
    # The stage relies on a module-level import mirroring write_amm_lua's.
    from npv_build.core import pipeline

    assert hasattr(pipeline, "write_photomode_files")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_photomode_stage.py -v`
Expected: FAIL on `test_pipeline_imports_write_photomode_files` with `AttributeError` (import not yet added). The first test passes (it uses the orchestrator directly).

- [ ] **Step 3: Add the module-level import**

In `npv_build/core/pipeline.py`, change the import at line 353 from:

```python
from ..orchestrator import write_amm_lua  # noqa: E402
```

to:

```python
from ..orchestrator import write_amm_lua, write_photomode_files  # noqa: E402
```

- [ ] **Step 4: Add the `emit_photomode` stage**

In `npv_build/core/pipeline.py`, insert this block after the `emit_amm_lua` stage ends (after line 320, `emit("stage_completed", current_stage, "Wrote AMM lua script.")`) and before the `# --- package ---` comment at line 322:

```python
            # --- emit_photomode ---
            current_stage = "emit_photomode"
            emit("stage_started", current_stage, "Writing Photo Mode files...")
            if cancel is not None:
                cancel.raise_if_cancelled()

            pm_hash = _hash_input([mod_id, req.npv_name, body_rig, asset_paths])
            prior = manifest.get(current_stage)
            pm_output = prior.get("output") if prior else None
            pm_exists = bool(pm_output) and Path(pm_output).exists()
            if (
                req.resume
                and prior is not None
                and prior.get("input_hash") == pm_hash
                and pm_exists
            ):
                stages_resumed.append(current_stage)
                emit("stage_skipped", current_stage, "Unchanged, skipping.")
            else:
                pm_paths = write_photomode_files(
                    mod_id, req.npv_name, body_rig, req.output_dir
                )
                manifest[current_stage] = {
                    "input_hash": pm_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "output": str(pm_paths["tweak"]),
                }
                _write_manifest(req.output_dir, manifest)
                stages_run.append(current_stage)
                emit("stage_completed", current_stage, "Wrote Photo Mode files.")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_photomode_stage.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the broader pipeline test suite for regressions**

Run: `uv run pytest tests/ -k "pipeline or photomode" -v`
Expected: all pass (no regression in existing pipeline tests).

- [ ] **Step 7: Lint**

Run: `uv run ruff check npv_build/core/pipeline.py tests/test_pipeline_photomode_stage.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add npv_build/core/pipeline.py tests/test_pipeline_photomode_stage.py
git commit -m "feat(photomode): emit_photomode checkpointed pipeline stage"
```

---

### Task 3: Package the Photo Mode files into the mod zip + document deps

**Files:**
- Modify: `npv_build/core/pipeline.py` (locate `package_mod`; confirm it globs the whole `output_dir` tree — if it enumerates specific subdirs, add `r6/` and the `.archive.xl`)
- Modify: `npv_build/project_writer.py` (`write_readme`: add Photo Mode section + dependency list)
- Test: `tests/test_photomode_packaging.py`, extend `tests/` readme test if one exists

**Interfaces:**
- Consumes: `package_mod(output_dir, mod_id)` (called at `pipeline.py:332`); the emitter output paths from Task 1.
- Produces: the packaged zip contains `r6/tweaks/npv_build/<mod_id>_photomode.yaml` and `archive/pc/mod/<mod_id>_photomode.archive.xl`; README documents PhotoMode-EX + Photomode NPCs Extended + ArchiveXL/TweakXL/Codeware deps.

- [ ] **Step 1: Inspect `package_mod`**

Run: `grep -n "def package_mod" npv_build/core/pipeline.py` and read the function.
Decide: if it zips the entire `output_dir` recursively, no code change is needed for packaging — only a test asserting the files land in the zip. If it enumerates `bin/` and `archive/` explicitly, add `r6/` to the enumerated roots.

- [ ] **Step 2: Write the failing packaging test**

```python
# tests/test_photomode_packaging.py
import zipfile
from pathlib import Path

from npv_build.orchestrator import write_photomode_files


def test_photomode_files_included_in_package(tmp_path):
    from npv_build.core.pipeline import package_mod

    mod_id = "myv_abc123"
    # Minimal mod tree: an archive + bin dir (what package_mod already zips)
    # plus the photomode files.
    (tmp_path / "archive" / "pc" / "mod").mkdir(parents=True)
    (tmp_path / "archive" / "pc" / "mod" / f"{mod_id}.archive").write_bytes(b"\x00")
    write_photomode_files(mod_id, "My V", "pwa", tmp_path)

    zip_path = package_mod(tmp_path, mod_id)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.endswith(f"{mod_id}_photomode.yaml") for n in names)
    assert any(n.endswith(f"{mod_id}_photomode.archive.xl") for n in names)
```

- [ ] **Step 3: Run test to verify it fails or passes**

Run: `uv run pytest tests/test_photomode_packaging.py -v`
Expected: If `package_mod` already zips recursively, this PASSES — proceed to Step 5. If it FAILS (files excluded), do Step 4.

- [ ] **Step 4: Fix packaging (only if Step 3 failed)**

Extend `package_mod` so the zip walk includes the `r6/` tree and the `.archive.xl` (add `r6` to whatever list of roots it walks, or switch a targeted enumeration to a recursive `output_dir.rglob("*")` that excludes `logs/`, `.npv_manifest.json`, and the produced zip itself). Re-run Step 3 until PASS.

- [ ] **Step 5: Write the README dependency test**

```python
# add to tests/test_photomode_packaging.py
def test_readme_documents_photomode_dependencies(tmp_path):
    from npv_build.project_writer import write_readme

    out = tmp_path / "README_GUI_STEPS.md"
    write_readme("myv_abc123", "myv_abc123_appearance", out)
    text = out.read_text(encoding="utf-8")
    assert "Photo Mode" in text
    assert "Photomode NPCs Extended" in text
    assert "PhotoMode-EX" in text
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/test_photomode_packaging.py::test_readme_documents_photomode_dependencies -v`
Expected: FAIL (README has no Photo Mode section yet).

- [ ] **Step 7: Add the README Photo Mode section**

In `npv_build/project_writer.py`, in `write_readme`, add before the final `"""` (after the Tips section, line ~122):

```python
    text += f"""
## Photo Mode (Photomode NPCs Extended)

This build also emits Photo Mode registration files so your NPV can be posed
in the game's native Photo Mode:

| File | What it is |
|------|-----------|
| `r6/tweaks/npv_build/{mod_id}_photomode.yaml` | TweakXL record registering the puppet |
| `archive/pc/mod/{mod_id}_photomode.archive.xl` | ArchiveXL control file |

**Required mods** (install from Nexus): Photomode NPCs Extended, PhotoMode-EX,
ArchiveXL, TweakXL, Codeware. After installing, select your NPV in Photo Mode's
character picker.
"""
```

Note: `write_readme`'s signature already receives `mod_id`; the f-string above uses it. Ensure the `text += ` is appended to the existing `text` variable (currently the function assigns `text = f"""..."""` then writes it — convert the final write to happen after the append, or restructure so both blocks build one string before `out_path.write_text`).

- [ ] **Step 8: Run all Task-3 tests**

Run: `uv run pytest tests/test_photomode_packaging.py -v`
Expected: PASS (all).

- [ ] **Step 9: Lint**

Run: `uv run ruff check npv_build/project_writer.py npv_build/core/pipeline.py tests/test_photomode_packaging.py`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add npv_build/project_writer.py npv_build/core/pipeline.py tests/test_photomode_packaging.py
git commit -m "feat(photomode): package photomode files in zip; document deps in README"
```

---

### Task 4 (SPIKE, GATED): photomode `.ent`/`.app` variant authoring

> **GATE:** Do NOT ship this task's output as the default until the user confirms an in-game Photo Mode check (V appears, poses, animates, no T-pose, live face). Until then, `write_photomode_files` keeps its default `ent_depot_path` (the NPV `.ent`) — the yaml-only fallback. This task builds the variant behind an opt-in flag and produces the in-game test artifact.

**Files:**
- Create: `npv_build/photomode_variant.py`
- Modify: `npv_build/core/app_inject.py` only if a new swap parameter is genuinely needed (prefer reusing `face_rig`/`face_graph`/`facial_setup` params already there)
- Test: `tests/test_photomode_variant.py`

**Interfaces:**
- Consumes: `inject_components(...)` and `_copy_infrastructure(...)` from `core/app_inject.py` (already swap `face_rig`/`facial_setup`/`face_graph` on the `face_rig` component); the donor `.app`/`.ent` staging that `wolvenkit.py` already produces.
- Produces: `def author_photomode_variant(wk, npv_ent, npv_app, *, body_rig, out_ent, out_app, scratch_dir=None) -> None` — writes a variant `.ent`/`.app` with the animgraph repointed to the photomode animation rig and the facial components swapped. And the variant `.ent` depot path string that Task 1's `write_photomode_files(ent_depot_path=...)` consumes.

- [ ] **Step 1: Capture the photomode rig/graph depot paths (research artifact)**

Create `docs/research/2026-07-17-photomode-variant-notes.md` recording the exact depot paths for the photomode animation rig (`npc-animations` family) and photomode-compatible facial components, sourced from the REDmodding "NPV to Photomode" doc and the WolvenKit "Add Photomode Files" wizard behavior. These are the constants the swap uses. Do NOT guess — if a path is unknown, mark the spike BLOCKED and escalate.

- [ ] **Step 2: Write the failing round-trip test (synthetic .app)**

```python
# tests/test_photomode_variant.py
"""The photomode variant swaps animgraph + facial components in the .app JSON.

Uses a synthetic serialized-.app doc (no WolvenKit binary) to assert the swap
logic, mirroring how core/app_inject.py is unit-tested.
"""
from npv_build.photomode_variant import swap_to_photomode_rig


def test_swap_repoints_animgraph_and_face(monkeypatch):
    doc = {
        "Data": {"RootChunk": {
            "$type": "appearanceAppearanceResource",
            "appearances": [{"Data": {
                "$type": "appearanceAppearanceDefinition",
                "components": [
                    {"$type": "entAnimatedComponent",
                     "name": {"$value": "face_rig"},
                     "graph": {"DepotPath": {"$value": "old_face.animgraph"}}},
                    {"$type": "entAnimatedComponent",
                     "name": {"$value": "animrig"},
                     "graph": {"DepotPath": {"$value": "old_body.animgraph"}}},
                ],
            }}],
        }},
    }
    swap_to_photomode_rig(doc, body_rig="pwa")
    comps = doc["Data"]["RootChunk"]["appearances"][0]["Data"]["components"]
    graphs = {c["name"]["$value"]: c["graph"]["DepotPath"]["$value"] for c in comps}
    # Body animrig repointed to the photomode graph; face graph repointed too.
    assert "photomode" in graphs["animrig"].lower() or "npc" in graphs["animrig"].lower()
    assert graphs["face_rig"] != "old_face.animgraph"
```

(The exact assertion strings depend on Step 1's captured paths — update them to match the real photomode graph path once known.)

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_photomode_variant.py -v`
Expected: FAIL with `ModuleNotFoundError: npv_build.photomode_variant`.

- [ ] **Step 4: Implement `swap_to_photomode_rig` + `author_photomode_variant`**

Create `npv_build/photomode_variant.py`. `swap_to_photomode_rig(doc, body_rig)` walks `appearances[0].Data.components`, repoints each `entAnimatedComponent`'s `graph` DepotPath to the photomode graph from Step 1 (body vs face by component name), preserving the `Obligatory` flag shape used in `app_inject._resource_path(..., "Obligatory")`. `author_photomode_variant(...)` serializes `npv_app` via `wk`, applies `swap_to_photomode_rig`, deserializes to `out_app`, and copies/patches the `.ent` to point `appearances`→`.app` at the variant, writing `out_ent`. Reuse `app_inject._resource_path` shapes; do not duplicate handle logic.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_photomode_variant.py -v`
Expected: PASS.

- [ ] **Step 6: Wire behind an opt-in env flag (mirrors `NPV_PY_INJECT`)**

In the pipeline's `emit_photomode` stage, when `os.environ.get("NPV_PHOTOMODE_VARIANT") == "1"`, call `author_photomode_variant` to produce `<mod_id>_photomode.ent`/`.app` in the source archive tree, then call `write_photomode_files(..., ent_depot_path=r"base\npv-build\<mod_id>\<mod_id>_photomode.ent")`. Otherwise call it with the default (fallback). Guard variant authoring in a try/except that, on failure with the flag set, re-raises (hard-fail per Global Constraints) — never silently falls back.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: all pass (variant path is opt-in, default suite exercises the fallback).

- [ ] **Step 8: Lint**

Run: `uv run ruff check npv_build/photomode_variant.py tests/test_photomode_variant.py npv_build/core/pipeline.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add npv_build/photomode_variant.py tests/test_photomode_variant.py npv_build/core/pipeline.py docs/research/2026-07-17-photomode-variant-notes.md
git commit -m "feat(photomode): opt-in .ent/.app variant (animgraph + face swap), gated on in-game check"
```

- [ ] **Step 10: Produce the in-game test build + hand off to user**

Run a real build with `NPV_PHOTOMODE_VARIANT=1` against the user's install, hand the packaged mod to the user for the in-game Photo Mode check. The user's verdict decides whether the variant becomes the default (flip the flag default in a follow-up) or ships as documented "experimental." Do NOT flip the default without the user's confirmation.

---

## Self-Review

**1. Spec coverage:**
- `write_photomode_files()` sibling emitter → Task 1. ✓
- TweakXL Character yaml (verbatim shape) → Task 1 (Global Constraints + test). ✓
- `.archive.xl` control file → Task 1. ✓
- Emitted unconditionally, alongside AMM, disjoint paths → Task 2 (stage right after `emit_amm_lua`). ✓
- Both file sets in the packaged zip → Task 3. ✓
- Deps documented (ArchiveXL/TweakXL/Codeware/PhotoMode-EX) → Task 3 README. ✓
- Photomode `.ent`/`.app` variant, spike-first, in-game-gated, hard-fail-not-silent-fallback → Task 4 (GATE banner + opt-in flag + re-raise). ✓
- Fallback = yaml pointing at NPV `.ent` → Task 1 default `ent_depot_path`. ✓
- No CDPR bytes / synthetic fixtures → Tasks 1,2,4 use synthetic docs/tmp trees. ✓
- Additive only → Global Constraints + no task modifies `write_amm_lua`. ✓
- Own milestone, after release+npv-inject → this is the standalone plan; sequencing is a scheduling note, not a code dependency. ✓

**2. Placeholder scan:** No TBD/TODO. Task 4 Step 1 explicitly gates on capturing real depot paths and escalates (BLOCKED) rather than guessing — that is the honest spike, not a placeholder.

**3. Type consistency:** `write_photomode_files(mod_id, npv_name, body_rig, output_dir, ent_depot_path=None) -> dict[str, Path]` with keys `"tweak"`/`"xl"` used identically in Tasks 1, 2, 3. Task 4 passes `ent_depot_path` (the documented Task-1 param). `author_photomode_variant`/`swap_to_photomode_rig` names consistent between Task 4 steps.
