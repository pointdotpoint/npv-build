# Vanilla Clothing Catalog (GUI redesign plan 4/4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Browse… picker on the inspector's clothing slots showing vanilla garments by name (with thumbnails when available), where picking an item sets a buildable garment override — never a broken build.

**Architecture:** A front-loaded spike decides how item names map to garment meshes (the WolvenKit CLI shipped here has **no TweakDB dump command** — verified against `cp77tools --help` on 2026-07-19, so the spec's "dump TweakDB via WolvenKit CLI" needs a measured fallback). A `clothing_catalog.py` module then builds a per-rig-validated catalog cached at `~/.cache/npv/clothing_catalog.json`; `thumbs.py` lazily generates ~256px thumbnails from the user's `clothing_images_dir` (setting shipped 2026-07-19); the bridge exposes search + thumbnail endpoints; the picker UI plugs into plan 2's inspector rows and translates picks into the existing `BuildRequest.garments` mechanism.

**Tech Stack:** Python 3.11+ (Pillow for thumbs — already in the `gui` extra), vanilla JS, pytest + Playwright smoke.

**Spec:** `docs/superpowers/specs/2026-07-18-gui-redesign-webui-design.md` §"Vanilla clothing catalog".

**Depends on:** plan 2 (`2026-07-19-webui-appearance-inspector.md`) Tasks 1+5+6 — the row/override contract and the inspector UI. Task 1 (spike) and Task 2 can run before/parallel to plan 2.

## Global Constraints

- **Never vendored:** images (1.3 GB in `~/cyberpunk_mod_list/static/images/clothes/`). **Vendored:** a copy of `clothes.json` (strings only).
- No CDPR bytes in repo; the catalog cache is built at runtime on the user's machine from their install.
- Unresolvable items grey out ("not available for NPCs") — never a broken build; picks are validated against the archive index before becoming overrides.
- Missing `clothing_images_dir` → text-only rows; the feature degrades cleanly, never errors.
- Bridge returns JSON dicts; `uv run ruff check .` + `uv run pytest -q` green per task.

## Reference (verified 2026-07-19)

- `~/cyberpunk_mod_list/data/clothes.json`: list of 1,485 items shaped `{"command": "Game.AddToInventory(\"Items.Mask_02_basic_01\", 1)", "name": "TITANIUM-REINFORCED GAS MASK", "image": "/images/clothes/titanium-reinforced_gas_mask_2_basic_01___.jpg"}` — the TweakDB item id is inside `command`.
- Garment slot prefixes (from `data/fallback_outfit.json` / `clothing.py`): `t1_` inner torso, `t2_` outer torso, `l1_` legs, `s1_` feet, plus `h*_`/mask heads. `--garment` values are part `.ent`/mesh depot paths like `base\characters\garment\player_equipment\torso\t1_024_tshirt__sweater\t1_024_pwa_tshirt__sweater.mesh`.
- `cp77tools` subcommands: archive/extract/uncook/import/export/pack/build/convert/conflicts/hash/oodle/settings/wwise — **no `tweak`**.
- Settings already has `clothing_images_dir` (validated dir-or-None) and the Settings UI field.

---

### Task 1: SPIKE — name→mesh mapping source + coverage measurement

**Files:**
- Create: `scripts/clothing_spike.py` (throwaway quality is fine, but committed)
- Create: `docs/research/2026-07-XX-clothing-catalog-spike.md` (findings; fill the date)

**Decision to make.** Three candidate mapping sources, in preference order:

1. **Filename join (no TweakDB at all):** `clothes.json`'s `image` filename embeds a normalized item name + variant (`titanium-reinforced_gas_mask_2_basic_01___.jpg` ↔ `Items.Mask_02_basic_01`). Garment mesh paths in the game archives are also name-structured (`t1_024_tshirt__sweater/t1_024_pwa_tshirt__sweater.mesh`). Enumerate all garment meshes once via `cp77tools archive <basegame archives> -l --regex base\\characters\\garment\\.*\.mesh$`, then fuzzy-join on normalized tokens. Zero external deps; coverage is the open question.
2. **Vendored community TweakDB dump (strings only):** a pinned JSON of clothing records (item id → `appearanceName`, `entityTemplatePath`) from a community TweakDB export. Check license/redistribution before vendoring; record the source + SHA in the research note.
3. **Parse `tweakdb.bin` ourselves:** rejected unless 1 and 2 both fail — the format is documented only in WolvenKit sources and is a large maintenance surface.

- [ ] **Step 1: Enumerate garment meshes from the user's install**

```python
# scripts/clothing_spike.py (core of it)
"""Measure clothes.json -> garment-mesh join coverage per rig.
Usage: uv run python scripts/clothing_spike.py "<game_dir>"
"""
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

GAME = Path(sys.argv[1])
WK = Path.home() / ".cache/npv/tools/wolvenkit/cp77tools"
CLOTHES = json.load(open(Path.home() / "cyberpunk_mod_list/data/clothes.json"))

meshes = []
for archive in sorted((GAME / "archive/pc/content").glob("basegame_*.archive")):
    out = subprocess.run(
        [str(WK), "archive", str(archive), "-l", "--regex",
         r"base\\characters\\garment\\.*\.mesh$"],
        capture_output=True, text=True, timeout=600).stdout
    meshes += re.findall(r"base\\characters\\garment\\\S+\.mesh", out)
print(f"{len(meshes)} garment meshes found")

def norm(s):
    return set(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())

def item_id(entry):
    m = re.search(r'"Items\.([^"]+)"', entry["command"])
    return m.group(1) if m else ""

hits = defaultdict(list)
for entry in CLOTHES:
    tokens = norm(entry["name"]) | norm(item_id(entry))
    best, best_score = None, 0.0
    for mesh in meshes:
        stem = mesh.rsplit("\\", 1)[-1]
        score = len(tokens & norm(stem)) / max(len(tokens), 1)
        if score > best_score:
            best, best_score = mesh, score
    if best_score >= 0.5:
        hits[entry["name"]] = (best, round(best_score, 2))

print(f"joined {len(hits)}/{len(CLOTHES)} = {len(hits)/len(CLOTHES):.0%}")
json.dump(hits, open("/tmp/clothing_spike_join.json", "w"), indent=1)
```

- [ ] **Step 2: Measure.** Run it; record: total meshes, join % overall, join % per slot prefix (t1/t2/l1/s1/h), 20 random joins eyeballed for correctness, and per-rig availability (a mesh is pwa-buildable when a `_pwa_` sibling exists, pma likewise).

- [ ] **Step 3: Decide + write the research note** with the numbers. Gate:
  - ≥60% overall with ≥90% eyeballed precision → ship option 1 (Task 2 consumes the join logic).
  - Otherwise evaluate option 2 (find a community dump, verify license, re-measure).
  - Record the decision as the note's first line; Task 2 reads it.

- [ ] **Step 4: Vendor the strings data**

```bash
cp ~/cyberpunk_mod_list/data/clothes.json npv_build/data/clothes.json
git add npv_build/data/clothes.json scripts/clothing_spike.py docs/research/
git commit -m "spike(clothing): measure name->mesh join coverage; vendor clothes.json"
```

---

### Task 2: `clothing_catalog.py` — build + cache with per-rig buildable flags

**Files:**
- Create: `npv_build/gui_logic/clothing_catalog.py`
- Test: `tests/gui_logic/test_clothing_catalog.py`

**Interfaces:**
- Produces: `build_catalog(mesh_paths: list[str], clothes: list[dict]) -> list[dict]` — pure join (mesh enumeration is injected so tests need no WolvenKit). Entry: `{"item_id", "name", "image", "slot", "mesh", "buildable_pwa", "buildable_pma"}`; unjoined items keep `mesh: None` and both flags False (grey rows).
- Produces: `load_catalog(cache_path: Path) -> list[dict] | None`, `save_catalog(cache_path: Path, entries) -> None`; default cache path `get_cache_dir() / "clothing_catalog.json"`.
- Produces: `slot_for_mesh(mesh: str) -> str` mapping prefix → `inner_torso|outer_torso|legs|feet|head|other`.
- Consumes: the join scoring proven in Task 1 (copy the normalized-token approach into the module — the spike script stays a script).

- [ ] **Step 1: Failing tests**

```python
# tests/gui_logic/test_clothing_catalog.py
from npv_build.gui_logic.clothing_catalog import (
    build_catalog,
    load_catalog,
    save_catalog,
    slot_for_mesh,
)

MESHES = [
    "base\\characters\\garment\\player_equipment\\torso\\t1_024_tshirt__sweater\\t1_024_pwa_tshirt__sweater.mesh",
    "base\\characters\\garment\\player_equipment\\torso\\t1_024_tshirt__sweater\\t1_024_pma_tshirt__sweater.mesh",
    "base\\characters\\garment\\player_equipment\\legs\\l1_012_pants__jeans_tight\\l1_012_pwa_pants__jeans_tight.mesh",
]
CLOTHES = [
    {"command": 'Game.AddToInventory("Items.Tshirt_024_basic_01", 1)',
     "name": "SWEATER TSHIRT", "image": "/images/clothes/tshirt_sweater.jpg"},
    {"command": 'Game.AddToInventory("Items.Hat_99_rare", 1)',
     "name": "IMAGINARY UNMATCHABLE HAT ZZZZ", "image": "/images/clothes/hat.jpg"},
]


def test_build_catalog_joins_and_flags_rigs():
    entries = build_catalog(MESHES, CLOTHES)
    sweater = next(e for e in entries if e["item_id"] == "Tshirt_024_basic_01")
    assert sweater["mesh"].endswith("t1_024_pwa_tshirt__sweater.mesh")
    assert sweater["buildable_pwa"] is True and sweater["buildable_pma"] is True
    assert sweater["slot"] == "inner_torso"


def test_unjoined_items_grey_out_not_dropped():
    entries = build_catalog(MESHES, CLOTHES)
    hat = next(e for e in entries if e["item_id"] == "Hat_99_rare")
    assert hat["mesh"] is None
    assert hat["buildable_pwa"] is False and hat["buildable_pma"] is False


def test_slot_for_mesh_prefixes():
    assert slot_for_mesh("...\\t1_024_pwa_x.mesh") == "inner_torso"
    assert slot_for_mesh("...\\t2_010_pwa_x.mesh") == "outer_torso"
    assert slot_for_mesh("...\\l1_012_pwa_x.mesh") == "legs"
    assert slot_for_mesh("...\\s1_066_pwa_x.mesh") == "feet"


def test_cache_roundtrip(tmp_path):
    entries = build_catalog(MESHES, CLOTHES)
    save_catalog(tmp_path / "c.json", entries)
    assert load_catalog(tmp_path / "c.json") == entries
    assert load_catalog(tmp_path / "missing.json") is None
```

- [ ] **Step 2: Run to verify failure**, then implement the module: `item_id`/`norm` helpers from the spike, join threshold as decided in Task 1's research note, rig flags by checking a `_pwa_`/`_pma_` sibling within the mesh list, `slot_for_mesh` on the filename prefix, JSON cache with corrupt-file → `None`.

- [ ] **Step 3: Add the WolvenKit-backed builder** (thin, integration-tested by the e2e gate only):

```python
def build_catalog_from_game(game_dir: Path, wk, clothes_path: Path,
                            cache_path: Path) -> list[dict]:
    """Enumerate garment meshes via the WolvenKit adapter, join against the
    vendored clothes.json, cache, and return the entries."""
```

using `wk.list_archive(archive, pattern=r"base\\characters\\garment\\.*\.mesh$")`
per basegame archive — **verify before use:** the exact `WolvenKit.list_archive`
signature in `npv_build/wk_cli.py` (adapter exists; match its parameter names).

- [ ] **Step 4: Gate + commit**

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/gui_logic/clothing_catalog.py tests/gui_logic/test_clothing_catalog.py
git commit -m "feat(gui_logic): clothing catalog join, rig flags, cache"
```

---

### Task 3: Thumbnails

**Files:**
- Create: `npv_build/gui_logic/thumbs.py`
- Test: `tests/gui_logic/test_thumbs.py`

**Interfaces:**
- Produces: `thumbnail_b64(image_rel: str, images_dir: str | None, cache_dir: Path, size: int = 256) -> str | None` — None when `images_dir` is unset/missing/unreadable (text-only degradation); otherwise a base64 JPEG string, generated lazily into `cache_dir / "thumbs" / <sha16>.jpg` and reused on later calls.
- `image_rel` is clothes.json's `image` field (`/images/clothes/foo.jpg`) resolved against `images_dir`'s parent-of-`images` layout: try `<images_dir>/<basename>` first, then `<images_dir>/<image_rel lstrip '/'>`.

- [ ] **Step 1: Failing tests**

```python
# tests/gui_logic/test_thumbs.py
import base64

from PIL import Image

from npv_build.gui_logic.thumbs import thumbnail_b64


def _img(path, size=(512, 512)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "red").save(path, "JPEG")


def test_thumbnail_generated_cached_and_decodable(tmp_path):
    _img(tmp_path / "imgs" / "foo.jpg")
    out = thumbnail_b64("/images/clothes/foo.jpg", str(tmp_path / "imgs"),
                        tmp_path / "cache")
    assert out is not None
    raw = base64.b64decode(out)
    assert raw[:2] == b"\xff\xd8"  # JPEG magic
    thumbs = list((tmp_path / "cache" / "thumbs").iterdir())
    assert len(thumbs) == 1
    mtime = thumbs[0].stat().st_mtime_ns
    assert thumbnail_b64("/images/clothes/foo.jpg", str(tmp_path / "imgs"),
                         tmp_path / "cache") == out
    assert thumbs[0].stat().st_mtime_ns == mtime  # reused, not regenerated


def test_missing_dir_or_file_degrades_to_none(tmp_path):
    assert thumbnail_b64("/images/clothes/foo.jpg", None, tmp_path) is None
    assert thumbnail_b64("/images/clothes/foo.jpg", str(tmp_path / "nope"),
                         tmp_path) is None
    (tmp_path / "imgs").mkdir()
    assert thumbnail_b64("/images/clothes/ghost.jpg", str(tmp_path / "imgs"),
                         tmp_path) is None
```

- [ ] **Step 2: Run red, implement** (Pillow `Image.thumbnail((size, size))`, save JPEG quality=80, all I/O in try/except OSError → None), run green.

- [ ] **Step 3: Commit**

```bash
git add npv_build/gui_logic/thumbs.py tests/gui_logic/test_thumbs.py
git commit -m "feat(gui_logic): lazy clothing thumbnails with clean degradation"
```

---

### Task 4: Bridge — catalog build/search/thumbnail

**Files:**
- Modify: `npv_build/webui_api.py`
- Test: `tests/test_webui_api.py` (append)

**Interfaces:**
- `clothing_catalog_status() -> {"ok", "built": bool, "count": int}` (reads cache only).
- `build_clothing_catalog() -> {"ok"} | error` — runs `build_catalog_from_game` in the same background-worker pattern as `install_tools` (reuse a queue + `poll_tool_events`-style method `poll_catalog_events`), since enumeration takes WolvenKit minutes.
- `clothing_search(query: str, slot: str | None, rig: str, limit: int = 50) -> {"ok", "items": [...]}` — case-insensitive substring on `name`; `slot` filter; items carry `buildable` (the rig's flag) so the UI greys rather than hides; buildable-first ordering.
- `clothing_thumb(image_rel: str) -> {"ok", "b64": str | None}` — uses `settings.clothing_images_dir` and `get_cache_dir()`.

- [ ] **Step 1: Failing tests** (monkeypatch `load_catalog` with 3 entries covering: name match, slot filter, non-buildable greying, limit; `clothing_thumb` with monkeypatched `thumbnail_b64`). Follow the structural pattern of `test_cache_info_and_clear` / `test_install_tools_runs_worker_and_emits_events` already in the file.

```python
# append to tests/test_webui_api.py
CATALOG = [
    {"item_id": "A", "name": "RED SWEATER", "image": "/i/a.jpg",
     "slot": "inner_torso", "mesh": "m1", "buildable_pwa": True, "buildable_pma": False},
    {"item_id": "B", "name": "BLUE JEANS", "image": "/i/b.jpg",
     "slot": "legs", "mesh": "m2", "buildable_pwa": True, "buildable_pma": True},
    {"item_id": "C", "name": "GHOST HAT", "image": "/i/c.jpg",
     "slot": "head", "mesh": None, "buildable_pwa": False, "buildable_pma": False},
]


def test_clothing_search_filters_and_flags(monkeypatch):
    monkeypatch.setattr("npv_build.webui_api.load_clothing_catalog",
                        lambda: CATALOG)
    api = WebUiApi()
    out = api.clothing_search("sweater", None, "pma")
    assert [i["item_id"] for i in out["items"]] == ["A"]
    assert out["items"][0]["buildable"] is False  # pma flag
    out = api.clothing_search("", "legs", "pwa")
    assert [i["item_id"] for i in out["items"]] == ["B"]
    out = api.clothing_search("", None, "pwa")
    assert out["items"][0]["buildable"] is True  # buildable-first ordering
    assert out["items"][-1]["item_id"] == "C"


def test_clothing_catalog_status_unbuilt(monkeypatch):
    monkeypatch.setattr("npv_build.webui_api.load_clothing_catalog", lambda: None)
    out = WebUiApi().clothing_catalog_status()
    assert out == {"ok": True, "built": False, "count": 0}
```

- [ ] **Step 2: Run red, implement.** Module-level helper `load_clothing_catalog()` wraps `clothing_catalog.load_catalog(get_cache_dir() / "clothing_catalog.json")`. The background builder mirrors `install_tools` exactly (own queue, `poll_catalog_events`, `catalog_done`/`catalog_error` kinds).

- [ ] **Step 3: Gate + commit**

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/webui_api.py tests/test_webui_api.py
git commit -m "feat(webui): clothing catalog bridge (status/build/search/thumb)"
```

---

### Task 5: Picker UI in the inspector

**Files:**
- Modify: `npv_build/webui/js/appearance.js` (clothing rows + picker modal), `npv_build/webui/app.css`
- Modify: `npv_build/webui_api.py` (`start_build`: clothing overrides → `garments`)
- Modify: `tests/webui_smoke/mock_api.js`; Test: smoke append

**Interfaces:**
- Inspector gains a "Clothing" category with one row per slot (`inner_torso`, `outer_torso`, `legs`, `feet`) whose control is a `Browse…` button (`.browse-garment`), not a dropdown. Current value = fallback-outfit name or the picked item name.
- Picks store into the same overrides dict as plan 2 under slot ids `garment_inner_torso` etc., with the value being the item's `mesh` depot path (validated: only `buildable` items are clickable; grey items get `.disabled` + title "not available for NPCs").
- `set_overrides` (plan 2) accepts `garment_*` slots: extend plan 2's `EDITABLE_SLOTS` handling — `validate_overrides` treats `garment_*` as known slots; `apply_overrides` **ignores** them (they are not cc_settings edits). Instead, `start_build` splits them out: `garments = [v for k, v in overrides.items() if k.startswith("garment_")]` passed as `BuildRequest.garments` (existing, working mechanism), and only the remaining overrides go to `cc_overrides`.
- Picker modal contract for tests: `.picker` overlay with `#picker-search` input, `.picker-item` cells (img optional), `.picker-item.disabled` for non-buildable.

- [ ] **Step 1: Mock + failing smoke test**

```javascript
// mock_api.js additions
  clothing_catalog_status: async () => ({ ok: true, built: true, count: 2 }),
  clothing_search: async (q, slot, rig) => ({ ok: true, items: [
    { item_id: "A", name: "RED SWEATER", image: "/i/a.jpg", slot: "inner_torso",
      mesh: "base\\characters\\garment\\t1_024_pwa_tshirt__sweater.mesh", buildable: true },
    { item_id: "C", name: "GHOST HAT", image: "/i/c.jpg", slot: "inner_torso",
      mesh: null, buildable: false },
  ].filter(i => !q || i.name.toLowerCase().includes(q.toLowerCase())) }),
  clothing_thumb: async () => ({ ok: true, b64: null }),
```

```python
def test_clothing_picker_flow(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card.selectable").first.click()
        page.click("text=Continue →")
        row = page.locator(".irow", has_text="Inner torso")
        row.locator("button.browse-garment").click()
        expect(page.locator(".picker")).to_be_visible()
        expect(page.locator(".picker-item.disabled", has_text="GHOST HAT")
               ).to_be_visible()
        page.locator(".picker-item", has_text="RED SWEATER").click()
        expect(page.locator(".picker")).to_have_count(0)
        expect(row).to_have_class(re.compile("overridden"))
        expect(row).to_contain_text("RED SWEATER")
        browser.close()
```

- [ ] **Step 2: Run red, implement** the clothing rows (appended by `appearance.js` after the bridge rows, from a static slot list with labels via `display_names.json`: add `garment_inner_torso: "Inner torso"` etc.), the modal (single overlay div appended to `body`, closed on pick/Escape/backdrop), and the `start_build` garment split in `webui_api.py` with a unit test:

```python
def test_start_build_splits_garment_overrides(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    started = {}

    class FakeWorker:
        def __init__(self, q): pass
        def start(self, **kw): started.update(kw)

    monkeypatch.setattr("npv_build.webui_api.BuildWorker", FakeWorker)
    monkeypatch.setattr(
        "npv_build.webui_api.load_overrides",
        lambda p: {"skin_tone": "03_ca_medium",
                   "garment_inner_torso": "base\\g\\t1_x_pwa.mesh"})
    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True))
    WebUiApi().start_build({"save_path": "/s/sav.dat", "npv_name": "V",
                            "output_dir": str(tmp_path / "o")})
    assert started["garments"] == ["base\\g\\t1_x_pwa.mesh"]
    assert started["cc_overrides"] == {"skin_tone": "03_ca_medium"}
```

Also extend plan 2's `validate_overrides` to accept `garment_*` slot ids (one
added test in `tests/gui_logic/test_appearance.py`:
`validate_overrides({"garment_legs": "base\\..."}, {}) == []`).

- [ ] **Step 3: Catalog-not-built state:** the Browse button, when `clothing_catalog_status().built` is false, shows a small inline prompt with a "Build catalog" button wired to `build_clothing_catalog` + `poll_catalog_events` (same polling pattern as Settings' tool installer). Smoke-test just the prompt render with a `built: false` mock override via `add_init_script`.

- [ ] **Step 4: Gate + commit**

```bash
uv run pytest tests/webui_smoke/ -q && uv run ruff check . && uv run pytest -q
git add npv_build/webui/ npv_build/webui_api.py npv_build/data/display_names.json tests/
git commit -m "feat(webui): clothing Browse picker wired to garment overrides"
```

---

### Task 6: Live end-to-end verification (manual gate)

- [ ] Build the real catalog from the game install (`build_clothing_catalog` via the harness — memory note `gui-qa-harness`), record the real join coverage vs the spike's numbers.
- [ ] Pick a garment for a real save's NPV, build, install, verify in game the NPV wears it (user step).
- [ ] Set `clothing_images_dir` to `~/cyberpunk_mod_list/static/images/clothes`, confirm thumbnails render in the picker and `~/.cache/npv/thumbs/` populates lazily.

## Self-review notes

- Spec coverage: vendored clothes.json (T1), runtime catalog with per-rig flags + cache path (T2), thumbnails dir + lazy ~256px cache + clean degradation (T3), picker grid with search/slot filter/rig-buildable greying (T4/T5), picks → same override dict + validated buildability (T5), front-loaded spike (T1). Deviation from spec: mapping source may be the filename join rather than a TweakDB dump — forced by the CLI's missing `tweak` command; the spike measures and documents it.
- Names consistent: `clothing_catalog.json` cache, `garment_<slot>` override ids, `buildable` per-rig flag in search results.
