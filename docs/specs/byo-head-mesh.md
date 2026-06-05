# Spec: User-Supplied Head ("Bring Your Own" head mesh)

Status: implemented
Date: 2026-06-05
Scope: let the user supply their own Blender output for V's head, so the pipeline
skips face-morph baking and only assembles the rest of the NPV.

## 1. Motivation

`bake_head()` is the only step that needs Blender + the user's face-morph values.
Everything downstream keys off a single artifact: a baked `.mesh` written to

```
<out_dir>/base/npv-build/<mod_id>/<mod_id>_head.mesh
```

with `baked_mesh_depot = base\npv-build\<mod_id>\<mod_id>_head.mesh`
(`wolvenkit.py:538`). If the user can drop their own head at that depot path, the
program no longer needs to run Blender at all and "only deals with the other
parts of generating the NPV" (clothing, recipe parts, hair, .ent/.app authoring,
component injection, packing) — all of which are untouched from line `542`
onward in `build_project()`.

This spec defines **two** override modes. Both bypass `bake_head()`; they differ
in what the user hands us and how much of the WolvenKit round-trip we still run.

| | Option A — supply `.glb` | Option B — supply `.mesh` |
|---|---|---|
| User gives | edited GLB (shapekeys applied / sculpted) | finished cooked `.mesh` |
| We run WolvenKit `import --keep` | yes | no |
| We run `_restore_head_materials` | yes | yes |
| Skinning / rig rebuilt by us | yes (via `--keep`) | no (must already be intact) |
| Footgun surface | low | high |
| Recommended default | ✅ | power users only |

Both modes are **optional**. With neither flag set, behavior is exactly today's
(extract morphs → Blender bake).

## 2. Shared design

### 2.1 The contract `bake_head()` fulfills

`bake_head(wk, mod_id, build_dir, body_rig, face_morphs, verbosity)` (`head_bake.py:205`)
writes, into `build_dir` at their depot paths:

1. `<mod_id>_head.mesh`        — baked h0_ head mesh (required)
2. `<mod_id>_heb.mesh`         — baked heb_ skin-detail layer (optional)
3. `<mod_id>_morphs.morphtarget.json` — mod-scoped morphtarget re-pointed at the baked mesh

…and returns `True`. The override path must produce **(1)** at the same path and
return truthily. **(2)** and **(3)** are addressed in §5.

### 2.2 New abstraction: `prepare_head()`

Introduce one entry point that the orchestrator/`build_project` calls instead of
`bake_head()` directly. It dispatches on which (if any) override is present:

```python
# head_bake.py
def prepare_head(
    wk, mod_id, build_dir, body_rig, face_morphs, verbosity,
    *,
    user_glb: Path | None = None,    # Option A
    user_mesh: Path | None = None,   # Option B
    user_heb_mesh: Path | None = None,
) -> bool | None:
    if user_mesh:
        return _import_user_mesh(wk, mod_id, build_dir, body_rig,
                                 user_mesh, user_heb_mesh, verbosity)
    if user_glb:
        return _import_user_glb(wk, mod_id, build_dir, body_rig,
                                user_glb, user_heb_mesh, verbosity)
    return bake_head(wk, mod_id, build_dir, body_rig, face_morphs, verbosity)
```

`bake_head()` itself is unchanged — the two new helpers reuse its tail (material
restore + morphtarget authoring) by extracting it into a shared internal:

```python
def _finalize_head(wk, mod_id, build_dir, body_rig, baked_mesh_fs,
                   baked_mesh_depot, heb_baked_fs, verbosity) -> bool | None:
    """material restore + morphtarget re-point. Lines head_bake.py:233 and 254-280
    extracted verbatim. Called by bake_head AND both override helpers."""
```

This keeps material-restore and morphtarget logic in one place for all three
paths.

### 2.3 CLI surface

`cli.py`, mutually-exclusive group:

```python
head_group = parser.add_mutually_exclusive_group()
head_group.add_argument("--head-glb", metavar="<path>",
    help="Use your own Blender-edited head GLB instead of baking face morphs. "
         "We import it to .mesh and restore materials/skinning.")
head_group.add_argument("--head-mesh", metavar="<path>",
    help="Use your own finished cooked .mesh as V's head. Skips Blender AND "
         "WolvenKit import — the mesh must already have intact skinning/rig.")
parser.add_argument("--heb-mesh", metavar="<path>",
    help="Optional skin-detail (heb_) layer to accompany --head-glb/--head-mesh. "
         "If omitted, the heb_ component is dropped (see spec §5).")
parser.add_argument("--no-restore-head-materials", action="store_true",
    help="With --head-mesh: keep the materials baked into your .mesh instead of "
         "restoring stock head materials (see spec §4.4).")
```

`--no-restore-head-materials` is only meaningful with `--head-mesh`; if passed
with `--head-glb` or with no override, hard-fail in validation (§2.4) — the GLB
import path always needs material restore because `import --keep` strips
materials (`head_bake.py:86`).

Thread through `run_orchestrator()` (`orchestrator.py:28`) →
`build_project()` (`wolvenkit.py:479`) as keyword args
`user_head_glb`, `user_head_mesh`, `user_heb_mesh`. In `build_project` the
existing block at `wolvenkit.py:534`:

```python
if face_morphs and game_dir:
    try:
        result = bake_head(wk, mod_id, source_dir, body_rig, face_morphs, verbosity)
```

becomes:

```python
override = user_head_glb or user_head_mesh
if (face_morphs or override) and game_dir:
    try:
        result = prepare_head(
            wk, mod_id, source_dir, body_rig, face_morphs, verbosity,
            user_glb=user_head_glb, user_mesh=user_head_mesh,
            user_heb_mesh=user_heb_mesh,
        )
```

`face_morphs` becomes optional when an override is present — morph extraction in
`save_parser` still runs but its output is ignored for the head.

### 2.4 Validation (both modes, fail fast — hard-fail policy)

- Path exists and is readable; else `WolvenKitError("user head not found: <path>")`.
- Extension matches the flag (`.glb` for A, `.mesh` for B). Reject mismatch.
- `--heb-mesh` only accepted alongside one of the head flags; error otherwise.
- `--head-glb`/`--head-mesh` are mutually exclusive (enforced by argparse group).

## 3. Option A — user supplies `.glb`

The user edits only the Blender step on their own (any shapekey weights, sculpts,
external tooling) and hands us a GLB. We run the same `import --keep` round-trip
the bake already uses, so skinning is rebuilt from the stock head's CR2W skeleton
and we keep full control of materials.

### 3.1 Flow (`_import_user_glb`)

1. Resolve the **stock head mesh** for `body_rig` (same canonical head the bake
   uses as the `--keep` skeleton donor — see `find_stock_head_part` /
   `HEAD_MORPHTARGET` base mesh). Unbundle it to a staging dir.
2. Copy the user GLB next to the stock `.mesh` as `<stem>.glb` (the `--keep`
   matcher pairs by stem — same trick as `blender_module.py:188`).
3. `wk.import_mesh(staging_dir, dest=staging_dir, allow_exit_codes=(3,))`
   (`wk_cli.py:219`). Tolerate exit code 3 exactly as the bake does
   (`blender_module.py:196`); verify the `.mesh` mtime advanced.
4. Copy rebuilt `.mesh` → `build_dir/.../<mod_id>_head.mesh`.
5. Call `_finalize_head()` (material restore + morphtarget).

### 3.2 Why recommended

- Skinning/rig is rebuilt by `--keep` against the real stock skeleton → no
  floating/T-pose risk from a user who forgot weights.
- `_restore_head_materials` runs against a mesh whose material slot layout we
  control, so skin tone (`skin_override`/save tone, `wolvenkit.py:518`) still
  applies cleanly.

### 3.3 Constraints surfaced to the user (docs) + topology mismatch

- GLB vertex/shapekey topology should derive from the stock head export
  (`bake_head`'s `.glb`, or `--dump-head-glb` §9 — the natural base to edit).
  Wild topology changes may desync `--keep` skinning.
- We do **not** apply face morphs from the save in this mode; the GLB is the
  source of truth for shape.

**Topology mismatch → warn, never hard-fail.** After import (step 3), compare the
user GLB's vertex count against the stock head's (cheap — read both glTF
headers). If they differ, log at any verbosity:
`[Head] warning: head GLB vertex count (N) differs from stock head (M); skinning may be imperfect`.
We proceed regardless — power users intentionally remesh, and `--keep` often
copes. Hard-failing here would block legitimate edits; the warning is enough.

## 4. Option B — user supplies a finished `.mesh`

Maximum control, minimum safety net. We treat the user `.mesh` as already cooked
and skinned; we only copy it in and restore materials.

### 4.1 Flow (`_import_user_mesh`)

1. Copy user `.mesh` → `build_dir/.../<mod_id>_head.mesh` verbatim.
2. Call `_finalize_head()` — **but** material restore (`_restore_head_materials`)
   assumes the mesh's `materialEntries`/`appearances`/`localMaterialBuffer` slot
   shape matches the stock head it pulls from (`head_bake.py:171-174`). If the
   user mesh diverges, this silently mismatches → wrong-skin head.
3. Morphtarget re-point as normal.

### 4.2 Risks (must be documented, and `-v` should warn)

- **Skinning/rig:** if the user mesh lost `boneNames`/skin weights, the head
  floats or T-poses. We cannot detect this cheaply; surface a `[Head] warning:
  user mesh — skinning not verified` at `verbosity > 0`.
- **Material slots:** mismatch → skin tone wrong. Consider an opt-out
  `--no-restore-head-materials` so a user who baked materials in keeps theirs.
- Because of these, B is gated behind documentation as "power users only" and is
  **not** the default suggestion in `--help`.

### 4.3 Optional hardening (nice-to-have, not required for v1)

Serialize the user `.mesh` (`wk.serialize`) and assert it has a non-empty
`renderResourceBlob`/bone list before accepting it; hard-fail with a clear
message rather than producing a broken NPV. Deferred unless field reports
warrant it.

### 4.4 `--no-restore-head-materials` (ships v1)

By default Option B still runs `_restore_head_materials` (`head_bake.py:67`),
which overwrites the mesh's `materialEntries`/`appearances`/`localMaterialBuffer`
with the stock head's. A user who authored their own materials in the `.mesh`
loses them. `--no-restore-head-materials` skips that step:

- In `_finalize_head()`, gate the `_restore_*` call on a `restore_materials`
  flag (default `True`; `False` when the user passes the flag).
- When skipped, the user's `skin_override`/save skin tone (`wolvenkit.py:518`)
  no longer drives the head — the mesh's own appearance is authoritative. Log at
  `verbosity > 0`: `[Head] material restore skipped; using mesh's own materials`.
- The morphtarget re-point (`head_bake.py:254-280`) still runs regardless.

Only valid with `--head-mesh` (Option B). See §2.4 validation.

## 5. The `heb_` skin-detail layer

`bake_head()` also bakes the heb_ layer with the *same* morphs
(`head_bake.py:238-252`) and emits a second component
(`<mod_id>_heb.mesh`, consumed near `wolvenkit.py:662`). Its purpose: deform the
skin-detail mesh identically so it doesn't overlap the morphed head ("doubled
jaw/mouth").

A user-supplied head won't include heb_. Policy:

1. **If `--heb-mesh` is given:** import/copy it parallel to the head (Option A →
   `import --keep`; Option B → copy), run `_restore_part_materials`
   (`head_bake.py:248`), emit the heb_ component as today.
2. **If `--heb-mesh` is omitted:** **drop the heb_ component entirely** for this
   build (do not emit `<mod_id>_heb.mesh`, skip the spec append near
   `wolvenkit.py:662`). Rationale: an un-deformed stock heb_ over a custom head
   is *worse* (guaranteed overlap) than no heb_ layer. Log at `verbosity > 0`:
   `[Head] no --heb-mesh with custom head; skin-detail layer omitted`.

The VTK seamfix/headpatch auto-injection (`wolvenkit.py:553-579`) is independent
of the head source and stays as-is for both options.

## 6. Files touched

| File | Change |
|---|---|
| `cli.py` | add `--head-glb`, `--head-mesh` (mutex), `--heb-mesh`, `--no-restore-head-materials`, `--dump-head-glb`; pass through |
| `orchestrator.py` | thread `user_head_glb/_mesh/_heb`, `restore_head_materials` into `build_project`; short-circuit for `--dump-head-glb` |
| `head_bake.py` | add `prepare_head`, `_import_user_glb`, `_import_user_mesh`, `dump_head_glb`; extract `_finalize_head` (with `restore_materials` flag) from `bake_head` tail |
| `wolvenkit.py` | accept new kwargs; call `prepare_head`; conditional heb_ drop |
| `README` / docs | document both modes, dump→edit→`--head-glb` workflow, B's risks |

No change to `config_editor`, `clothing`, `mapping`, `part_resolver`,
`project_writer`, packing, or `npv-inject`.

## 7. Test plan

- **A happy path:** export stock head GLB, edit a vertex, `--head-glb` →
  `<mod_id>_head.mesh` exists, mtime advanced, materials restored, NPV packs.
- **B happy path:** feed a previously-baked `.mesh` via `--head-mesh` → identical
  output to the bake (golden-compare the packed component spec).
- **heb_ dropped:** override without `--heb-mesh` → no heb_ component in
  `npv_components.json`; with `--heb-mesh` → heb_ present.
- **Validation:** missing file, wrong extension, both head flags together,
  `--heb-mesh` without a head flag → each hard-fails with a clear message.
- **No-override regression:** neither flag → byte-identical to current pipeline.
- **`--no-restore-head-materials`:** Option B with the flag → mesh's own
  `materialEntries` survive into the packed component; without it → stock
  materials restored. Flag with `--head-glb` or no override → hard-fail.
- **`--dump-head-glb`:** produces a non-empty, Blender-openable `.glb` for
  `body_rig`, exits without building an NPV.
- **Topology warn:** GLB with a different vertex count than stock → warning
  logged, build still completes and packs.

## 8. Resolved decisions

1. **`--no-restore-head-materials` ships in v1** (Option B). A user who baked
   their own materials into the `.mesh` keeps them; the flag skips
   `_restore_head_materials`. See §4.4.
2. **`--dump-head-glb` helper ships** alongside the override flags, so Option A
   has an obvious starting point. See §9.
3. **Topology mismatch in Option A → warn only**, never hard-fail. See §3.3.

## 9. `--dump-head-glb` helper (ships v1)

Gives Option A an obvious starting point: export the stock head as an editable
GLB so the user edits *that* and feeds it back via `--head-glb`. Without this,
a user has to know how to extract+export the stock head by hand.

### 9.1 CLI

```python
parser.add_argument("--dump-head-glb", metavar="<path>",
    help="Export the stock head GLB for editing (then feed back via --head-glb) "
         "and exit. Requires --game-dir; needs a body rig.")
```

`--dump-head-glb` is a **terminal sub-mode**, not a build flag: when present, the
orchestrator runs only the dump and exits 0 — no save parsing, no NPV assembled.
Because we need a `body_rig` and the dump is standalone, resolve the rig from
`--cc-json`/`sav.dat` if supplied, else default to `pwa` with a logged note (and
accept an explicit rig if a `--body-rig`-style hint already exists; otherwise
`pwa` is fine for v1).

### 9.2 Flow (`dump_head_glb` in `head_bake.py`)

Reuses the first half of the bake (the export side, mirroring
`blender_module.py` steps 1–2):

1. Resolve + unbundle the stock head `.mesh` for `body_rig` (same source the
   bake/`_import_user_glb` use).
2. `wk.export(...)` the `.mesh` → `.glb` (the existing WolvenKit export already
   used pre-bake).
3. Copy the `.glb` to the user's `--dump-head-glb` path. Print:
   `[Head] stock head GLB written: <path> — edit and pass via --head-glb`.

No Blender, no morphs, no material restore — it's the unmodified stock head, by
design (the user supplies the edits).

### 9.3 Round-trip guarantee

The dumped GLB is exactly the base that `_import_user_glb` (§3.1) expects, so
`--dump-head-glb` → edit → `--head-glb` is a closed loop with matching topology
(no §3.3 warning on an unedited or vertex-count-preserving GLB).
