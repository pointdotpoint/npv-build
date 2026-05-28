# Hybrid CLI+GUI NPV Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `pack_mod` archive-packing pipeline with a `build_project` function that outputs a WolvenKit GUI project + `npv_components.json` + `README_GUI_STEPS.md`. User does one GUI step (add components to .app), then packs in GUI.

**Architecture:** `build_project()` reuses existing bake/morphtarget/donor logic but stops before packing. Instead of authoring a full .app with partsValues, it authors a minimal template .app (empty components). All component specs are serialized to `npv_components.json`. The orchestrator calls `build_project` instead of `pack_mod`, then writes the README and AMM lua.

**Tech Stack:** Python 3.14, WolvenKit CLI 8.18.0, Blender 5.1.2 (flatpak), pytest

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `npv_build/config_editor.py` | Modify | Add `build_app_template()`, remove dead code |
| `npv_build/wolvenkit.py` | Modify | Replace `pack_mod()` with `build_project()` |
| `npv_build/project_writer.py` | Create | `write_components_json()`, `write_readme()` |
| `npv_build/orchestrator.py` | Modify | Call `build_project` + `write_components_json` + `write_readme` |
| `npv_build/cli.py` | Modify | Print GUI steps to stdout after build |
| `tests/test_project_writer.py` | Create | Unit tests for JSON + README generation |
| `tests/test_build_project.py` | Create | Integration test for build_project |

---

### Task 1: Add `build_app_template()` to config_editor.py

**Files:**
- Modify: `npv_build/config_editor.py`
- Test: `tests/test_config_editor_template.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config_editor_template.py
import json
from npv_build.config_editor import build_app_template


def test_template_has_empty_components_and_no_parts():
    result = build_app_template("my_npv_abc123")
    app_def = result["Data"]["RootChunk"]["appearances"][0]["Data"]
    assert app_def["name"]["$value"] == "my_npv_abc123_appearance"
    assert app_def["components"] == []
    assert app_def["partsValues"] == []
    assert app_def["partsOverrides"] == []
    tags = [t["$value"] for t in app_def["visualTags"]["tags"]]
    assert "AppearanceParts" not in tags


def test_template_has_correct_resource_type():
    result = build_app_template("x")
    assert result["Data"]["RootChunk"]["$type"] == "appearanceAppearanceResource"
    assert result["Header"]["WolvenKitVersion"] == "8.18.0"
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd /home/pdp/npv_project && python -m pytest tests/test_config_editor_template.py -v`
Expected: ImportError — `build_app_template` does not exist

- [ ] **Step 3: Implement `build_app_template`**

Add to `npv_build/config_editor.py` after the existing `build_app` function:

```python
def build_app_template(mod_id: str):
    """Minimal .app with one empty appearance. User adds components in WolvenKit GUI."""
    appearance_name = f"{mod_id}_appearance"
    return {
        "Header": {
            "WolvenKitVersion": "8.18.0",
            "WKitJsonVersion": "0.0.9",
            "GameVersion": 2310,
            "DataType": "CR2W",
        },
        "Data": {
            "RootChunk": {
                "$type": "appearanceAppearanceResource",
                "appearances": [
                    {
                        "HandleId": "0",
                        "Data": {
                            "$type": "appearanceAppearanceDefinition",
                            "name": _cname(appearance_name),
                            "partsValues": [],
                            "partsOverrides": [],
                            "components": [],
                            "visualTags": {"$type": "redTagList", "tags": []},
                            "resolvedDependencies": [],
                            "censorFlags": 0,
                        },
                    }
                ],
                "baseEntityType": _cname("None"),
                "baseType": _cname("None"),
                "cookingPlatform": "PLATFORM_PC",
            }
        },
    }
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd /home/pdp/npv_project && python -m pytest tests/test_config_editor_template.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```
feat: add build_app_template for hybrid CLI+GUI workflow
```

---

### Task 2: Create `project_writer.py` — component JSON + README generation

**Files:**
- Create: `npv_build/project_writer.py`
- Create: `tests/test_project_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_project_writer.py
import json
from pathlib import Path
from npv_build.project_writer import write_components_json, write_readme


def test_components_json_structure(tmp_path):
    specs = [
        {"comp_type": "entMorphTargetSkinnedMeshComponent",
         "name": "MorphTargetSkinnedMesh7243",
         "mesh": "base\\characters\\head\\my_head.mesh",
         "appearance": "01_ca_pale",
         "morph_resource": "base\\characters\\head\\my_morphs.morphtarget",
         "source": "baked head"},
        {"comp_type": "entSkinnedMeshComponent",
         "name": "hair_1",
         "mesh": "base\\hair\\mesh.mesh",
         "appearance": "molten_marmalade",
         "source": "modded hair"},
    ]
    out = tmp_path / "npv_components.json"
    write_components_json(specs, "my_npv_abc_appearance", out)
    data = json.loads(out.read_text())
    assert data["appearance_name"] == "my_npv_abc_appearance"
    assert len(data["components"]) == 2
    c0 = data["components"][0]
    assert c0["type"] == "entMorphTargetSkinnedMeshComponent"
    assert c0["name"] == "MorphTargetSkinnedMesh7243"
    assert c0["meshAppearance"] == "01_ca_pale"
    assert c0["morphResource"] == "base\\characters\\head\\my_morphs.morphtarget"
    assert c0["bindTo"] == "root"
    assert c0["source"] == "baked head"
    c1 = data["components"][1]
    assert "morphResource" not in c1


def test_readme_contains_key_sections(tmp_path):
    out = tmp_path / "README_GUI_STEPS.md"
    write_readme("my_npv_abc", "my_npv_abc_appearance", out)
    text = out.read_text()
    assert "WolvenKit" in text
    assert "my_npv_abc.app" in text
    assert "my_npv_abc_appearance" in text
    assert "parentTransform" in text
    assert "bindName" in text
    assert "root" in text
    assert "Pack" in text


def test_readme_mentions_component_json(tmp_path):
    out = tmp_path / "README_GUI_STEPS.md"
    write_readme("x", "x_appearance", out)
    text = out.read_text()
    assert "npv_components.json" in text
```

- [ ] **Step 2: Run tests, verify fail**

Run: `cd /home/pdp/npv_project && python -m pytest tests/test_project_writer.py -v`
Expected: ImportError

- [ ] **Step 3: Implement `project_writer.py`**

```python
# npv_build/project_writer.py
"""Generate npv_components.json and README_GUI_STEPS.md for the hybrid workflow."""

import json
from pathlib import Path


def write_components_json(component_specs, appearance_name, out_path: Path):
    """Serialize component specs to a JSON file the user reads in WolvenKit GUI.

    Each spec dict has: comp_type, name, mesh, appearance, and optionally
    morph_resource and source.
    """
    components = []
    for spec in component_specs:
        entry = {
            "type": spec["comp_type"],
            "name": spec["name"],
            "mesh": spec.get("mesh", ""),
            "meshAppearance": spec.get("appearance", "default"),
            "bindTo": "root",
        }
        if spec.get("morph_resource"):
            entry["morphResource"] = spec["morph_resource"]
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd /home/pdp/npv_project && python -m pytest tests/test_project_writer.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```
feat: add project_writer for component JSON + README generation
```

---

### Task 3: Replace `pack_mod()` with `build_project()` in wolvenkit.py

**Files:**
- Modify: `npv_build/wolvenkit.py`
- Test: `tests/test_build_project.py`

This is the core change. `build_project` does everything `pack_mod` does EXCEPT:
- Does NOT call `build_app` with partsValues — uses `build_app_template` instead
- Does NOT pack an archive — user does that in GUI
- Collects component specs and returns them for `project_writer`

- [ ] **Step 1: Write integration test**

```python
# tests/test_build_project.py
"""Integration test for build_project — requires WolvenKit CLI + game dir."""
import json
import os
import pytest
from pathlib import Path

GAME_DIR = os.environ.get("NPV_GAME_DIR", "")
SKIP_REASON = "Set NPV_GAME_DIR to run integration tests"


@pytest.mark.skipif(not GAME_DIR, reason=SKIP_REASON)
def test_build_project_produces_expected_files(tmp_path):
    from npv_build.wolvenkit import build_project

    asset_paths = {
        "part_entities": [
            r"base\characters\common\player_base_bodies\appearances\entity\t0_000_pwa_base__full.ent",
            r"base\characters\common\player_base_bodies\appearances\entity\a0_000_pwa_base__full.ent",
        ],
        "recipe_parts": [],
        "recipe_overrides": [],
        "face_morphs": {},
        "hair_components": [],
        "body_rig": "pwa",
        "_game_dir": GAME_DIR,
    }
    component_specs = build_project("test_int", tmp_path, asset_paths, verbosity=0)
    # Template .app should exist (cooked)
    app = tmp_path / "source" / "archive" / "base" / "characters" / "appearances" / "test_int.app"
    assert app.exists(), f"Cooked .app not found at {app}"
    # Donor .ent should exist (cooked)
    ent = tmp_path / "source" / "archive" / "base" / "characters" / "entities" / "test_int.ent"
    assert ent.exists(), f"Cooked .ent not found at {ent}"
    # Component specs returned
    assert isinstance(component_specs, list)
    assert len(component_specs) > 0
    for spec in component_specs:
        assert "comp_type" in spec
        assert "name" in spec


@pytest.mark.skipif(not GAME_DIR, reason=SKIP_REASON)
def test_build_project_with_face_bake(tmp_path):
    from npv_build.wolvenkit import build_project

    asset_paths = {
        "part_entities": [
            r"base\characters\common\player_base_bodies\appearances\entity\t0_000_pwa_base__full.ent",
        ],
        "recipe_parts": [],
        "recipe_overrides": [],
        "face_morphs": {"jaw": "h114", "nose": "h042"},
        "hair_components": [],
        "body_rig": "pwa",
        "_game_dir": GAME_DIR,
    }
    specs = build_project("test_bake", tmp_path, asset_paths, verbosity=0)
    # Baked mesh + morphtarget should exist
    mesh = tmp_path / "source" / "archive" / "base" / "characters" / "head" / "test_bake_head.mesh"
    mt = tmp_path / "source" / "archive" / "base" / "characters" / "head" / "test_bake_morphs.morphtarget"
    assert mesh.exists(), "Baked head mesh not found"
    assert mt.exists(), "Morphtarget not found"
    # Should have a head component spec
    head_specs = [s for s in specs if s["name"] == "MorphTargetSkinnedMesh7243"]
    assert len(head_specs) == 1
    assert head_specs[0]["morph_resource"].endswith("_morphs.morphtarget")
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd /home/pdp/npv_project && python -m pytest tests/test_build_project.py -v`
Expected: ImportError — `build_project` doesn't exist

- [ ] **Step 3: Implement `build_project()`**

Replace `pack_mod` in `npv_build/wolvenkit.py`. Keep all the existing helper functions (`_bake_and_author_head`, `_extract_part_components`, `_apply_recipe_overrides`, `_find_stock_head_part`, `_swap_head_part`). The new function:

```python
def build_project(mod_id, out_dir, asset_paths, verbosity):
    """Build a WolvenKit project with all binary assets. User completes the
    .app in WolvenKit GUI.

    Returns a list of component spec dicts for npv_components.json.
    """
    from .config_editor import build_app_template, build_ent_from_donor, NPC_BASE_ENT

    source_dir = out_dir / "source" / "archive"
    if source_dir.exists():
        shutil.rmtree(source_dir)
    source_dir.mkdir(parents=True, exist_ok=True)

    game_dir = Path(asset_paths["_game_dir"]) if asset_paths.get("_game_dir") else None
    if not game_dir:
        raise WolvenKitError("game_dir required")

    # --- Collect component specs (for npv_components.json) ---
    component_specs = []

    # 1. Extract components from stock part-ents
    recipe_parts = asset_paths.get("recipe_parts", [])
    part_entities = asset_paths.get("part_entities", [])

    all_part_depots = set()
    for pv in recipe_parts:
        dp = pv.get("resource", {}).get("DepotPath", {}).get("$value", "")
        if dp:
            all_part_depots.add(dp)
    for p in part_entities:
        all_part_depots.add(p)

    stock_head_depot = None
    for dp in all_part_depots:
        if "appearances\\entity\\head\\h0_" in dp or "appearances/entity/head/h0_" in dp:
            stock_head_depot = dp
            break

    for dp in sorted(all_part_depots):
        if dp == stock_head_depot:
            continue
        comps = _extract_part_components(game_dir, dp, source_dir, verbosity)
        for c in comps:
            c["source"] = dp.replace("\\", "/").rsplit("/", 1)[-1]
        if verbosity > 0 and comps:
            short = dp.rsplit("\\", 1)[-1]
            print(f"[Project]   {short}: {len(comps)} component(s)")
        component_specs.extend(comps)

    # 2. Face bake → baked mesh + morphtarget (written to source_dir)
    face_morphs = asset_paths.get("face_morphs", {})
    body_rig = asset_paths.get("body_rig", "pwa")
    baked_mesh_depot = None
    mt_depot = None

    if face_morphs and game_dir:
        try:
            result = _bake_and_author_head(
                mod_id, source_dir, game_dir, body_rig, face_morphs, verbosity)
            if result:
                baked_mesh_depot = f"base\\characters\\head\\{mod_id}_head.mesh"
                mt_depot = f"base\\characters\\head\\{mod_id}_morphs.morphtarget"
        except Exception as e:
            print(f"[Head] face bake failed ({e}); using stock head.")

    if baked_mesh_depot and mt_depot:
        stock_comps = _extract_part_components(
            game_dir, stock_head_depot, source_dir, verbosity) if stock_head_depot else []
        morph_name = "MorphTargetSkinnedMesh7243"
        for sc in stock_comps:
            if sc.get("comp_type") == "entMorphTargetSkinnedMeshComponent":
                morph_name = sc["name"]
                break
        component_specs.append({
            "comp_type": "entMorphTargetSkinnedMeshComponent",
            "name": morph_name,
            "mesh": baked_mesh_depot,
            "appearance": "default",
            "morph_resource": mt_depot,
            "source": "baked head (face morphs applied)",
        })
        if verbosity > 0:
            print(f"[Head] baked head component: {morph_name}")
    elif stock_head_depot:
        comps = _extract_part_components(game_dir, stock_head_depot, source_dir, verbosity)
        for c in comps:
            c["source"] = "stock head"
        component_specs.extend(comps)
        if verbosity > 0:
            print(f"[Head] stock head: {len(comps)} component(s)")

    # 3. Hair components
    hair_components = asset_paths.get("hair_components", [])
    hair_color = asset_paths.get("hair_color", "")
    if hair_components:
        for c in hair_components:
            if c.get("$type") != "entSkinnedMeshComponent":
                continue
            mesh_dp = c.get("mesh", {}).get("DepotPath", {}).get("$value", "")
            if not mesh_dp:
                continue
            nm = c.get("name", {}).get("$value", f"hair_{len(component_specs)}")
            if hair_color and "shadow" not in nm.lower():
                ma = hair_color
            else:
                ma = c.get("meshAppearance", {}).get("$value", "default")
            component_specs.append({
                "comp_type": "entSkinnedMeshComponent",
                "name": nm,
                "mesh": mesh_dp,
                "appearance": ma,
                "source": "modded hair",
            })
        if verbosity > 0:
            count = sum(1 for c in hair_components if c.get("$type") == "entSkinnedMeshComponent")
            print(f"[Project]   hair: {count} component(s)")

    # 4. Apply recipe material overrides
    recipe_overrides = asset_paths.get("recipe_overrides", [])
    _apply_recipe_overrides(component_specs, recipe_overrides)

    if verbosity > 0:
        print(f"[Project] Total components: {len(component_specs)}")

    # --- Author template .app ---
    app_json = build_app_template(mod_id)
    app_out = source_dir / "base" / "characters" / "appearances" / f"{mod_id}.app.json"
    app_out.parent.mkdir(parents=True, exist_ok=True)
    app_out.write_text(json.dumps(app_json, indent=2))

    # --- Author donor .ent ---
    import re as _re
    donor_ent_depot = NPC_BASE_ENT.get(body_rig, NPC_BASE_ENT["pwa"])
    donor_basename = donor_ent_depot.replace("\\", "/").rsplit("/", 1)[-1]
    donor_stage = source_dir / ".donor_ent"
    donor_stage.mkdir(parents=True, exist_ok=True)
    _run_wk(["uncook",
             str(game_dir / "archive" / "pc" / "content" / "basegame_4_appearance.archive"),
             "-o", str(donor_stage), "-s",
             "-r", _re.escape(donor_basename) + r"$"],
            verbosity, error_prefix="UncookDonorEnt")
    donor_json_files = list(donor_stage.rglob(donor_basename + ".json"))
    if not donor_json_files:
        raise WolvenKitError(f"Could not uncook donor .ent {donor_ent_depot}")
    donor_data = json.loads(donor_json_files[0].read_text())
    ent_json = build_ent_from_donor(mod_id, donor_data, body_rig)
    if verbosity > 0:
        print(f"[Project] NPV .ent based on {donor_basename}")
    shutil.rmtree(donor_stage, ignore_errors=True)

    ent_out = source_dir / "base" / "characters" / "entities" / f"{mod_id}.ent.json"
    ent_out.parent.mkdir(parents=True, exist_ok=True)
    ent_out.write_text(json.dumps(ent_json, indent=2))

    # --- Cook all JSON → binary ---
    if verbosity > 0:
        print("[WolvenKit] Cooking JSON to binary...")
    _run_wk(
        ["convert", "deserialize", str(source_dir)],
        verbosity,
        error_prefix="ConvertFailedError",
    )

    # Clean up JSON (keep cooked binaries)
    for p in list(source_dir.rglob("*.json")):
        p.unlink()
    for p in list(source_dir.rglob("*.buffer")):
        p.unlink()

    # Clean up the head .ent authored by _bake_and_author_head (not needed
    # in the project — user inlines the component in the .app via GUI)
    head_ent_cooked = source_dir / "base" / "characters" / "head" / f"{mod_id}_head.ent"
    if head_ent_cooked.exists():
        head_ent_cooked.unlink()

    return component_specs
```

- [ ] **Step 4: Update import in `__init__.py` or verify module loads**

Run: `cd /home/pdp/npv_project && python -c "from npv_build.wolvenkit import build_project; print('OK')"`
Expected: OK

- [ ] **Step 5: Run integration test (if game dir available)**

Run: `cd /home/pdp/npv_project && NPV_GAME_DIR="$HOME/.local/share/Steam/steamapps/common/Cyberpunk 2077" python -m pytest tests/test_build_project.py -v -x`

- [ ] **Step 6: Commit**

```
feat: replace pack_mod with build_project for hybrid workflow
```

---

### Task 4: Update orchestrator to use `build_project`

**Files:**
- Modify: `npv_build/orchestrator.py`

- [ ] **Step 1: Update imports**

Change line 9:
```python
# Old:
from .wolvenkit import check_wolvenkit_version, resolve_templates, pack_mod, WolvenKitError
# New:
from .wolvenkit import check_wolvenkit_version, resolve_templates, build_project, WolvenKitError
```

- [ ] **Step 2: Replace the packaging section (lines ~153-176)**

Replace the `pack_mod` call + lua generation section with:

```python
    # Build WolvenKit project (all binary assets, no archive packing)
    if verbosity > 0:
        print("[Project] Building WolvenKit project...")

    try:
        component_specs = build_project(mod_id, output_dir, asset_paths, verbosity)
    except WolvenKitError as e:
        raise OrchestratorError(e.module_name, str(e))
    except Exception as e:
        raise OrchestratorError("WolvenKit Automation", f"Unexpected error: {e}")

    # Write component specs JSON
    from .project_writer import write_components_json, write_readme
    appearance_name = f"{mod_id}_appearance"

    write_components_json(
        component_specs, appearance_name,
        output_dir / "npv_components.json",
    )

    # Write GUI instructions
    write_readme(mod_id, appearance_name, output_dir / "README_GUI_STEPS.md")

    # AMM Lua
    lua_dir = output_dir / "bin" / "x64" / "plugins" / "cyber_engine_tweaks" / "mods" / "AppearanceMenuMod" / "Collabs" / "Custom Entities"
    lua_dir.mkdir(parents=True, exist_ok=True)
    lua_file = lua_dir / f"{mod_id}.lua"
    lua_file.write_text(lua_code, encoding="utf-8")

    if verbosity > 0:
        print(f"[Orchestrator] Project built: {output_dir}")
        print(f"[Orchestrator] Components: {len(component_specs)}")
        print(f"[Orchestrator] Next: open in WolvenKit GUI, follow README_GUI_STEPS.md")

    return str(output_dir)
```

- [ ] **Step 3: Remove the `resolve_templates` call and its surrounding try/except (lines ~80-94)**

It was a no-op. Remove the call and the `templates` variable. The `build_project` function doesn't take a `templates` arg.

- [ ] **Step 4: Verify existing orchestrator test still passes**

Run: `cd /home/pdp/npv_project && python -m pytest tests/test_orchestrator.py -v`

- [ ] **Step 5: Commit**

```
refactor: orchestrator uses build_project, outputs WolvenKit project
```

---

### Task 5: Update CLI to print GUI steps

**Files:**
- Modify: `npv_build/cli.py`

- [ ] **Step 1: Add post-build output**

After the `run_orchestrator` call succeeds (line ~53), add:

```python
        # Print GUI next-steps
        readme_path = Path(args.output).resolve() / "README_GUI_STEPS.md"
        if readme_path.exists():
            print("\n" + "=" * 60)
            print("PROJECT READY — Open in WolvenKit GUI")
            print("=" * 60)
            print(f"\nProject dir: {Path(args.output).resolve()}")
            print(f"Instructions: {readme_path}")
            print(f"\nQuick summary:")
            print(f"  1. Open project in WolvenKit GUI")
            print(f"  2. Add components from npv_components.json to the .app")
            print(f"  3. Set parentTransform.bindName = root on each")
            print(f"  4. Set skinning.bindName = root on each")
            print(f"  5. Pack mod in WolvenKit GUI")
            print(f"  6. Copy archive/ + bin/ to game dir")
```

- [ ] **Step 2: Verify CLI runs end-to-end**

Run: `cd /home/pdp/npv_project && source venv/bin/activate && npv-build "$HOME/.local/share/Steam/steamapps/compatdata/1091500/pfx/drive_c/users/steamuser/Saved Games/CD Projekt Red/Cyberpunk 2077/AutoSave-0/sav.dat" "Test V" --output /tmp/npv_hybrid_test --game-dir "$HOME/.local/share/Steam/steamapps/common/Cyberpunk 2077" --hair zara -v`

Expected: Project directory at `/tmp/npv_hybrid_test` with:
- `source/archive/.../*.app` (cooked template)
- `source/archive/.../*.ent` (cooked donor)
- `source/archive/.../*_head.mesh` (baked)
- `source/archive/.../*_morphs.morphtarget` (cooked)
- `npv_components.json`
- `README_GUI_STEPS.md`
- `bin/.../Custom Entities/*.lua`

- [ ] **Step 3: Commit**

```
feat: CLI prints WolvenKit GUI next-steps after build
```

---

### Task 6: Clean up dead code

**Files:**
- Modify: `npv_build/wolvenkit.py`
- Modify: `npv_build/config_editor.py`

- [ ] **Step 1: Remove `pack_mod` from wolvenkit.py**

Delete the entire `pack_mod` function. It's replaced by `build_project`.

- [ ] **Step 2: Remove `resolve_templates` from wolvenkit.py**

It was a no-op. Delete the function.

- [ ] **Step 3: Remove unused functions from config_editor.py**

Remove:
- `build_app()` — replaced by `build_app_template()`
- `_make_inline_component()` — was for the inline approach (dead end)
- `build_head_ent()` — head component is now a spec in npv_components.json, not a separate .ent
- `build_hair_ent()` — hair components are now specs in npv_components.json
- `build_hair_ent_via_app()` — unused

Keep:
- `_cname()`, `_resource()` — used by `build_app_template` and `build_ent_from_donor`
- `_transform_binding()`, `_skinning_binding()` — may be useful for future work, but remove if unused
- `build_ent_from_donor()` — used by `build_project`
- `NPC_BASE_ENT` — used by `build_project`
- `_MESH_COMPONENT_TYPES` — used by `_extract_part_components`

- [ ] **Step 4: Update imports in wolvenkit.py line 7**

```python
# Old:
from .config_editor import build_app, build_ent_from_donor, NPC_BASE_ENT
# New:
from .config_editor import build_ent_from_donor, NPC_BASE_ENT
```

(`build_app_template` is imported inside `build_project` to avoid circular imports)

- [ ] **Step 5: Run all tests**

Run: `cd /home/pdp/npv_project && python -m pytest tests/ -v`

- [ ] **Step 6: Commit**

```
refactor: remove dead code from partsValues/inline approaches
```

---

### Task 7: End-to-end verification

**Files:** None (verification only)

- [ ] **Step 1: Full CLI build**

```bash
source ~/npv_project/venv/bin/activate
export PATH="$HOME/.local/bin:$PATH"
rm -rf /tmp/npv_final_test

npv-build "$HOME/.local/share/Steam/steamapps/compatdata/1091500/pfx/drive_c/users/steamuser/Saved Games/CD Projekt Red/Cyberpunk 2077/AutoSave-0/sav.dat" \
  "My V" \
  --output /tmp/npv_final_test \
  --game-dir "$HOME/.local/share/Steam/steamapps/common/Cyberpunk 2077" \
  --hair zara \
  --garment 'base\characters\garment\player_equipment\torso\t1_097_pwa_tank__corset_doll_prostitute.ent' \
  -v
```

- [ ] **Step 2: Verify output files exist**

```bash
echo "=== Project structure ==="
find /tmp/npv_final_test -type f | sort

echo "=== Components JSON ==="
python3 -c "import json; d=json.load(open('/tmp/npv_final_test/npv_components.json')); print(f'{len(d[\"components\"])} components'); [print(f'  {c[\"type\"][:30]:30s} {c[\"name\"][:30]:30s} app={c[\"meshAppearance\"]}') for c in d['components']]"

echo "=== README exists ==="
head -5 /tmp/npv_final_test/README_GUI_STEPS.md
```

- [ ] **Step 3: Verify cooked assets are valid**

```bash
# Uncook the template .app to verify it's valid
ARCHIVE_DIR=/tmp/npv_final_test/source/archive
APP=$(find "$ARCHIVE_DIR" -name "*.app" | head -1)
echo "Template .app: $APP ($(stat -c %s "$APP") bytes)"

ENT=$(find "$ARCHIVE_DIR" -name "*.ent" | head -1)
echo "Donor .ent: $ENT ($(stat -c %s "$ENT") bytes)"

MESH=$(find "$ARCHIVE_DIR" -name "*_head.mesh" | head -1)
echo "Baked mesh: $MESH ($(stat -c %s "$MESH") bytes)"

MT=$(find "$ARCHIVE_DIR" -name "*.morphtarget" | head -1)
echo "Morphtarget: $MT ($(stat -c %s "$MT") bytes)"
```

- [ ] **Step 4: Commit (if any fixes were needed)**

```
fix: address issues found in end-to-end verification
```
