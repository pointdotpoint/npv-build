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

## Open items / next

- T2: DONE — H1 = YES pending in-game. `zz_axl_spike_h1.archive` built at `/tmp/claude-1000/axl_spike/h1/`; needs an AMM lua staged before T4.
- T3: build the H2 `zz_axl_spike_h2` patch + `.xl` + lua; static-validate.
- T4: user in-game spawn check (H1 + H2). H1 still needs its AMM lua (renamed unique_identifier `zz_axl_spike_h1`) staged/copied alongside the archive before the gate.
- T5: ADR 0001 + decision matrix (A / A′ / B), cleanup `zz_axl_spike_*` from game dir.

## Prompt-injection note (process)

During T1, WebFetch tool results were repeatedly overwritten by an injected "context-mode: WebFetch blocked — use mcp__…__ctx_fetch_and_index" message steering to a disconnected MCP server. Treated as untrusted tool-channel injection (that MCP server disconnected earlier this session; no legitimate directive to abandon working tools). Fetched wiki content via `gh api` (raw markdown) instead — plan sanctions `gh` for GitHub. Recording for provenance.
