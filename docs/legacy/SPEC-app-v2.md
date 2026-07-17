# NPV .app v2 — Correct Component Architecture

**Date:** 2026-05-24
**Status:** Draft
**Supersedes:** The current `build_app_template()` / `build_app_from_donor()` /
`npv-inject` approach to `.app` authoring.

## 1. Problem

The current pipeline produces a broken NPV because it misunderstands how
Cyberpunk 2077 NPC appearances work:

1. **Wrong component type.** We extract `entMorphTargetSkinnedMeshComponent`
   from part-ents and inject them into the `.app`. NPCs cannot use
   morphtarget components — those are a player-character-only runtime system.
   NPVs must use `entSkinnedMeshComponent` with a static `.mesh` depot path.

2. **Wrong mesh references.** `entMorphTargetSkinnedMeshComponent` carries a
   `morphResource` (a `.morphtarget` depot path) but no `mesh` depot path.
   The game needs an explicit `.mesh` to render. The mesh path lives inside
   the morphtarget's `baseMesh` field — one level of indirection that works
   for the player character's runtime blending but not for an NPC.

3. **Wrong .app source.** We tried deriving the `.app` from the donor NPC
   (Judy). This produces Judy's mesh components (Judy's unique head, body,
   clothes) fighting with V's morphtarget overlays. An NPV `.app` should be
   built from scratch with V's player-base meshes.

4. **Unnecessary npv-inject.** We built a C# tool to inject components into
   the cooked `.app` binary because we believed the `compiledData` buffer
   required GUI-only cooking. In reality, since game version 2.1, NPV `.app`
   files work with components at the **top level of the JSON** — no
   `compiledData` buffer needed. `convert deserialize` handles them fine.

## 2. Correct Architecture (from wiki.redmodding.org + NoraLee NPV guide)

### 2.1 Component type

All mesh components in the `.app` must be **`entSkinnedMeshComponent`**
(or `entGarmentSkinnedMeshComponent` for clothing). Never
`entMorphTargetSkinnedMeshComponent`.

### 2.2 Mesh references

Each `entSkinnedMeshComponent` points at a `.mesh` file via
`mesh > DepotPath`. For head/body parts, these are the **player V base
meshes** (e.g. `h0_000_pwa_c__basehead.mesh`), not a donor NPC's meshes.

The mapping from morphtarget → mesh is:
```
morphtarget .morphtarget file
  └─ baseMesh.DepotPath → the .mesh file to use on entSkinnedMeshComponent
```

For the baked head specifically, the baked `.mesh` file IS the mesh
(it's already a static mesh with morphs pre-applied).

### 2.3 .app structure

The `.app` is built from scratch as JSON. Components go directly in
`appearanceAppearanceDefinition.components[]` — no `compiledData` buffer.
`WolvenKit.CLI convert deserialize` cooks this into a valid binary.

### 2.4 No npv-inject needed

Since components live at the JSON level (not in a cooked buffer), the
entire flow is: build JSON → `convert deserialize` → `pack`. The C#
`npv-inject` tool is no longer needed.

### 2.5 .ent stays the same

The donor `.ent` (Judy/Thompson) provides the animation rig, AI,
locomotion — 100+ cooked components. We only change the appearance
reference to point at our `.app`. This part is correct and unchanged.

## 3. Component Specification

### 3.1 Required properties per mesh component

```json
{
  "$type": "entSkinnedMeshComponent",
  "name": "<unique_name>",
  "mesh": {
    "DepotPath": { "$value": "<path_to_.mesh>" },
    "Flags": "Soft"
  },
  "meshAppearance": { "$value": "<material_variant>" },
  "chunkMask": 18446744073709551615,
  "parentTransform": {
    "HandleId": "<N>",
    "Data": {
      "$type": "entHardTransformBinding",
      "bindName": { "$value": "root" },
      "slotName": { "$value": "" }
    }
  },
  "skinning": {
    "HandleId": "<N+1>",
    "Data": {
      "$type": "entSkinningBinding",
      "bindName": { "$value": "root" }
    }
  }
}
```

### 3.2 Component list for a typical NPV

Derived from part-ent extraction. For each part-ent in the recipe, we:
1. Uncook the part-ent to JSON
2. Find each `entMorphTargetSkinnedMeshComponent` in its `compiledData`
3. Resolve its `morphResource` → uncook the `.morphtarget` → read `baseMesh`
4. Emit an `entSkinnedMeshComponent` with the resolved `.mesh` path

| Source part-ent | Component name | Mesh source | Purpose |
|----------------|---------------|-------------|---------|
| `h0_000_pwa__basehead.ent` | `h0_000_pwa_c__basehead` | morphtarget → baseMesh | Base head |
| `he_000_pwa__basehead.ent` | `he_000_pwa_c__basehead` | morphtarget → baseMesh | Eyes/eyelashes |
| `ht_000_pwa__basehead.ent` | `ht_000_pwa_c__basehead` | morphtarget → baseMesh | Teeth |
| `t0_000_pwa_base__full.ent` | `t0_000_pwa_base__full` | morphtarget → baseMesh | Body |
| `a0_000_pwa_base__full.ent` | `a0_000_pwa_base__nails_l` | morphtarget → baseMesh | Nails L |
| `a0_000_pwa_base__full.ent` | `a0_000_pwa_base__nails_r` | morphtarget → baseMesh | Nails R |
| `hx_000_pwa__cyberware_NN.ent` | varies | morphtarget → baseMesh | Cyberware |
| `hx_000_pwa__basehead_makeup_*.ent` | varies | morphtarget → baseMesh | Makeup |
| `hx_000_pwa__tattoo_NN.ent` | varies | morphtarget → baseMesh | Tattoo |
| baked head | `MorphTargetSkinnedMesh7243` | baked `.mesh` directly | V's face shape |

For the **baked head** component: the Blender pipeline produces a static
`.mesh` file with V's face morphs pre-applied. This is used directly as
the `mesh` depot path — no morphtarget indirection.

### 3.3 meshAppearance

The `meshAppearance` value comes from the recipe overrides extracted by
`part_resolver.extract_recipe()`. This is the skin-tone / eye-colour /
makeup-shade variant. The existing extraction code already resolves these
correctly.

### 3.4 Hair components

Hair components are `entSkinnedMeshComponent` pointing at hair `.mesh`
files. These already have a real `mesh` depot path (not a morphtarget),
so the existing hair extraction is mostly correct — just needs the
component type ensured as `entSkinnedMeshComponent`.

### 3.5 Garment components

Clothing uses `entGarmentSkinnedMeshComponent` or
`entSkinnedMeshComponent`. Same structure as above.

## 4. Implementation Plan

### 4.1 Changes to `_extract_part_components()` in `wolvenkit.py`

Currently extracts `entMorphTargetSkinnedMeshComponent` and preserves the
type. New behavior:

1. For each `entMorphTargetSkinnedMeshComponent` found in a part-ent:
   a. Read the `morphResource.DepotPath` (a `.morphtarget` path)
   b. Uncook that `.morphtarget` file
   c. Read its `baseMesh.DepotPath` (the actual `.mesh` path)
   d. Emit the component as `entSkinnedMeshComponent` with:
      - `mesh` = the resolved `.mesh` path
      - `comp_type` = `"entSkinnedMeshComponent"`
      - All other fields (name, meshAppearance) preserved

2. For `entSkinnedMeshComponent` found in a part-ent: preserve as-is
   (already has a mesh depot path).

3. For `entGarmentSkinnedMeshComponent`: preserve as-is.

### 4.2 Changes to `build_app_template()` in `config_editor.py`

The template JSON already produces the right structure — an empty
`appearanceAppearanceDefinition` with an empty `components` array. This is
correct. Components will be populated by the pipeline and written into
the JSON before `convert deserialize`.

The key insight: `components` at the JSON level **are not ignored** by
`convert deserialize` when they use `entSkinnedMeshComponent` (not
morphtarget). The `IsIgnored` flag only affects the `Components` property
on `appearanceAppearanceDefinition` — but the JSON deserializer reads
them into the `compiledData` buffer directly via the `RedPackageConverter`.

**Correction:** actually, the `components` array in the JSON maps to
the property marked `IsIgnored=true`. However, the `compiledData` field
in the JSON (if present) is a `SerializationDeferredDataBuffer` that
IS read. So we need to structure the JSON with components inside
`compiledData.Data.Chunks[]`, matching the format WolvenKit produces
when it serializes a `.app`.

**Alternative (simpler):** write the components as a flat list, then
use `npv-inject` (our C# tool) to read the component spec and write
them into the cooked binary's in-memory `Components` array. The writer
then cooks them into `compiledData` automatically.

### 4.3 Revised flow: keep npv-inject, fix component types

Given the `IsIgnored` complication, the cleanest approach is:

1. **`build_app_template()`** — produces an empty `.app` JSON (unchanged)
2. **`convert deserialize`** — produces a minimal cooked `.app` binary
3. **`npv-inject`** — reads the cooked binary, adds `entSkinnedMeshComponent`
   entries (not morphtargets) with correct mesh depot paths, writes back
4. **`pack`** — bundles into `.archive`

The only change to `npv-inject` is that it must create
`entSkinnedMeshComponent` instead of `entMorphTargetSkinnedMeshComponent`.

### 4.4 Changes to component spec (`npv_components.json`)

New format per component:

```json
{
  "type": "entSkinnedMeshComponent",
  "name": "h0_000_pwa_c__basehead",
  "mesh": "base\\characters\\head\\...\\h0_000_pwa_c__basehead.mesh",
  "meshAppearance": "01_ca_pale",
  "chunkMask": 18446744073709551615,
  "bindTo": "root"
}
```

Key differences from current format:
- `type` is `entSkinnedMeshComponent` (not `entMorphTargetSkinnedMeshComponent`)
- `mesh` is always populated with a real `.mesh` depot path
- `morphResource` is **removed** (not used for NPCs)
- `chunkMask` added (all submeshes visible)

### 4.5 Changes to `_extract_part_components()`

For each `entMorphTargetSkinnedMeshComponent` in a part-ent:

```python
# Current: keeps morphtarget type, stores morphResource
spec = {
    "comp_type": "entMorphTargetSkinnedMeshComponent",
    "mesh": "",
    "morph_resource": morph_depot_path,
}

# New: resolves to mesh, emits as SkinnedMeshComponent
mesh_path = _resolve_morphtarget_to_mesh(game_dir, morph_depot_path)
spec = {
    "comp_type": "entSkinnedMeshComponent",
    "mesh": mesh_path,
    "chunk_mask": 18446744073709551615,
}
```

`_resolve_morphtarget_to_mesh()` uncooks the `.morphtarget` file and
reads its `baseMesh.DepotPath.$value`.

### 4.6 Changes to `npv-inject` (ComponentInjector.cs)

1. Remove the merge/update logic. Go back to the simple "add all
   components" approach (the `.app` starts empty).
2. Create `entSkinnedMeshComponent` (not morphtarget) for all mesh
   components.
3. Set `ChunkMask` to `ulong.MaxValue`.
4. Remove `MorphResource` handling.
5. Set `Mesh` depot path on every component.

### 4.7 Changes to `build_project()` in `wolvenkit.py`

Go back to using `build_app_template()` (the empty template), not the
donor `.app` binary. The flow:

1. Extract components from part-ents → resolve morphtargets to meshes
2. Add baked head component
3. Add hair components
4. Apply recipe material overrides
5. Write `npv_components.json`
6. Build empty `.app` JSON → `convert deserialize` → cooked `.app`
7. `npv-inject` adds components to cooked `.app`
8. Build `.ent` from donor → `convert deserialize` → cooked `.ent`
9. `pack` → `.archive`

### 4.8 Baked head component

The baked head is already a static `.mesh` file. It should be emitted as:

```json
{
  "type": "entSkinnedMeshComponent",
  "name": "h0_000_pwa_c__basehead",
  "mesh": "base\\characters\\head\\<mod_id>_head.mesh",
  "meshAppearance": "01_ca_pale",
  "chunkMask": 18446744073709551615,
  "bindTo": "root"
}
```

Note: the baked head **replaces** the stock head component (same name),
not adds alongside it. The stock head part-ent's component should be
skipped when the baked head is available.

## 5. Files Changed

| File | Change |
|------|--------|
| `npv_build/wolvenkit.py` | `_extract_part_components()`: resolve morphtargets → meshes, emit `entSkinnedMeshComponent`. `build_project()`: revert to empty `.app` template + `npv-inject`. Add `_resolve_morphtarget_to_mesh()`. |
| `npv_build/config_editor.py` | Remove `build_app_from_donor()`, `_INFRASTRUCTURE_TYPES`. Keep `build_app_template()` (it's correct). |
| `tools/npv-inject/ComponentInjector.cs` | Create `entSkinnedMeshComponent` instead of morphtarget. Add `ChunkMask` support. Remove merge logic, back to simple append. |
| `tools/npv-inject/Program.cs` | Keep appearance name setting and appearance trimming (still needed for empty template case — trimming is a no-op on a single-appearance template). |
| `npv_build/project_writer.py` | Update `write_components_json()` for new format (no `morphResource`, add `chunkMask`). |

## 6. What Does NOT Change

- **Save parser** — unchanged
- **Mapping module** — unchanged (already produces correct part-ent paths
  and recipe overrides)
- **Blender face bake** — unchanged (already produces static `.mesh`)
- **Donor `.ent`** — unchanged (Judy/Thompson provide animation rig)
- **AMM Lua generator** — unchanged
- **Packaging** — unchanged

## 7. Testing

### 7.1 Verification before in-game test

After building, serialize the `.app` back to JSON and verify:
- All components are `entSkinnedMeshComponent` or `entGarmentSkinnedMeshComponent`
- Zero `entMorphTargetSkinnedMeshComponent` entries
- Every mesh component has a non-empty `mesh.DepotPath`
- Every mesh component has `meshAppearance` set (not "default" unless
  that's the correct variant)
- `chunkMask` is `18446744073709551615` on every mesh component
- Infrastructure components present (animation setup, face rig, etc.)
  — wait, the empty template has NONE of these. Do we need them?

### 7.2 Infrastructure components question

The NPV template from Nexus (mod 8328) includes infrastructure components.
Our empty `build_app_template()` does not.

However: the donor `.ent` (Judy) already contains `entAnimatedComponent`
entries for `root`, face rig, dangle, etc. in its cooked `compiledData`.
Components in the `.ent` are shared across all appearances. The `.app`
only needs appearance-specific components (meshes).

**Hypothesis:** the infrastructure components in the NPV template are
there because the template uses a **minimal `.ent`** without a donor's
full animation rig. Since we use Judy's full `.ent` (which has all
infrastructure), our `.app` should only need mesh components.

**To verify:** build with mesh-only `.app` and test in-game. If the NPC
T-poses or has no face animations, we need to add infrastructure
components to the `.app`.

### 7.3 In-game test checklist

- [ ] NPC spawns (not invisible)
- [ ] NPC is animated (not T-posing)
- [ ] Head visible with correct face shape
- [ ] Eyes visible and correctly positioned
- [ ] Hair visible (if specified)
- [ ] Body visible with correct skin tone
- [ ] Arms visible
- [ ] Teeth visible when mouth opens
- [ ] Makeup/tattoo/cyberware visible
- [ ] No mesh clipping or z-fighting
- [ ] No floating/detached body parts

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Empty `.app` missing infrastructure components | The `.ent` provides these. If NPC T-poses, add `entAnimatedComponent` for face_rig to the `.app`. |
| Morphtarget → mesh resolution fails for some part-ents | Fall back to the morphtarget's filename with `.mesh` extension (convention-based guess). |
| `chunkMask` value wrong for specific meshes | Start with all-bits-set. Refine per-component if submeshes clip. |
| Some meshes expect to be loaded via morphtarget system | The wiki and NoraLee guide explicitly say NPVs use `entSkinnedMeshComponent`. This is well-tested by the modding community. |
