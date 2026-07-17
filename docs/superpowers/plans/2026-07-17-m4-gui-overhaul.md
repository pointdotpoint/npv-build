# M4 — GUI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the GUI the complete primary interface — first-run wizard, save browser with metadata, build view with cancel + retry-from-failed-stage, mod manager, multi-appearance NPVs, and settings — with all logic testable outside Tk; milestone M4 of `docs/superpowers/specs/2026-07-17-npv-build-2.0-design.md`.

**Architecture:** `gui.py` is 1141 lines and already unwieldy; M4 adds five screens, so the plan SPLITS it. Testable logic (discovery, mod-manager ops, wizard state, settings I/O) moves into pure modules under `npv_build/gui_logic/` and `npv_build/core/`; the Tk widgets become thin views over those. Every task ships pure-function/view-model logic with unit tests plus a headless smoke; no task's correctness depends on a human clicking.

**Tech Stack:** customtkinter, tkinterdnd2, stdlib; the M1 core layer (PipelineService, CancelToken, platform, errors); pytest with the existing headless-smoke pattern.

## Global Constraints (from spec)

- Python 3.11 floor; run everything via `uv run`. Gates every task: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` (format-check tripped CI twice already — run it).
- **GUI-8 / ERR-3:** no raw tracebacks in the UI. Every failure surfaces `NpvError.user_message` + `remediation` (now in `__str__` since M2) via the existing `show_error`; unexpected exceptions are caught at the view boundary and shown, never propagated into the Tk mainloop (keep the sanctioned `# noqa: BLE001 - GUI event loop must survive` pattern).
- **GUI logic is testable:** any code a test could exercise (discovery, filtering, state machines, file ops) lives in a pure module and is unit-tested; only widget wiring stays in `gui.py`/view files. When a file you touch has grown too large, split it (the spec's isolation principle).
- Backend cancel/resume already exist (M1): `BuildWorker.cancel()` → `CancelToken`; `PipelineService(resume=True)` skips checkpointed stages. M4 WIRES them to widgets — it does not reimplement them.
- Game depot paths keep Windows backslashes; no CDPR bytes in repo (save thumbnails are the user's own screenshots, fine to read/display, never commit).
- Mod ID stays the deterministic hash (NFR-5).
- Do not modify the `WolvenKit/` submodule.
- Config lives via `config.load_config()`/`save_config()` (dict + TOML); extend it, don't fork it.

## Deferred GUI minors folded in (from M1–M3 reviews)

- Preview label truncates `user_message` to 25 chars, never shows remediation → fixed in Task 3 (build view uses full error surface).
- `open_output_folder` dead fallback to entry field → cleaned up in Task 5 (mod manager owns folder-open).
- `configure_logging` global-handler mutation is only single-build-safe → Task 3 documents the single-build gate as an invariant; no concurrent workers introduced.

## File Structure

- `npv_build/gui_logic/` (new package) — pure, Tk-free:
  - `discovery.py` — save browser data (list saves + metadata + thumbnail path).
  - `modmanager.py` — enumerate/install/uninstall built NPV mods.
  - `wizard.py` — first-run wizard state machine + completion → config.
  - `settings.py` — settings read/validate/write over `config`.
- `npv_build/gui_views/` (new package) — thin Tk views, one screen each: `wizard_view.py`, `save_browser_view.py`, `build_view.py`, `modmanager_view.py`, `settings_view.py`.
- `npv_build/gui.py` — shrinks to app shell + navigation between views.
- `npv_build/core/multi_appearance.py` (new) — merge an appearance into an existing NPV mod (GUI-6 backend).

## Plan Roadmap

Plan 5 of 7. Order: T1 discovery → T2 save browser view → T3 build view (cancel+retry) → T4 wizard → T5 mod manager → T6 settings → T7 multi-appearance (deepest; backend + UI) → T8 shell integration + milestone gate. T1/T4/T5/T6 logic modules are independent and could parallelize; views depend on their logic module. T7 depends on T5 (operates on a listed mod).

---

### Task 1: Save discovery logic (`gui_logic/discovery.py`)

**Files:**
- Create: `npv_build/gui_logic/__init__.py` (empty), `npv_build/gui_logic/discovery.py`
- Test: `tests/gui_logic/__init__.py` (empty), `tests/gui_logic/test_discovery.py`

**Interfaces:**
- Consumes: `core.platform.candidate_save_dirs`, `gui_backend.preview_save`.
- Produces: `@dataclass SaveEntry(path: Path, name: str, mtime: float, thumbnail: Path | None)`; `list_saves(save_dirs: list[Path] | None = None) -> list[SaveEntry]` (newest first; `save_dirs=None` → auto-discover; a save = a directory containing `sav.dat`; `name` = the save folder name; `thumbnail` = the folder's `screenshot.png` if present else None). Task 2's view renders these.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_discovery.py
from pathlib import Path

from npv_build.gui_logic.discovery import SaveEntry, list_saves


def _make_save(root: Path, name: str, with_thumb: bool = False) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "sav.dat").write_bytes(b"\x00")
    if with_thumb:
        (d / "screenshot.png").write_bytes(b"\x89PNG")
    return d


def test_lists_saves_newest_first(tmp_path):
    import os, time

    a = _make_save(tmp_path, "AutoSave-1")
    b = _make_save(tmp_path, "QuickSave-2")
    # make b newer deterministically
    os.utime(a / "sav.dat", (1000, 1000))
    os.utime(b / "sav.dat", (2000, 2000))
    entries = list_saves([tmp_path])
    assert [e.name for e in entries] == ["QuickSave-2", "AutoSave-1"]
    assert all(isinstance(e, SaveEntry) for e in entries)


def test_thumbnail_detected_when_present(tmp_path):
    _make_save(tmp_path, "WithThumb", with_thumb=True)
    [e] = list_saves([tmp_path])
    assert e.thumbnail is not None and e.thumbnail.name == "screenshot.png"


def test_no_thumbnail_is_none(tmp_path):
    _make_save(tmp_path, "NoThumb")
    [e] = list_saves([tmp_path])
    assert e.thumbnail is None


def test_ignores_dirs_without_savdat(tmp_path):
    (tmp_path / "not_a_save").mkdir()
    assert list_saves([tmp_path]) == []
```

- [ ] **Step 2: RED** — `uv run pytest tests/gui_logic/test_discovery.py -q` → module not found.

- [ ] **Step 3: Implement**

```python
# npv_build/gui_logic/discovery.py
"""Tk-free data for the save browser (spec GUI-3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.platform import candidate_save_dirs

_THUMB_NAMES = ("screenshot.png",)


@dataclass
class SaveEntry:
    path: Path  # the sav.dat file
    name: str
    mtime: float
    thumbnail: Path | None


def list_saves(save_dirs: list[Path] | None = None) -> list[SaveEntry]:
    dirs = candidate_save_dirs() if save_dirs is None else save_dirs
    entries: list[SaveEntry] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for sub in d.iterdir():
            sav = sub / "sav.dat"
            if not sav.is_file():
                continue
            thumb = next((sub / n for n in _THUMB_NAMES if (sub / n).is_file()), None)
            entries.append(SaveEntry(path=sav, name=sub.name, mtime=sav.stat().st_mtime, thumbnail=thumb))
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries
```

- [ ] **Step 4: GREEN** — `uv run pytest tests/gui_logic/test_discovery.py -q`; then real-data check: `uv run python -c "from npv_build.gui_logic.discovery import list_saves; xs=list_saves(); print(len(xs), xs[0].name if xs else 'none')"` — on this machine expect ~30 and a QuickSave/AutoSave name.

- [ ] **Step 5: Commit** — `git add npv_build/gui_logic tests/gui_logic && git commit -m "feat(gui): save discovery logic (spec GUI-3)"`

---

### Task 2: Save browser view (`gui_views/save_browser_view.py`)

**Files:**
- Create: `npv_build/gui_views/__init__.py` (empty), `npv_build/gui_views/save_browser_view.py`
- Test: `tests/gui_logic/test_save_browser_view.py` (logic-only assertions + headless smoke)

**Interfaces:**
- Consumes: `SaveEntry`, `list_saves` (Task 1).
- Produces: `class SaveBrowserView(ctk.CTkFrame)` with `__init__(self, master, on_select: Callable[[Path], None], save_dirs=None)`, a `refresh()` method that repopulates from `list_saves`, and a manual-picker button fallback (`filedialog.askopenfilename`) that also calls `on_select`. The row-building logic is a static/module function `build_rows(entries) -> list[dict]` (pure, testable) that the view consumes.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_save_browser_view.py
from pathlib import Path

from npv_build.gui_views.save_browser_view import build_rows
from npv_build.gui_logic.discovery import SaveEntry


def test_build_rows_shape():
    e = SaveEntry(path=Path("/x/QuickSave-1/sav.dat"), name="QuickSave-1", mtime=1000.0, thumbnail=None)
    [row] = build_rows([e])
    assert row["name"] == "QuickSave-1"
    assert row["path"] == e.path
    assert "timestamp" in row  # human-readable
    assert row["has_thumb"] is False


def test_build_rows_empty():
    assert build_rows([]) == []
```

Plus append to a `tests/gui_logic/test_gui_smoke.py` a smoke that instantiates the view under the display (guard with the existing DISPLAY-available check pattern; skip if headless-no-display).

- [ ] **Step 2: RED** — module not found.

- [ ] **Step 3: Implement** `build_rows` (maps each `SaveEntry` to `{"name", "path", "timestamp": <strftime of mtime>, "has_thumb": bool}` — no `Date.now`; format the entry's own mtime) and `SaveBrowserView` (scrollable frame of rows, each a button calling `on_select(entry.path)`; a "Browse…" button for the manual picker; `refresh()` clears and rebuilds). Thumbnails: load via `ctk.CTkImage` from `entry.thumbnail` when present, guarded in try/except → fall back to no image on any load error (never crash the list).

- [ ] **Step 4: GREEN** — `uv run pytest tests/gui_logic/test_save_browser_view.py -q` + headless smoke: `timeout 12 uv run python -c "import customtkinter as ctk; from npv_build.gui_views.save_browser_view import SaveBrowserView; r=ctk.CTk(); SaveBrowserView(r, lambda p: None, save_dirs=[]); r.update(); r.destroy(); print('ok')"`

- [ ] **Step 5: Commit** — `git commit -m "feat(gui): save browser view with thumbnails + manual fallback (spec GUI-3)"`

---

### Task 3: Build view — cancel + retry-from-failed-stage (`gui_views/build_view.py`)

**Files:**
- Create: `npv_build/gui_views/build_view.py`
- Modify: `npv_build/gui_backend.py` (expose `resume` passthrough already present via `_request_kwargs`; add `last_failed` awareness)
- Test: `tests/gui_logic/test_build_view.py`

**Interfaces:**
- Consumes: `BuildWorker` (M1), `PipelineService.STAGES`, the queue-tuple protocol (`("log"|"progress"|"done"|"error", val)`).
- Produces: `class BuildView(ctk.CTkFrame)` owning the stage-progress display, live log pane, Cancel button (wired to `worker.cancel()`), and — new — a **Retry from failed stage** button shown only after a failure, which re-dispatches the build with `resume=True` (reusing checkpoints for stages that completed). A pure `BuildViewModel` holds the state machine: `on_event(kind, val)` transitions `idle→running→(done|failed)` and exposes `can_cancel`, `can_retry`, `stage_progress`. Test the view-model, not the widgets.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_build_view.py
from npv_build.gui_views.build_view import BuildViewModel


def test_lifecycle_running_then_done():
    vm = BuildViewModel()
    assert not vm.can_cancel and not vm.can_retry
    vm.on_start()
    assert vm.can_cancel and not vm.can_retry
    vm.on_event("done", "/out")
    assert not vm.can_cancel and not vm.can_retry
    assert vm.state == "done"


def test_failure_enables_retry():
    vm = BuildViewModel()
    vm.on_start()
    vm.on_event("error", "Bake failed")
    assert vm.state == "failed"
    assert vm.can_retry and not vm.can_cancel
    assert vm.last_error == "Bake failed"


def test_cancel_transitions_to_cancelling():
    vm = BuildViewModel()
    vm.on_start()
    vm.on_cancel_requested()
    assert vm.state == "cancelling" and not vm.can_cancel
    vm.on_event("error", "Build cancelled.")
    assert vm.state == "failed"  # cancelled surfaces as a terminal error tuple
    assert vm.can_retry


def test_retry_resets_to_running():
    vm = BuildViewModel()
    vm.on_start(); vm.on_event("error", "x")
    vm.on_start(resume=True)
    assert vm.state == "running" and vm.resume_requested
```

- [ ] **Step 2: RED**

- [ ] **Step 3: Implement** `BuildViewModel` (plain class, the state machine above; `stage_progress` derived from `stage_started`/`stage_completed` events like the M1 backend maps them) and `BuildView` (renders the VM; Cancel button `state=disabled` unless `vm.can_cancel`; Retry button gridded only when `vm.can_retry`, its command re-invokes the app's build entry with `resume=True`). The error display shows the full `val` string (which now carries user_message + remediation) — this closes the 25-char-truncation minor. Keep the `# noqa: BLE001` view-boundary guard.

- [ ] **Step 4: GREEN** — `uv run pytest tests/gui_logic/test_build_view.py -q` + headless smoke of `BuildView`.

- [ ] **Step 5: Commit** — `git commit -m "feat(gui): build view with cancel + retry-from-failed-stage (spec GUI-4, CORE-3/4)"`

---

### Task 4: First-run wizard (`gui_logic/wizard.py` + `gui_views/wizard_view.py`)

**Files:**
- Create: `npv_build/gui_logic/wizard.py`, `npv_build/gui_views/wizard_view.py`
- Test: `tests/gui_logic/test_wizard.py`

**Interfaces:**
- Consumes: `core.platform.find_game_dirs`/`is_valid_game_dir`, `gui_backend.check_dependencies`, `config.load_config`/`save_config`, `installer.auto_install_missing`.
- Produces: `class WizardModel` with `steps = ("game_dir", "dependencies", "done")`, `detect_game_dirs() -> list[Path]`, `set_game_dir(p: Path) -> bool` (validates via `is_valid_game_dir`, returns accepted), `dependency_status() -> dict` (from check_dependencies), `needs_wizard(config) -> bool` (True when no valid game_dir in config), `finish() -> None` (writes game_dir to config via save_config). `WizardView` drives the model step-by-step. The app shows the wizard on launch when `WizardModel.needs_wizard(load_config())`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_wizard.py
from pathlib import Path

from npv_build.gui_logic.wizard import WizardModel


def _valid_game(tmp_path):
    (tmp_path / "archive" / "pc" / "content").mkdir(parents=True)
    return tmp_path


def test_needs_wizard_when_no_game_dir():
    assert WizardModel.needs_wizard({}) is True
    assert WizardModel.needs_wizard({"game_dir": "/x"}) is False


def test_set_game_dir_validates(tmp_path):
    m = WizardModel()
    assert m.set_game_dir(tmp_path) is False  # not a game dir
    g = _valid_game(tmp_path / "game")
    assert m.set_game_dir(g) is True
    assert m.game_dir == g


def test_finish_writes_config(tmp_path, monkeypatch):
    written = {}
    import npv_build.gui_logic.wizard as wz
    monkeypatch.setattr(wz, "save_config", lambda c: written.update(c))
    m = WizardModel()
    g = _valid_game(tmp_path / "game")
    m.set_game_dir(g)
    m.finish()
    assert written["game_dir"] == str(g)
```

- [ ] **Step 2: RED**

- [ ] **Step 3: Implement** `WizardModel` (as specified; `needs_wizard` is a `@staticmethod`; `finish` merges `{"game_dir": str(self.game_dir)}` into loaded config and `save_config`s it) and `WizardView` (three panes: game-dir with auto-detect list + manual browse; dependency lamps + an "Install missing" button calling the InstallerWorker; a done pane). Auto-install runs through the existing `InstallerWorker` queue pattern — do not shell out fresh.

- [ ] **Step 4: GREEN** + headless smoke.

- [ ] **Step 5: Commit** — `git commit -m "feat(gui): first-run wizard (spec GUI-2)"`

---

### Task 5: Mod manager (`gui_logic/modmanager.py` + `gui_views/modmanager_view.py`)

**Files:**
- Create: `npv_build/gui_logic/modmanager.py`, `npv_build/gui_views/modmanager_view.py`
- Test: `tests/gui_logic/test_modmanager.py`

**Interfaces:**
- Consumes: `config` (game_dir), `core.platform.open_folder` (M2), the build output layout (`archive/pc/mod/*.archive`, AMM lua under `bin/x64/plugins/.../Custom Entities/*.lua`).
- Produces: `@dataclass ModEntry(mod_id, archive_path, lua_path, installed: bool)`; `list_mods(output_root: Path, game_dir: Path) -> list[ModEntry]` (enumerate built mods under output_root, mark `installed` if the archive exists in game_dir's `archive/pc/mod/`); `install_mod(entry, game_dir)` / `uninstall_mod(entry, game_dir)` (copy/remove archive + lua, idempotent, raise `InstallError` on missing source); `game_mod_dir(game_dir) -> Path`. The view lists mods with install/uninstall/open-folder buttons. This is where `open_output_folder`'s dead fallback (M1 minor) is retired — folder-open lives here via `open_folder`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_modmanager.py
from pathlib import Path

import pytest

from npv_build.core.errors import InstallError
from npv_build.gui_logic.modmanager import (
    ModEntry, install_mod, list_mods, uninstall_mod, game_mod_dir,
)


def _built_mod(root: Path, mod_id: str) -> Path:
    d = root / mod_id
    (d / "archive" / "pc" / "mod").mkdir(parents=True)
    (d / "archive" / "pc" / "mod" / f"{mod_id}.archive").write_bytes(b"A")
    lua_dir = d / "bin" / "x64" / "plugins" / "cyber_engine_tweaks" / "mods" / "AppearanceMenuMod" / "Collabs" / "Custom Entities"
    lua_dir.mkdir(parents=True)
    (lua_dir / f"{mod_id}.lua").write_text("return {}", encoding="utf-8")
    return d


def _game(tmp_path: Path) -> Path:
    (tmp_path / "archive" / "pc" / "mod").mkdir(parents=True)
    return tmp_path


def test_list_and_install_roundtrip(tmp_path):
    out = tmp_path / "out"; out.mkdir()
    _built_mod(out, "my_v_abc")
    game = _game(tmp_path / "game")

    mods = list_mods(out, game)
    assert len(mods) == 1 and mods[0].mod_id == "my_v_abc" and mods[0].installed is False

    install_mod(mods[0], game)
    assert (game_mod_dir(game) / "my_v_abc.archive").is_file()
    assert list_mods(out, game)[0].installed is True

    uninstall_mod(mods[0], game)
    assert not (game_mod_dir(game) / "my_v_abc.archive").exists()


def test_install_missing_source_raises(tmp_path):
    game = _game(tmp_path / "game")
    ghost = ModEntry(mod_id="x", archive_path=tmp_path / "nope.archive", lua_path=tmp_path / "nope.lua", installed=False)
    with pytest.raises(InstallError):
        install_mod(ghost, game)
```

- [ ] **Step 2: RED**

- [ ] **Step 3: Implement** the module (glob `output_root/*/archive/pc/mod/*.archive` → derive mod_id from the archive stem, find the sibling lua; `installed` = archive present in `game_mod_dir`; install/uninstall copy/remove both archive and lua, and any `.xl` beside the archive; missing source → `InstallError` with remediation) and the view (list + buttons). `.xl` handling makes this forward-compatible with an ArchiveXL-based pipeline (M3 branch A/A′).

- [ ] **Step 4: GREEN** + headless smoke + real check against `/tmp/claude-1000/npv_e2e_out` if still present (list it, assert the e2e mod shows).

- [ ] **Step 5: Commit** — `git commit -m "feat(gui): mod manager — list/install/uninstall built NPVs (spec GUI-5)"`

---

### Task 6: Settings (`gui_logic/settings.py` + `gui_views/settings_view.py`)

**Files:**
- Create: `npv_build/gui_logic/settings.py`, `npv_build/gui_views/settings_view.py`
- Test: `tests/gui_logic/test_settings.py`

**Interfaces:**
- Consumes: `config.load_config`/`save_config`.
- Produces: `@dataclass Settings(game_dir: str|None, output_dir: str|None, log_verbosity: int, patch_override: str|None, check_updates: bool)`; `load_settings() -> Settings`; `save_settings(s: Settings) -> None` (merges into config dict, preserving unknown keys); `validate(s) -> list[str]` (returns human-readable problems: game_dir set but invalid, verbosity out of 0–2, etc.). The view is a form bound to Settings.

- [ ] **Step 1: Write the failing tests**

```python
# tests/gui_logic/test_settings.py
from npv_build.gui_logic.settings import Settings, load_settings, save_settings, validate


def test_roundtrip_preserves_unknown_keys(monkeypatch):
    import npv_build.gui_logic.settings as st
    store = {"game_dir": "/g", "some_future_key": 7}
    monkeypatch.setattr(st, "load_config", lambda: dict(store))
    monkeypatch.setattr(st, "save_config", lambda c: store.clear() or store.update(c))
    s = load_settings()
    assert s.game_dir == "/g"
    s.log_verbosity = 2
    save_settings(s)
    assert store["some_future_key"] == 7  # not clobbered
    assert store["log_verbosity"] == 2


def test_validate_flags_bad_verbosity():
    s = Settings(game_dir=None, output_dir=None, log_verbosity=9, patch_override=None, check_updates=True)
    problems = validate(s)
    assert any("verbosity" in p.lower() for p in problems)
```

- [ ] **Step 2: RED**

- [ ] **Step 3: Implement** (load reads known keys with defaults; save merges into the full loaded dict so unknown keys survive; validate checks verbosity ∈ {0,1,2} and game_dir validity when set) and the settings form view.

- [ ] **Step 4: GREEN** + headless smoke.

- [ ] **Step 5: Commit** — `git commit -m "feat(gui): settings screen with config round-trip (spec GUI-7)"`

---

### Task 7: Multi-appearance NPVs (`core/multi_appearance.py` + view hook)

**Files:**
- Create: `npv_build/core/multi_appearance.py`
- Modify: `npv_build/gui_views/modmanager_view.py` (add "Add appearance…" action per mod)
- Test: `tests/core/test_multi_appearance.py`

**Interfaces:**
- Consumes: `WolvenKit` adapter (serialize/deserialize/pack), an existing built mod's `.app`, and a second build's appearance.
- Produces: `add_appearance(wk, existing_mod_archive: Path, new_appearance_app: Path, new_appearance_name: str, out_archive: Path) -> Path` — merges the new appearance's entry into the existing mod's `.app` appearances array (via serialize→merge-JSON→deserialize→pack), returns the repacked archive; plus `append_amm_appearance(lua_path: Path, appearance_name: str) -> None` (adds the name to the AMM lua's `appearances` list). Raise `NpvError` on name collision (appearance already present).

**Design note (implementer context):** This is the one M4 task with real backend depth. The community "add appearance to an NPV" workflow appends an appearance entry (with its own component array) to the mod's `.app` and registers the name in the AMM lua. H1 from the M3 spike proved WolvenKit serialize→deserialize round-trips a full component-bearing `.app` faithfully — reuse that exact mechanism. Do NOT rebuild the whole pipeline; you are merging one already-built appearance into one already-built mod. Scope guard: if merging requires resolving cross-`.app` handle/CRUID collisions that the round-trip can't handle cleanly, STOP and report — that's a spike-shaped unknown, not a mechanical task, and it should become its own investigation rather than a guessed implementation.

- [ ] **Step 1: Write the failing tests** (JSON-level, no real WolvenKit — mock `wk.serialize`/`deserialize`/`pack` to operate on JSON files, matching the real adapter's file-in/file-out contract):

```python
# tests/core/test_multi_appearance.py
import json
from pathlib import Path

import pytest

from npv_build.core.errors import NpvError
from npv_build.core.multi_appearance import append_amm_appearance, merge_appearance_json


def test_merge_appearance_adds_entry():
    base = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "app_a"}}]}}}
    new = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "app_b"}}]}}}
    merged = merge_appearance_json(base, new, "app_b")
    names = [a["Data"]["name"] for a in merged["Data"]["RootChunk"]["appearances"]]
    assert names == ["app_a", "app_b"]


def test_merge_rejects_name_collision():
    base = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "dup"}}]}}}
    new = {"Data": {"RootChunk": {"appearances": [{"Data": {"name": "dup"}}]}}}
    with pytest.raises(NpvError):
        merge_appearance_json(base, new, "dup")


def test_append_amm_appearance(tmp_path):
    lua = tmp_path / "x.lua"
    lua.write_text('return {\n  appearances = {\n    "first"\n  }\n}\n', encoding="utf-8")
    append_amm_appearance(lua, "second")
    text = lua.read_text(encoding="utf-8")
    assert '"first"' in text and '"second"' in text
```

- [ ] **Step 2: RED**

- [ ] **Step 3: Implement** `merge_appearance_json(base, new, new_name)` (pure dict merge: copy the named appearance entry from `new` into `base`'s appearances list; raise `NpvError` if `new_name` already in base — the real handle/CRUID reconciliation caveat from the design note is documented in the module docstring and surfaced as a known limitation), `append_amm_appearance` (text-insert into the lua appearances block, idempotent), and the file-level `add_appearance(wk, ...)` orchestrating serialize→merge→deserialize→pack. Keep the pure `merge_appearance_json` separate from the WolvenKit I/O so it's unit-tested without the tool.

- [ ] **Step 4: GREEN** — `uv run pytest tests/core/test_multi_appearance.py -q`. (Real-WolvenKit + in-game validation of a genuinely-merged NPV is a follow-up gated like M3-T4; note it.)

- [ ] **Step 5: Commit** — `git commit -m "feat(core): multi-appearance NPV merge (spec GUI-6)"`

---

### Task 8: App shell integration + milestone gate

**Files:**
- Modify: `npv_build/gui.py` (reduce to shell + nav; mount the five views; show wizard on first run)
- Test: `tests/gui_logic/test_gui_smoke.py` (full-app headless smoke)

**Interfaces:**
- Consumes: all view classes (Tasks 2–7) and their logic modules.
- Produces: a navigable app — wizard on first run (`WizardModel.needs_wizard`), else the main view with tabs/nav to Save Browser → Build → Mod Manager → Settings. Feature parity (GUI-1) preserved: the existing build inputs (name, garments, BYO head, CET-dump, hair mod, output) remain reachable. `gui.py` should shrink substantially (target: under ~400 lines; the screens now live in `gui_views/`).

- [ ] **Step 1:** Write the full-app headless smoke test (instantiate `App`, `update()`, navigate each view via its public method, `destroy()`, assert no exception). Guard with DISPLAY-available skip.

- [ ] **Step 2: RED/iterate** — refactor `gui.py`: extract the existing build-input widgets into the appropriate view, mount views under a `CTkTabview` or nav frame, gate the wizard on `needs_wizard`. Run the smoke after each extraction.

- [ ] **Step 3:** Feature-parity check — a scripted (non-widget) assertion that every CLI-reachable input has a corresponding view field (enumerate `BuildRequest` fields, assert each is settable through some view's public setter or the build view). This is the GUI-1 gate.

- [ ] **Step 4: Milestone gate** — `uv run pytest -q` (all green, suite grown), `uv run ruff check .`, `uv run ruff format --check .`; headless smoke of the whole app; push branch, CI green both OSes.

- [ ] **Step 5: Commit** — `git commit -m "feat(gui): app shell integration, view navigation, wizard gating (spec GUI-1/8)"`

---

## Exit Criteria (spec M4)

- GUI-1 feature parity verified by the enumerated-inputs check (Task 8).
- GUI-2 wizard shows on first run and writes config; GUI-3 save browser lists real saves with thumbnails + manual fallback.
- GUI-4 build view has working Cancel (kills in-flight tools via M1 backend) and Retry-from-failed-stage (resume); full error surface (no 25-char truncation, no tracebacks).
- GUI-5 mod manager lists/installs/uninstalls; GUI-6 multi-appearance merges an appearance into an existing mod (JSON-level tested; real-WolvenKit + in-game validation noted as follow-up).
- GUI-7 settings round-trip config preserving unknown keys; GUI-8 all errors via user_message+remediation.
- `gui.py` split into `gui_logic/` (tested, Tk-free) + `gui_views/` (thin); every logic module unit-tested; whole-app headless smoke green.
- CI green both OSes.

## Notes / Dependencies

- **M3 outcome (ADR 0001) = Branch A′:** `npv-inject` is being retired (WolvenKit round-trip replaces it — M4/M5 backlog), so the **wizard's dependency check (Task 4 / GUI-2) must drop .NET** from what it detects/installs (keep WolvenKit + Blender). The donor entity stays. The mod manager's `.xl` handling (Task 5) and multi-appearance merge (Task 7) are the right primitives either way and operate on whatever the pipeline emits.
- **No new concurrency:** the single-build-at-a-time invariant (M1) stays; `configure_logging`'s global handler is safe under it. Do not add a second concurrent worker.
