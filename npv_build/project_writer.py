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
        # Determine binding target: head-related components bind to "face_rig", others to "root"
        bind_to = spec.get("bind_to")
        if not bind_to:
            name_lower = (spec.get("name") or "").lower()
            mesh_lower = (spec.get("mesh") or "").lower()
            source_lower = (spec.get("source") or "").lower()
            is_head = (
                any(p in name_lower for p in ["h0_", "he_", "ht_", "hb_", "hx_", "heb_"]) or
                "player_base_heads" in mesh_lower or
                "characters\\head" in mesh_lower or
                "characters/head" in mesh_lower or
                "basehead" in name_lower or
                "basehead" in source_lower or
                "_head.mesh" in mesh_lower or
                "eyes" in name_lower or
                "eyes" in source_lower or
                "eyes" in mesh_lower or
                "teeth" in name_lower or
                "teeth" in source_lower or
                "cyberware" in name_lower or
                "cyberware" in source_lower or
                "makeup" in name_lower or
                "makeup" in source_lower or
                "freckles" in name_lower or
                "freckles" in source_lower or
                "pimples" in name_lower or
                "pimples" in source_lower or
                ("tattoo" in name_lower and "tattoo_08" in mesh_lower) or
                ("tattoo" in source_lower and "tattoo_08" in mesh_lower)
            )
            bind_to = "face_rig" if is_head else "root"

        if spec["comp_type"] == "entAnimatedComponent":
            entry["graph"] = spec.get("graph", "")
            entry["rig"] = spec.get("rig", "")
            entry["bindTo"] = bind_to
        elif spec["comp_type"] == "entMorphTargetSkinnedMeshComponent":
            entry["mesh"] = spec.get("mesh", "")
            entry["meshAppearance"] = spec.get("appearance", "default")
            entry["bindTo"] = bind_to
            entry["graph"] = spec.get("graph", "") or spec.get("morph_resource", "")
            entry["morphResource"] = spec.get("morph_resource", "") or spec.get("graph", "")
        else:
            entry["mesh"] = spec.get("mesh", "")
            entry["meshAppearance"] = spec.get("appearance", "default")
            entry["bindTo"] = bind_to
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
