# Appearance Inspector with Overrides (GUI redesign plan 2/4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Appearance step's read-only summary with a two-pane inspector where hair style/color, eye color and skin tone are editable via dropdowns, overrides apply to a copy of `cc_settings` before resolve, persist per-save-file, and produce a distinct mod id.

**Architecture:** A pure module `npv_build/gui_logic/appearance.py` transforms `cc_settings` into inspector rows and applies overrides; a small `overrides_store.py` persists them under `~/.config/npv/overrides/`; `BuildRequest` gains `cc_overrides` applied right after the parse checkpoint (before the resolve hash, so checkpointing and mod-id derivation stay correct for free); the frontend renders rows with amber override badges, revert, and Reset all.

**Tech Stack:** Python 3.11+ (stdlib only in gui_logic), vanilla JS frontend, pytest + Playwright smoke.

**Spec:** `docs/superpowers/specs/2026-07-18-gui-redesign-webui-design.md` §"Step 2 — Appearance" + §"Appearance data & override model".

## Spec deviations (decided 2026-07-19, verified against a real 2.31 save)

1. **Face morphs are preset IDs, not floats.** Real `cc_settings["face_morphs"]` is `{"ear": "h035", "eyes": "h091", "jaw": "h114", "mouth": "h013", "nose": "h042"}` — there are no float morphs in the decoded save, so the spec's "sliders" cannot exist. v1 renders face morphs as **read-only rows** (lock + tooltip). Making them editable dropdowns is a data task (enumerate valid `hNNN` presets per region) deferred past this plan.
2. **"Dry-run resolve on Continue" is a fast local validation.** A real `resolve_assets` run takes ~2 minutes (WolvenKit archive scans, measured 2026-07-19). Continue instead validates each override against its known option list (instant, offline). A full `MappingResolutionError` at build time still names the offending slot; the Build screen shows it.
3. **Brows/beard/clothing dropdowns are out of scope here.** Brows/beard need selection-label mapping work (data task); clothing gets its own plan (`2026-07-19-clothing-catalog.md`, plan 4/4) which plugs into the row/override contract defined here.
4. **Added beyond the spec: modded hair (CCXL) input** (user request 2026-07-19). The Hair category gains a "Use hair mod file…" input: the user picks a CCXL hair mod file (`.archive`/`.zip`/`.7z`/`.rar`), it is installed into the game dir via the existing security-hardened `hair_mod_helper.install_hair_mod`, validated with `part_resolver.extract_hair_components`, and stored as a `hair_mod: <token>` override that `apply_overrides` maps onto `cc["hair"]` so the pipeline's existing CCXL-native branch attaches it. Full rationale + external format: `docs/research/2026-07-19-ccxl-hair-input.md`. Tasks 1 and 5a below carry it.

## Global Constraints

- No CDPR bytes in repo: mapping/display data are strings and option IDs only.
- Hard-fail policy: unknown override slots raise; never emit a half-applied build.
- Depot paths keep Windows backslashes (`base\characters\...`) on every platform.
- All bridge methods return JSON dicts; errors as `{"ok": False, "error", "remediation"}` — never raise into JS.
- `gui_logic/` stays display-free (unit-testable headless, no webview/pywebview imports).
- Lint gate: `uv run ruff check .` clean; suite gate: `uv run pytest -q` green after every task.

## Reference: verified shapes this plan builds on

`cc_settings` (from `parse_save`, real 2.31 save):

```python
{
  "patch": "2.31", "body_rig": "pwa",
  "selections": [{"slot": "character_customization", "prefix": "he", "index": 0,
                  "rig": "pwa", "group": "basehead", "variant": "11_gradient_blue",
                  "raw": "he_000_pwa__basehead__11_gradient_blue",
                  "cname_hash": 713..., "label": "eyes_color"}, ...],
  "head": {"preset_id": 0, "raw": "h0_000_pwa__basehead__01_ca_pale"},
  "eyes": {"raw": "he_000_pwa__basehead__11_gradient_blue"},
  "teeth": {"raw": "female_ht_000__basehead"},
  "skin": {"tone_id": "01_ca_pale"},
  "hair": {"style_id": "winona_2", "raw": "winona_2_hair"},
  "overlays": ["hx_000_pwa__cyberware_07__01_ca_pale", ...],
  "face_morphs": {"ear": "h035", "eyes": "h091", "jaw": "h114",
                  "mouth": "h013", "nose": "h042"},
}
```

Part index (`~/.cache/npv/index/2.13.json`, via `part_resolver.get_index_path(patch)`):
`{"part_ents": {name: ent_depot_path}, "head_apps": {...}, "app_appearances": {app_depot_path: [appearance_name, ...]}, "appearance_to_app": {...}}`

`BuildRequest` (`npv_build/core/pipeline.py:28`) — dataclass with `save_path`,
`npv_name`, `output_dir`, `game_dir`, `template_cache`, `clear_cache`,
`cc_json_path`, `hair_override`, `skin_override`, `garments`, `user_head_*`,
`restore_head_materials`, `resume`.

---

### Task 1: `gui_logic/appearance.py` — rows + apply_overrides + validate

**Files:**
- Create: `npv_build/gui_logic/appearance.py`
- Test: `tests/gui_logic/test_appearance.py`

**Interfaces:**
- Produces: `inspector_rows(cc_settings: dict, options: dict, display_names: dict) -> list[dict]`
  where each row is `{"category": str, "slot_id": str, "label": str, "value_label": str, "value_raw": str, "editable": bool, "options": list[str]}`.
- Produces: `apply_overrides(cc_settings: dict, overrides: dict) -> dict` (deep copy; unknown slot_id -> `ValueError`).
- Produces: `validate_overrides(overrides: dict, options: dict) -> list[str]` (problem strings; empty = valid).
- Produces: `EDITABLE_SLOTS = ("skin_tone", "hair_style", "hair_color", "eye_color")`.
- Special slot outside `EDITABLE_SLOTS`: `hair_mod` (CCXL hair token from `install_hair_mod`) — `apply_overrides` maps it to `cc["hair"] = {"style_id": token, "raw": token + "_hair"}` (wins over `hair_style`); `validate_overrides` accepts any non-empty token.
- Consumes: nothing from other tasks (pure stdlib).

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_appearance.py
import copy

import pytest

from npv_build.gui_logic.appearance import (
    EDITABLE_SLOTS,
    apply_overrides,
    inspector_rows,
    validate_overrides,
)


def _cc():
    return {
        "patch": "2.31", "body_rig": "pwa",
        "selections": [
            {"slot": "character_customization", "label": "eyes_color",
             "raw": "he_000_pwa__basehead__11_gradient_blue",
             "variant": "11_gradient_blue", "rig": "pwa", "group": "basehead",
             "prefix": "he", "index": 0, "cname_hash": 1},
            {"slot": "character_customization", "label": "winona_2_hair",
             "raw": "51_succulent", "variant": "", "rig": "", "group": "",
             "prefix": "", "index": 0, "cname_hash": 2},
        ],
        "head": {"preset_id": 0, "raw": "h0_000_pwa__basehead__01_ca_pale"},
        "eyes": {"raw": "he_000_pwa__basehead__11_gradient_blue"},
        "teeth": {"raw": "female_ht_000__basehead"},
        "skin": {"tone_id": "01_ca_pale"},
        "hair": {"style_id": "winona_2", "raw": "winona_2_hair"},
        "overlays": [],
        "face_morphs": {"ear": "h035", "eyes": "h091", "jaw": "h114",
                        "mouth": "h013", "nose": "h042"},
    }


OPTIONS = {
    "skin_tone": ["01_ca_pale", "02_ca_limestone", "03_ca_medium"],
    "hair_style": ["hh_040_pwa__morrigan", "hh_041_pwa__bob"],
    "hair_color": ["03_ginger_copper", "51_succulent", "06_black_carbon"],
    "eye_color": ["01_black", "11_gradient_blue", "21_green"],
}


def test_rows_cover_editable_and_readonly():
    rows = inspector_rows(_cc(), OPTIONS, {})
    by_id = {r["slot_id"]: r for r in rows}
    for slot in EDITABLE_SLOTS:
        assert by_id[slot]["editable"] is True
        assert by_id[slot]["options"]
    assert by_id["skin_tone"]["value_raw"] == "01_ca_pale"
    assert by_id["hair_style"]["value_raw"] == "winona_2"
    assert by_id["hair_color"]["value_raw"] == "51_succulent"
    assert by_id["eye_color"]["value_raw"] == "11_gradient_blue"
    # Read-only rows exist and are locked
    assert by_id["body_rig"]["editable"] is False
    assert by_id["face_morph_eyes"]["editable"] is False
    assert by_id["face_morph_eyes"]["value_raw"] == "h091"


def test_rows_editable_without_option_list_degrades_to_readonly():
    rows = inspector_rows(_cc(), {}, {})
    by_id = {r["slot_id"]: r for r in rows}
    assert by_id["hair_style"]["editable"] is False  # no options -> locked


def test_rows_use_display_names_with_raw_fallback():
    rows = inspector_rows(_cc(), OPTIONS, {"skin_tone": "Skin tone"})
    by_id = {r["slot_id"]: r for r in rows}
    assert by_id["skin_tone"]["label"] == "Skin tone"
    assert by_id["hair_color"]["label"] == "hair_color"  # fallback = slot_id


def test_apply_overrides_is_pure_and_targets_the_right_fields():
    cc = _cc()
    before = copy.deepcopy(cc)
    out = apply_overrides(cc, {
        "skin_tone": "03_ca_medium",
        "hair_style": "hh_041_pwa__bob",
        "hair_color": "06_black_carbon",
        "eye_color": "21_green",
    })
    assert cc == before  # input untouched
    assert out["skin"]["tone_id"] == "03_ca_medium"
    assert out["hair"]["style_id"] == "hh_041_pwa__bob"
    hair_sel = next(s for s in out["selections"] if s["label"].endswith("_hair"))
    assert hair_sel["raw"] == "06_black_carbon"
    assert out["eyes"]["raw"] == "he_000_pwa__basehead__21_green"
    eye_sel = next(s for s in out["selections"] if s["label"] == "eyes_color")
    assert eye_sel["raw"] == "he_000_pwa__basehead__21_green"
    assert eye_sel["variant"] == "21_green"


def test_apply_overrides_empty_is_identity_copy():
    cc = _cc()
    out = apply_overrides(cc, {})
    assert out == cc and out is not cc


def test_apply_overrides_unknown_slot_raises():
    with pytest.raises(ValueError):
        apply_overrides(_cc(), {"nose_shape": "x"})


def test_apply_overrides_hair_mod_emulates_ccxl_save():
    """hair_mod: <token> must reshape cc.hair exactly like a save that used
    that CCXL hair — mapping.resolve_assets' CCXL branch keys off
    hair.raw.endswith('_hair') + hair.style_id (see research note
    2026-07-19-ccxl-hair-input.md)."""
    out = apply_overrides(_cc(), {"hair_mod": "edie"})
    assert out["hair"] == {"style_id": "edie", "raw": "edie_hair"}


def test_apply_overrides_hair_mod_wins_over_hair_style():
    # UI keeps them mutually exclusive, but the transform must still be
    # deterministic if both arrive: hair_mod wins regardless of dict order.
    out = apply_overrides(_cc(), {"hair_style": "hh_041_pwa__bob",
                                  "hair_mod": "edie"})
    assert out["hair"] == {"style_id": "edie", "raw": "edie_hair"}


def test_validate_overrides_reports_bad_values():
    problems = validate_overrides({"skin_tone": "nope"}, OPTIONS)
    assert problems and "skin_tone" in problems[0]
    assert validate_overrides({"skin_tone": "03_ca_medium"}, OPTIONS) == []
    # Unknown slot is a problem, not a crash
    assert validate_overrides({"bogus": "x"}, OPTIONS)


def test_validate_overrides_hair_mod_token():
    # hair_mod has no options list — any non-empty token passes, empty fails.
    assert validate_overrides({"hair_mod": "edie"}, OPTIONS) == []
    assert validate_overrides({"hair_mod": ""}, OPTIONS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/gui_logic/test_appearance.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'npv_build.gui_logic.appearance'`

- [ ] **Step 3: Write the implementation**

```python
# npv_build/gui_logic/appearance.py
"""Pure cc_settings <-> inspector-row transforms (GUI redesign plan 2).

No I/O, no webview imports: everything here is unit-tested headless.
Row contract (consumed by webui/js/appearance.js and webui_api.appearance_data):
  {"category", "slot_id", "label", "value_label", "value_raw", "editable", "options"}
"""

from __future__ import annotations

import copy

EDITABLE_SLOTS = ("skin_tone", "hair_style", "hair_color", "eye_color")

_CATEGORIES = {
    "skin_tone": "Skin", "hair_style": "Hair", "hair_color": "Hair",
    "eye_color": "Eyes", "body_rig": "Body", "teeth": "Face",
}


def _hair_color_selection(cc: dict) -> dict | None:
    for s in cc.get("selections", []):
        lbl = (s.get("label") or "").lower()
        if (s.get("slot") in ("character_customization", "hairs")
                and "hair" in lbl and "fpp" not in lbl
                and s.get("raw", "") != "default"):
            return s
    return None


def _eye_variant(cc: dict) -> str:
    raw = (cc.get("eyes") or {}).get("raw", "")
    # "he_000_pwa__basehead__11_gradient_blue" -> "11_gradient_blue"
    return raw.split("__")[-1] if "__" in raw else raw


def _current_values(cc: dict) -> dict:
    hair_sel = _hair_color_selection(cc)
    return {
        "skin_tone": (cc.get("skin") or {}).get("tone_id", ""),
        "hair_style": (cc.get("hair") or {}).get("style_id", ""),
        "hair_color": hair_sel.get("raw", "") if hair_sel else "",
        "eye_color": _eye_variant(cc),
    }


def inspector_rows(cc_settings: dict, options: dict, display_names: dict) -> list[dict]:
    rows: list[dict] = []
    current = _current_values(cc_settings)

    def label_for(slot_id: str) -> str:
        return display_names.get(slot_id, slot_id)

    for slot_id in EDITABLE_SLOTS:
        opts = list(options.get(slot_id) or [])
        rows.append({
            "category": _CATEGORIES.get(slot_id, "Other"),
            "slot_id": slot_id,
            "label": label_for(slot_id),
            "value_label": current[slot_id],
            "value_raw": current[slot_id],
            "editable": bool(opts),
            "options": opts,
        })

    def readonly(slot_id: str, category: str, value: str) -> dict:
        return {"category": category, "slot_id": slot_id,
                "label": label_for(slot_id), "value_label": value,
                "value_raw": value, "editable": False, "options": []}

    rows.append(readonly("body_rig", "Body", cc_settings.get("body_rig", "")))
    rows.append(readonly("teeth", "Face", (cc_settings.get("teeth") or {}).get("raw", "")))
    for region, preset in sorted((cc_settings.get("face_morphs") or {}).items()):
        rows.append(readonly(f"face_morph_{region}", "Face morphs", preset))
    return rows


def apply_overrides(cc_settings: dict, overrides: dict) -> dict:
    """Return a deep copy of cc_settings with overrides applied.

    Raises ValueError on unknown slot ids — the pipeline hard-fails rather
    than silently building without a requested change.
    """
    out = copy.deepcopy(cc_settings)
    for slot_id, value in overrides.items():
        if slot_id == "skin_tone":
            out.setdefault("skin", {})["tone_id"] = value
        elif slot_id == "hair_style":
            out.setdefault("hair", {})["style_id"] = value
        elif slot_id == "hair_color":
            sel = _hair_color_selection(out)
            if sel is not None:
                sel["raw"] = value
        elif slot_id == "eye_color":
            rig = out.get("body_rig", "pwa")
            raw = f"he_000_{rig}__basehead__{value}"
            out.setdefault("eyes", {})["raw"] = raw
            for s in out.get("selections", []):
                if s.get("label") == "eyes_color":
                    s["raw"] = raw
                    s["variant"] = value
        elif slot_id == "hair_mod":
            pass  # applied last, below — must win over hair_style
        else:
            raise ValueError(f"Unknown override slot: {slot_id}")
    if "hair_mod" in overrides:
        # Emulate a save that used this CCXL hair: mapping.resolve_assets'
        # CCXL branch (hair.raw endswith '_hair' + style_id token) then finds
        # the installed mod via extract_hair_components. Applied after the
        # loop so it wins over a simultaneous hair_style regardless of order.
        token = overrides["hair_mod"]
        out["hair"] = {"style_id": token, "raw": f"{token}_hair"}
    return out


def validate_overrides(overrides: dict, options: dict) -> list[str]:
    """Fast, offline check of override values against known option lists.
    Stands in for the spec's 'dry-run resolve' (full resolve takes minutes)."""
    problems = []
    for slot_id, value in overrides.items():
        if slot_id == "hair_mod":
            # Token from install_hair_mod; no option list. The real
            # existence check happened at add time (add_hair_mod probe).
            if not value:
                problems.append("hair_mod: empty hair mod token")
            continue
        opts = options.get(slot_id)
        if slot_id not in EDITABLE_SLOTS:
            problems.append(f"Unknown override slot: {slot_id}")
        elif opts and value not in opts:
            problems.append(f"{slot_id}: '{value}' is not a known option")
    return problems
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/gui_logic/test_appearance.py -q`
Expected: 10 passed

- [ ] **Step 5: Lint + full suite, then commit**

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/gui_logic/appearance.py tests/gui_logic/test_appearance.py
git commit -m "feat(gui_logic): appearance inspector rows + override transforms"
```

---

### Task 2: Option lists from the part-resolver index

**Files:**
- Modify: `npv_build/gui_logic/appearance.py` (append)
- Test: `tests/gui_logic/test_appearance.py` (append)

**Interfaces:**
- Produces: `option_lists(index: dict, body_rig: str) -> dict[str, list[str]]` returning the `options` dict Task 1 consumes. Empty dict when `index` is `None`/empty (rows degrade to read-only — Task 1 already handles that).
- Consumes: the part index shape `{"part_ents": {name: path}, "app_appearances": {app_path: [names]}}`.

Derivation rules (verified against the real 2.13/2.31 index on 2026-07-19):
- `hair_style`: keys of `part_ents` matching `^hh_\d+_{rig}__` and not ending `_fpp` — these are vanilla hair part names.
- `eye_color`: appearance names of the `he_000_{rig}__basehead` app — find the app path in `app_appearances` whose basename starts `he_000_{rig}__basehead`; option = the `__`-suffix of each appearance name (e.g. `he_000_pwa__basehead__11_gradient_blue` → `11_gradient_blue`).
- `skin_tone`: same rule against `h0_000_{rig}__basehead` appearance names (suffixes like `01_ca_pale`).
- `hair_color`: appearance names of any `hh_*_{rig}` app, deduplicated, stripped of `^\d+_` is NOT applied (keep raw names like `03_ginger_copper` — that is what the selection raw stores).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/gui_logic/test_appearance.py
from npv_build.gui_logic.appearance import option_lists

INDEX = {
    "part_ents": {
        "hh_040_pwa__morrigan": "base\\...\\hh_040_pwa__morrigan.ent",
        "hh_041_pwa__bob": "base\\...\\hh_041_pwa__bob.ent",
        "hh_044_pma__hairs_140": "base\\...\\hh_044_pma__hairs_140.ent",
        "hh_044_pma__hairs_140_fpp": "base\\...\\hh_044_pma__hairs_140_fpp.ent",
        "hx_000_pwa__tattoo_09": "base\\...\\hx_000_pwa__tattoo_09.ent",
    },
    "app_appearances": {
        "base\\x\\he_000_pwa__basehead.app": [
            "he_000_pwa__basehead__01_black", "he_000_pwa__basehead__11_gradient_blue"],
        "base\\x\\h0_000_pwa__basehead.app": [
            "h0_000_pwa__basehead__01_ca_pale", "h0_000_pwa__basehead__03_ca_medium"],
        "base\\x\\hh_040_pwa.app": ["03_ginger_copper", "51_succulent"],
    },
}


def test_option_lists_derivation():
    opts = option_lists(INDEX, "pwa")
    assert opts["hair_style"] == ["hh_040_pwa__morrigan", "hh_041_pwa__bob"]
    assert opts["eye_color"] == ["01_black", "11_gradient_blue"]
    assert opts["skin_tone"] == ["01_ca_pale", "03_ca_medium"]
    assert opts["hair_color"] == ["03_ginger_copper", "51_succulent"]


def test_option_lists_other_rig_and_empty_index():
    opts = option_lists(INDEX, "pma")
    assert opts["hair_style"] == ["hh_044_pma__hairs_140"]  # no _fpp
    assert option_lists({}, "pwa") == {}
    assert option_lists(None, "pwa") == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/gui_logic/test_appearance.py -q`
Expected: FAIL — `ImportError: cannot import name 'option_lists'`

- [ ] **Step 3: Implement**

```python
# append to npv_build/gui_logic/appearance.py
import re


def option_lists(index: dict | None, body_rig: str) -> dict[str, list[str]]:
    """Derive per-slot option lists from the part-resolver index.
    Returns {} when the index is unavailable (rows then render read-only)."""
    if not index:
        return {}
    part_ents = index.get("part_ents", {})
    app_appearances = index.get("app_appearances", {})

    hair_re = re.compile(rf"^hh_\d+_{body_rig}__")
    hair_style = sorted(
        n for n in part_ents if hair_re.match(n) and not n.endswith("_fpp")
    )

    def app_suffixes(app_prefix: str) -> list[str]:
        for app_path, names in app_appearances.items():
            base = app_path.replace("\\", "/").rsplit("/", 1)[-1]
            if base.startswith(app_prefix):
                return sorted({n.split("__")[-1] for n in names if "__" in n})
        return []

    hair_color: set[str] = set()
    hair_app_re = re.compile(rf"^hh_\d+_{body_rig}\b")
    for app_path, names in app_appearances.items():
        base = app_path.replace("\\", "/").rsplit("/", 1)[-1]
        if hair_app_re.match(base):
            hair_color.update(n for n in names if "__" not in n)

    out = {
        "hair_style": hair_style,
        "eye_color": app_suffixes(f"he_000_{body_rig}__basehead"),
        "skin_tone": app_suffixes(f"h0_000_{body_rig}__basehead"),
        "hair_color": sorted(hair_color),
    }
    return {k: v for k, v in out.items() if v}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/gui_logic/test_appearance.py -q`
Expected: 12 passed

- [ ] **Step 5: Sanity-check against the real index, then commit**

Run: `uv run python -c "import json; from npv_build.gui_logic.appearance import option_lists; from npv_build.part_resolver import get_index_path; idx=json.load(open(get_index_path('2.13'))); o=option_lists(idx,'pwa'); print({k: len(v) for k,v in o.items()})"`
Expected: non-zero counts for at least hair_style, eye_color, skin_tone (machine with a built index only; skip on CI).

```bash
git add npv_build/gui_logic/appearance.py tests/gui_logic/test_appearance.py
git commit -m "feat(gui_logic): derive inspector option lists from part index"
```

---

### Task 3: Overrides through the pipeline (`BuildRequest.cc_overrides`)

**Files:**
- Modify: `npv_build/core/pipeline.py` (BuildRequest at line ~28; build() parse stage at line ~178)
- Test: `tests/core/test_pipeline_overrides.py` (create; `tests/core/` already exists)

**Interfaces:**
- Produces: `BuildRequest.cc_overrides: dict = field(default_factory=dict)`.
- Behavior: after the parse checkpoint resolves (fresh or resumed), `cc_settings = apply_overrides(cc_settings, req.cc_overrides)` when overrides are non-empty. The parse checkpoint stores the UN-overridden output (so changing overrides later still resumes parse); the resolve hash already includes `cc_settings`, so overridden builds re-resolve, and `compute_mod_id(npv_name, cc_settings)` sees the overridden dict → distinct mod ids for free.
- Consumes: `apply_overrides` from Task 1.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_pipeline_overrides.py
"""cc_overrides apply after the parse checkpoint and change the mod id."""
import pytest

from npv_build.core.pipeline import BuildRequest, PipelineService


def _req(tmp_path, overrides):
    return BuildRequest(
        save_path=tmp_path / "sav.dat", npv_name="V", output_dir=tmp_path / "o",
        game_dir=tmp_path, template_cache=tmp_path / "tc",
        cc_overrides=overrides,
    )


def test_overrides_reach_resolve_and_mod_id(monkeypatch, tmp_path, synth_save_2310):
    seen = {}

    def fake_resolve(cc, game_dir, hair_override, garments, wk):
        seen["cc"] = cc
        raise RuntimeError("stop after resolve")  # don't run the real assemble

    monkeypatch.setattr("npv_build.core.pipeline.resolve_assets", fake_resolve)
    req = _req(tmp_path, {"skin_tone": "03_ca_medium"})
    req.save_path = synth_save_2310
    with pytest.raises(RuntimeError):
        PipelineService().build(req)
    assert seen["cc"]["skin"]["tone_id"] == "03_ca_medium"


def test_parse_checkpoint_stores_unmodified_cc(monkeypatch, tmp_path, synth_save_2310):
    import json

    def fake_resolve(cc, *a, **k):
        raise RuntimeError("stop")

    monkeypatch.setattr("npv_build.core.pipeline.resolve_assets", fake_resolve)
    req = _req(tmp_path, {"skin_tone": "03_ca_medium"})
    req.save_path = synth_save_2310
    with pytest.raises(RuntimeError):
        PipelineService().build(req)
    manifest = json.loads((req.output_dir / ".npv_manifest.json").read_text())
    stored = manifest["parse_save"]["output"]
    assert stored["skin"]["tone_id"] != "03_ca_medium"  # checkpoint = raw parse


def test_unknown_override_slot_fails_the_build(tmp_path, synth_save_2310):
    req = _req(tmp_path, {"bogus_slot": "x"})
    req.save_path = synth_save_2310
    with pytest.raises(ValueError):
        PipelineService().build(req)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_pipeline_overrides.py -q`
Expected: FAIL with `TypeError: BuildRequest.__init__() got an unexpected keyword argument 'cc_overrides'`

- [ ] **Step 3: Implement**

In `npv_build/core/pipeline.py`, add the field after `garments`:

```python
    garments: list[str] = field(default_factory=list)
    cc_overrides: dict = field(default_factory=dict)
```

Add the import at the top with the other project imports:

```python
from ..gui_logic.appearance import apply_overrides
```

In `build()`, immediately after the parse checkpoint block (after the
`else:` branch writes the manifest, right before `wk = _make_wolvenkit(...)`):

```python
            # Apply GUI overrides to a copy; the checkpoint above stored the
            # raw parse so a later overrides change still resumes parse_save.
            if req.cc_overrides:
                cc_settings = apply_overrides(cc_settings, req.cc_overrides)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_pipeline_overrides.py tests/gui_logic/test_appearance.py -q`
Expected: all pass. (If `gui_logic.appearance` importing from `core` creates a
cycle, it will surface here — `appearance.py` imports only stdlib, so it must not.)

- [ ] **Step 5: Full gate + commit**

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/core/pipeline.py tests/core/test_pipeline_overrides.py
git commit -m "feat(pipeline): BuildRequest.cc_overrides applied after parse checkpoint"
```

---

### Task 4: Per-save overrides persistence

**Files:**
- Create: `npv_build/gui_logic/overrides_store.py`
- Test: `tests/gui_logic/test_overrides_store.py`

**Interfaces:**
- Produces: `load_overrides(save_path: str) -> dict`, `save_overrides(save_path: str, overrides: dict) -> None` (empty dict deletes the file), `store_path(save_path: str) -> Path`.
- Storage: `~/.config/npv/overrides/<sha256(save_path)[:16]>.json` — derived from `npv_build.config.load_config`'s parent dir. Uses `config.get_config_dir()` if it exists; otherwise reuse `Path(load_config.__wrapped__...)` — **verify before use:** check `npv_build/config.py` for the config-dir helper name; if only `load_config`/`save_config` exist, add `get_config_dir()` there returning the directory `config.toml` lives in.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_overrides_store.py
from npv_build.gui_logic import overrides_store


def test_roundtrip_and_delete(monkeypatch, tmp_path):
    monkeypatch.setattr(overrides_store, "_overrides_dir", lambda: tmp_path)
    overrides_store.save_overrides("/saves/a/sav.dat", {"skin_tone": "03_ca_medium"})
    assert overrides_store.load_overrides("/saves/a/sav.dat") == {
        "skin_tone": "03_ca_medium"}
    # distinct saves don't collide
    assert overrides_store.load_overrides("/saves/b/sav.dat") == {}
    # empty dict removes the file
    overrides_store.save_overrides("/saves/a/sav.dat", {})
    assert overrides_store.load_overrides("/saves/a/sav.dat") == {}
    assert list(tmp_path.iterdir()) == []


def test_corrupt_file_reads_as_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(overrides_store, "_overrides_dir", lambda: tmp_path)
    p = overrides_store.store_path("/saves/a/sav.dat")
    p.write_text("{not json")
    assert overrides_store.load_overrides("/saves/a/sav.dat") == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/gui_logic/test_overrides_store.py -q`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# npv_build/gui_logic/overrides_store.py
"""Per-save-file appearance overrides (spec: 'Overrides persist per-save-file
in config'). One JSON file per save under <config>/overrides/."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _overrides_dir() -> Path:
    from ..config import get_config_dir  # verified/added alongside this module

    return Path(get_config_dir()) / "overrides"


def store_path(save_path: str) -> Path:
    digest = hashlib.sha256(str(save_path).encode("utf-8")).hexdigest()[:16]
    return _overrides_dir() / f"{digest}.json"


def load_overrides(save_path: str) -> dict:
    try:
        data = json.loads(store_path(save_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_overrides(save_path: str, overrides: dict) -> None:
    p = store_path(save_path)
    if not overrides:
        p.unlink(missing_ok=True)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(overrides, indent=2, sort_keys=True), encoding="utf-8")
```

If `npv_build/config.py` has no `get_config_dir()`, add one next to `load_config`
(returning the same directory `config.toml` is read from) with a one-line test in
`tests/` mirroring how `get_cache_dir` is tested.

- [ ] **Step 4: Run tests, full gate, commit**

```bash
uv run pytest tests/gui_logic/test_overrides_store.py -q   # expect 2 passed
uv run ruff check . && uv run pytest -q
git add npv_build/gui_logic/overrides_store.py tests/gui_logic/test_overrides_store.py npv_build/config.py
git commit -m "feat(gui_logic): per-save overrides store"
```

---

### Task 5: Bridge — appearance_data / set_overrides / validate, wired into start_build

**Files:**
- Modify: `npv_build/webui_api.py`
- Test: `tests/test_webui_api.py` (append)

**Interfaces:**
- Produces bridge methods (all JSON-safe):
  - `appearance_data(save_path: str) -> {"ok", "rows", "overrides", "categories"}` — parses the save via `preview`-style guarded call, loads the part index from `part_resolver.get_index_path(cc["patch"])` when the file exists (else `{}` options), loads vendored `data/display_names.json`, returns `inspector_rows` + stored overrides + ordered category list.
  - `set_overrides(save_path: str, overrides: dict) -> {"ok"} | error` — validates with `validate_overrides` first; persists via `save_overrides`.
  - `get_overrides(save_path: str) -> {"ok", "overrides"}`.
- Modifies: `start_build` passes `cc_overrides=load_overrides(req["save_path"])` into `BuildWorker.start(...)` kwargs (BuildWorker passes kwargs straight into `BuildRequest`, verified at `gui_backend.py:90`).
- Consumes: Tasks 1, 2, 4.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_webui_api.py
def test_appearance_data_rows_and_overrides(monkeypatch, tmp_path):
    cc = {
        "patch": "2.31", "body_rig": "pwa", "selections": [],
        "head": {}, "eyes": {"raw": "he_000_pwa__basehead__11_gradient_blue"},
        "teeth": {"raw": ""}, "skin": {"tone_id": "01_ca_pale"},
        "hair": {"style_id": "winona_2", "raw": ""}, "overlays": [],
        "face_morphs": {"eyes": "h091"},
    }
    monkeypatch.setattr("npv_build.webui_api.parse_save_for_inspector", lambda p: cc)
    monkeypatch.setattr("npv_build.webui_api.load_part_index", lambda patch: {})
    monkeypatch.setattr("npv_build.webui_api.load_overrides",
                        lambda p: {"skin_tone": "03_ca_medium"})
    out = WebUiApi().appearance_data("/s/sav.dat")
    assert out["ok"] is True
    ids = [r["slot_id"] for r in out["rows"]]
    assert "skin_tone" in ids and "face_morph_eyes" in ids
    assert out["overrides"] == {"skin_tone": "03_ca_medium"}


def test_set_overrides_validates_and_persists(monkeypatch):
    saved = {}
    monkeypatch.setattr("npv_build.webui_api.save_overrides",
                        lambda p, o: saved.update({p: o}))
    monkeypatch.setattr("npv_build.webui_api.load_part_index", lambda patch: {})
    monkeypatch.setattr("npv_build.webui_api.parse_save_for_inspector",
                        lambda p: {"patch": "2.31", "body_rig": "pwa"})
    api = WebUiApi()
    # no option list available -> value accepted (validated at build)
    assert api.set_overrides("/s/sav.dat", {"skin_tone": "x"}) == {"ok": True}
    assert saved["/s/sav.dat"] == {"skin_tone": "x"}
    # unknown slot always rejected
    out = api.set_overrides("/s/sav.dat", {"bogus": "x"})
    assert out["ok"] is False and "bogus" in out["error"]


def test_start_build_passes_stored_overrides(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    started = {}

    class FakeWorker:
        def __init__(self, q): pass
        def start(self, **kwargs): started.update(kwargs)

    monkeypatch.setattr("npv_build.webui_api.BuildWorker", FakeWorker)
    monkeypatch.setattr("npv_build.webui_api.load_overrides",
                        lambda p: {"skin_tone": "03_ca_medium"})
    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    WebUiApi().start_build({"save_path": "/s/sav.dat", "npv_name": "V",
                            "output_dir": str(tmp_path / "o")})
    assert started["cc_overrides"] == {"skin_tone": "03_ca_medium"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_webui_api.py -q`
Expected: FAIL — missing names `parse_save_for_inspector`, `appearance_data`, ...

- [ ] **Step 3: Implement in `webui_api.py`**

Add imports:

```python
from .gui_logic.appearance import inspector_rows, option_lists, validate_overrides
from .gui_logic.overrides_store import load_overrides, save_overrides
from .save_parser import parse_save as parse_save_for_inspector
```

Add module-level helpers + methods on `WebUiApi`:

```python
def load_part_index(patch: str) -> dict:
    """Cached part index for this patch, or {} when it was never generated.
    Never generates it here — index generation needs WolvenKit and minutes."""
    import json

    from .part_resolver import get_index_path

    try:
        return json.loads(get_index_path(patch).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _display_names() -> dict:
    import json

    p = Path(__file__).parent / "data" / "display_names.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
```

```python
    def appearance_data(self, save_path: str) -> dict:
        try:
            cc = parse_save_for_inspector(Path(save_path))
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False, "error": str(e), "remediation": ""}
        options = option_lists(load_part_index(cc.get("patch", "")),
                               cc.get("body_rig", "pwa"))
        rows = inspector_rows(cc, options, _display_names())
        categories = list(dict.fromkeys(r["category"] for r in rows))
        return {"ok": True, "rows": rows, "categories": categories,
                "overrides": load_overrides(save_path)}

    def get_overrides(self, save_path: str) -> dict:
        return {"ok": True, "overrides": load_overrides(save_path)}

    def set_overrides(self, save_path: str, overrides: dict) -> dict:
        try:
            cc = parse_save_for_inspector(Path(save_path))
            options = option_lists(load_part_index(cc.get("patch", "")),
                                   cc.get("body_rig", "pwa"))
        except Exception:  # noqa: BLE001 - index/parse problems fall back to slot-only checks
            options = {}
        problems = validate_overrides(overrides, options)
        if problems:
            return {"ok": False, "error": "; ".join(problems),
                    "remediation": "Pick values from the dropdowns."}
        save_overrides(save_path, overrides)
        return {"ok": True}
```

In `start_build`, extend the worker kwargs:

```python
        self._worker.start(
            save_path=Path(req["save_path"]),
            npv_name=req["npv_name"],
            output_dir=Path(req["output_dir"]),
            game_dir=Path(s.game_dir),
            template_cache=get_cache_dir() / "templates",
            clear_cache=bool(req.get("clear_cache", False)),
            resume=bool(req.get("resume", False)),
            cc_overrides=load_overrides(req["save_path"]),
        )
```

**Verify before use:** `gui_backend._request_kwargs` filters kwargs into
`BuildRequest` fields — confirm it passes `cc_overrides` through (it filters by
`BuildRequest.__dataclass_fields__`; Task 3 added the field, so it will).
Also create the vendored data file with just the slots this plan ships:

```json
// npv_build/data/display_names.json
{
  "skin_tone": "Skin tone",
  "hair_style": "Hair style",
  "hair_color": "Hair color",
  "eye_color": "Eye color",
  "body_rig": "Body rig",
  "teeth": "Teeth",
  "face_morph_ear": "Ears (morph preset)",
  "face_morph_eyes": "Eyes (morph preset)",
  "face_morph_jaw": "Jaw (morph preset)",
  "face_morph_mouth": "Mouth (morph preset)",
  "face_morph_nose": "Nose (morph preset)"
}
```

- [ ] **Step 4: Run tests + full gate**

Run: `uv run pytest tests/test_webui_api.py -q` → all pass; `uv run ruff check . && uv run pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add npv_build/webui_api.py npv_build/data/display_names.json tests/test_webui_api.py
git commit -m "feat(webui): appearance inspector bridge + overrides in start_build"
```

---

### Task 5a: Modded hair (CCXL) — bridge install + probe

**Files:**
- Modify: `npv_build/webui_api.py`
- Test: `tests/test_webui_api.py` (append)

**Interfaces:**
- Produces: `add_hair_mod(path: str) -> {"ok", "token", "source", "warning"} | {"ok": False, "error", "remediation"}` — installs the mod file into the game dir and validates it contains a findable hair `.app`.
- Produces: `browse_for_hair_mod() -> same` — native file dialog (`.archive`/`.zip`/`.7z`/`.rar` filter), mirrors `browse_for_save`'s structure exactly (webview probe, `cancelled` key).
- Consumes: `hair_mod_helper.install_hair_mod(source_path, game_dir)` (existing: returns `(token, installed_paths)`, raises `ValueError`/`InstallError`/`SecurityError`), `part_resolver.extract_hair_components(game_dir, token, body_rig, wk=)` (existing: returns `(comps, src_archive, app_depot, app_name)`; `app_depot is None` = no hair `.app` found), `wk_cli.WolvenKit`/`WolvenKitConfig` for the probe adapter.
- Contract: the probe runs on the freshly installed mod only (extract_hair_components pre-filters candidate archives by filename tokens and `.xl` sidecar content — verified `part_resolver.py:491`, ~one 6s listing). `app_depot` found → ok with `source` = archive name; not found → the installed files are **left in place** (harmless, standard mod install) but the method returns a structured error so no override is stored.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_webui_api.py
def test_add_hair_mod_installs_probes_and_returns_token(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.install_hair_mod",
                        lambda src, gd: ("edie", [tmp_path / "edie_hair.archive"]))
    monkeypatch.setattr(
        "npv_build.webui_api.extract_hair_components",
        lambda gd, token, rig, verbosity=0, wk=None:
            ([{"name": "c"}], "edie_hair.archive", "base\\x\\edie.app", "edie"),
    )
    out = WebUiApi().add_hair_mod(str(tmp_path / "edie_hair.zip"))
    assert out["ok"] is True
    assert out["token"] == "edie"
    assert out["source"] == "edie_hair.archive"


def test_add_hair_mod_no_hair_app_is_structured_error(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.install_hair_mod",
                        lambda src, gd: ("notahair", []))
    monkeypatch.setattr(
        "npv_build.webui_api.extract_hair_components",
        lambda gd, token, rig, verbosity=0, wk=None: ([], None, None, None),
    )
    out = WebUiApi().add_hair_mod(str(tmp_path / "notahair.zip"))
    assert out["ok"] is False
    assert "hair" in out["error"].lower()
    assert out["remediation"]


def test_add_hair_mod_without_game_dir_is_structured(monkeypatch):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    out = WebUiApi().add_hair_mod("/x/hair.zip")
    assert out["ok"] is False and "Game directory" in out["error"]


def test_add_hair_mod_bad_package_is_structured(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )

    def boom(src, gd):
        raise ValueError("No .archive file found inside the mod package.")

    monkeypatch.setattr("npv_build.webui_api.install_hair_mod", boom)
    out = WebUiApi().add_hair_mod(str(tmp_path / "empty.zip"))
    assert out["ok"] is False and "No .archive" in out["error"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_webui_api.py -q`
Expected: FAIL — `AttributeError: ... no attribute 'add_hair_mod'` (and missing imports)

- [ ] **Step 3: Implement in `webui_api.py`**

Imports:

```python
from .hair_mod_helper import install_hair_mod
from .part_resolver import extract_hair_components
from .wk_cli import WolvenKit, WolvenKitConfig
```

Methods:

```python
    def add_hair_mod(self, path: str) -> dict:
        """Install a CCXL/hair mod file into the game and return its token.

        The mod is a runtime dependency of the built NPV (the .app is attached
        by appearance reference), so installing into the game dir here is the
        end state, not a side effect."""
        s = load_settings()
        if not s.game_dir:
            return {"ok": False, "error": "Game directory not configured.",
                    "remediation": "Set it in Settings."}
        game_dir = Path(s.game_dir)
        try:
            token, _installed = install_hair_mod(Path(path), game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        except (ValueError, OSError) as e:
            return {"ok": False, "error": str(e),
                    "remediation": "Pick a hair mod file: .archive, .zip, .7z or .rar."}
        # Probe: does the installed mod actually carry a findable hair .app?
        # extract_hair_components pre-filters candidates by filename/.xl
        # sidecar, so this lists ~1 archive, not the whole mod dir.
        try:
            wk = WolvenKit(WolvenKitConfig(game_dir=game_dir, verbosity=0))
            _comps, src, app_depot, _app_name = extract_hair_components(
                game_dir, token, "pwa", verbosity=0, wk=wk)
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            logger.exception("hair mod probe failed")
            return {"ok": False, "error": f"Could not inspect the hair mod: {e}",
                    "remediation": "Check the file and try again."}
        if not app_depot:
            return {"ok": False,
                    "error": f"No hair appearance found in '{Path(path).name}'.",
                    "remediation": "This does not look like a CCXL/hair mod — "
                                   "pick the mod's main .archive (or its zip/7z/rar)."}
        return {"ok": True, "token": token, "source": src or "",
                "warning": "The NPV needs this hair mod to stay installed."}

    def browse_for_hair_mod(self) -> dict:
        try:
            import webview

            if not webview.windows:
                raise RuntimeError("no webview window")
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Hair mod (*.archive;*.zip;*.7z;*.rar)",
                            "All files (*.*)"),
            )
        except Exception as e:  # noqa: BLE001 - bridge boundary must not raise into JS
            return {"ok": False,
                    "error": "File dialog is unavailable outside the desktop app.",
                    "remediation": "Drag & drop the mod file instead.",
                    "details": str(e)}
        if not result:
            return {"ok": False, "cancelled": True, "error": ""}
        return self.add_hair_mod(result[0])
```

**Verify before use:** `WolvenKitConfig` field names (`game_dir`, `verbosity` —
confirmed frozen dataclass in `wk_cli.py`; adjust `cli_binary` default handling
if the constructor requires it). The probe's `body_rig` is hardcoded `"pwa"`
only for candidate filtering — `extract_hair_components` uses it to prefer
`fhair_`/`mhair_`; passing the real rig from the loaded save is better: accept
an optional `body_rig: str = "pwa"` parameter on `add_hair_mod` and have the
frontend pass `s.save.preview.body_rig`.

- [ ] **Step 4: Run tests + full gate**

`uv run pytest tests/test_webui_api.py -q` → all pass; `uv run ruff check . && uv run pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add npv_build/webui_api.py tests/test_webui_api.py
git commit -m "feat(webui): add_hair_mod bridge — install + probe CCXL hair mods"
```

---

### Task 6: Inspector frontend (two-pane, search, badges, revert, reset)

**Files:**
- Modify: `npv_build/webui/js/appearance.js` (replace summary card with inspector; keep the NPV name / output dir form + validation added 2026-07-19)
- Modify: `npv_build/webui/app.css` (inspector styles)
- Modify: `tests/webui_smoke/mock_api.js` (add `appearance_data`, `set_overrides` mocks)
- Test: `tests/webui_smoke/test_webui_smoke.py` (append)

**Interfaces:**
- Consumes: `appearance_data(save_path)` / `set_overrides(save_path, overrides)` from Task 5, row contract from Task 1.
- UI contract for tests: left pane `.inspector-cats` (one `.cat` per category with count + `.badge.override-count` when overridden), right pane `.inspector-rows` with one `.irow` per row; editable rows contain a `<select>`; overridden rows get class `overridden` and a `button.revert`; header has `#inspector-search` input and a `#reset-all` button; validation errors from `set_overrides` render in `.form-error`.
- Modded hair row (consumes Task 5a): the frontend appends one extra `.irow.hair-mod-row` to the Hair category (not produced by `inspector_rows` — same pattern plan 4 uses for clothing rows): label "Modded hair", value = current `hair_mod` token or "—", a `button.browse-hair-mod` ("Use hair mod file…") calling `browse_for_hair_mod` (and `add_hair_mod` on drag-drop of a file, mirroring Source's drop handler). On `ok`: set `this._overrides.hair_mod = out.token` and **delete `this._overrides.hair_style`** (mutually exclusive — and choosing a `hair_style` from the dropdown deletes `hair_mod`); render `out.warning` as a `.muted` note under the row. On error: render in `.form-error`. The row participates in overridden/revert/reset like every other row.

- [ ] **Step 1: Extend the mock**

```javascript
// append to tests/webui_smoke/mock_api.js (inside window.__mockApi)
  appearance_data: async () => ({
    ok: true,
    categories: ["Skin", "Hair", "Eyes", "Body", "Face morphs"],
    overrides: {},
    rows: [
      { category: "Skin", slot_id: "skin_tone", label: "Skin tone",
        value_label: "01_ca_pale", value_raw: "01_ca_pale", editable: true,
        options: ["01_ca_pale", "03_ca_medium"] },
      { category: "Hair", slot_id: "hair_style", label: "Hair style",
        value_label: "winona_2", value_raw: "winona_2", editable: true,
        options: ["winona_2", "hh_041_pwa__bob"] },
      { category: "Hair", slot_id: "hair_color", label: "Hair color",
        value_label: "51_succulent", value_raw: "51_succulent", editable: true,
        options: ["51_succulent", "06_black_carbon"] },
      { category: "Face morphs", slot_id: "face_morph_eyes",
        label: "Eyes (morph preset)", value_label: "h091", value_raw: "h091",
        editable: false, options: [] },
    ],
  }),
  _overrides: {},
  set_overrides: async function (path, overrides) {
    if (overrides.skin_tone === "reject_me")
      return { ok: false, error: "skin_tone: not a known option", remediation: "" };
    this._overrides = overrides;
    return { ok: true };
  },
  browse_for_hair_mod: async () => ({
    ok: true, token: "edie", source: "edie_hair.archive",
    warning: "The NPV needs this hair mod to stay installed.",
  }),
  add_hair_mod: async (path) => ({
    ok: true, token: "edie", source: "edie_hair.archive",
    warning: "The NPV needs this hair mod to stay installed.",
  }),
```

- [ ] **Step 2: Write the failing smoke test**

```python
def test_appearance_inspector_override_flow(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card.selectable").first.click()
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        rows = page.locator(".irow")
        expect(rows).to_have_count(5)  # 4 mock rows + appended hair-mod row
        # Read-only row has no select
        morph = page.locator(".irow", has_text="Eyes (morph preset)")
        expect(morph.locator("select")).to_have_count(0)
        # Override skin tone -> row marked, revert appears, category badge counts
        skin = page.locator(".irow", has_text="Skin tone")
        skin.locator("select").select_option("03_ca_medium")
        expect(skin).to_have_class(re.compile("overridden"))
        expect(skin.locator("button.revert")).to_be_visible()
        expect(page.locator(".cat", has_text="Skin").locator(".override-count")
               ).to_have_text("1")
        # Search filters rows (hair style + hair color + modded-hair row)
        page.fill("#inspector-search", "hair")
        expect(page.locator(".irow")).to_have_count(3)
        page.fill("#inspector-search", "")
        # Revert clears it
        skin.locator("button.revert").click()
        expect(skin).not_to_have_class(re.compile("overridden"))
        # Reset all after two overrides
        skin.locator("select").select_option("03_ca_medium")
        page.locator(".irow", has_text="Hair color").locator("select"
            ).select_option("06_black_carbon")
        page.click("#reset-all")
        expect(page.locator(".irow.overridden")).to_have_count(0)
        # Continue persists via set_overrides and advances
        skin.locator("select").select_option("03_ca_medium")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        assert page.evaluate("() => window.__mockApi._overrides") == {
            "skin_tone": "03_ca_medium"}
        browser.close()


def test_appearance_modded_hair_flow(webui_server):
    """Picking a CCXL hair mod file sets the hair_mod override, is mutually
    exclusive with the vanilla hair_style dropdown, and shows the
    stay-installed warning."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        page.locator(".card.selectable").first.click()
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        hair_mod_row = page.locator(".irow.hair-mod-row")
        expect(hair_mod_row).to_contain_text("—")  # no mod hair yet
        # First set a vanilla style override, then pick a mod file
        style_row = page.locator(".irow", has_text="Hair style")
        style_row.locator("select").select_option("hh_041_pwa__bob")
        expect(style_row).to_have_class(re.compile("overridden"))
        hair_mod_row.locator("button.browse-hair-mod").click()
        expect(hair_mod_row).to_have_class(re.compile("overridden"))
        expect(hair_mod_row).to_contain_text("edie")
        expect(page.locator("main")).to_contain_text(
            "needs this hair mod to stay installed")
        # Mutual exclusion: the vanilla style override was cleared
        expect(style_row).not_to_have_class(re.compile("overridden"))
        # Re-picking a vanilla style clears the mod override
        style_row.locator("select").select_option("hh_041_pwa__bob")
        expect(hair_mod_row).not_to_have_class(re.compile("overridden"))
        # Back to the mod, then Continue persists hair_mod
        hair_mod_row.locator("button.browse-hair-mod").click()
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        assert page.evaluate("() => window.__mockApi._overrides") == {
            "hair_mod": "edie"}
        browser.close()
```

Add `import re` to the smoke test module imports if not present.

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/webui_smoke/test_webui_smoke.py::test_appearance_inspector_override_flow -q`
Expected: FAIL (`.irow` count 0)

- [ ] **Step 4: Implement `appearance.js`**

Replace the summary-card block (keep `esc`, the name/output form, `.form-error`,
and the Continue validation from the current file) with:

```javascript
window.screens.appearance = {
  _data: null,
  _overrides: {},
  _search: "",
  async load(savePath) {
    const out = await Api.call("appearance_data", savePath);
    this._data = out;
    this._overrides = out.ok ? { ...out.overrides } : {};
    store.set({});
  },
  render(el, s) {
    el.innerHTML = "<h1>Appearance</h1>" +
      "<p class='subtitle'>Adjust the decoded appearance. Overridden rows " +
      "are marked; everything else builds exactly as saved.</p>";
    if (!s.save) { el.innerHTML += "<p class='muted'>Pick a save first.</p>"; return; }
    if (this._data === null) {
      el.innerHTML += "<p class='muted'>Decoding…</p>";
      this.load(s.save.path);
      return;
    }
    if (!this._data.ok) {
      el.innerHTML += `<p class="err">${esc(this._data.error)}</p>`;
      return;
    }

    const wrap = document.createElement("div");
    wrap.className = "inspector";

    const cats = document.createElement("div");
    cats.className = "inspector-cats";
    for (const cat of this._data.categories) {
      const rows = this._data.rows.filter((r) => r.category === cat);
      const n = rows.filter((r) => r.slot_id in this._overrides).length;
      const div = document.createElement("div");
      div.className = "cat";
      div.innerHTML = `<span>${esc(cat)}</span><span class="muted">${rows.length}</span>` +
        (n ? `<span class="badge override-count">${n}</span>` : "");
      cats.appendChild(div);
    }
    wrap.appendChild(cats);

    const right = document.createElement("div");
    const search = document.createElement("input");
    search.id = "inspector-search";
    search.placeholder = "Search settings…";
    search.value = this._search;
    search.addEventListener("input", (e) => {
      this._search = e.target.value;
      store.set({});
    });
    right.appendChild(search);

    const reset = document.createElement("button");
    reset.id = "reset-all";
    reset.className = "secondary";
    reset.textContent = "Reset all";
    reset.onclick = () => { this._overrides = {}; store.set({}); };
    right.appendChild(reset);

    const rowsEl = document.createElement("div");
    rowsEl.className = "inspector-rows";
    const q = this._search.toLowerCase();
    for (const row of this._data.rows) {
      if (q && !(row.label + row.value_label).toLowerCase().includes(q)) continue;
      const overridden = row.slot_id in this._overrides;
      const div = document.createElement("div");
      div.className = "irow" + (overridden ? " overridden" : "");
      div.innerHTML = `<span>${esc(row.label)}</span>`;
      if (row.editable) {
        const sel = document.createElement("select");
        for (const opt of row.options) {
          const o = document.createElement("option");
          o.value = opt; o.textContent = opt;
          sel.appendChild(o);
        }
        if (!row.options.includes(row.value_raw)) {
          const o = document.createElement("option");
          o.value = row.value_raw; o.textContent = row.value_raw + " (current)";
          sel.appendChild(o);
        }
        sel.value = overridden ? this._overrides[row.slot_id] : row.value_raw;
        sel.onchange = () => {
          if (sel.value === row.value_raw) delete this._overrides[row.slot_id];
          else this._overrides[row.slot_id] = sel.value;
          store.set({});
        };
        div.appendChild(sel);
        if (overridden) {
          const rv = document.createElement("button");
          rv.className = "secondary revert"; rv.textContent = "↺";
          rv.title = "Revert to the save's value";
          rv.onclick = () => { delete this._overrides[row.slot_id]; store.set({}); };
          div.appendChild(rv);
        }
      } else {
        div.innerHTML += `<span class="muted" title="Not editable yet">` +
          `${esc(row.value_label)} 🔒</span>`;
      }
      rowsEl.appendChild(div);
    }
    right.appendChild(rowsEl);
    wrap.appendChild(right);
    el.appendChild(wrap);

    // ... existing NPV name / output dir form + formError + Continue button ...
    // Continue's onclick gains, before the store.set that advances:
    //   const out = await Api.call("set_overrides", s.save.path, this._overrides);
    //   if (!out.ok) { formError.textContent = out.error; formError.style.display = ""; return; }
  },
};
```

(The Continue handler becomes `async`; the existing missing-fields validation
stays first, then `set_overrides`, then advance. `this._data = null` must be
reset when the selected save changes — key it on `s.save.path`:
store `this._forPath` on load and reload when it differs.)

CSS additions to `app.css`:

```css
.inspector { display: grid; grid-template-columns: 200px 1fr; gap: var(--pad-l); }
.inspector-cats .cat { display: flex; gap: 8px; padding: 6px 8px; align-items: center; }
.irow { display: flex; justify-content: space-between; align-items: center;
        gap: var(--pad-m); padding: 6px 0; border-left: 2px solid transparent; }
.irow.overridden { border-left-color: #e0a83c; padding-left: 8px; }
.override-count { border-color: #e0a83c; color: #e0a83c; }
#inspector-search { margin-right: 8px; }
```

- [ ] **Step 5: Run smoke + full gate, commit**

```bash
uv run pytest tests/webui_smoke/ -q       # all pass
uv run ruff check . && uv run pytest -q
git add npv_build/webui/js/appearance.js npv_build/webui/app.css tests/webui_smoke/
git commit -m "feat(webui): two-pane appearance inspector with overrides"
```

---

### Task 7: Live end-to-end verification (manual gate)

**Files:** none (verification only)

- [ ] **Step 1:** Rebuild the QA harness pattern from memory note `gui-qa-harness` (HTTP bridge serving the real `WebUiApi`), open the app, pick a real save.
- [ ] **Step 2:** On Appearance, override skin tone; confirm the row turns amber, Continue persists (check `~/.config/npv/overrides/*.json` appears), and Build → the built `cc_settings.json` in the output dir contains the overridden `skin.tone_id`, and the mod id differs from the non-overridden build of the same save.
- [ ] **Step 3:** Confirm reverting all overrides and rebuilding reproduces the original mod id (mod-id determinism).
- [ ] **Step 4 (modded hair):** Pick a real CCXL hair mod file (e.g. a Nexus hair zip) via "Use hair mod file…"; confirm: the `.archive`+`.xl` land in the game's `archive/pc/mod/`, the row shows the token + stay-installed warning, and the built `asset_paths.json` carries `hair_app`/`hair_appearance_name` pointing into the mod. The user's own save uses a CCXL hair (winona_2) whose token match previously failed ("no mod .app matched tokens ['winona', '2']" in the 2026-07-19 build log) — verify the explicit-file path finds it where the save-token path could not, and spawn the NPV in game to confirm the hair renders (user step).
- [ ] **Step 5:** Commit any fixes found, re-run `uv run pytest -q`.

## Self-review notes

- Spec coverage: rows/categories/search (T1/T6), dropdowns from mapping data (T2), amber badge + revert + reset (T6), overrides dict on a copy (T1/T3), distinct mod ids (T3 test), per-save persistence (T4), name+output-dir on this step (already shipped 2026-07-19), dry-run on Continue (deviation #2 — fast validation, T5/T6). Beyond spec: modded hair (CCXL) file input (deviation #4 — T1 `hair_mod` transform, T5a bridge, T6 row, T7 live check; research note `docs/research/2026-07-19-ccxl-hair-input.md`). Not covered by design: morph sliders (deviation #1), clothing Browse (plan 4), from-scratch entry (plan 3).
- Types check: row dict keys consistent across T1/T5/T6; `cc_overrides` name identical in BuildRequest, worker kwargs, bridge; `hair_mod` slot name identical in T1 transforms, T5a bridge return→override storage, T6 UI, and mod-id/hash behavior inherited via cc_settings (no new BuildRequest field).
- hair_mod design invariant: it changes `cc_settings` (not a side-channel), so mod-id distinctness and resolve-checkpoint invalidation hold with zero pipeline changes; the mod install itself happens at pick time because the mod is a runtime dependency of the NPV either way.
