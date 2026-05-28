"""Generate npv_components.json and README_GUI_STEPS.md for the hybrid workflow."""

import json
from pathlib import Path


def write_components_json(component_specs, appearance_name, out_path: Path):
    """Serialize component specs to JSON for npv-inject.

    Each spec dict has: comp_type, name, mesh, appearance, and optionally source.
    All mesh components use entSkinnedMeshComponent with real .mesh depot paths.
    """
    components = []
    for spec in component_specs:
        entry = {
            "type": spec["comp_type"],
            "name": spec["name"],
        }
        if spec["comp_type"] == "entAnimatedComponent":
            entry["graph"] = spec.get("graph", "")
            entry["rig"] = spec.get("rig", "")
            entry["bindTo"] = spec.get("bind_to", "root")
        elif spec["comp_type"] == "entMorphTargetSkinnedMeshComponent":
            entry["mesh"] = spec.get("mesh", "")
            entry["meshAppearance"] = spec.get("appearance", "default")
            entry["bindTo"] = spec.get("bind_to", "root")
            entry["graph"] = spec.get("graph", "") or spec.get("morph_resource", "")
            entry["morphResource"] = spec.get("morph_resource", "") or spec.get("graph", "")
        else:
            entry["mesh"] = spec.get("mesh", "")
            entry["meshAppearance"] = spec.get("appearance", "default")
            entry["bindTo"] = spec.get("bind_to", "root")
        if spec.get("source"):
            entry["source"] = spec["source"]
        components.append(entry)

    data = {
        "appearance_name": appearance_name,
        "components": components,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2))


def write_readme(mod_id, appearance_name, out_path: Path):
    """Write step-by-step GUI instructions."""
    app_file = f"{mod_id}.app"
    text = f"""\
# NPV Build — WolvenKit GUI Steps

Your NPV project is ready. One manual step remains: adding mesh components
to the .app file in WolvenKit GUI.

## Steps

1. Open **WolvenKit** (GUI, not CLI)
2. File → Open Project → select this directory
3. In the Project Explorer, open:
   `source/archive/base/characters/appearances/{app_file}`
4. In the file editor, expand:
   `appearances → 0 → {appearance_name} → components`
5. For **each entry** in `npv_components.json`:
   a. Right-click `components` → **Add New** → select the `type` from the JSON
   b. Set `name` to the value from the JSON
   c. Set `mesh → DepotPath` to the `mesh` value (or leave empty for morph components)
   d. If the entry has `morphResource`, set `morphResource → DepotPath` to that value
   e. Set `meshAppearance` to the `meshAppearance` value
   f. Expand `parentTransform` → set `bindName` = **root**
   g. Expand `skinning` → set `bindName` = **root**
6. **Save** the .app file (Ctrl+S)
7. Menu → **Pack Mod** (or toolbar pack button)
8. Copy the produced `archive/` and `bin/` folders to your game directory

## Files in this project

| File | What it is |
|------|-----------|
| `source/archive/.../{app_file}` | Appearance file — you add components here |
| `source/archive/.../{mod_id}.ent` | Entity template (Judy donor, animation rig) |
| `source/archive/.../{mod_id}_head.mesh` | Baked face mesh (your V's morphs applied) |
| `source/archive/.../{mod_id}_morphs.morphtarget` | Morphtarget pointing at baked mesh |
| `bin/.../Custom Entities/{mod_id}.lua` | AMM custom entity script |
| `npv_components.json` | Component specs for step 5 above |

## Tips

- Each component needs both `parentTransform.bindName = root` AND
  `skinning.bindName = root` — missing either causes floating/detached parts
- The `meshAppearance` controls skin tone, eye colour, makeup colour etc.
- After packing, test in-game: AMM → Custom Entities → your NPV name
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
