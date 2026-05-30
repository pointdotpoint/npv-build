# NPV Equipped-Clothing Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the NPV wear V's currently-equipped clothing, captured in-game via the CET dumper and fed into the build through `--cc-json`.

**Architecture:** The CET dumper (`data/cet_dumper/init.lua`) already walks `player:GetComponents()`. Extend it to emit a `clothing` array of equipped garment components (name/mesh/appearance/slot). `clothing.py:resolve_clothing` gains an `equipped` param: when present it builds the outfit from the equipped list (both torso layers kept) instead of `fallback_outfit.json`; `--garment` still overrides per-slot. The equipped list is carried in `asset_paths["equipped_clothing"]` from `mapping.resolve_assets` (which already has `cc_settings`) and consumed in `wolvenkit.build_project`. The raw `sav.dat` path supplies no clothing → unchanged fallback.

**Tech Stack:** Python 3 (stdlib only), pytest; Lua (CET) for the dumper. Run tests with the project venv: `venv/bin/python -m pytest`.

---

### Task 1: `resolve_clothing` accepts and uses an `equipped` list

**Files:**
- Modify: `npv_build/clothing.py`
- Test: `tests/test_clothing.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_clothing.py`:

```python
def test_resolve_clothing_uses_equipped_outfit():
    equipped = [
        {"name": "t1_097_pwa_tank", "mesh": "base\\g\\t1_097_pwa_tank.mesh",
         "appearance": "red", "slot": "inner_torso"},
        {"name": "l1_055_pwa_pants", "mesh": "base\\g\\l1_055_pwa_pants.mesh",
         "appearance": "black", "slot": "legs"},
    ]
    specs = resolve_clothing("pwa", equipped=equipped)
    names = [s["name"] for s in specs]
    assert "t1_097_pwa_tank" in names
    assert "l1_055_pwa_pants" in names
    # equipped appearance is preserved
    tank = next(s for s in specs if s["name"] == "t1_097_pwa_tank")
    assert tank["appearance"] == "red"
    assert tank["comp_type"] == "entGarmentSkinnedMeshComponent"
    # fallback defaults (sweater/jeans/boots) are NOT present when equipped given
    assert "t1_024_pwa_tshirt__sweater" not in names


def test_resolve_clothing_equipped_keeps_both_torso_layers():
    equipped = [
        {"name": "t1_inner", "mesh": "base\\g\\t1_inner.mesh",
         "appearance": "default", "slot": "inner_torso"},
        {"name": "t2_outer", "mesh": "base\\g\\t2_outer.mesh",
         "appearance": "default", "slot": "outer_torso"},
    ]
    specs = resolve_clothing("pwa", equipped=equipped)
    names = [s["name"] for s in specs]
    assert "t1_inner" in names and "t2_outer" in names


def test_resolve_clothing_garment_override_beats_equipped():
    equipped = [
        {"name": "l1_old", "mesh": "base\\g\\l1_old.mesh",
         "appearance": "default", "slot": "legs"},
    ]
    specs = resolve_clothing("pwa", garment_overrides=[
        "base\\garment\\l1_new_pwa.ent",
    ], equipped=equipped)
    names = [s["name"] for s in specs]
    assert "l1_new_pwa" in names
    assert "l1_old" not in names


def test_resolve_clothing_empty_equipped_falls_back():
    specs_none = resolve_clothing("pwa", equipped=None)
    specs_empty = resolve_clothing("pwa", equipped=[])
    base = resolve_clothing("pwa")
    assert len(specs_none) == len(base)
    assert len(specs_empty) == len(base)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_clothing.py -k equipped -v`
Expected: FAIL — `resolve_clothing() got an unexpected keyword argument 'equipped'`.

- [ ] **Step 3: Implement the `equipped` path in `resolve_clothing`**

Replace the body of `resolve_clothing` in `npv_build/clothing.py` with (signature gains `equipped`):

```python
def resolve_clothing(
    body_rig: str,
    garment_overrides: list[str] | None = None,
    equipped: list[dict] | None = None,
    verbosity: int = 0,
) -> list[dict]:
    """Return component specs for the NPV's clothing.

    If `equipped` (from the CET dump) is non-empty, the base outfit is V's
    equipped garments; otherwise it loads data/fallback_outfit.json. User
    `--garment` overrides apply on top, by slot (inferred from prefix), and
    win over both. Layered torso (t1_ + t2_) is preserved.
    """
    PREFIX_SLOTS = [
        ("t2_", "outer_torso"), ("t1_", "inner_torso"),
        ("l1_", "legs"), ("s1_", "feet"), ("h1_", "head"),
    ]

    def slot_for(basename: str) -> str:
        for prefix, slot in PREFIX_SLOTS:
            if basename.startswith(prefix):
                return slot
        return ""

    # base specs come from equipped clothing if present, else the fallback file.
    base_specs: list[dict] = []
    if equipped:
        for item in equipped:
            mesh = item.get("mesh", "")
            name = item.get("name", "")
            if not mesh or not name:
                continue
            base_specs.append({
                "comp_type": "entGarmentSkinnedMeshComponent",
                "name": name,
                "mesh": mesh,
                "appearance": item.get("appearance") or "default",
                "source": f"clothing:{item.get('slot') or 'equipped'} (equipped)",
            })
            if verbosity > 0:
                print(f"[Clothing] equipped {item.get('slot') or '?'}: {name}")
    else:
        fallback_file = Path(__file__).parent / "data" / "fallback_outfit.json"
        fallback = json.loads(fallback_file.read_text()).get(body_rig, {})
        for slot_name, slot_data in fallback.items():
            base_specs.append({
                "comp_type": "entGarmentSkinnedMeshComponent",
                "name": slot_data["name"],
                "mesh": slot_data["mesh"],
                "appearance": slot_data["appearance"],
                "source": f"clothing:{slot_name}",
            })

    # apply --garment overrides by slot: an override replaces any base spec in the
    # same slot (custom_ slot for unknown prefixes so it is purely additive).
    override_specs: list[dict] = []
    overridden_slots: set[str] = set()
    for i, g in enumerate(garment_overrides or []):
        g = g.strip()
        if not g:
            continue
        basename = g.replace("\\", "/").rsplit("/", 1)[-1].lower()
        slot = slot_for(basename) or f"custom_{i}"
        overridden_slots.add(slot)
        name = basename.rsplit(".", 1)[0]
        override_specs.append({
            "comp_type": "entGarmentSkinnedMeshComponent",
            "name": name,
            "mesh": g,
            "appearance": "default",
            "source": f"clothing:{slot}",
        })
        if verbosity > 0:
            print(f"[Clothing] override {slot}: {name}")

    def base_slot(spec: dict) -> str:
        # source is "clothing:<slot>" or "clothing:<slot> (equipped)" -> "<slot>"
        return spec["source"].split(":", 1)[1].split(" ", 1)[0]

    specs = [s for s in base_specs if base_slot(s) not in overridden_slots]
    specs.extend(override_specs)
    return specs
```

- [ ] **Step 4: Run the clothing tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_clothing.py -v`
Expected: PASS — all tests including the four new ones and the four existing ones.

- [ ] **Step 5: Commit**

```bash
git add npv_build/clothing.py tests/test_clothing.py
git commit -m "feat(clothing): use equipped garments from CET dump as base outfit"
```

---

### Task 2: Thread the equipped clothing through the build

**Files:**
- Modify: `npv_build/mapping.py` (asset_paths init ~line 44; resolve_assets signature ~line 11)
- Modify: `npv_build/wolvenkit.py` (resolve_clothing call ~line 698)
- Test: `tests/test_build_project.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_project.py`:

```python
def test_asset_paths_carries_equipped_clothing():
    """resolve_assets surfaces cc_settings['clothing'] as asset_paths['equipped_clothing']
    so build_project can pass it to resolve_clothing."""
    from npv_build.mapping import resolve_assets
    cc = {
        "patch": "2.13",
        "body_rig": "pwa",
        "selections": [],
        "clothing": [
            {"name": "t1_x", "mesh": "base\\g\\t1_x.mesh",
             "appearance": "default", "slot": "inner_torso"},
        ],
    }
    ap = resolve_assets(cc, game_dir=None)
    assert ap["equipped_clothing"] == cc["clothing"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_build_project.py::test_asset_paths_carries_equipped_clothing -v`
Expected: FAIL — `KeyError: 'equipped_clothing'` (the key isn't in the returned dict yet). Note: `resolve_assets(cc, game_dir=None)` runs fine using the cached index, so the only failure is the missing key.

- [ ] **Step 3: Carry `clothing` into asset_paths**

In `npv_build/mapping.py`, in the `asset_paths = { ... }` dict literal (around line 44), add the key sourced from `cc_settings`:

```python
    asset_paths = {
        "patch": patch,
        "body_rig": body_rig,
        "head_app": "",
        "head_appearance_name": "",
        "part_entities": [],
        "external_dependencies": [],
        "unresolved": [],
        "equipped_clothing": cc_settings.get("clothing", []),
    }
```

That dict-literal addition is the entire production change for this step. `cc_settings`
is the first parameter of `resolve_assets`, already in scope.

- [ ] **Step 4: Pass it to resolve_clothing in build_project**

In `npv_build/wolvenkit.py`, change the clothing call (around line 698) from:

```python
    component_specs.extend(resolve_clothing(body_rig, garment_overrides, verbosity))
```

to:

```python
    component_specs.extend(resolve_clothing(
        body_rig, garment_overrides,
        equipped=asset_paths.get("equipped_clothing"), verbosity=verbosity))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_build_project.py tests/test_clothing.py -v`
Expected: PASS — `test_asset_paths_carries_equipped_clothing` now finds the key.

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `venv/bin/python -m pytest -q`
Expected: PASS (all prior tests still green).

- [ ] **Step 7: Commit**

```bash
git add npv_build/mapping.py npv_build/wolvenkit.py tests/test_build_project.py
git commit -m "feat(build): pass equipped clothing from cc-json to resolve_clothing"
```

---

### Task 3: CET dumper emits the `clothing` array

**Files:**
- Modify: `npv_build/data/cet_dumper/init.lua` (inside `gather()`, after the existing `player:GetComponents()` walks; before `return out`)

This is in-game Lua — not unit-testable. Verified by running the dumper.

- [ ] **Step 1: Add clothing capture to `gather()`**

In `npv_build/data/cet_dumper/init.lua`, initialize `out.clothing = {}` near the other `out.*` fields at the top of `gather()` (next to `out.head = {}` etc.). Then, before `return out` at the end of `gather()`, add:

```lua
  -- Equipped clothing: the player's live garment mesh components ARE the worn
  -- outfit. Capture name/mesh/appearance/slot so npv-build can dress the NPV in
  -- V's actual clothes (consumed by resolve_clothing via --cc-json).
  pcall(function()
    local comps = player:GetComponents()
    if not comps then return end
    local prefixSlots = {
      { "t2_", "outer_torso" }, { "t1_", "inner_torso" },
      { "l1_", "legs" }, { "s1_", "feet" }, { "h1_", "head" },
    }
    for _, comp in ipairs(comps) do
      local cn = nil
      pcall(function() cn = safeCNameStr(comp:GetName()) end)
      if cn then
        local slot = nil
        for _, ps in ipairs(prefixSlots) do
          if cn:sub(1, #ps[1]) == ps[1] then slot = ps[2] break end
        end
        if slot then
          local mesh = nil
          pcall(function()
            local m = comp.mesh
            if m and m.value then mesh = safeCNameStr(m.value) end
          end)
          local appearance = nil
          pcall(function()
            local a = comp.meshAppearance
            if a ~= nil then appearance = safeCNameStr(a) end
          end)
          if mesh then
            table.insert(out.clothing, {
              name = cn,
              mesh = mesh,
              appearance = appearance or "default",
              slot = slot,
            })
          end
        end
      end
    end
  end)
```

- [ ] **Step 2: Update the Dump() summary line (optional but helpful)**

In `NPVDumper.Dump()`, after the existing print, add a clothing count line:

```lua
  print("[npv_dumper] clothing items captured: " .. tostring(#data.clothing))
```

- [ ] **Step 3: Commit**

```bash
git add npv_build/data/cet_dumper/init.lua
git commit -m "feat(cet-dumper): capture equipped garment components into cc dump"
```

- [ ] **Step 4: In-game verification (manual, by the user)**

1. Copy `npv_build/data/cet_dumper/init.lua` to
   `<CP2077>/bin/x64/plugins/cyber_engine_tweaks/mods/npv_dumper/init.lua`.
2. Load the save, open the CET overlay, run `GetMod("npv_dumper").Dump()`.
3. Confirm the console prints `clothing items captured: N` (N ≥ 1) and that
   `cc_dump.json` contains a non-empty `"clothing"` array with `name`/`mesh`/
   `appearance`/`slot` per item.

---

### Task 4: End-to-end build + verify

**Files:** none (verification only).

- [ ] **Step 1: Build from the CET dump**

Run (substitute the dump path produced in Task 3 Step 4):

```bash
venv/bin/npv-build --cc-json <path/to/cc_dump.json> "MyV03" \
  --output ./my_v_mod \
  --game-dir "/home/pdp/.local/share/Steam/steamapps/common/Cyberpunk 2077" -v
```

Expected: build succeeds; verbose log shows `[Clothing] equipped <slot>: <name>` lines
matching V's outfit (not the sweater/jeans/boots fallback).

- [ ] **Step 2: Verify components carry the equipped garments**

Run:

```bash
venv/bin/python -c "import json; d=json.load(open('my_v_mod/npv_components.json')); \
print([c['name'] for c in (d if isinstance(d,list) else d.get('components',d)) \
if 'clothing' in c.get('source','')])"
```

Expected: the printed names are V's equipped garments (both torso layers if worn),
not the fallback `t1_024_pwa_tshirt__sweater` / `l1_012_..._jeans_tight` / `s1_066_..._bovver`.

- [ ] **Step 3: Reinstall + in-game check (manual, by the user)**

Copy the rebuilt `my_v_mod/archive/pc/mod/<mod_id>.archive` into the game, restart /
CET reload, AMM → Despawn All, spawn the NPV fresh, confirm it wears V's outfit.

---

## Notes for the executor

- Always run pytest via `venv/bin/python -m pytest` (the system python lacks
  `tomli_w` and the editable install).
- The `sav.dat` path produces no `clothing` key → `equipped_clothing` defaults to
  `[]` → `resolve_clothing` falls back to `fallback_outfit.json`. Do not change that.
- `--garment` overrides must continue to win over the equipped base (Task 1 covers this).
