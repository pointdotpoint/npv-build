# ArchiveXL Spike — Research Notes

*Running log for M3 (docs/superpowers/plans/2026-07-17-m3-archivexl-spike.md). Committed artifact. Updated per task.*

## Environment (measured 2026-07-17)

- **ArchiveXL 1.14.0** installed and live (`red4ext/plugins/ArchiveXL/ArchiveXL.dll`, version string `1.14.0` in the DLL; active logs dated through 2026-07-16). The wiki requires **≥ 1.14** for appearance resource patching — **this install qualifies.**
- Live `.xl` files already loading on this install prove ArchiveXL works here:
  - `archive/pc/mod/AMM_PlayerBodyTag.xl` uses `resource:` → `scope:` (the resource-scoping form).
  - `archive/pc/mod/Adshield_Harness_Top.xl` uses `factories:` + `localization:`.
- Game patch: 2.13 (pre-2.2). **Validity bound:** all spike results are for game 2.13 + ArchiveXL 1.14 + WolvenKit 8.19.0. Resource-patching semantics on 2.3x/newer AXL must be re-confirmed after the game updates (ties to M2/T7's gate).
- WolvenKit.CLI resolves to **8.19.0** (from M2 T4).

## T1 — Resource patching: available? YES

**Finding: H2 is NOT blocked-by-environment.** ArchiveXL 1.14 resource patching supports adding appearances to an existing `.app` at load time without editing the original. Source: [REDmodding wiki — Resource Patching: Mesh Appearances](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators-theory/core-mods-explained/archivexl/archivexl-resource-patching/archivexl-patching-appearances) (published 2024-07-23 by Zhincore, last updated 2025-10-24).

### The `.archive.xl` patch syntax (verbatim from wiki)

```yaml
resource:
  patch:
    relative\path\to\your\file.mesh:
      - relative\path\to\original\game\file.mesh
    relative\path\to\your\file.app:
      - relative\path\to\original\game\file.app
```

Semantics (verbatim): "Each key (anything ending with a `:`) is a **patch file path**, while the array entries below (anything starting with a `-`) are the **destination files**. AXL will take the data from the patch file, and add it to every file in the list."

### What can / cannot be patched (verbatim)

- CAN patch: **appearances, components, entity, visualTags, partsValues**.
- CANNOT patch: **partsOverrides**, materials, or material definitions.

### Rules that matter for H2

- **New appearance:** rename the appearance entry in the patch file (e.g. `gbstripes` → `sammy_gbstripes`) so it's *added* rather than *replacing* an existing one. So our NPV appearance name must be unique within the target `.app`.
- **Patch file minimization:** delete everything you aren't changing from the patch `.app` (keep only the appearance(s) being added).
- **Material renaming caveat (mesh-level):** when patching a `.mesh`, the appearance name must match the original but material names must differ. For a whole *new* appearance added to a `.app` this is less constraining, but note it — our NPV meshes are custom-pathed already.
- **Custom paths:** patch files must live outside `base`/`ep1` under `your_name\mod_name\` — npv-build already custom-paths under `base\npv-build\<mod_id>\`, which needs revisiting (it's under `base`; the wiki says keep patch files *out* of base — worth testing whether AXL's `patch:` cares, or only the "install would break without .xl" custom-path guidance applies).

## H2 target picker (from `data/donors/2.13.json`)

The donor table already names the stock NPCs whose `.app`/`.ent` we author against — reuse as the H2 patch target:

- **pwa (matches the E2E NPV rig):** target `.app` = `base\characters\appearances\main_npc\judy.app`, `.ent` = `base\characters\entities\main_npc\judy.ent`, in `basegame_4_appearance.archive`.
- pma: `thompson.app` / `thompson.ent`.

H2 plan: author a patch `.app` containing ONLY our NPV appearance (renamed unique, e.g. `npv_zz_axl_spike_h2`), `patch:` it onto `judy.app`, AMM lua points entity_path at `judy.ent` with that appearance name.

## Spike raw material (from M1 E2E build, still on disk)

`/tmp/claude-1000/npv_e2e_out/`:
- Uncooked sources: `source/archive/base/npv-build/e2e_test_v_244d1527/` → `.app`, `.ent`, `_head.mesh`, `_heb.mesh`, `_morphs.morphtarget`.
- `npv_components.json` (the injected component array — H1's reference for what npv-inject writes).
- Packed `archive/pc/mod/e2e_test_v_244d1527.archive`.

## H1 results (WolvenKit deserialize replaces npv-inject) — T2

**Verdict: H1 = YES, pending in-game confirmation (T4).** WolvenKit.CLI 8.19.0 round-trips the npv-inject-produced cooked `.app` through `serialize`→`deserialize` with zero errors and JSON-structural equality (modulo tool-internal metadata). No second attempt was needed — the "harder variant" (patch the pre-injection template in JSON) was not required.

### What npv-inject writes (from SPEC-inject.md + `wolvenkit.py::_inject_components`, confirmed against the real cooked `.app`)

Per component spec in `npv_components.json` (types: `entMorphTargetSkinnedMeshComponent`, `entSkinnedMeshComponent`, `entGarmentSkinnedMeshComponent`), npv-inject:
- Instantiates a typed RED4 component, sets `name` (CName) and `meshAppearance` (CName).
- Sets `mesh` (and `morphResource` for morph components) as depot-path resource references — observed in the cooked JSON as `mesh.DepotPath` with `$storage: "uint64"` and a **hashed** `$value` (e.g. `9917615001986833823`), i.e. npv-inject resolves the plaintext depot path string to CDPR's path-hash form at injection time, not a plaintext string.
- Sets `parentTransform` = `entHardTransformBinding{ bindName }` and `skinning` = `entSkinningBinding{ bindName }`, both `"root"` for plain NPV components (E2E build also showed `"face_rig"`/`"hair_dangle"` binds for head/hair sub-components — confirms `_inject_components`'s additional `face_rig`/`facial_setup`/`face_graph`/donor-hair-dangle params feed extra bind targets beyond the SPEC's basic `bindTo` field). These render in JSON as handle references (`HandleRefId`/`HandleId` pairs into the CR2W handle table), not inline objects.
- Appends each component to `appearances[appearance_index].Data.components` (confirmed: 0-indexed default).
- Result written via `CR2WWriter.WriteFile()` — this is "what equivalent output" means: an `.app` whose `appearances[0].components` array contains all N injected component objects with correct type, name, resolved mesh/morph depot-path hash, meshAppearance, and bind-name-correct parentTransform/skinning handles, layered on top of the ~10 donor-infrastructure components (anim setup, light blocking, slot, animated, visual controller) already in the appearance from the template.

### Round-trip procedure and outcome

1. Extracted the npv-inject-produced cooked `.app` from the packed E2E archive (`wk.extract` on `e2e_test_v_244d1527\.app$` against `/tmp/claude-1000/npv_e2e_out/archive/pc/mod/e2e_test_v_244d1527.archive`) → reference binary, 7509 bytes.
2. `wk.serialize` → JSON. **Confirmed all 27 injected components visible**: JSON shows 37 total components in `appearances[0].components` — breakdown `entAnimationSetupExtensionComponent`×1, `entLightBlockingComponent`×1, `entSlotComponent`×1, `entAnimatedComponent`×6, `entVisualControllerComponent`×1 (donor infra, 10) + `entSkinnedMeshComponent`×24 + `entGarmentSkinnedMeshComponent`×3 (27 injected) = 37. Matches `npv_components.json`'s component count.
3. `wk.deserialize` on that same JSON (no edits — first-pass "does the round-trip survive at all" test) → **succeeded, exit 0, no errors.** Produced a fresh cooked `.app`, same byte size (7509 bytes) as the reference, first byte diff at offset 33 (CR2W header, expected — see below).
4. Re-`wk.serialize`'d the round-tripped candidate and diffed (`jq -S` sort + `diff`) against the original reference JSON. **Result: 76 diff lines total, 3 hunks**:
   - A `CruidDict` value table (WolvenKit-internal component-handle UID remap generated fresh on every `CR2WWriter` write — keys 0-6 matched byte-for-byte, keys 7-36 differ in value but not structure/count).
   - `ArchiveFileName` (absolute scratch-dir tool metadata, differs because the two invocations read different file paths).
   - `ExportedDateTime` (serialize-time timestamp).
   No component, mesh/morph depot-path hash, meshAppearance, bind name, or appearance-name field differs. **JSON-structural equality confirmed** — the plan's PASS-pending-in-game bar is met on the first attempt; the "two distinct root-caused failures → NO" branch was never triggered.

### H1 test archive built

- Copied the E2E mod's uncooked/cooked source tree to `/tmp/claude-1000/axl_spike/h1/mod_source/`, replaced its `.app` with the H1 round-trip candidate (JSON-identical to npv-inject's output, confirmed above).
- `wk.pack` → **`/tmp/claude-1000/axl_spike/h1/zz_axl_spike_h1.archive`** (6,619,136 bytes). Contents verified via `wk.list_archive`: all 5 expected files present (`.app`, `.ent`, `_head.mesh`, `_heb.mesh`, `_morphs.morphtarget`) at the same depot paths as the original E2E archive.
- **Not installed into the game dir** — per the plan, that's T4's user-assisted gate. Archive + a renamed AMM lua (unique_identifier `zz_axl_spike_h1`) still need staging for T4; lua generation/copy was out of scope for T2 and is left for the T4 prep step.

### Caveat / what "pending in-game" means

Desk verification (JSON structural equality) cannot confirm the cooked binary is bit-semantically valid for the game's own reader — WolvenKit's serializer/deserializer could theoretically round-trip a field faithfully in JSON while still writing something the game engine rejects (e.g. buffer alignment, chunk-table ordering). That risk is identical for npv-inject's own output today (never fully divorced from an in-game check), so H1 carries no *additional* unverified risk over the status quo — but T4's spawn test is still the actual proof.

WolvenKit version used: 8.19.0 (matches M2 T4, matches this spike's ground-truth environment note).

## H2 results (ArchiveXL resource patch onto stock judy.app) — T3

**Verdict: H2 = YES (desk-validated), pending in-game confirmation (T4).** A single-appearance patch `.app` deserializes cleanly, round-trips JSON-structurally identical, packs into an archive with correctly-formed depot paths, and the `.archive.xl` resource-patch block validates as YAML and matches a **live production example already loaded on this install** (not just the wiki). No blockers hit; the "two distinct root-caused failures" fallback was never triggered.

### Patch `.app` authoring approach

1. Started from the H1 round-trip candidate JSON (`/tmp/claude-1000/axl_spike/h1/candidate_roundtrip/e2e_test_v_244d1527.app.json`) rather than re-serializing from scratch — it already carries the full 37-component appearance (10 donor-infra + 27 NPV-injected) that H1 proved cooks cleanly. Copied to `/tmp/claude-1000/axl_spike/h2/patch_app_json/`.
2. The E2E `.app` already contains exactly **one** appearance (`appearances` array length 1) — the plan's "delete other appearances, keep only ours" step was a no-op here; nothing to delete.
3. Renamed the single appearance's `name.$value`: `e2e_test_v_244d1527_appearance` → **`zz_axl_spike_h2`** (unique within the target `judy.app`, per the T1 rename rule).
4. Confirmed `parentAppearance` = `"None"`, `partsValues` empty, `partsOverrides` has 12 entries (all internal to our own new appearance, not modifying an existing one on judy — the wiki's "cannot patch partsOverrides" constraint is about patching fields *within* an existing target appearance; adding a wholly new appearance with its own partsOverrides is a different code path and unaffected. Recorded as an open question for T4 regardless, since this reasoning is desk-only.)
5. **Custom-pathed the patch `.app` + its meshes under `zz_axl_spike\h2\`** (not `base\...`). Relocated the two custom baked meshes (`_head.mesh`, `_heb.mesh`) from their E2E path (`base\npv-build\e2e_test_v_244d1527\...`) to `zz_axl_spike\h2\zz_axl_spike_h2_head.mesh` / `..._heb.mesh`. The `.morphtarget` file was also copied to the new path for completeness, though tracing `wolvenkit.py`/`head_bake.py` confirmed **no component in the final `.app` references the `.morphtarget` directly** — it's consumed only as an intermediate Blender-baking input; the two baked meshes are the only artifacts components point at.
6. **Depot-path rehashing:** the two custom mesh components (`h0_000_pwa_c__basehead`, `heb_000_pwa__basehead`) reference their mesh via a `ResourcePath` with `$storage: uint64` — i.e. CDPR resolves depot-path strings to a **hashed** form at cook time (confirmed in H1 notes), so moving the file requires recomputing the hash for the new path, not just editing a string. Verified the hash algorithm is plain **FNV-1a 64-bit** over the UTF-8 depot-path bytes by reproducing the two known hashes from their original plaintext paths (`base\npv-build\e2e_test_v_244d1527\e2e_test_v_244d1527_head.mesh` → `9917615001986833823`; `..._heb.mesh` → `6042445093930301692` — both matched exactly). Computed new hashes for the relocated paths and patched them into the two `mesh.DepotPath.$value` fields:
   - `zz_axl_spike\h2\zz_axl_spike_h2_head.mesh` → `4317227685453093004`
   - `zz_axl_spike\h2\zz_axl_spike_h2_heb.mesh` → `6608104136889739041`
   All other component mesh paths (vanilla game assets, body/garment/hair) were untouched — they're plaintext `$storage: string` depot paths already resolvable at their existing locations, not moved.
7. `WolvenKit.CLI convert deserialize zz_axl_spike_h2.app.json` → **exit 0**, produced a 7494-byte cooked `.app`.
8. Re-serialized the cooked candidate and verified: 1 appearance named `zz_axl_spike_h2`, 37 components intact, both remapped mesh hashes present and correct in the round-tripped JSON. Structural round-trip confirmed clean (same bar as H1).

### Path-choice rationale (custom path vs `base`)

Per T1's captured wiki rule, patch files should live **outside `base`/`ep1`** under a modder-namespaced folder. Chose `zz_axl_spike\h2\` (matching the spike's `zz_axl_spike_*` game-dir file-naming convention from the plan's Global Constraints, so cleanup/sorting stays consistent). This diverges from npv-build's production convention (`base\npv-build\<mod_id>\...`), which the T1 notes already flagged as worth revisiting. **Could not fully test in this desk phase whether AXL's `patch:` block actually *requires* the source live outside `base`, or whether that's only guidance to avoid `base`-folder collisions** — no negative-control build (patch file left under `base`) was attempted, since the point was to test the documented-safe path. Recorded as an open question for T4/M4 (does npv-build's real convention need to move out of `base` if H2 is adopted?).

### The `.xl` patch file (exact content)

`/tmp/claude-1000/axl_spike/h2/zz_axl_spike_h2.archive.xl`:

```yaml
resource:
  patch:
    zz_axl_spike\h2\zz_axl_spike_h2.app:
      - base\characters\appearances\main_npc\judy.app
```

YAML-validated with `uv run --with pyyaml python -c "import yaml; print(yaml.safe_load(open('...')))"` → parses to `{'resource': {'patch': {'zz_axl_spike\\h2\\zz_axl_spike_h2.app': ['base\\characters\\appearances\\main_npc\\judy.app']}}}` — structurally correct, single key (our patch file), single destination (`judy.app`).

**Naming convention confirmed against live installed mods**: `<name>.archive.xl` sitting next to `<name>.archive` is exactly the pattern used by multiple already-loading mods (`1g1_Body_Suit_with_Gun_Harness_FemV.archive.xl`, `b1_koeru_wa_ccxl_mod.archive.xl`, `operator.archive.xl`). Our `zz_axl_spike_h2.archive` + `zz_axl_spike_h2.archive.xl` matches.

**Bonus finding — live production precedent for `.app`-patches-`.app`, not just wiki theory:** `rm_acc_wrist_rolex.xl` (an installed mod) contains a real `resource:patch:` block whose keys are `.app` files patching *other* `.app` files (e.g. `raem\accessories\rm_wrist_reyesbrac\rm_wrist_reyesbrac_app_patch_rolex.app: [raem\accessories\rm_wrist_reyesbrac\rm_wrist_reyesbrac_app.app]`), confirming the exact `.app`→`.app` resource-patch shape H2 relies on is already working in this AXL 1.14 install, on a real player's modlist, today — not merely a wiki-documented possibility. This is materially stronger evidence than T1's wiki citation alone.

### AMM lua for H2

`/tmp/claude-1000/axl_spike/h2/zz_axl_spike_h2.lua` (modeled on the E2E build's generated lua template):

```lua
return {
  modder = "npv-build-spike",
  unique_identifier = "zz_axl_spike_h2",
  rig = "pwa",
  entity_info = {
    name = "ZZ AXL Spike H2 (stock judy.ent + patched appearance)",
    path = "base\\characters\\entities\\main_npc\\judy.ent",
    record = "Character.Judy",
    type = "Character",
    customName = true
  },
  appearances = {
    "zz_axl_spike_h2"
  },
  attributes = nil
}
```

Key difference from the E2E/H1 lua: `entity_info.path` points at the **STOCK** `judy.ent` (never touched, never authored by npv-build), not an npv-build-authored donor `.ent`. If H2 works in-game, this is the artifact that retires the donor-.ent-authoring code path entirely.

### Packed archive contents (verified via `wk.list_archive`)

`/tmp/claude-1000/axl_spike/h2/zz_axl_spike_h2.archive` (6,594,560 bytes):
```
zz_axl_spike\h2\zz_axl_spike_h2_head.mesh
zz_axl_spike\h2\zz_axl_spike_h2.app
zz_axl_spike\h2\zz_axl_spike_h2_heb.mesh
zz_axl_spike\h2\zz_axl_spike_h2_morphs.morphtarget
```
4 files, all at the expected custom-namespaced paths, no `base\` prefix, no stray `.json` files packed in (cleaned before `wk.pack`). **Not installed into the game dir** — staged only, per the spike constraint that installs are T4's responsibility.

### Static validation summary

| Check | Result |
|---|---|
| `wk.deserialize` on patch `.app` JSON | exit 0, no errors |
| Re-`wk.serialize` round-trip | 1 appearance (`zz_axl_spike_h2`), 37 components, both mesh-hash remaps present |
| `.xl` YAML parse | valid, matches T1 wiki syntax exactly |
| `.xl` naming convention | matches multiple live installed mods |
| `.app`→`.app` patch shape | matches a live installed mod's real usage (`rm_acc_wrist_rolex.xl`) |
| Archive contents | 4 files at correct custom depot paths |
| Game-dir install | NOT done (correctly deferred to T4) |

### Open questions for T4 (in-game test)

1. **Does judy.ent's appearance list need the new appearance name registered anywhere, or does the `.app` resource patch alone suffice** for AMM to resolve `zz_axl_spike_h2` when spawning stock `judy.ent`? (AMM reads appearance names off the `.app`, not the `.ent`, per the existing donor-.ent design — but this is unconfirmed for the *stock* unmodified `.ent` + patched `.app` combination specifically.)
2. Does the custom path *have* to be outside `base` for the patch to apply, or was that only wiki guidance about avoiding collisions? (Not negative-tested at desk time.)
3. Does AXL's resource patch apply before or after AMM's own appearance-list enumeration at menu-open time — i.e. will `zz_axl_spike_h2` actually show up as a selectable appearance in AMM's UI for the Judy entity, or only apply if manually specified (as this lua does, bypassing AMM's UI appearance picker)?
4. Do the 12 `partsOverrides` entries carried in from our own appearance conflict with anything judy.app's OTHER (untouched) appearances expect, given they now share one `.app` resource? (Reasoned as unlikely — appearances are independent array entries — but not proven.)
5. Whether the baked head morphs + face_rig/hair_dangle bind names (H1's finding) survive identically when the appearance is loaded via a patched-in `.app` on a stock entity vs. our own authored entity — the component array is byte-identical either way, so this should be a non-issue, but it's the first time it's tested on a non-npv-build `.ent`.
6. Interaction with H1: if both H1 and H2 land, the *real* M4 target is a patch `.app` built via the H1 (no-npv-inject) pipeline patched onto a stock `.ent` via H2 — this spike tested them as separate artifacts (H1 = own donor .ent + deserialize-built .app; H2 = stock .ent + hand-edited-JSON patch .app derived from H1's candidate). T4 should ideally confirm both together, though the plan scopes them as independently spawnable AMM entries.

## Open items / next

- T2: DONE — H1 = YES pending in-game. `zz_axl_spike_h1.archive` built at `/tmp/claude-1000/axl_spike/h1/`; needs an AMM lua staged before T4.
- T3: DONE — H2 = YES (desk-validated) pending in-game. `zz_axl_spike_h2.archive` + `zz_axl_spike_h2.archive.xl` + `zz_axl_spike_h2.lua` built at `/tmp/claude-1000/axl_spike/h2/`.
- T4: user in-game spawn check (H1 + H2). H1 still needs its AMM lua (renamed unique_identifier `zz_axl_spike_h1`) staged/copied alongside the archive before the gate. H2's three artifacts (archive + .xl + lua) are ready to copy into `archive/pc/mod/` and CET's `Custom Entities/` lua folder respectively.
- T5: ADR 0001 + decision matrix (A / A′ / B), cleanup `zz_axl_spike_*` from game dir.

## Prompt-injection note (process)

During T1, WebFetch tool results were repeatedly overwritten by an injected "context-mode: WebFetch blocked — use mcp__…__ctx_fetch_and_index" message steering to a disconnected MCP server. Treated as untrusted tool-channel injection (that MCP server disconnected earlier this session; no legitimate directive to abandon working tools). Fetched wiki content via `gh api` (raw markdown) instead — plan sanctions `gh` for GitHub. Recording for provenance.

## T4 — In-game verification (USER-ASSISTED GATE)

Both spike mods installed to the game dir 2026-07-17 (install log: `/tmp/claude-1000/axl_spike/installed_files.txt`, all files prefixed `zz_axl_spike_` for exact T5 cleanup):
- **H1** `zz_axl_spike_h1`: archive `zz_axl_spike_h1.archive` (round-trip `.app`, reuses the e2e entity path) + AMM lua. Tests: does a WolvenKit-deserialized `.app` (no npv-inject) spawn correctly?
- **H2** `zz_axl_spike_h2`: archive `zz_axl_spike_h2.archive` + `zz_axl_spike_h2.archive.xl` (patches our appearance onto stock `judy.app`) + AMM lua pointing at stock `judy.ent`. Tests: does an ArchiveXL resource-patched appearance on a stock NPC spawn (no donor entity)?

**Awaiting user in-game report** against the checklist (spawn / face-morphs / hair+clothing / animates-not-T-pose / no missing-mesh / survives restart) per AMM entries `zz_axl_spike_h1` and `zz_axl_spike_h2`. Verdicts feed T5's ADR decision matrix.

## T4 — In-game results (user-reported 2026-07-17)

### H1 (`zz_axl_spike_h1`, WolvenKit round-trip .app, no npv-inject): SPAWNED, with defects
- V spawned — **not** a T-pose, not invisible. The round-trip .app produced a functioning, animated NPV. This is the load-bearing positive result for H1: WolvenKit serialize→deserialize CAN stand in for npv-inject at the "does it spawn and animate" level.
- Defects reported:
  1. **Overlapping/double eye colors** — stock eyes rendering under custom eyes → the modded-eye suppression (`cc_selections` read from `cc_settings.json`, wolvenkit.py ~L725) did not take effect for this spike .app.
  2. **Wrong piercings, no body tattoos** — these correspond to the many "Unresolved selection (fallback used)" warnings in the ORIGINAL e2e build log (piercings, tattoos, makeup). They are **pre-existing mapping-resolution gaps in the e2e NPV**, present before the spike, NOT introduced by the H1 round-trip.
- **Interpretation:** H1's spawn/animation success is real. The eye-overlap is the one defect that could be H1-specific (a component the round-trip altered vs. what npv-inject writes) OR the same cc_selections gap — needs a JSON compare of the round-trip .app's eye-suppression components vs the npv-inject .app. The piercing/tattoo issues are out of scope for H1 (mapping problem, tracked separately).
- **H1 verdict: PROMISING, not clean.** Round-trip is viable for spawn+anim; one appearance-fidelity defect (eyes) needs root-causing before npv-inject can be retired with confidence. NOT a clean YES; NOT a NO.

### H2 (`zz_axl_spike_h2`, ArchiveXL patch onto stock judy.app): FAILED — spawned stock naked Judy, not V
- ArchiveXL log (`ArchiveXL-2026-07-17-16-33-53.log`) shows: `Loading "zz_axl_spike_h2.archive.xl"...` (loaded, twice across two game launches) — BUT **no `[ResourcePatch]` line for our patch at all** (the only ResourcePatch entries are unrelated errors from Photomode_NPCs' `femv_boobs` patches). AXL parsed our .xl but did not apply the `resource: patch:` block to `judy.app`.
- Result in-game: AMM spawned the stock `judy.ent` with no appearance applied → **naked default Judy**, confirming the appearance was never patched in.
- **Likely cause:** the T1-flagged untested caveat — our patch .app was custom-pathed under `base\zz_axl_spike\h2\...`, and/or the `resource: patch:` path form / key didn't match what AXL 1.14 expects for a `.app`→`.app` appearance patch. The patch file existed and loaded but produced no ResourcePatch action, which points at the patch-declaration/path, not a missing file (a missing file logs a "doesn't exist" error, which ours did NOT get — so the file resolved, but the patch was a no-op).
- **H2 verdict: FAILED as-built.** Not proven impossible (the mechanism is real and used by other mods on this install), but this spike artifact did not apply. Would need: (a) move the patch .app out of `base\` per the wiki custom-path rule, (b) verify the exact `resource: patch:` shape against a working `.app`-patch example (`rm_acc_wrist_rolex.xl` found in T3), (c) re-test. That's a second spike iteration.

### Decision-matrix inputs
- H1 = PROMISING (spawn+anim proven; eye-fidelity defect to root-cause) → supports **retiring npv-inject** but with a fidelity caveat, not a clean green.
- H2 = FAILED-as-built (loaded but no-op patch) → does **NOT** currently support retiring the donor entity; needs a second iteration to reach a real verdict.
- Net: neither hypothesis is a clean YES this round. Branch decision leans **B (keep current design)** for now, with H1 as a tracked follow-up (root-cause the eye defect; if it's just cc_selections and not a round-trip loss, H1 graduates to A′) and H2 as a re-test (fix custom-path + patch syntax).

## M2 T7 executed — patch 2.31 support (2026-07-17)

User confirmed client is on 2.31 and created a new save (`ManualSave-0`, written 16:52). Probe: `(269, 2310, 195)` — **identical build + CC struct to every 2.13 save**. CDPR kept the save-format build (2310) and the CC struct (v3=195) stable from 2.13 through 2.31. `parse_save` decoded it cleanly (body_rig=pwa, 102 selections, all CC fields present — sane, not garbage).

**Outcome:** the plan's "v3 differs → author a new decoder" branch did NOT fire. T7 collapsed to relabel + alias:
- `save_versions.json`: `2310 -> "2.31"` (was `"2.13"` — the label was stale, not the format).
- `mapping.resolve_table_key()`: aliases `2.2/2.21/2.3/2.31 -> "2.13"` shared tables (mapping, donor, part index) — one physical table set serves the whole current patch line; a future asset-changing patch just drops its alias and vendors a new file.
- 2.13 saves still resolve (identity path), proven by the unchanged `test_mapping` explicit-2.13 test.

**Real proof:** full E2E build from the 2.31 `ManualSave-0` → `v_2_31_build_26d728d6.archive` + AMM lua + mod-manager `.zip` + checkpoint manifest, exit 0. Decoded THIS save's character (Senna skin tones, genitals_none) — distinct from the earlier 2.13 e2e build, confirming live decode not cache. The whole pipeline (parse → resolve → bake → author → assemble → pack → zip) works on patch 2.31.
