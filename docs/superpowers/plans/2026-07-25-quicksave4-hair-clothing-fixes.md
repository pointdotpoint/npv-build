# QuickSave 4 Hair and Clothing Correctness Plan

> **Goal:** A build from QuickSave 4 must retain the selected CCXL hairstyle
> and must render the exact clothing item selected in the picker, including its
> material/color appearance. Neither path may silently substitute bald hair or
> a mesh's `default` appearance.

## Confirmed diagnosis

### Hair

QuickSave 4 contains this authoritative third-person hair selection:

```json
{
  "slot": "hairs",
  "label": "b1w_003_wa",
  "raw": "04_teal_ombre"
}
```

It also contains a duplicate `character_customization` row and the expected
FPP companion `b1w_003_wa_fpp`.

The built `cc_settings.json` instead contains:

```json
{
  "hair": {
    "style_id": "",
    "raw": "",
    "vanilla_style": 0
  }
}
```

As a result, `asset_paths.json` has no `vanilla_hair_ent`, `hair_app`, or hair
components, and `npv_components.json` contains no hair.

There are two independent defects:

1. `npv_build/save_parser.py` recognizes modded hair only when its label starts
   with `fhair_` or ends with `_hair`. `b1w_003_wa` uses a valid generic CCXL
   naming convention and is discarded. The hair-color helper uses the same
   naming assumption and also discards `04_teal_ombre`.
2. `npv_build/part_resolver.py` prefilters mod archives by filename. The
   registration is in `b1whair003ccxl.archive.xl`, but the resource itself is
   in `#B1W_CCXL_S2-g.archive`. The current `xl.with_suffix(".archive")`
   operation would also turn `*.archive.xl` into `*.archive.archive`.

The installed ArchiveXL sidecar explicitly registers:

```text
b1w\ccxl\hair003\appearances\b1w_003_wa.app
```

An aggregate WolvenKit listing of `archive/pc/mod` finds that exact `.app`, so
the resource is present and the NPV does not need to be bald.

### Clothing

The persisted override contains:

```text
base\characters\garment\player_equipment\torso\
t1_001_shirt__militech_agent\t1_001_pwa_shirt__militech_agent.mesh
```

That same mesh reaches `asset_paths.json` and `npv_components.json`. The build
therefore did not drop or replace the selected mesh. It emitted:

```json
{
  "type": "entGarmentSkinnedMeshComponent",
  "name": "t1_001_pwa_shirt__militech_agent",
  "mesh": "base\\characters\\garment\\player_equipment\\torso\\...",
  "meshAppearance": "default",
  "source": "clothing:inner_torso"
}
```

The mesh has many real appearances, including `black_silver`, `black_violet`,
`black_wine`, `blue_gold`, `canvas_blue_white`, `canvas_navy`, `green_yellow`,
`leather_white_red`, `red_gold`, and `white_gold`.

The selected shirt identity is lost in three places:

1. `clothing_catalog.py` maps many distinct item IDs and thumbnails to the same
   family mesh and stores no item appearance.
2. `appearance.js` persists only `item.mesh`; the `item_id` and display name
   are not part of the override.
3. `clothing.py` accepts only mesh strings and hard-codes every override to
   `"appearance": "default"`.

For this mesh alone, more than twenty distinct inventory records currently
collapse to the same override. The exact item selected in the previous GUI
session cannot be recovered from the persisted mesh string. Existing ambiguous
overrides must therefore require one re-selection after the fix rather than
guessing a visual variant.

## Correctness invariants

- Hair classification is based on the selected CC slot and explicit vanilla
  patterns, not on a mod author's filename convention.
- The TPP `hairs` row wins over duplicate `character_customization` and FPP
  rows.
- A recognized non-vanilla hair selection is either resolved to an installed
  `.app` or reported as a blocking, actionable build error. It never silently
  produces a bald NPV.
- A clothing choice retains `item_id`, display name, slot, rig-specific mesh,
  and exact mesh appearance from picker through build output.
- A clothing item is selectable only after its mesh and appearance have both
  been validated against the user's installed game data.
- Existing raw mesh CLI arguments remain supported as an explicit legacy
  escape hatch, but the GUI must not claim that they reproduce a catalog item.
- No game assets or TweakDB contents are committed to the repository.

---

## Task 1: Freeze QuickSave 4 as minimal regression fixtures

**Files:**

- Create: `tests/fixtures/quicksave4_hair_selections.json`
- Create: `tests/fixtures/quicksave4_garment_case.json`
- Modify: `tests/test_save_parser.py`
- Modify: `tests/test_mapping.py`
- Modify: `tests/test_clothing.py`

### Steps

1. Store only the decoded selection dictionaries required to reproduce the
   hair bug; do not commit `sav.dat`.
2. Store a synthetic garment case with two item IDs sharing the same mesh but
   using different appearances.
3. Add failing tests proving the current behavior:
   - `b1w_003_wa` is classified as modded TPP hair.
   - its normalized mesh appearance is `teal_ombre`;
   - the FPP duplicate is ignored;
   - two garment selections sharing a mesh emit distinct
     `meshAppearance` values.
4. Add an artifact-level assertion that hair absence and unresolved garment
   appearance cannot pass as a successful exact-appearance build.

### Gate

The new tests fail for the diagnosed reasons before production code changes.

---

## Task 2: Replace hair-name heuristics with an explicit selection model

**Files:**

- Modify: `npv_build/save_parser.py`
- Modify: `npv_build/gui_logic/appearance.py`
- Modify: `npv_build/mapping.py`
- Modify: `tests/test_save_parser.py`
- Modify: `tests/test_vanilla_hair.py`
- Modify: `tests/gui_logic/test_appearance.py`
- Modify: `tests/test_mapping.py`

### Steps

1. Introduce one canonical helper that selects the hair record:
   - inspect `hairs` first;
   - fall back to `character_customization`;
   - reject FPP rows;
   - classify the known vanilla label regex as `vanilla`;
   - classify a non-default, non-vanilla TPP hair row as `modded`;
   - distinguish an explicit no-hair selection from an unknown record.
2. Replace the overloaded `raw`/`style_id` interpretation with explicit fields:

   ```json
   {
     "kind": "modded",
     "selection_label": "b1w_003_wa",
     "mesh_appearance": "teal_ombre",
     "vanilla_style": 0
   }
   ```

   Keep compatibility fields while old manifests and overrides still exist,
   but make all new mapping decisions from the explicit fields.
3. Derive hair color from the selected hair record itself. Strip only the
   numeric CC prefix (`04_`), not arbitrary semantic text.
4. Update appearance overrides so a manually loaded hair mod produces the same
   explicit model instead of manufacturing an `_hair` suffix.
5. Remove `fhair_`/`_hair` predicates from `mapping.py`. `kind == "modded"` is
   the only condition for external-hair resolution.
6. Add cases for:
   - current `fhair_*` mods;
   - current `*_hair` mods;
   - QuickSave 4's `b1w_003_wa`;
   - vanilla hair;
   - bald;
   - malformed and FPP-only selections.

### Gate

QuickSave 4 produces `kind=modded`, `selection_label=b1w_003_wa`, and
`mesh_appearance=teal_ombre` without changing existing vanilla-hair results.

---

## Task 3: Resolve CCXL hair resources by depot identity

**Files:**

- Modify: `npv_build/part_resolver.py`
- Modify: `npv_build/wk_cli.py`
- Modify: `npv_build/mapping.py`
- Modify: `tests/test_part_resolver.py`
- Modify: `tests/test_wk_cli.py`
- Modify: `tests/test_mapping.py`

### Steps

1. Treat ArchiveXL sidecars as registration hints:
   - scan `*.xl` for registered non-FPP `.app` paths whose basename matches
     the selected label;
   - do not infer a same-stem `.archive`;
   - normalize slash direction and compare exact basenames case-insensitively.
2. Add a WolvenKit directory-level exact lookup against `archive/pc/mod`.
   Search once for an anchored escaped basename such as
   `b1w_003_wa\.app$`. This replaces the archive-filename prefilter as the
   authoritative path.
3. When more than one exact candidate exists, score only explicit properties:
   rig, TPP versus FPP, and cyberware variant. Do not use vague substring
   matching to silently choose between ties.
4. Uncook the exact depot resource from the aggregate mod directory. Preserve
   the resolved depot path and source dependency in `asset_paths.json`.
5. Apply `hair.mesh_appearance` to the resolved hair components/wrapper.
6. Replace “NPV will be bald” warnings for selected hair with a structured
   resolution error containing:
   - selected label;
   - searched depot basename;
   - mod directory;
   - remediation to reinstall/load the supplying hair mod.
7. Keep fuzzy matching only as a backward-compatible fallback for legacy
   manually loaded tokens, and surface that fallback in diagnostics.

### Tests

- A sidecar named `b1whair003ccxl.archive.xl` may resolve a resource stored in
  `#B1W_CCXL_S2-g.archive`.
- Compound `.archive.xl` names never become `.archive.archive`.
- Exact TPP beats `_fpp` and `_cyberware`.
- An exact ambiguous tie fails visibly.
- A selected missing hair fails rather than yielding an empty successful
  build.

### Gate

On the installed game, the resolver returns:

```text
b1w\ccxl\hair003\appearances\b1w_003_wa.app
```

and the built component/wrapper uses `teal_ombre`.

---

## Task 4: Establish the exact item-to-appearance source

This is a front-loaded implementation spike. The current filename join proves
only a mesh family; it cannot prove a visual item.

**Files:**

- Create: `tools/npv-tweakdb/npv-tweakdb.csproj`
- Create: `tools/npv-tweakdb/Program.cs`
- Create: `scripts/probe_clothing_appearances.py`
- Create: `tests/fixtures/clothing_appearance_probe.json`
- Modify: `docs/research/2026-07-25-clothing-catalog-spike.md`

### Steps

1. Use the already-vendored WolvenKit RED4 libraries to read the user's
   `r6/cache/tweakdb.bin` and `tweakdb_ep1.bin`.
2. For requested `Items.*` records, export only the fields needed to traverse
   item factory data: record identity/type, `appearanceName`, `entityName`,
   inherited/base values, and referenced records/resources.
3. Resolve the item record through its entity/appearance graph until it yields:
   - rig-specific garment mesh;
   - exact mesh appearance for that component.
4. Uncook each unique mesh once and validate that the derived appearance is
   present in its `appearances` array.
5. Test at least:
   - two `Shirt_01_*` items that currently map to
     `t1_001_pwa_shirt__militech_agent.mesh`;
   - one PWA/PMA sibling pair;
   - one expansion item if `tweakdb_ep1.bin` is installed.
6. Record measured coverage and all unresolved record shapes. If an item cannot
   be resolved unambiguously, it remains visible but disabled. Do not fall back
   to `default` while showing its inventory thumbnail.
7. Cache only derived metadata, keyed by game patch plus size/`mtime_ns` of
   both TweakDB files and the WolvenKit helper. Never cache or ship raw game
   records.

### Gate

Two inventory items that share the same mesh must resolve to distinct,
validated appearances matching their thumbnails. If this gate cannot be met,
exact catalog selection remains disabled and the implementation stops before
UI wiring.

---

## Task 5: Version the catalog and preserve a structured garment selection

**Files:**

- Modify: `npv_build/gui_logic/clothing_catalog.py`
- Modify: `npv_build/webui_api.py`
- Modify: `npv_build/core/models.py` or the current build-request model module
- Modify: `tests/gui_logic/test_clothing_catalog.py`
- Modify: `tests/test_webui_api.py`

### Steps

1. Replace the bare cached list with a versioned envelope containing source
   fingerprints and catalog schema.
2. Extend each buildable row with:

   ```json
   {
     "item_id": "Shirt_01_basic_01",
     "name": "BRAINDANCE BLUE TRILAYER LONG-SLEEVE",
     "slot": "inner_torso",
     "mesh_pwa": "base\\...\\t1_001_pwa_shirt__militech_agent.mesh",
     "mesh_pma": "base\\...\\t1_001_pma_shirt__militech_agent.mesh",
     "appearance_pwa": "validated_value",
     "appearance_pma": "validated_value"
   }
   ```

3. Define a `GarmentSelection` request object with `item_id`, `name`, `slot`,
   `mesh`, `appearance`, and `source_kind`.
4. Validate at the API boundary:
   - slot agrees with mesh prefix;
   - mesh is the catalog row for the chosen rig;
   - appearance is the catalog row's validated appearance;
   - client-supplied paths or appearances cannot impersonate a catalog item.
5. Include the full structured selection in pipeline input hashes.
6. Accept legacy string garments for CLI compatibility with
   `source_kind=legacy_mesh` and `appearance=default`, but never create them
   from a catalog click.

### Gate

Catalog identity and appearance survive API serialization, request creation,
manifest hashing, and reload.

---

## Task 6: Update picker persistence and make legacy ambiguity visible

**Files:**

- Modify: `npv_build/webui/js/appearance.js`
- Modify: `npv_build/webui/js/store.js`
- Modify: `npv_build/webui/js/build.js`
- Modify: `npv_build/webui/app.css`
- Modify: `tests/webui_smoke/mock_api.js`
- Modify: `tests/webui_smoke/test_webui_smoke.py`

### Steps

1. Store the complete `GarmentSelection` object in
   `garment_<slot>`, not `item.mesh`.
2. Remove `_garmentNames` as an ephemeral source of truth. Render the selected
   name from the persisted selection object.
3. Show the selected item's exact appearance/variant in secondary text where
   useful for diagnosis.
4. On reload, restore both thumbnail identity and display name from persisted
   state.
5. Detect old string-only GUI overrides. Mark the row:
   **“Variant unknown — reselect this garment”** and block exact build until
   the user reselects or reverts it.
6. Keep raw mesh entry, if exposed at all, in a clearly labeled advanced path:
   **“Custom mesh (appearance defaults unless specified)”**.
7. Add smoke tests for selecting, reloading, building, reverting, and migrating
   an old override.

### Gate

A selection survives a page/application restart with the same item ID, name,
mesh, and appearance. The previous QuickSave 4 mesh-only override cannot be
silently rebuilt as if it were exact.

---

## Task 7: Emit and validate the chosen garment appearance

**Files:**

- Modify: `npv_build/clothing.py`
- Modify: `npv_build/mapping.py`
- Modify: `npv_build/wolvenkit.py`
- Modify: `npv_build/project_writer.py` if validation belongs at emission
- Modify: `tests/test_clothing.py`
- Modify: `tests/test_build_project.py`
- Modify: `tests/core/test_pipeline_overrides.py`

### Steps

1. Make `resolve_clothing` consume `GarmentSelection` objects and emit their
   exact `appearance`.
2. Preserve slot replacement semantics: inner torso replaces inner torso,
   while outer torso remains independently layered.
3. Validate the requested appearance against uncooked/cached mesh metadata
   before authoring the component. A missing appearance is a structured build
   error, not a fallback.
4. Emit the validated value as `meshAppearance` in
   `npv_components.json` and the final entity resource.
5. Include item ID and display name in diagnostic metadata without putting
   them into runtime fields that do not support them.
6. Add regression tests proving that two items sharing one mesh produce
   different output and that `default` is used only for an explicit legacy
   raw-mesh request.

### Gate

The selected catalog item's validated appearance is present in both
`npv_components.json` and the final entity component.

---

## Task 8: End-to-end QuickSave 4 verification

### Automated gates

```bash
uv run pytest \
  tests/test_save_parser.py \
  tests/test_vanilla_hair.py \
  tests/test_part_resolver.py \
  tests/test_mapping.py \
  tests/test_clothing.py \
  tests/gui_logic/test_clothing_catalog.py \
  tests/gui_logic/test_appearance.py \
  tests/test_webui_api.py \
  tests/webui_smoke/test_webui_smoke.py -q

uv run ruff check npv_build tests tools/npv-tweakdb scripts/probe_clothing_appearances.py
```

Then run the full suite.

### Real build gate

1. Invalidate only the QuickSave 4 output/checkpoints affected by the changed
   hair and garment schemas.
2. Re-open QuickSave 4.
3. Confirm the inspector identifies `b1w_003_wa` as loaded installed hair.
4. Re-select the intended shirt once, because the old override did not retain
   its identity.
5. Build and inspect:
   - `cc_settings.json`: explicit modded hair and `teal_ombre`;
   - `asset_paths.json`: `b1w_003_wa.app`;
   - `npv_components.json`: hair present and shirt appearance is not an
     accidental `default`;
   - final cooked entity: same hair and shirt values.
6. Install, launch Photo Mode, and visually confirm:
   - NPV is not bald;
   - hair color matches the save;
   - shirt matches the picker thumbnail;
   - existing body/genital and Photo Mode regressions remain fixed.

## Recommended implementation order

Tasks 1–3 fix hair independently. Task 4 must pass before Tasks 5–7 claim exact
clothing support. Task 8 is the release gate. Do not combine the hair repair
with the clothing metadata spike in one commit; each should remain separately
revertible and testable.
