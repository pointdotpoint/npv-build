# From-Scratch Builds (GUI redesign plan 3/4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate the "From scratch" card on the Source step: pick a body rig (pwa/pma), load a vendored default-V preset as the `cc_settings`, and run the normal pipeline without any save file.

**Architecture:** `BuildRequest` gains `cc_settings_override: dict | None` as a third CC source inside the existing `_run_parse` three-mode logic (save / cc-json / preset — exactly one required). Presets are complete `cc_settings` dicts decoded by our own parser from untouched default-V saves and vendored as JSON (option IDs and path strings only — no CDPR bytes). A generation script turns a user-provided save into a preset file; the GUI exposes rig cards through a `load_preset` bridge method.

**Tech Stack:** Python 3.11+, vanilla JS frontend, pytest (+ `e2e` marker for the resolve test).

**Spec:** `docs/superpowers/specs/2026-07-18-gui-redesign-webui-design.md` §"From-scratch builds".

## User-gated data prerequisite (do first, can run in parallel with Tasks 2+)

The preset files themselves require **two saves the repo does not have**: a new
game saved with an untouched default V, one per rig (pwa and pma). Only the
user can produce these (start new game → skip character creation changes →
save). Until they exist, `data/presets/` ships empty and every test that needs
a preset **skips with a clear reason** — the plan is still fully executable and
mergeable; the data lands later via Task 1's script.

## Global Constraints

- No CDPR bytes in repo: presets contain option IDs/strings decoded by our parser only.
- Hard-fail policy; exactly one CC source per build (save XOR cc-json XOR preset).
- Depot paths keep Windows backslashes in all data files.
- Bridge methods return JSON dicts, never raise into JS.
- `uv run ruff check .` + `uv run pytest -q` green after every task.

## Reference (verified 2026-07-19)

- `BuildRequest` (`npv_build/core/pipeline.py:28`): already has `save_path: Path | None` and `cc_json_path: Path | None`; `_run_parse` (line ~67) implements the save/cc-json modes. The parse checkpoint hashes `[str(req.save_path), save_stat, str(req.cc_json_path)]`.
- `cc_settings` keys: `patch, body_rig, selections, head, eyes, teeth, skin, hair, overlays, face_morphs` (see plan 2/4 for the full sample).
- Existing e2e marker: `pyproject.toml` defines `e2e: end-to-end build tests requiring a real game install`.

---

### Task 1: Preset generation script

**Files:**
- Create: `scripts/make_preset.py`
- Test: `tests/test_make_preset.py`

**Interfaces:**
- Produces: `python scripts/make_preset.py <sav.dat> <pwa|pma>` → writes `npv_build/data/presets/default_v_<rig>.json`.
- Produces (importable): `make_preset(save_path: Path, rig: str) -> dict` — parses the save, asserts `body_rig == rig`, returns the full `cc_settings` dict ready to vendor.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_make_preset.py
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from make_preset import make_preset  # noqa: E402


def test_make_preset_roundtrips_parser_output(synth_save_2310):
    preset = make_preset(synth_save_2310, "pwa")
    assert preset["body_rig"] == "pwa"
    assert preset["selections"]
    json.dumps(preset)  # vendorable: JSON-serializable, strings/ints only


def test_make_preset_rejects_rig_mismatch(synth_save_2310):
    with pytest.raises(SystemExit):
        make_preset(synth_save_2310, "pma")
```

**Verify before use:** the synthetic save fixture's decoded `body_rig` — run
`uv run python -c "from npv_build.save_parser import parse_save; import sys"` +
inspect `tests/conftest.py::_build_cc_node` to confirm it decodes as `pwa`. If it
decodes differently, adjust the expected rig in both tests.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_make_preset.py -q`
Expected: FAIL with ModuleNotFoundError / ImportError

- [ ] **Step 3: Implement**

```python
# scripts/make_preset.py
"""Decode an untouched default-V save into a vendorable preset.

Usage: uv run python scripts/make_preset.py <sav.dat> <pwa|pma>
Writes npv_build/data/presets/default_v_<rig>.json (strings/IDs only).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from npv_build.save_parser import parse_save  # noqa: E402

PRESET_DIR = Path(__file__).parents[1] / "npv_build" / "data" / "presets"


def make_preset(save_path: Path, rig: str) -> dict:
    cc = parse_save(Path(save_path))
    if cc.get("body_rig") != rig:
        sys.exit(f"Save decodes as body_rig={cc.get('body_rig')!r}, expected {rig!r}.")
    return cc


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[2] not in ("pwa", "pma"):
        sys.exit(__doc__)
    preset = make_preset(Path(sys.argv[1]), sys.argv[2])
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    out = PRESET_DIR / f"default_v_{sys.argv[2]}.json"
    out.write_text(json.dumps(preset, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {out} ({len(preset.get('selections', []))} selections)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_make_preset.py -q` → 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/make_preset.py tests/test_make_preset.py
git commit -m "feat(presets): default-V preset generation script"
```

**Hand-off note for the user (goes in the PR/commit description):** run
`uv run python scripts/make_preset.py <default-V pwa save> pwa` and the same for
`pma`, then commit the two files under `npv_build/data/presets/`.

---

### Task 2: `BuildRequest.cc_settings_override` in the pipeline

**Files:**
- Modify: `npv_build/core/pipeline.py` (`BuildRequest`, `_run_parse`, parse hash)
- Test: `tests/core/test_pipeline_preset.py` (create)

**Interfaces:**
- Produces: `BuildRequest.cc_settings_override: dict | None = None`.
- Behavior: `_run_parse` returns a deep copy of `cc_settings_override` when set; it is an error to combine it with `save_path` or `cc_json_path`, and an error to provide no CC source at all. The parse-stage hash includes the override dict so checkpoint resume works ("same checkpoint shape; input hash from the settings dict" — spec).

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_pipeline_preset.py
import pytest

from npv_build.core.errors import NpvError
from npv_build.core.pipeline import BuildRequest, PipelineService, _run_parse

CC = {"patch": "2.31", "body_rig": "pma", "selections": [], "head": {},
      "eyes": {}, "teeth": {}, "skin": {"tone_id": "01"},
      "hair": {"style_id": "x"}, "overlays": [], "face_morphs": {}}


def _req(tmp_path, **kw):
    return BuildRequest(
        save_path=None, npv_name="V", output_dir=tmp_path / "o",
        game_dir=tmp_path, template_cache=tmp_path / "tc", **kw)


def test_run_parse_returns_copy_of_override(tmp_path):
    req = _req(tmp_path, cc_settings_override=CC)
    out = _run_parse(req)
    assert out == CC and out is not CC


def test_override_is_exclusive_with_save(tmp_path, synth_save_2310):
    req = _req(tmp_path, cc_settings_override=CC)
    req.save_path = synth_save_2310
    with pytest.raises(NpvError):
        _run_parse(req)


def test_no_cc_source_is_an_error(tmp_path):
    with pytest.raises(NpvError):
        _run_parse(_req(tmp_path))


def test_preset_build_resumes_parse_stage(monkeypatch, tmp_path):
    calls = []

    def fake_resolve(cc, *a, **k):
        calls.append(cc["body_rig"])
        raise RuntimeError("stop")

    monkeypatch.setattr("npv_build.core.pipeline.resolve_assets", fake_resolve)
    req = _req(tmp_path, cc_settings_override=CC)
    with pytest.raises(RuntimeError):
        PipelineService().build(req)
    req2 = _req(tmp_path, cc_settings_override=CC, resume=True)
    with pytest.raises(RuntimeError):
        PipelineService().build(req2)
    import json
    manifest = json.loads((tmp_path / "o" / ".npv_manifest.json").read_text())
    assert manifest["parse_save"]["output"]["body_rig"] == "pma"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_pipeline_preset.py -q`
Expected: FAIL — unexpected keyword `cc_settings_override`

- [ ] **Step 3: Implement**

In `BuildRequest`, after `cc_json_path`:

```python
    cc_json_path: Path | None = None
    cc_settings_override: dict | None = None
```

At the top of `_run_parse`:

```python
    sources = [s for s in (req.save_path, req.cc_json_path,
                           req.cc_settings_override) if s is not None]
    if len(sources) > 1 and req.cc_settings_override is not None:
        raise NpvError(
            "A preset build cannot also use a save or CC dump.",
            remediation="Provide exactly one CC source.",
        )
    if not sources:
        raise NpvError(
            "No CC source provided.",
            remediation="Provide a save file, a --cc-json dump, or a preset.",
        )
    if req.cc_settings_override is not None:
        logger.info("[CC Loader] Using preset CC settings (from-scratch build).")
        import copy

        return copy.deepcopy(req.cc_settings_override)
```

In `build()`, extend the parse hash so preset changes invalidate the checkpoint:

```python
            parse_hash = _hash_input([
                str(req.save_path), save_stat, str(req.cc_json_path),
                req.cc_settings_override,
            ])
```

- [ ] **Step 4: Run tests + full gate**

Run: `uv run pytest tests/core/ tests/test_orchestrator.py -q` → all pass
(orchestrator tests confirm the save/cc-json modes did not regress).

- [ ] **Step 5: Commit**

```bash
git add npv_build/core/pipeline.py tests/core/test_pipeline_preset.py
git commit -m "feat(pipeline): cc_settings_override as a third exclusive CC source"
```

---

### Task 3: Preset loading + guard tests

**Files:**
- Create: `npv_build/gui_logic/presets.py`
- Test: `tests/gui_logic/test_presets.py`

**Interfaces:**
- Produces: `list_presets() -> list[dict]` — `[{"rig": "pwa", "available": bool}, {"rig": "pma", ...}]` (both rigs always listed; availability = data file exists).
- Produces: `load_preset(rig: str) -> dict` — parsed preset JSON; raises `NpvError` with remediation when the file is missing.
- Produces: `preset_path(rig: str) -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_presets.py
import json

import pytest

from npv_build.core.errors import NpvError
from npv_build.gui_logic import presets


def test_list_presets_reports_availability(monkeypatch, tmp_path):
    monkeypatch.setattr(presets, "_preset_dir", lambda: tmp_path)
    (tmp_path / "default_v_pwa.json").write_text(json.dumps({"body_rig": "pwa"}))
    out = presets.list_presets()
    assert out == [{"rig": "pwa", "available": True},
                   {"rig": "pma", "available": False}]


def test_load_preset_roundtrip_and_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(presets, "_preset_dir", lambda: tmp_path)
    (tmp_path / "default_v_pwa.json").write_text(json.dumps({"body_rig": "pwa"}))
    assert presets.load_preset("pwa")["body_rig"] == "pwa"
    with pytest.raises(NpvError):
        presets.load_preset("pma")
    with pytest.raises(NpvError):
        presets.load_preset("weird")


@pytest.mark.parametrize("rig", ["pwa", "pma"])
def test_vendored_preset_structure(rig):
    """Guards the real vendored files once the user generates them."""
    p = presets.preset_path(rig)
    if not p.exists():
        pytest.skip(f"preset for {rig} not vendored yet (user-gated data)")
    cc = json.loads(p.read_text(encoding="utf-8"))
    assert cc["body_rig"] == rig
    assert cc["selections"], "preset must carry the full default CC selections"
    for key in ("patch", "skin", "hair", "face_morphs"):
        assert key in cc
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/gui_logic/test_presets.py -q` → ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# npv_build/gui_logic/presets.py
"""Vendored default-V presets for from-scratch builds (plan 3/4)."""

from __future__ import annotations

import json
from pathlib import Path

from ..core.errors import NpvError

RIGS = ("pwa", "pma")


def _preset_dir() -> Path:
    return Path(__file__).parents[1] / "data" / "presets"


def preset_path(rig: str) -> Path:
    return _preset_dir() / f"default_v_{rig}.json"


def list_presets() -> list[dict]:
    return [{"rig": rig, "available": preset_path(rig).is_file()} for rig in RIGS]


def load_preset(rig: str) -> dict:
    if rig not in RIGS:
        raise NpvError(f"Unknown body rig: {rig}",
                       remediation="Valid rigs: pwa, pma.")
    p = preset_path(rig)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except OSError as e:
        raise NpvError(
            f"No default-V preset for {rig} is bundled yet.",
            remediation="Generate it with scripts/make_preset.py from an "
                        "untouched default-V save.",
        ) from e
    except ValueError as e:
        raise NpvError(f"Preset for {rig} is corrupt: {e}",
                       remediation="Regenerate it with scripts/make_preset.py.") from e
```

- [ ] **Step 4: Run + gate** — `uv run pytest tests/gui_logic/test_presets.py -q` → 4 passed, 2 skipped (vendored-structure params skip until data lands); full gate green.

- [ ] **Step 5: Commit**

```bash
git add npv_build/gui_logic/presets.py tests/gui_logic/test_presets.py
git commit -m "feat(gui_logic): default-V preset loader with availability listing"
```

---

### Task 4: e2e resolve guard (runs only with a real game install)

**Files:**
- Test: `tests/test_preset_resolves_e2e.py` (create)

**Interfaces:** none new — this is the spec's "each preset resolves cleanly through the mapping (guards patch bumps)".

- [ ] **Step 1: Write the test**

```python
# tests/test_preset_resolves_e2e.py
"""Spec guard: every vendored preset must resolve through the mapping.
Needs a real game install + part index -> e2e marker, skipped in CI."""
import json

import pytest

from npv_build.gui_logic.presets import RIGS, preset_path
from npv_build.gui_logic.settings import load_settings
from npv_build.mapping import resolve_assets


@pytest.mark.e2e
@pytest.mark.parametrize("rig", RIGS)
def test_preset_resolves_cleanly(rig):
    p = preset_path(rig)
    if not p.exists():
        pytest.skip(f"preset for {rig} not vendored yet")
    s = load_settings()
    if not s.game_dir:
        pytest.skip("no game_dir configured")
    from pathlib import Path

    cc = json.loads(p.read_text(encoding="utf-8"))
    asset_paths = resolve_assets(cc, Path(s.game_dir), None, [], None)
    assert not asset_paths.get("unresolved"), asset_paths.get("unresolved")
```

- [ ] **Step 2: Verify collection** — `uv run pytest tests/test_preset_resolves_e2e.py -q` → 2 skipped (no presets yet). `uv run pytest -q` stays green (e2e excluded by default? **verify:** check `pyproject.toml` marker config — if e2e is not auto-excluded, the skips above make it safe either way).

- [ ] **Step 3: Commit**

```bash
git add tests/test_preset_resolves_e2e.py
git commit -m "test(presets): e2e resolve guard per rig"
```

---

### Task 5: Bridge + frontend (rig cards, preset flow through Build)

**Files:**
- Modify: `npv_build/webui_api.py`, `npv_build/webui/js/source.js`, `npv_build/webui/js/appearance.js`, `npv_build/webui/js/build.js` (start payload), `npv_build/webui/js/store.js` (add `preset: null` to state)
- Modify: `tests/webui_smoke/mock_api.js`
- Test: `tests/test_webui_api.py` + `tests/webui_smoke/test_webui_smoke.py` (append)

**Interfaces:**
- Bridge produces: `list_presets() -> {"ok", "presets": [{"rig", "available"}]}`; `preview_preset(rig) -> {"ok", body_rig, skin_tone, hair_style, hair_color, selections_count} | error` (same summary shape as `preview_save`, built by reusing `gui_backend.preview_save`'s field extraction on the preset dict — factor that extraction into `gui_backend.summarize_cc(cc: dict) -> dict` and reuse it in both).
- `start_build(req)` accepts either `req["save_path"]` or `req["preset_rig"]`; with `preset_rig` it passes `save_path=None, cc_settings_override=load_preset(rig)` to the worker and writes `build_meta.json` with `{"npv_name", "preset_rig"}` instead of `save_path`.
- Frontend: store gains `preset` (`{rig}` or null; mutually exclusive with `save`). Source "From scratch" card becomes active when any preset is available: clicking shows two rig buttons (`#rig-pwa`, `#rig-pma`; unavailable rig disabled with tooltip); picking one sets `store.preset`, clears `store.save`, fetches `preview_preset` for the Appearance summary, auto-fills NPV name (`"Default V"`) + output dir. Appearance renders `appearance_data` only for saves; for presets it shows the summary card (overrides for presets are a follow-up, spec: "read-only rows stay at preset defaults").
- Build: `start` sends `{preset_rig}` instead of `save_path` when `s.preset` is set.

- [ ] **Step 1: Bridge tests (failing)**

```python
# append to tests/test_webui_api.py
def test_preview_preset_and_start_build_with_preset(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    cc = {"patch": "2.31", "body_rig": "pma", "selections": [1, 2],
          "skin": {"tone_id": "02"}, "hair": {"style_id": "hh_01", "raw": ""},
          "head": {}, "eyes": {}, "teeth": {}, "overlays": [], "face_morphs": {}}
    monkeypatch.setattr("npv_build.webui_api.load_preset", lambda rig: cc)
    monkeypatch.setattr("npv_build.webui_api.list_gui_presets",
                        lambda: [{"rig": "pwa", "available": False},
                                 {"rig": "pma", "available": True}])
    api = WebUiApi()
    assert api.list_presets()["presets"][1]["available"] is True
    prev = api.preview_preset("pma")
    assert prev["ok"] is True and prev["body_rig"] == "pma"
    assert prev["selections_count"] == 2

    started = {}

    class FakeWorker:
        def __init__(self, q): pass
        def start(self, **kw): started.update(kw)

    monkeypatch.setattr("npv_build.webui_api.BuildWorker", FakeWorker)
    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    out = api.start_build({"preset_rig": "pma", "npv_name": "Default V",
                           "output_dir": str(tmp_path / "o")})
    assert out == {"ok": True}
    assert started["save_path"] is None
    assert started["cc_settings_override"] == cc
    import json
    meta = json.loads((tmp_path / "o" / "build_meta.json").read_text())
    assert meta == {"npv_name": "Default V", "preset_rig": "pma"}


def test_preview_preset_missing_is_structured(monkeypatch):
    from npv_build.core.errors import NpvError

    def boom(rig):
        raise NpvError("No preset", remediation="Generate it")

    monkeypatch.setattr("npv_build.webui_api.load_preset", boom)
    out = WebUiApi().preview_preset("pwa")
    assert out["ok"] is False and out["remediation"]
```

- [ ] **Step 2: Run to verify failure**, then implement the bridge:

```python
# webui_api.py imports
from .gui_backend import summarize_cc
from .gui_logic.presets import list_presets as list_gui_presets
from .gui_logic.presets import load_preset
```

```python
    def list_presets(self) -> dict:
        return {"ok": True, "presets": list_gui_presets()}

    def preview_preset(self, rig: str) -> dict:
        try:
            cc = load_preset(rig)
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True, **summarize_cc(cc)}
```

Refactor `gui_backend.preview_save` so the dict-building part becomes

```python
def summarize_cc(cc_settings: dict) -> dict:
    hair = cc_settings.get("hair") or {}
    skin = cc_settings.get("skin") or {}
    return {
        "body_rig": cc_settings.get("body_rig", "Unknown"),
        "skin_tone": skin.get("tone_id") or "Unknown",
        "hair_style": hair.get("style_id") or "Unknown",
        "hair_color": (hair.get("color")
                       or hair_color_from_selections(cc_settings.get("selections", []))
                       or "Unknown"),
        "selections_count": len(cc_settings.get("selections", [])),
    }
```

and `preview_save` returns `summarize_cc(parse_save(save_path))`. Existing
`gui_backend` tests must stay green unchanged.

In `start_build`, branch on the CC source (keeping the existing save branch):

```python
        if req.get("preset_rig"):
            try:
                cc_override = load_preset(req["preset_rig"])
            except NpvError as e:
                return {"ok": False, "error": e.user_message,
                        "remediation": e.remediation or ""}
            meta = {"npv_name": req["npv_name"], "preset_rig": req["preset_rig"]}
            save_path = None
            extra = {"cc_settings_override": cc_override, "cc_overrides": {}}
        else:
            meta = {"npv_name": req["npv_name"], "save_path": req["save_path"]}
            save_path = Path(req["save_path"])
            extra = {"cc_overrides": load_overrides(req["save_path"])}
```

then write `meta` as build_meta.json (existing code) and pass
`save_path=save_path, **extra` to `self._worker.start(...)`.
(`cc_overrides` in `extra` assumes plan 2 Task 5 landed; if executing this plan
first, drop the `cc_overrides` lines — grep `webui_api.py` for `load_overrides`
to know which world you are in.)

- [ ] **Step 3: Frontend + smoke test**

Mock additions (`tests/webui_smoke/mock_api.js`):

```javascript
  list_presets: async () => ({ ok: true, presets: [
    { rig: "pwa", available: true }, { rig: "pma", available: false }] }),
  preview_preset: async () => ({ ok: true, body_rig: "pwa", skin_tone: "01_ca_pale",
    hair_style: "hh_040", hair_color: "copper", selections_count: 150 }),
```

Smoke test (append):

```python
def test_from_scratch_preset_flow(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        scratch = page.locator(".card", has_text="From scratch")
        scratch.click()
        page.click("#rig-pwa")
        expect(page.locator("#rig-pma")).to_be_disabled()
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        expect(page.locator("main")).to_contain_text("pwa")
        expect(page.locator("#npv-name")).to_have_value("Default V")
        page.fill("#output-dir", "/out/defaultv")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        browser.close()
```

`source.js` changes: replace the static greyed scratch card with an active card
(when `list_presets` reports any available rig) that on click renders two rig
buttons (`id="rig-pwa"` / `id="rig-pma"`, disabled + `title` explaining when
unavailable); clicking an available rig runs:

```javascript
const prev = await Api.call("preview_preset", rig);
if (!prev.ok) { showError(prev.error + " " + (prev.remediation || "")); return; }
store.set({
  preset: { rig, preview: prev }, save: null,
  npvName: store.state.npvName || "Default V",
  outputDir: store.state.outputDir ||
    ((store.state.appState.default_output_root || "") + "/DefaultV-" + rig),
});
```

Source's Continue enables when `s.save?.preview?.ok || s.preset`. Appearance
renders the preset summary card (reusing the existing summary markup with
`s.preset.preview`) instead of the inspector when `s.preset` is set. Build's
`start()` sends `preset_rig: s.preset.rig` instead of `save_path` when preset
mode is active; `store.js` initial state gains `preset: null`, and install.js's
"Build another" reset adds `preset: null`.

- [ ] **Step 4: Run everything**

`uv run pytest tests/webui_smoke/ tests/test_webui_api.py -q` → green;
`uv run ruff check . && uv run pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add npv_build/webui_api.py npv_build/gui_backend.py npv_build/webui/ tests/
git commit -m "feat(webui): from-scratch preset builds (rig cards through Build)"
```

---

### Task 6: Live verification (manual gate, needs vendored presets)

- [ ] Generate at least the pwa preset from a real default-V save (`scripts/make_preset.py`), run the QA harness (memory note `gui-qa-harness`), build "Default V" from scratch end-to-end, install, and spawn via AMM in game. Only after the in-game spawn check does the "From scratch" feature count as shipped.

## Self-review notes

- Spec coverage: `cc_settings_override` exclusive source (T2), `load_preset` checkpoint semantics (T2 hash), vendored presets + generation (T1, user-gated), resolve guard per rig (T4), rig picker UI + defaults flow (T5), boundary "read-only at preset defaults" honored by rendering the summary card, not the editable inspector (T5).
- Names consistent: `cc_settings_override` (BuildRequest/worker/bridge), `preset_rig` (bridge/frontend/build_meta), `summarize_cc` shared by both previews.
