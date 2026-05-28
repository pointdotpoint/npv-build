# Hybrid CLI+GUI NPV Build — Design Spec

## Problem

The WolvenKit CLI cannot produce a working NPV `.app` file. NPC entities require
mesh components inlined in the `.app`'s cooked `compiledData` buffer with
`HandleRefId` bindings — something only WolvenKit GUI can author. The CLI's
from-scratch `.app` with `partsValues` either renders heads invisible (no
`AppearanceParts` tag) or T-poses the NPC (`AppearanceParts` breaks animation).

Community NPV mods are built entirely in WolvenKit GUI. This is a 2–4 hour
manual process per character. `npv-build` automates ~95% of it; the user does
one GUI step.

## Goal

```
npv-build /path/to/sav.dat "My V" --output ./my_v_project --game-dir <path>
```

Produces a **WolvenKit project directory** the user opens in WolvenKit GUI.
All assets are pre-generated. The user follows a short guide (printed to stdout +
README in the project) to do the one GUI step, then packs in GUI.

## What the CLI produces

```
my_v_project/
  source/
    archive/
      base/
        characters/
          head/
            <mod_id>_head.mesh          # baked face mesh (morphs applied)
            <mod_id>_morphs.morphtarget # mod-scoped, baseMesh → baked mesh
            <mod_id>_hair.ent           # hair part-ent (skeleton bindings)
          appearances/
            <mod_id>.app                # TEMPLATE — user completes in GUI
          entities/
            <mod_id>.ent                # donor NPC .ent (Judy, appearances swapped)
  bin/
    x64/plugins/cyber_engine_tweaks/mods/AppearanceMenuMod/
      Collabs/Custom Entities/
        <mod_id>.lua                    # AMM custom entity
  npv_components.json                   # component specs for the GUI step
  README_GUI_STEPS.md                   # step-by-step guide
```

### npv_components.json

Machine-readable list of components the user adds in WolvenKit GUI. Each entry
has the info needed to create an inline `.app` component:

```json
{
  "appearance_name": "<mod_id>_appearance",
  "components": [
    {
      "type": "entMorphTargetSkinnedMeshComponent",
      "name": "MorphTargetSkinnedMesh7243",
      "mesh": "",
      "morphResource": "base\\characters\\head\\<mod_id>_morphs.morphtarget",
      "meshAppearance": "01_ca_pale",
      "bindTo": "root",
      "source": "baked head (face morphs applied)"
    },
    {
      "type": "entMorphTargetSkinnedMeshComponent",
      "name": "MorphTargetSkinnedMesh3637",
      "mesh": "",
      "morphResource": "base\\characters\\head\\...\\he_000_pwa__morphs.morphtarget",
      "meshAppearance": "gradient_grey",
      "bindTo": "root",
      "source": "eyes (stock)"
    },
    {
      "type": "entSkinnedMeshComponent",
      "name": "hair_1",
      "mesh": "base\\mel_ccxl_hair\\meshes\\zara_01.mesh",
      "meshAppearance": "molten_marmalade",
      "bindTo": "root",
      "source": "modded hair (Zara)"
    }
  ]
}
```

### README_GUI_STEPS.md

Printed to stdout AND written to project. Roughly:

```
1. Open WolvenKit GUI
2. File → Open Project → select my_v_project/
3. In Asset Browser, open source/archive/base/characters/appearances/<mod_id>.app
4. Expand appearances → <mod_id>_appearance → components
5. For each entry in npv_components.json:
   a. Right-click components → Add New → <type>
   b. Set name, mesh/morphResource, meshAppearance per the JSON
   c. Set parentTransform → bindName = "root"
   d. Set skinning → bindName = "root"
6. Save the .app
7. WolvenKit menu → Pack Mod
8. Copy archive/ and bin/ to your game directory
```

## What changes in existing code

### config_editor.py

**`build_app()`** — new mode: produces a **template `.app`** with an empty
`components` array and no `partsValues`. Just the appearance definition shell
that the user populates in GUI.

```python
def build_app_template(mod_id: str) -> dict:
    """Produce a minimal .app with one empty appearance definition.
    User adds components in WolvenKit GUI."""
```

**`build_head_ent()`** — no longer needed as a separate part-ent. The head
component goes directly into the `.app` (via GUI). But we still need to produce
the baked `.mesh` and the mod-scoped `.morphtarget`. Refactor
`_bake_and_author_head()` to return the mesh + morphtarget depot paths without
authoring a head `.ent`.

**`build_hair_ent()`** — still needed. Hair is a mod-authored part-ent with
skeleton bindings. Referenced from the `.app` components (user adds an
`entSkinnedMeshComponent` pointing at the hair meshes, or we ship the hair
`.ent` and reference it). Two options:

- **Option A:** Ship hair `.ent`, user adds it as a `partsValues` entry in the
  `.app` — but partsValues don't load for NPCs without `AppearanceParts`.
- **Option B:** User adds individual hair mesh components inline in the `.app`.
  We list them in `npv_components.json`.

**Decision: Option B.** Consistent with the inline-everything approach. Hair mesh
depot paths + appearance names go into `npv_components.json`. No hair `.ent`
needed.

### wolvenkit.py

**`pack_mod()`** — rename to **`build_project()`**. New flow:

1. Bake face mesh (Blender) → `<mod_id>_head.mesh`
2. Author mod-scoped morphtarget → `<mod_id>_morphs.morphtarget`
3. Uncook donor `.ent`, swap appearances → `<mod_id>.ent`
4. Author template `.app` → `<mod_id>.app`
5. Cook all authored JSON → binary (WolvenKit `convert deserialize`)
6. Generate `npv_components.json` from recipe + hair + head specs
7. Generate `README_GUI_STEPS.md`
8. Write AMM `.lua`

The `.app` template cooks to a minimal binary. User opens it in GUI, adds
components, and the GUI updates the cooked buffer.

### orchestrator.py

Update to call `build_project()` instead of `pack_mod()`. No longer calls
`pack` — the user does that in GUI.

### cli.py

Update `--output` help text. Print the GUI steps to stdout after build.

## Component spec generation

The CLI already extracts all the information needed for each component:

| Source | Component type | Name | Mesh/MorphResource | meshAppearance |
|--------|---------------|------|-------------------|----------------|
| Recipe head | entMorphTargetSkinnedMeshComponent | MorphTargetSkinnedMesh7243 | mod morphtarget | skin tone (01_ca_pale) |
| Recipe eyes | entMorphTargetSkinnedMeshComponent | MorphTargetSkinnedMesh3637 | stock morphtarget | eye colour |
| Recipe teeth | entMorphTargetSkinnedMeshComponent | ht_000_pwa__basehead | stock morphtarget | teeth variant |
| Recipe brows | entMorphTargetSkinnedMeshComponent | heb_000_pwa__basehead | stock morphtarget | brow colour+shape |
| Recipe makeup | entMorphTargetSkinnedMeshComponent | various | stock morphtarget | colour variant |
| Recipe cyberware | entMorphTargetSkinnedMeshComponent | MorphTargetSkinnedMesh2004 | stock morphtarget | cyberware variant |
| Hair (modded) | entSkinnedMeshComponent | hair_1..N | mod mesh paths | hair colour |
| Body | entSkinnedMeshComponent | t0_000_pwa_base__full | stock mesh | skin tone |
| Arms | entMorphTargetSkinnedMeshComponent | a0_000_pwa_base__nails_* | stock morphtarget | nail colour |
| Garments | entGarmentSkinnedMeshComponent | from stock .ent | stock mesh | default |

All of this comes from `_extract_part_components()` (already written) plus the
recipe extraction in `part_resolver.py`. The `npv_components.json` is just a
serialization of what `pack_mod` already computes.

## What the user does in GUI

Estimated time: **5–10 minutes** (vs 2–4 hours for fully manual NPV).

1. Open project (30 sec)
2. Open `.app` file (10 sec)
3. Add ~15–20 components from `npv_components.json` (3–5 min)
   - Each: right-click → add → set 4 fields → done
   - Could be scripted with a WolvenKit extension in the future
4. Save + Pack (30 sec)
5. Copy to game dir (30 sec)

## Acceptance criteria

1. `npv-build <save> <name> --output <dir> --game-dir <path>` produces a valid
   WolvenKit project directory
2. All binary assets (baked mesh, morphtarget, donor .ent, template .app) cook
   successfully via `convert deserialize`
3. `npv_components.json` contains complete specs for all head/face/body/hair
   components with correct names, depot paths, and meshAppearance values
4. `README_GUI_STEPS.md` has step-by-step instructions a user can follow
5. After user completes GUI step + packs, the resulting `.archive` produces an
   animated NPV with correct face morphs, skin tone, hair, and clothing
6. AMM `.lua` is correct and spawns the NPV

## Out of scope (v1)

- Automated WolvenKit GUI scripting (no WolvenKit extension/plugin)
- Garment extraction from save (still `--garment` flags)
- Hair auto-resolve from save name (still `--hair` flag)
- Multiple appearances per NPV
- Male V support (pma rig — untested, likely works with minor changes)

## Risk: template .app editability

**Concern:** Can WolvenKit GUI open a CLI-cooked `.app` and add components?

The template `.app` has one appearance with empty `components` and empty
`partsValues`. WolvenKit GUI should be able to open it, navigate to the
appearance, and add components. This needs testing.

**Fallback:** If the CLI-cooked `.app` isn't editable in GUI, ship the `.app` as
uncooked JSON (`.app.json`) and have the user import it in WolvenKit GUI, which
will cook it. WolvenKit GUI's "Import" handles this.

**Fallback 2:** Don't ship an `.app` at all. Have the user create one from
scratch in GUI following the README. The README tells them the appearance name
and all component details. Slightly more manual but guaranteed to work.
