# NPV equipped-clothing capture — design

## Context

The NPV currently wears a hardcoded fallback outfit (sweater + jeans + boots from
`data/fallback_outfit.json`), optionally overridden per-slot via the `--garment`
flag. The user wants the NPV to wear **V's currently-equipped clothing** from their
playthrough.

Equipped clothing is **not** in the save's CC appearance node (`save_parser.py` reads
only head/face/skin/hair). In the binary `sav.dat` it lives in the 126 KB `inventory`
node as TweakDBID hashes — parsing that plus an item→garment mapping table is a large,
patch-fragile effort.

The project already has a second, richer input path: the **CET dumper**
(`data/cet_dumper/init.lua` → `cc_dump.json`, consumed via `--cc-json`). It runs
in-game with full game-object access and already walks `player:GetComponents()`. The
player's equipped clothing is present there as live **garment mesh components**
(`t1_`/`t2_`/`l1_`/`s1_`/`g1_`/`f1_`/etc.), each exposing its `.mesh` depot path and
current `meshAppearance`. This sidesteps inventory/TweakDB parsing entirely.

Decision: capture equipped clothing via the CET dumper only (the raw `sav.dat` path
keeps the existing fallback behavior). Layered torso (inner `t1_` + outer `t2_`) is
kept as separate components.

## Approach

Three changes, smallest viable:

### 1. `data/cet_dumper/init.lua` — emit a `clothing` array

In `gather()`, while iterating `player:GetComponents()`, collect garment components
into `out.clothing`. For each component whose name matches a garment prefix, capture:

```
{ name = <component name>, mesh = <comp.mesh depot path>, appearance = <meshAppearance>, slot = <derived> }
```

- Garment prefixes → slots (mirrors `clothing.py`):
  `t1_`→inner_torso, `t2_`→outer_torso, `l1_`→legs, `s1_`→feet, `f1_`→face,
  `g1_`→hands/arms (gloves), `h1_`→head. Unknown garment-looking prefixes →
  `custom_<n>`.
- Read mesh from `comp.mesh.value` (same pattern already used for head_components).
- Skip components with no `.mesh` (procedural/hidden) and non-garment components.
- Keep ALL matched components — layered torso (t1_ + t2_) both retained.

This is additive; existing dump fields are unchanged.

### 2. `npv_build/clothing.py` — use equipped clothing when present

`resolve_clothing(body_rig, garment_overrides=None, equipped=None, verbosity=0)`:

- If `equipped` is a non-empty list, build the base outfit from it (one spec per
  entry, slot taken from the entry; preserve `appearance`) **instead of**
  `fallback_outfit.json`. Implementation note: equipped entries are emitted as specs
  directly (one per entry), not stored in a slot→spec dict — so two distinct meshes
  (inner t1_ and outer t2_) both survive. The slot→dict collapse is only used for the
  fallback outfit and for applying `--garment` overrides by slot.
- If `equipped` is empty/None, current behavior (load fallback) — backward compatible.
- `--garment` overrides apply on top, by slot, exactly as today (overrides win).
- Emits the same `entGarmentSkinnedMeshComponent` specs as today.

### 3. Thread `clothing` from cc-json through to `resolve_clothing`

- `orchestrator.py`: when `cc_json_path` is loaded, pass its `clothing` list down.
- `wolvenkit.py` (`build_project`): accept the equipped list and pass it to
  `resolve_clothing(..., equipped=...)`.
- The `sav.dat` path supplies no `clothing` → `equipped=None` → unchanged.

## Out of scope

- Binary `inventory`/TweakDB parsing from `sav.dat` (the deferred Approach B).
- Outfit *appearance* dyes that aren't expressed as the component's `meshAppearance`.
- Cyberware/weapons/accessories — clothing garment slots only.

## Edge cases

- Garment component without a resolvable mesh → skip (logged at verbosity > 0).
- Two torso layers (t1_ + t2_) → both kept as distinct components.
- cc-json predating this change (no `clothing` key) → treated as empty → fallback.
- `--garment` override for a slot that the equipped set also fills → override wins.

## Testing

- `clothing.py` unit tests (pure function, no game/WolvenKit):
  - equipped list used as base when provided (one spec per entry, appearance preserved)
  - both torso layers (t1_ + t2_) retained
  - `--garment` override replaces the equipped item for that slot
  - empty/None equipped → falls back to `fallback_outfit.json` (existing behavior)
- The `init.lua` change is in-game Lua (not unit-testable); verified by running the
  dumper on a save and inspecting `cc_dump.json.clothing`.

## User workflow

1. Copy updated `init.lua` to `<CP2077>/bin/x64/plugins/cyber_engine_tweaks/mods/npv_dumper/`.
2. Load the save, open CET overlay, run `GetMod("npv_dumper").Dump()`.
3. `npv-build --cc-json <cc_dump.json> "MyV03" --output ./my_v_mod --game-dir <...> -v`
   → NPV wears V's equipped outfit (plus any `--garment` overrides).
