# NPV Clothing — Specification

**Date:** 2026-05-24
**Status:** Draft
**Depends on:** SPEC-app-v2.md, ADR-0004

## 1. Problem

The NPV spawns naked. Clothing is not extracted from the save or applied
to the `.app` file. The user must manually specify garments with
`--garment` flags or accept a naked NPC.

## 2. Goal

Automatically dress the NPV with a sensible outfit. Three sources, in
priority order:

1. **Equipped items from the save** — read the player's currently equipped
   clothing from `sav.dat` and resolve to garment mesh depot paths.
2. **User overrides** — `--garment` CLI flags (already implemented) take
   priority over save-derived items for individual slots.
3. **Fallback defaults** — if a slot can't be resolved, use a curated
   default garment so the NPC is never naked.

## 3. Architecture

### 3.1 Equipment slots

The game uses these equipment slots relevant to NPC appearance:

| Slot | Prefix | Description |
|------|--------|-------------|
| InnerTorso | `t1_` | T-shirt, tank top, bra |
| OuterTorso | `t2_` | Jacket, coat |
| Legs | `l1_` | Pants, shorts, skirt |
| Feet | `s1_` | Shoes, boots |
| Head | `h1_` | Hat, helmet |

Only `InnerTorso`, `Legs`, and `Feet` are required for a non-naked NPV.
`OuterTorso` and `Head` are optional.

### 3.2 Data flow

```
sav.dat
  └─ ScriptableSystemsContainer
       └─ EquipmentSystem / EquipmentSystemPlayerData
            └─ equipped item TweakDB IDs per slot
                    │
                    ▼
              TweakDB ID → garment depot path resolution
              (via WolvenKit CLI archive search or vendored mapping)
                    │
                    ▼
              Garment mesh depot paths
                    │
                    ▼
              entGarmentSkinnedMeshComponent in .app
```

### 3.3 TweakDB resolution challenge

The save stores equipped items as **TweakDB record IDs** (e.g.
`Items.GenericHeadClothing`), not mesh depot paths. Resolving a TweakDB
ID to a garment mesh path requires:

1. Finding the item's `appearanceResource` (an `.app` file) in the
   TweakDB dump
2. Uncooking that `.app` to find the mesh components
3. Extracting the mesh depot path

This is complex and fragile. For v1, we take a simpler approach.

### 3.4 v1 approach: fallback defaults + user overrides

Instead of parsing the save's equipment system (which requires TweakDB
resolution), v1 uses:

1. **Curated fallback outfit** — a set of vanilla garment mesh depot
   paths vendored in the repo, one per body rig. These are plain,
   generic garments that look reasonable on any V.
2. **`--garment` overrides** — the user can specify garment `.ent` or
   `.mesh` depot paths to override individual slots.
3. **Future: save equipment parsing** — deferred to v2.

## 4. Fallback Outfit

### 4.1 Female V (pwa)

| Slot | Garment | Depot path |
|------|---------|------------|
| InnerTorso | Plain tank top | `base\characters\garment\player_equipment\torso\t1_024_tshirt__sweater\t1_024_pwa_tshirt__sweater.mesh` |
| Legs | Tight jeans | `base\characters\garment\player_equipment\legs\l1_012_pants__jeans_tight\l1_012_pwa_pants__jeans_tight.mesh` |
| Feet | Bovver boots | `base\characters\garment\player_equipment\feet\s1_066_boot__bovver\s1_066_pwa_boot__bovver.mesh` |

### 4.2 Male V (pma)

| Slot | Garment | Depot path |
|------|---------|------------|
| InnerTorso | Plain tank top | `base\characters\garment\player_equipment\torso\t1_024_tshirt__sweater\t1_024_pma_tshirt__sweater.mesh` |
| Legs | Tight jeans | `base\characters\garment\player_equipment\legs\l1_012_pants__jeans_tight\l1_012_pma_pants__jeans_tight.mesh` |
| Feet | Bovver boots | `base\characters\garment\player_equipment\feet\s1_066_boot__bovver\s1_066_pma_boot__bovver.mesh` |

### 4.3 meshAppearance

All fallback garments use `meshAppearance = "default"`. This renders the
garment with its default material, which is always valid.

## 5. Implementation

### 5.1 Data file: `npv_build/data/fallback_outfit.json`

```json
{
  "pwa": {
    "inner_torso": {
      "name": "t1_024_pwa_tshirt__sweater",
      "mesh": "base\\characters\\garment\\player_equipment\\torso\\t1_024_tshirt__sweater\\t1_024_pwa_tshirt__sweater.mesh",
      "appearance": "default"
    },
    "legs": {
      "name": "l1_012_pwa_pants__jeans_tight",
      "mesh": "base\\characters\\garment\\player_equipment\\legs\\l1_012_pants__jeans_tight\\l1_012_pwa_pants__jeans_tight.mesh",
      "appearance": "default"
    },
    "feet": {
      "name": "s1_066_pwa_boot__bovver",
      "mesh": "base\\characters\\garment\\player_equipment\\feet\\s1_066_boot__bovver\\s1_066_pwa_boot__bovver.mesh",
      "appearance": "default"
    }
  },
  "pma": {
    "inner_torso": {
      "name": "t1_024_pma_tshirt__sweater",
      "mesh": "base\\characters\\garment\\player_equipment\\torso\\t1_024_tshirt__sweater\\t1_024_pma_tshirt__sweater.mesh",
      "appearance": "default"
    },
    "legs": {
      "name": "l1_012_pma_pants__jeans_tight",
      "mesh": "base\\characters\\garment\\player_equipment\\legs\\l1_012_pants__jeans_tight\\l1_012_pma_pants__jeans_tight.mesh",
      "appearance": "default"
    },
    "feet": {
      "name": "s1_066_pma_boot__bovver",
      "mesh": "base\\characters\\garment\\player_equipment\\feet\\s1_066_boot__bovver\\s1_066_pma_boot__bovver.mesh",
      "appearance": "default"
    }
  }
}
```

### 5.2 Changes to `build_project()` in `wolvenkit.py`

After the existing component assembly (head, body, arms, hair, etc.),
add a new step:

```python
# 7. Clothing — fallback outfit + user overrides
clothing_specs = _resolve_clothing(body_rig, garment_overrides, verbosity)
component_specs.extend(clothing_specs)
```

### 5.3 New function: `_resolve_clothing()`

```python
def _resolve_clothing(body_rig: str, garment_overrides: list,
                      verbosity: int) -> list:
    """Resolve clothing for the NPV.

    Uses fallback defaults for all slots, with user --garment overrides
    taking priority. Each garment becomes an entGarmentSkinnedMeshComponent.

    Returns a list of component spec dicts.
    """
    fallback_file = Path(__file__).parent / "data" / "fallback_outfit.json"
    fallback = json.loads(fallback_file.read_text()).get(body_rig, {})

    # Slot → depot path, filled from fallback
    slots = {}
    for slot_name, slot_data in fallback.items():
        slots[slot_name] = slot_data

    # User overrides replace slots by matching prefix
    # --garment accepts a mesh depot path; we match by t1_/l1_/s1_ prefix
    for g in garment_overrides:
        g = g.strip()
        if not g:
            continue
        basename = g.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if basename.startswith("t1_") or basename.startswith("t2_"):
            slot = "inner_torso" if basename.startswith("t1_") else "outer_torso"
        elif basename.startswith("l1_"):
            slot = "legs"
        elif basename.startswith("s1_"):
            slot = "feet"
        elif basename.startswith("h1_"):
            slot = "head"
        else:
            slot = f"custom_{len(slots)}"

        name = basename.rsplit(".", 1)[0]  # strip .mesh
        slots[slot] = {"name": name, "mesh": g, "appearance": "default"}
        if verbosity > 0:
            print(f"[Clothing] Override {slot}: {name}")

    # Convert to component specs
    specs = []
    for slot_name, slot_data in slots.items():
        specs.append({
            "comp_type": "entGarmentSkinnedMeshComponent",
            "name": slot_data["name"],
            "mesh": slot_data["mesh"],
            "appearance": slot_data["appearance"],
            "source": f"clothing:{slot_name}",
        })
        if verbosity > 0:
            print(f"[Clothing] {slot_name}: {slot_data['name']}")

    return specs
```

### 5.4 Changes to `build_project()` signature

Add `garment_overrides` parameter:

```python
def build_project(mod_id, out_dir, asset_paths, verbosity,
                  garment_overrides=None):
```

### 5.5 Changes to `orchestrator.py`

Pass the `garments` list from CLI args to `build_project()`:

```python
component_specs = build_project(
    mod_id, output_dir, asset_paths, verbosity,
    garment_overrides=garments or [],
)
```

### 5.6 Failure handling

- If the fallback outfit JSON is missing or malformed: hard error.
- If a `--garment` override path is invalid (doesn't look like a depot
  path): warning, skip that override, use fallback for that slot.
- If a fallback mesh doesn't exist in the game archives: the NPC will
  render without that garment slot. This is acceptable — the fallback
  paths are verified against the supported game version.
- **The NPV is never fully naked** as long as the fallback JSON is
  valid. At minimum, inner torso + legs + feet are always present.

## 6. CLI changes

No new flags. The existing `--garment` flag is reused:

```
--garment <depot_path>    # repeatable, overrides specific slots
```

Without any `--garment` flags, the fallback outfit is used. The user can
override individual slots:

```bash
# Use fallback outfit (sweater + jeans + boots)
npv-build save.dat "MyV" --output ./myv

# Override just the top
npv-build save.dat "MyV" --output ./myv \
  --garment 'base\characters\garment\player_equipment\torso\t1_090_tank__johnny\t1_090_pwa_tank__johnny.mesh'

# Override top + pants
npv-build save.dat "MyV" --output ./myv \
  --garment 'base\characters\garment\...\t1_090_pwa_tank__johnny.mesh' \
  --garment 'base\characters\garment\...\l1_063_pwa_pants__leather.mesh'
```

## 7. Future (v2): Save equipment extraction

### 7.1 Approach

Read the `EquipmentSystemPlayerData` node from `sav.dat`:
1. Parse the equipment slots to get TweakDB item record IDs
2. Resolve each TweakDB ID → item `.app` file → mesh depot path
3. Use resolved mesh paths instead of fallbacks

### 7.2 Requirements

- TweakDB-to-depot-path mapping table (large, ~50K entries)
- OR: runtime TweakDB dump from game files via WolvenKit
- Save format parser extended to read `ScriptableSystemsContainer`

### 7.3 Complexity

High. TweakDB resolution involves multiple indirections:
`TweakDB ID → record → appearanceResource → .app → components → mesh`.
Deferred to v2.

## 8. Testing

- Build with no `--garment` flags → NPV wears fallback outfit
- Build with one `--garment` override → that slot uses the override,
  others use fallback
- Verify fallback mesh paths exist in game archives via
  `WolvenKit.CLI archive -l`
- In-game: NPV is clothed, no clipping with body mesh
