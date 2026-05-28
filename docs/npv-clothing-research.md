# NPV Clothing Research Findings

## 1. Where is equipped clothing stored in sav.dat?

Equipped clothing is **NOT** in the CC (character creation) block. The CC block (`.inkcc`
format) only stores face/body customization choices (skin tone, eye color, hairstyle, etc.).

Equipped clothing lives in the **`ScriptableSystemsContainer`** node, specifically under:
- **`EquipmentSystem`** / **`EquipmentSystemPlayerData`** - tracks what's equipped in each slot
- The **inventory system** (separate node) stores the full item list

The save file (`sav.dat`) is a proprietary binary format:
- Magic: `CSAV` (0x43534156)
- LZ4-compressed chunks containing node data
- Node tree at end of file (magic: `NODE`)
- Equipment data is in the `ScriptableSystemsContainer` node's `EquipmentSystem` subsystem

**The wardrobe system** is a separate in-game feature (Patch 1.6+) that stores outfit presets,
but equipped items are still tracked by `EquipmentSystem`.

## 2. How modders add clothing to NPVs

Modders **manually specify garment mesh depot paths** in the `.app` file. They do NOT extract
equipped items from the save. The standard workflow is:

### The actual process:
1. **Find the clothing mesh** in WolvenKit's Asset Browser (or Tweak Browser for vanilla items)
2. **Add the `.mesh` file to the project** and custom-path it to avoid conflicts
3. **Add or modify a component** in the `.app` file's appearance definition:
   - Either duplicate an existing clothing component
   - Or swap the `DepotPath` in an existing component to point to the new mesh
4. **Set the `meshAppearance`** to select which material variant to use
5. **Custom-path textures** to avoid conflicts with other mods

### Key detail: Garment support does NOT work on NPVs
> "GarmentSupport only works on actual garment items that have been equipped using the game's
> transaction system. As of October 2024, that's not the case for NPCs."

This means NPV clothing won't auto-tuck/morph. Modders must manually refit meshes in Blender
to avoid clipping, or hide submeshes via ACM or WolvenKit chunk masks.

## 3. Component types for clothing

### entGarmentSkinnedMeshComponent (PREFERRED)
- The recommended component type for clothing meshes
- Does NOT have physics properties that can crash the game
- Supports path substitution when loaded via `.ent` files with Soft flag
- Supports garment morphing (but only on player-equipped items, not NPCs)

### entSkinnedMeshComponent
- Can be used interchangeably with `entGarmentSkinnedMeshComponent` for NPVs
- Since garment support doesn't work on NPVs anyway, either works
- Simpler component with same basic mesh-loading properties

### entSkinnedClothComponent (AVOID)
- Has physics via `physicalMesh` - can crash the game if mesh is altered
- Usually paired with `entAnimatedComponent` for cloth physics
- Not recommended unless you need physics simulation

### Shared component properties:
```
depotPath      - loads the .mesh file (the depot path)
chunkMask      - defines visibility of individual submeshes
meshAppearance - selects an entry from the mesh's appearances array
castShadows    - enables/disables real-time shadows
forceLODLevel  - force Level of Detail
```

## 4. Garment mesh depot path structure

### Pattern:
```
base\characters\garment\{category}\{body_part}\{item_id}\{mesh_file}.mesh
```

### Examples:
```
base\characters\garment\gang_nomad\legs\l1_021_pants__cargo_computer\...
base\characters\garment\player_equipment\torso\t1_001_ma_full__ripper_doc1487.mesh
```

### Body mesh (reference):
```
base\characters\common\player_base_bodies\player_female_average\t0_000_pwa_base__full.mesh
base\characters\common\player_base_bodies\player_male_average\t0_000_pma_base__full.mesh
```

### Naming convention:
```
{prefix}_{id}_{gender_body}_{variant}__{item_name}.mesh

prefix:  t0=body, t1=inner torso, t2=outer torso, s1=shoes, l1=legs,
         h1=head inner, h2=head outer, g1=gloves, i1=items
gender:  pwa=player woman average, pma=player male average,
         wa=woman average, ma=male average
```

## 5. How clothing components are added to the .app file

In the `.app` file, each appearance has a `components` array. Clothing is added as additional
component entries. The structure for each clothing component:

```
appearanceAppearanceDefinition
  -> components (array)
    -> entGarmentSkinnedMeshComponent (or entSkinnedMeshComponent)
        name: "t1_my_shirt"          # component name with garment prefix
        mesh:
          DepotPath: "path\to\mesh.mesh"   # depot path to the .mesh file
          Flags: Default (or Soft)
        meshAppearance: "black"       # which material variant
        chunkMask: 18446744073709551615  # all submeshes visible (max uint64)
```

### Component naming prefixes (used by ACM for categorization):
| Prefix | Category |
|--------|----------|
| t1_    | Inner torso (shirts) |
| t2_    | Outer torso (jackets, coats) |
| s1_    | Shoes |
| l1_    | Legs (pants) |
| h1_    | Head inner (masks, sunglasses) |
| h2_    | Head outer (helmets) |
| g1_    | Gloves |
| i1_    | Items (pouches, bags) |

These prefixes are not required for NPV function but are used by ACM (Appearance Change Menu)
for dress-up categorization and by EquipmentEx for slot scoring.

## 6. Reading equipped items from save file programmatically

### Python: CyberpunkPythonHacks (best option)
- Repository: https://github.com/fmwviormv/CyberpunkPythonHacks
- Pure Python, no compiled dependencies
- Can access `ScriptableSystemsContainer` including `EquipmentSystem` and
  `EquipmentSystemPlayerData`

```python
from cp2077save import SaveFile

savefile = SaveFile(r"path/to/sav.dat")
with savefile.nodes.ScriptableSystemsContainer as config:
    # Available subsystems include:
    # EquipmentSystem, EquipmentSystemPlayerData, CraftingSystem, etc.
    equipment = config.EquipmentSystem
    player_equip = config.EquipmentSystemPlayerData
```

### Other tools (C#, not Python):
- **CyberCAT** (github.com/WolvenKit/CyberCAT) - C# save editor, has inventory access
- **CyberpunkSaveEditor** (github.com/PixelRick/CyberpunkSaveEditor) - C#, inventory editor
- **CyberCAT-SimpleGUI** - GUI wrapper, shows equipped items sorted to top with slot column

### Key challenge:
The save stores items by **TweakDB ID** (item record ID), not by mesh depot path. To get from
a TweakDB item ID to the actual `.mesh` depot path, you need to:
1. Read the TweakDB ID from the save's equipment data
2. Look up that ID in the game's TweakDB to find the item's `entityTemplatePath`
3. Follow the `.ent` -> `.app` -> component chain to find the mesh depot path

This mapping requires either the game's TweakDB dump or a pre-built lookup table.

## 7. Fallback: Default clothed NPV

There is no single "default clothed NPC" entity file. For fallbacks:

### Option A: Use vanilla clothing meshes directly
Pick common base-game clothing meshes and add them as components:
```
# Example: simple t-shirt + jeans + shoes
t1: base\characters\garment\player_equipment\torso\t1_XXX_pwa_full__tshirt.mesh
l1: base\characters\garment\player_equipment\legs\l1_XXX_pwa__jeans.mesh
s1: base\characters\garment\player_equipment\feet\s1_XXX_pwa__sneakers.mesh
```

### Option B: Copy components from existing NPC appearances
Look at how CDPR dresses NPCs like Johnny, Judy, Panam etc. in their `.app` files and
copy those component definitions.

### Option C: Use the body mesh with no clothing
The base body component (`t0_000_pwa_base__full` or `t0_000_pma_base__full`) renders V's
body. Without any clothing components, the NPV appears in underwear/nude depending on
the body mesh variant used.

## 8. Practical approaches for automation

### Approach 1: Manual clothing specification (RECOMMENDED)
- User provides a list of clothing item names or TweakDB IDs
- Tool looks up the corresponding mesh depot paths from a pre-built mapping table
- Tool generates the component entries in the `.app` file
- This is how modders actually do it - they pick items manually

### Approach 2: Extract from save + TweakDB lookup
- Parse save with CyberpunkPythonHacks to get equipped TweakDB IDs
- Build/use a TweakDB item-to-mesh mapping table
- Auto-generate clothing components for the NPV `.app`
- Requires maintaining a TweakDB dump (changes with game patches)

### Approach 3: Curated defaults
- Ship a set of pre-defined outfit configurations (casual, formal, combat, etc.)
- Each outfit is a known set of mesh depot paths that work together
- User picks an outfit preset; tool generates the components
- Most reliable, no save parsing needed

### Approach 4: Hybrid
- Try to read equipped items from save
- If resolution fails (modded items, unknown TweakDB IDs), fall back to curated defaults
- Let user override individual slots

## Sources

- [NPV: How to add a new appearance to an NPV](https://wiki.redmodding.org/cyberpunk-2077-modding/modding-guides/npcs/npv-v-as-custom-npc/how-to-add-a-new-appearance-to-an-npv)
- [NPV: Creating a custom NPC](https://wiki.redmodding.org/cyberpunk-2077-modding/modding-guides/npcs/npv-v-as-custom-npc/npv-creating-a-custom-npc)
- [Garment Support: How does it work?](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators-theory/3d-modelling/garment-support-how-does-it-work)
- [Documented Components](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators-theory/files-and-what-they-do/components/documented-components)
- [Save file: .dat](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators-theory/files-and-what-they-do/file-formats/save-file-.dat)
- [CyberpunkPythonHacks](https://github.com/fmwviormv/CyberpunkPythonHacks)
- [CyberCAT](https://github.com/WolvenKit/CyberCAT)
- [CyberpunkSaveEditor](https://github.com/PixelRick/CyberpunkSaveEditor)
- [Garment support from scratch](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators-theory/3d-modelling/garment-support-how-does-it-work/garment-support-from-scratch)
