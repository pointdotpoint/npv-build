# Web UI Shell + Parity Implementation Plan (GUI redesign 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the customtkinter GUI with a pywebview shell + static web frontend at feature parity (source/build/install flow, library, settings, onboarding).

**Architecture:** A single Python bridge class (`npv_build/webui_api.py`) wraps existing `gui_logic/` + `gui_backend.py` and is exposed to a static vanilla-JS frontend (`npv_build/webui/`) via pywebview `js_api`. The frontend is a left-rail step flow (Source → Appearance placeholder → Build → Install) plus My NPVs and Settings, polling `poll_events()` during builds. No frameworks, no build step.

**Tech Stack:** Python 3.12+, pywebview, vanilla HTML/CSS/JS, pytest, Playwright (smoke).

**Spec:** `docs/superpowers/specs/2026-07-18-gui-redesign-webui-design.md`. Follow-up plans cover: appearance inspector (2), from-scratch presets (3), clothing catalog (4). This plan ships a working replacement GUI; the Appearance step renders a read-only summary placeholder until plan 2.

## Global Constraints

- No CDPR game bytes in the repo; only path strings and option IDs.
- Depot paths use Windows backslashes (`base\characters\...`) everywhere, including JSON shipped to the frontend.
- Hard-fail policy: errors surface with `user_message` + `remediation`; no partial output.
- Palette: bg `#16161e`, surface `#1f2029`, surface-alt `#1a1b23`, border `#2a2c3a`, text `#c0caf5`, text-muted `#565f89`, accent `#7aa2f7`, override-amber `#e0af68`, success `#9ece6a`, error `#f7768e`.
- `customtkinter` GUI keeps working until Task 10 deletes it; do not modify `gui.py`/`gui_views/` before then.
- All bridge methods return JSON-serializable dicts/lists only (no Path objects).
- Run `uv run pytest` and `uv run ruff check .` before every commit.

---

### Task 1: Bridge — state, settings, dependencies

**Files:**
- Create: `npv_build/webui_api.py`
- Test: `tests/test_webui_api.py`

**Interfaces:**
- Produces: `class WebUiApi` with `get_state() -> dict`, `save_config(cfg: dict) -> dict`. `get_state()` returns `{"settings": {game_dir, output_dir, log_verbosity, patch_override, check_updates}, "deps": {wolvenkit, blender, npv_inject, game_dir_valid}, "needs_onboarding": bool, "version": str}`.
- Consumes: `gui_logic.settings.load_settings/save_settings/validate`, `gui_backend.check_dependencies`, `gui_logic.wizard.WizardModel.needs_wizard`, `config.load_config`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_webui_api.py
from pathlib import Path

from npv_build.webui_api import WebUiApi


def test_get_state_shape(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(
            game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
            patch_override=None, check_updates=True,
        ),
    )
    monkeypatch.setattr(
        "npv_build.webui_api.check_dependencies",
        lambda game_dir: {"wolvenkit": True, "blender": False,
                          "npv_inject": True, "game_dir_valid": True},
    )
    state = WebUiApi().get_state()
    assert state["settings"]["game_dir"] == str(tmp_path)
    assert state["deps"]["blender"] is False
    assert isinstance(state["needs_onboarding"], bool)
    assert isinstance(state["version"], str)


def test_save_config_roundtrip(monkeypatch):
    saved = {}
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.save_settings",
                        lambda s: saved.update(vars(s)))
    monkeypatch.setattr("npv_build.webui_api.validate", lambda s: [])
    result = WebUiApi().save_config({"game_dir": "/g", "log_verbosity": 2})
    assert result == {"ok": True, "errors": []}
    assert saved["game_dir"] == "/g" and saved["log_verbosity"] == 2


def test_save_config_returns_validation_errors(monkeypatch):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.validate",
                        lambda s: ["game_dir does not exist"])
    result = WebUiApi().save_config({"game_dir": "/nope"})
    assert result == {"ok": False, "errors": ["game_dir does not exist"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_webui_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'npv_build.webui_api'`

- [ ] **Step 3: Write the bridge**

```python
# npv_build/webui_api.py
"""JSON bridge between the pywebview frontend and gui_logic/gui_backend.

Every public method returns JSON-serializable data only. This module must
stay import-safe without a webview (it is unit-tested headless).
"""

from __future__ import annotations

import logging
import queue
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from .config import load_config
from .gui_backend import check_dependencies
from .gui_logic.settings import load_settings, save_settings, validate
from .gui_logic.wizard import WizardModel

logger = logging.getLogger(__name__)


def _app_version() -> str:
    try:
        return pkg_version("npv-build")
    except PackageNotFoundError:
        return "dev"


class WebUiApi:
    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()

    def get_state(self) -> dict:
        s = load_settings()
        game_dir = Path(s.game_dir) if s.game_dir else None
        return {
            "settings": vars(s),
            "deps": check_dependencies(game_dir),
            "needs_onboarding": WizardModel.needs_wizard(load_config()),
            "version": _app_version(),
        }

    def save_config(self, cfg: dict) -> dict:
        s = load_settings()
        for key, value in cfg.items():
            if hasattr(s, key):
                setattr(s, key, value)
        errors = validate(s)
        if errors:
            return {"ok": False, "errors": errors}
        save_settings(s)
        return {"ok": True, "errors": []}
```

Note: if `load_config` does not exist under that name in `npv_build/config.py`, check the module and use its actual config-loading function; `WizardModel.needs_wizard(config: dict)` takes the loaded config dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_webui_api.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add npv_build/webui_api.py tests/test_webui_api.py
git commit -m "feat(webui): WebUiApi bridge — state, settings, dependency status"
```

---

### Task 2: Bridge — saves, mods

**Files:**
- Modify: `npv_build/webui_api.py`
- Test: `tests/test_webui_api.py`

**Interfaces:**
- Produces: `list_saves() -> list[dict]` (`{path, name, mtime, thumbnail}`), `preview_save(path: str) -> dict` (`{ok, body_rig, skin_tone, hair_style, hair_color, selections_count}` or `{ok: False, error, remediation}`), `list_mods() -> list[dict]` (`{mod_id, archive_path, installed}`), `install_mod(mod_id) -> dict`, `uninstall_mod(mod_id) -> dict`.
- Consumes: `gui_logic.discovery.list_saves`, `gui_backend.preview_save`, `gui_logic.modmanager.list_mods/install_mod/uninstall_mod`, `core.errors.NpvError`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_webui_api.py
def test_list_saves_serializes(monkeypatch, tmp_path):
    from npv_build.gui_logic.discovery import SaveEntry

    monkeypatch.setattr(
        "npv_build.webui_api.discover_saves",
        lambda: [SaveEntry(path=tmp_path / "sav.dat", name="AutoSave-0",
                           mtime=123.0, thumbnail=None)],
    )
    saves = WebUiApi().list_saves()
    assert saves == [{"path": str(tmp_path / "sav.dat"), "name": "AutoSave-0",
                      "mtime": 123.0, "thumbnail": None}]


def test_preview_save_ok(monkeypatch):
    monkeypatch.setattr(
        "npv_build.webui_api.preview_save_file",
        lambda p: {"body_rig": "pwa", "skin_tone": "03", "hair_style": "bob",
                   "hair_color": "copper", "selections_count": 152},
    )
    out = WebUiApi().preview_save("/s/sav.dat")
    assert out["ok"] is True and out["body_rig"] == "pwa"


def test_preview_save_error_is_structured(monkeypatch):
    from npv_build.core.errors import NpvError

    def boom(p):
        raise NpvError("Unsupported patch", remediation="Update mappings")

    monkeypatch.setattr("npv_build.webui_api.preview_save_file", boom)
    out = WebUiApi().preview_save("/s/sav.dat")
    assert out == {"ok": False, "error": "Unsupported patch",
                   "remediation": "Update mappings"}


def test_mod_roundtrip(monkeypatch, tmp_path):
    from npv_build.gui_logic.modmanager import ModEntry

    entry = ModEntry(mod_id="v_abc", archive_path=tmp_path / "v_abc.archive",
                     lua_path=tmp_path / "v_abc.lua", installed=False)
    installed = []
    monkeypatch.setattr("npv_build.webui_api.mm_list_mods",
                        lambda root, gd: [entry])
    monkeypatch.setattr("npv_build.webui_api.mm_install_mod",
                        lambda e, gd: installed.append(e.mod_id))
    api = WebUiApi()
    api._settings_for_mods = lambda: (tmp_path, tmp_path)  # test seam
    mods = api.list_mods()
    assert mods == [{"mod_id": "v_abc",
                     "archive_path": str(tmp_path / "v_abc.archive"),
                     "installed": False}]
    assert api.install_mod("v_abc") == {"ok": True}
    assert installed == ["v_abc"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_webui_api.py -v`
Expected: new tests FAIL with `AttributeError` (no `list_saves` on WebUiApi / import errors)

- [ ] **Step 3: Implement**

```python
# add to npv_build/webui_api.py imports
from .core.errors import NpvError
from .gui_backend import preview_save as preview_save_file
from .gui_logic.discovery import list_saves as discover_saves
from .gui_logic.modmanager import (
    install_mod as mm_install_mod,
    list_mods as mm_list_mods,
    uninstall_mod as mm_uninstall_mod,
)

# add methods to WebUiApi
    def list_saves(self) -> list[dict]:
        return [
            {"path": str(e.path), "name": e.name, "mtime": e.mtime,
             "thumbnail": str(e.thumbnail) if e.thumbnail else None}
            for e in discover_saves()
        ]

    def preview_save(self, path: str) -> dict:
        try:
            info = preview_save_file(Path(path))
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True, **info}

    def _settings_for_mods(self) -> tuple[Path, Path]:
        s = load_settings()
        output_root = Path(s.output_dir) if s.output_dir else Path.home() / "npv_builds"
        if not s.game_dir:
            raise NpvError("Game directory not configured.",
                           remediation="Set it in Settings.")
        return output_root, Path(s.game_dir)

    def list_mods(self) -> list[dict]:
        output_root, game_dir = self._settings_for_mods()
        return [
            {"mod_id": m.mod_id, "archive_path": str(m.archive_path),
             "installed": m.installed}
            for m in mm_list_mods(output_root, game_dir)
        ]

    def _find_mod(self, mod_id: str):
        output_root, game_dir = self._settings_for_mods()
        for m in mm_list_mods(output_root, game_dir):
            if m.mod_id == mod_id:
                return m, game_dir
        raise NpvError(f"Mod '{mod_id}' not found.",
                       remediation="Refresh the library.")

    def install_mod(self, mod_id: str) -> dict:
        try:
            entry, game_dir = self._find_mod(mod_id)
            mm_install_mod(entry, game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True}

    def uninstall_mod(self, mod_id: str) -> dict:
        try:
            entry, game_dir = self._find_mod(mod_id)
            mm_uninstall_mod(entry, game_dir)
        except NpvError as e:
            return {"ok": False, "error": e.user_message,
                    "remediation": e.remediation or ""}
        return {"ok": True}
```

Check `NpvError`'s constructor signature in `npv_build/core/errors.py` (`user_message`/`remediation` attribute names) and match it exactly.

- [ ] **Step 4: Run tests, then full suite**

Run: `uv run pytest tests/test_webui_api.py -v && uv run pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add npv_build/webui_api.py tests/test_webui_api.py
git commit -m "feat(webui): bridge saves discovery, preview, mod manager"
```

---

### Task 3: Bridge — build lifecycle with stage events

**Files:**
- Modify: `npv_build/gui_backend.py` (BuildWorker.on_event), `npv_build/webui_api.py`
- Test: `tests/test_webui_api.py`, `tests/test_gui_backend.py`

**Interfaces:**
- Produces: `start_build(req: dict) -> dict` (req keys: `save_path`, `npv_name`, `output_dir`, `clear_cache`, `resume`; fills `game_dir` from settings, `template_cache` from cache dir), `cancel_build() -> dict`, `poll_events() -> list[dict]` — each event one of `{"kind":"log","text":…}`, `{"kind":"progress","value":0..1}`, `{"kind":"stage","stage":name,"status":"started"|"completed"|"skipped"|"failed","message":…}`, `{"kind":"done","output_dir":…}`, `{"kind":"error","message":…}`.
- Consumes: `gui_backend.BuildWorker` (queue tuples `("log"|"progress"|"done"|"error", value)`), `config.get_cache_dir`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gui_backend.py
def test_build_worker_emits_stage_tuples(monkeypatch, tmp_path):
    """BuildWorker forwards stage_started/completed/skipped/failed as
    ("stage", {...}) tuples so the web UI can render a stage timeline."""

    class FakeService:
        def build(self, req, on_event=None, cancel=None):
            on_event(PipelineEvent(kind="stage_started", stage="parse_save", message="Parsing"))
            on_event(PipelineEvent(kind="stage_completed", stage="parse_save", message="ok"))

            class R:
                output_dir = str(tmp_path)

            return R()

    monkeypatch.setattr(gui_backend, "PipelineService", FakeService)
    q = queue_mod.Queue()
    w = gui_backend.BuildWorker(q)
    save = tmp_path / "s.dat"
    save.write_bytes(b"x")
    w.start(save_path=save, npv_name="V", output_dir=tmp_path, game_dir=tmp_path,
            template_cache=tmp_path, clear_cache=False)
    w._thread.join(timeout=10)
    items = _drain(q)
    stages = [val for kind, val in items if kind == "stage"]
    assert {"stage": "parse_save", "status": "started", "message": "Parsing"} in stages
    assert {"stage": "parse_save", "status": "completed", "message": "ok"} in stages
```

```python
# append to tests/test_webui_api.py
def test_poll_events_translates_queue(monkeypatch, tmp_path):
    api = WebUiApi()
    api._queue.put(("log", "[assemble] baking\n"))
    api._queue.put(("progress", 0.6))
    api._queue.put(("stage", {"stage": "assemble", "status": "started",
                              "message": "Assembling"}))
    api._queue.put(("done", "/out"))
    events = api.poll_events()
    assert events == [
        {"kind": "log", "text": "[assemble] baking\n"},
        {"kind": "progress", "value": 0.6},
        {"kind": "stage", "stage": "assemble", "status": "started",
         "message": "Assembling"},
        {"kind": "done", "output_dir": "/out"},
    ]
    assert api.poll_events() == []


def test_start_build_fills_context_and_starts_worker(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    started = {}

    class FakeWorker:
        def __init__(self, q):
            started["queue"] = q

        def start(self, **kwargs):
            started["kwargs"] = kwargs

        @property
        def is_alive(self):
            return False

    monkeypatch.setattr("npv_build.webui_api.BuildWorker", FakeWorker)
    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None,
                         log_verbosity=1, patch_override=None, check_updates=True),
    )
    api = WebUiApi()
    out = api.start_build({"save_path": str(tmp_path / "sav.dat"),
                           "npv_name": "V", "output_dir": str(tmp_path / "o"),
                           "clear_cache": False, "resume": False})
    assert out == {"ok": True}
    kw = started["kwargs"]
    assert kw["game_dir"] == Path(str(tmp_path))
    assert kw["npv_name"] == "V"
    assert str(kw["template_cache"]).endswith("templates")


def test_start_build_without_game_dir_errors(monkeypatch):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    out = WebUiApi().start_build({"save_path": "/s", "npv_name": "V",
                                  "output_dir": "/o"})
    assert out["ok"] is False and "Game directory" in out["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gui_backend.py::test_build_worker_emits_stage_tuples tests/test_webui_api.py -v`
Expected: FAIL (`stage` tuples absent; `poll_events`/`start_build` missing)

- [ ] **Step 3: Implement**

In `npv_build/gui_backend.py`, extend `on_event` inside `BuildWorker._run` (keep existing lines; add stage tuples):

```python
        def on_event(ev):
            # Non-checkpointed post-stages (e.g. "package") are not in STAGES;
            # log them but leave the progress bar where the last real stage put it.
            if ev.kind == "stage_started":
                self.queue.put(("log", f"[{ev.stage}] {ev.message}\n"))
                self.queue.put(("stage", {"stage": ev.stage, "status": "started",
                                          "message": ev.message}))
                if ev.stage in stages:
                    self.queue.put(("progress", stages.index(ev.stage) / len(stages)))
            elif ev.kind in ("stage_completed", "stage_skipped"):
                status = "completed" if ev.kind == "stage_completed" else "skipped"
                self.queue.put(("stage", {"stage": ev.stage, "status": status,
                                          "message": ev.message}))
                if ev.stage in stages:
                    self.queue.put(("progress", (stages.index(ev.stage) + 1) / len(stages)))
            elif ev.kind == "failed":
                self.queue.put(("log", f"[{ev.stage}] FAILED: {ev.message}\n"))
                self.queue.put(("stage", {"stage": ev.stage, "status": "failed",
                                          "message": ev.message}))
```

The old CTk `BuildView._poll_queue` ignores unknown tuple kinds only if it does; verify: it does `kind, val = get_nowait()` then `if kind == "log" … else: self.vm.on_event(kind, val)` and `BuildViewModel.on_event` ignores unknown kinds — safe.

In `npv_build/webui_api.py`:

```python
# add imports
from .config import get_cache_dir
from .gui_backend import BuildWorker

# add to WebUiApi.__init__
        self._worker: BuildWorker | None = None

# add methods
    def start_build(self, req: dict) -> dict:
        s = load_settings()
        if not s.game_dir:
            return {"ok": False, "error": "Game directory not configured.",
                    "remediation": "Set it in Settings."}
        self._worker = BuildWorker(self._queue)
        self._worker.start(
            save_path=Path(req["save_path"]),
            npv_name=req["npv_name"],
            output_dir=Path(req["output_dir"]),
            game_dir=Path(s.game_dir),
            template_cache=get_cache_dir() / "templates",
            clear_cache=bool(req.get("clear_cache", False)),
            resume=bool(req.get("resume", False)),
        )
        return {"ok": True}

    def cancel_build(self) -> dict:
        if self._worker is not None:
            self._worker.cancel()
        return {"ok": True}

    def poll_events(self) -> list[dict]:
        events: list[dict] = []
        while True:
            try:
                kind, val = self._queue.get_nowait()
            except queue.Empty:
                return events
            if kind == "log":
                events.append({"kind": "log", "text": val})
            elif kind == "progress":
                events.append({"kind": "progress", "value": val})
            elif kind == "stage":
                events.append({"kind": "stage", **val})
            elif kind == "done":
                events.append({"kind": "done", "output_dir": val})
            elif kind == "error":
                events.append({"kind": "error", "message": val})
```

- [ ] **Step 4: Run full suite**

Run: `uv run pytest -q`
Expected: all PASS (including old CTk gui tests — stage tuples are ignored by the old view model)

- [ ] **Step 5: Commit**

```bash
git add npv_build/gui_backend.py npv_build/webui_api.py tests/
git commit -m "feat(webui): build lifecycle bridge with typed stage events"
```

---

### Task 4: Frontend scaffold — tokens, store, rail

**Files:**
- Create: `npv_build/webui/index.html`, `npv_build/webui/app.css`, `npv_build/webui/js/store.js`, `npv_build/webui/js/rail.js`, `npv_build/webui/js/api.js`, `npv_build/webui/js/main.js`

**Interfaces:**
- Produces: `window.store` (`{state, set(patch), subscribe(fn)}`), `Api.call(method, ...args)` (awaits `window.pywebview.api[method]`, falls back to `window.__mockApi` for tests), rail rendering + screen switching by `store.state.screen` (`source|appearance|build|install|library|settings`). Each screen module registers `window.screens[name] = {render(el)}`.
- Consumes: bridge methods from Tasks 1–3.

- [ ] **Step 1: Write the files**

```html
<!-- npv_build/webui/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NPV Build</title>
<link rel="stylesheet" href="app.css">
</head>
<body>
<div id="app">
  <nav id="rail"></nav>
  <main id="screen"></main>
</div>
<script src="js/api.js"></script>
<script src="js/store.js"></script>
<script src="js/rail.js"></script>
<script src="js/source.js"></script>
<script src="js/appearance.js"></script>
<script src="js/build.js"></script>
<script src="js/install.js"></script>
<script src="js/library.js"></script>
<script src="js/settings.js"></script>
<script src="js/main.js"></script>
</body>
</html>
```

```css
/* npv_build/webui/app.css */
:root {
  --bg: #16161e; --surface: #1f2029; --surface-alt: #1a1b23;
  --border: #2a2c3a; --text: #c0caf5; --muted: #565f89;
  --accent: #7aa2f7; --amber: #e0af68; --ok: #9ece6a; --err: #f7768e;
  --radius: 10px; --radius-s: 8px;
  --pad-xs: 4px; --pad-s: 8px; --pad-m: 12px; --pad-l: 20px; --pad-xl: 32px;
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--bg); color: var(--text);
  font: 14px/1.5 system-ui, "Inter", "Segoe UI", sans-serif;
}
#app { display: flex; height: 100vh; }
#rail {
  width: 220px; background: var(--surface-alt);
  border-right: 1px solid var(--border);
  padding: var(--pad-l) var(--pad-m); flex-shrink: 0;
  display: flex; flex-direction: column; gap: var(--pad-xs);
}
#screen { flex: 1; overflow-y: auto; padding: var(--pad-xl); }
.rail-title { font-weight: 700; color: var(--accent); margin-bottom: var(--pad-l); }
.rail-item {
  padding: var(--pad-s) var(--pad-m); border-radius: var(--radius-s);
  color: var(--muted); cursor: pointer; user-select: none;
}
.rail-item.current { background: var(--surface); color: var(--text); }
.rail-item.done { color: var(--ok); }
.rail-item.locked { cursor: default; opacity: .5; }
.rail-sep { border-top: 1px solid var(--border); margin: var(--pad-m) 0; }
.rail-version { margin-top: auto; color: var(--muted); font-size: 11px; }
h1 { font-size: 20px; font-weight: 600; margin-bottom: var(--pad-xs); }
.subtitle { color: var(--muted); margin-bottom: var(--pad-l); }
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: var(--pad-m); margin-bottom: var(--pad-s);
}
.card.selectable { cursor: pointer; }
.card.selectable:hover, .card.selected { border-color: var(--accent); }
.row { display: flex; justify-content: space-between; align-items: center; gap: var(--pad-m); }
.muted { color: var(--muted); } .ok { color: var(--ok); } .err { color: var(--err); }
.badge {
  font-size: 11px; padding: 1px 8px; border-radius: 99px;
  border: 1px solid var(--border); color: var(--muted);
}
button {
  background: var(--accent); color: var(--bg); border: 0;
  border-radius: var(--radius-s); padding: var(--pad-s) var(--pad-l);
  font: inherit; font-weight: 600; cursor: pointer;
}
button.secondary { background: var(--surface); color: var(--text);
  border: 1px solid var(--border); }
button:disabled { opacity: .4; cursor: default; }
input[type=text], select {
  background: var(--surface-alt); color: var(--text);
  border: 1px solid var(--border); border-radius: var(--radius-s);
  padding: var(--pad-s) var(--pad-m); font: inherit; width: 100%;
}
label { display: block; color: var(--muted); font-size: 12px;
  margin: var(--pad-m) 0 var(--pad-xs); }
.error-card { border-color: var(--err); }
.error-card .remediation { color: var(--muted); margin-top: var(--pad-xs); }
.log {
  background: #0f0f14; border-radius: var(--radius-s); padding: var(--pad-m);
  font: 12px/1.6 ui-monospace, monospace; color: var(--muted);
  overflow-y: auto; height: 100%; white-space: pre-wrap;
}
.build-grid { display: grid; grid-template-columns: 300px 1fr;
  gap: var(--pad-l); height: calc(100vh - 160px); }
.stage { padding: var(--pad-xs) 0; }
.stage .time { float: right; color: var(--muted); font-size: 12px; }
.stage.pending { color: #3b3f51; } .stage.running { color: var(--accent); }
.stage.completed, .stage.skipped { color: var(--ok); } .stage.failed { color: var(--err); }
.progress { background: var(--surface); border-radius: 6px; height: 6px;
  margin: var(--pad-s) 0; }
.progress > div { background: var(--accent); height: 6px; border-radius: 6px;
  transition: width .3s; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--pad-m); }
```

```js
// npv_build/webui/js/api.js
"use strict";
const Api = {
  async call(method, ...args) {
    if (window.__mockApi) return window.__mockApi[method](...args);
    await Api._ready();
    return window.pywebview.api[method](...args);
  },
  _readyPromise: null,
  _ready() {
    if (window.pywebview) return Promise.resolve();
    if (!Api._readyPromise) {
      Api._readyPromise = new Promise((resolve) =>
        window.addEventListener("pywebviewready", resolve, { once: true }));
    }
    return Api._readyPromise;
  },
};
window.Api = Api;
```

```js
// npv_build/webui/js/store.js
"use strict";
window.store = {
  state: {
    screen: "source",
    stepsDone: { source: false, appearance: false, build: false },
    appState: null,            // get_state() payload
    save: null,                // selected save {path, name, preview}
    npvName: "", outputDir: "",
    build: { running: false, stages: [], log: "", error: null, outputDir: null },
  },
  _subs: [],
  set(patch) {
    Object.assign(this.state, patch);
    for (const fn of this._subs) fn(this.state);
  },
  subscribe(fn) { this._subs.push(fn); },
};
```

```js
// npv_build/webui/js/rail.js
"use strict";
const STEPS = [
  ["source", "1 · Source"], ["appearance", "2 · Appearance"],
  ["build", "3 · Build"], ["install", "4 · Install"],
];
const PAGES = [["library", "My NPVs"], ["settings", "Settings"]];
const STEP_ORDER = ["source", "appearance", "build", "install"];

function stepUnlocked(name, s) {
  const idx = STEP_ORDER.indexOf(name);
  if (idx <= 0) return true;
  return STEP_ORDER.slice(0, idx).every((n) => s.stepsDone[n]);
}

function renderRail(s) {
  const el = document.getElementById("rail");
  el.innerHTML = "";
  const title = document.createElement("div");
  title.className = "rail-title"; title.textContent = "NPV BUILD";
  el.appendChild(title);
  for (const [name, label] of STEPS) {
    const item = document.createElement("div");
    const unlocked = stepUnlocked(name, s);
    item.className = "rail-item"
      + (s.screen === name ? " current" : "")
      + (s.stepsDone[name] ? " done" : "")
      + (unlocked ? "" : " locked");
    item.textContent = (s.stepsDone[name] ? "✓ " : "") + label;
    if (unlocked) item.onclick = () => store.set({ screen: name });
    el.appendChild(item);
  }
  const sep = document.createElement("div");
  sep.className = "rail-sep"; el.appendChild(sep);
  for (const [name, label] of PAGES) {
    const item = document.createElement("div");
    item.className = "rail-item" + (s.screen === name ? " current" : "");
    item.textContent = label;
    item.onclick = () => store.set({ screen: name });
    el.appendChild(item);
  }
  const v = document.createElement("div");
  v.className = "rail-version";
  v.textContent = s.appState ? `v${s.appState.version}` : "";
  el.appendChild(v);
}
window.renderRail = renderRail;
```

```js
// npv_build/webui/js/main.js
"use strict";
window.screens = window.screens || {};
function renderApp(s) {
  renderRail(s);
  const el = document.getElementById("screen");
  const screen = window.screens[s.screen];
  el.innerHTML = "";
  if (screen) screen.render(el, s);
}
store.subscribe(renderApp);
(async function init() {
  const appState = await Api.call("get_state");
  const patch = { appState };
  if (appState.needs_onboarding) patch.screen = "settings";
  store.set(patch);
})();
```

- [ ] **Step 2: Create placeholder screen modules so the page loads**

Each of `source.js`, `appearance.js`, `build.js`, `install.js`, `library.js`, `settings.js` starts as (replace NAME/Title per file; Tasks 5–8 flesh them out):

```js
// npv_build/webui/js/NAME.js
"use strict";
window.screens = window.screens || {};
window.screens.NAME = {
  render(el) {
    el.innerHTML = "<h1>Title</h1><p class='subtitle'>Coming in a later task.</p>";
  },
};
```

- [ ] **Step 3: Verify manually in a browser**

Run: `cd /home/pdp/npv_project/npv_build/webui && python3 -m http.server 8901` then open `http://localhost:8901` with `window.__mockApi = {get_state: async () => ({settings:{},deps:{},needs_onboarding:false,version:"dev"})}` pasted in the console before reload (or temporarily in index.html).
Expected: dark rail with 4 steps + My NPVs/Settings, screen area renders placeholder. Steps 2–4 appear locked.

- [ ] **Step 4: Commit**

```bash
git add npv_build/webui/
git commit -m "feat(webui): static frontend scaffold — tokens, store, rail, screen registry"
```

---

### Task 5: Source screen (save discovery + preview + from-scratch stub)

**Files:**
- Modify: `npv_build/webui/js/source.js`

**Interfaces:**
- Consumes: `Api.call("list_saves")`, `Api.call("preview_save", path)`.
- Produces: on Continue → `store.set({save, npvName, outputDir, stepsDone:{...source:true}, screen:"appearance"})`. From-scratch mode renders a disabled card labeled "From scratch — coming soon" (plan 3).

- [ ] **Step 1: Implement the screen**

```js
// npv_build/webui/js/source.js
"use strict";
window.screens = window.screens || {};
window.screens.source = {
  saves: null,
  async load() {
    this.saves = await Api.call("list_saves");
    store.set({});
  },
  render(el, s) {
    if (this.saves === null) {
      el.innerHTML = "<h1>Source</h1><p class='subtitle'>Scanning for saves…</p>";
      this.load();
      return;
    }
    el.innerHTML = "<h1>Source</h1>" +
      "<p class='subtitle'>Pick the save to turn into an NPC, or start from scratch.</p>";
    const list = document.createElement("div");
    for (const save of this.saves) {
      const card = document.createElement("div");
      card.className = "card selectable" +
        (s.save && s.save.path === save.path ? " selected" : "");
      const date = new Date(save.mtime * 1000).toLocaleString();
      card.innerHTML = `<div class="row"><strong>${save.name}</strong>` +
        `<span class="muted">${date}</span></div>` +
        `<div class="muted preview">…</div>`;
      card.onclick = () => this.pick(save, card);
      list.appendChild(card);
    }
    const scratch = document.createElement("div");
    scratch.className = "card";
    scratch.style.opacity = ".5";
    scratch.innerHTML = "<strong>From scratch</strong>" +
      "<div class='muted'>Start from the default V preset — coming soon.</div>";
    list.appendChild(scratch);
    el.appendChild(list);

    const form = document.createElement("div");
    form.innerHTML = `
      <label>NPV name (AMM spawn label)</label>
      <input type="text" id="npv-name" value="${s.npvName || ""}">
      <label>Output directory</label>
      <input type="text" id="output-dir" value="${s.outputDir || ""}">`;
    el.appendChild(form);

    const cont = document.createElement("button");
    cont.textContent = "Continue →";
    cont.style.marginTop = "16px";
    cont.disabled = !(s.save && s.save.preview && s.save.preview.ok);
    cont.onclick = () => {
      const npvName = document.getElementById("npv-name").value.trim();
      const outputDir = document.getElementById("output-dir").value.trim();
      if (!npvName || !outputDir) return;
      store.set({
        npvName, outputDir,
        stepsDone: { ...store.state.stepsDone, source: true },
        screen: "appearance",
      });
    };
    el.appendChild(cont);
  },
  async pick(save, card) {
    card.querySelector(".preview").textContent = "Parsing…";
    const preview = await Api.call("preview_save", save.path);
    if (!preview.ok) {
      store.set({ save: null });
      card.classList.add("error-card");
      card.querySelector(".preview").innerHTML =
        `<span class="err">${preview.error}</span>` +
        `<div class="remediation">${preview.remediation}</div>`;
      return;
    }
    const defaults = {};
    if (!store.state.npvName) defaults.npvName = save.name;
    if (!store.state.outputDir && store.state.appState.settings.output_dir)
      defaults.outputDir = store.state.appState.settings.output_dir + "/" + save.name;
    store.set({ save: { ...save, preview }, ...defaults });
  },
};
```

- [ ] **Step 2: Verify manually**

Same http.server + `window.__mockApi` with `list_saves`/`preview_save` mocks returning two saves (one previewing ok, one erroring). Expected: cards render, error save shows inline red card with remediation, Continue enables only with a good save + name + output dir, Continue advances to Appearance and marks step 1 done in rail.

- [ ] **Step 3: Commit**

```bash
git add npv_build/webui/js/source.js
git commit -m "feat(webui): source screen — save cards, inline preview, from-scratch stub"
```

---

### Task 6: Appearance placeholder + Build screen

**Files:**
- Modify: `npv_build/webui/js/appearance.js`, `npv_build/webui/js/build.js`

**Interfaces:**
- Appearance (placeholder until plan 2): shows read-only preview summary (`rig/skin/hair/selections` from `store.state.save.preview`); Continue sets `stepsDone.appearance` and goes to build.
- Build: consumes `Api.call("start_build", req)`, `Api.call("poll_events")` (200ms interval while running), `Api.call("cancel_build")`. Stage list order: `["parse_save","resolve_assets","assemble","emit_amm_lua","emit_photomode","package"]` with labels `["Parse save","Resolve assets","Assemble mod","AMM script","Photo Mode files","Package zip"]`. On `done` → `stepsDone.build=true`, screen `install`. On `error` → failed stage red + Retry button (re-calls start_build with `resume:true`).

- [ ] **Step 1: Implement appearance placeholder**

```js
// npv_build/webui/js/appearance.js
"use strict";
window.screens = window.screens || {};
window.screens.appearance = {
  render(el, s) {
    const p = s.save ? s.save.preview : null;
    el.innerHTML = "<h1>Appearance</h1>" +
      "<p class='subtitle'>Full inspector with overrides arrives in the next milestone. " +
      "Review the decoded summary below.</p>";
    if (p) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML =
        `<div class="row"><span>Body rig</span><strong>${p.body_rig}</strong></div>` +
        `<div class="row"><span>Skin tone</span><strong>${p.skin_tone}</strong></div>` +
        `<div class="row"><span>Hair</span><strong>${p.hair_style} (${p.hair_color})</strong></div>` +
        `<div class="row"><span>Decoded selections</span><strong>${p.selections_count}</strong></div>`;
      el.appendChild(card);
    }
    const cont = document.createElement("button");
    cont.textContent = "Continue →";
    cont.onclick = () => store.set({
      stepsDone: { ...store.state.stepsDone, appearance: true },
      screen: "build",
    });
    el.appendChild(cont);
  },
};
```

- [ ] **Step 2: Implement build screen**

```js
// npv_build/webui/js/build.js
"use strict";
window.screens = window.screens || {};
const STAGE_DEFS = [
  ["parse_save", "Parse save"], ["resolve_assets", "Resolve assets"],
  ["assemble", "Assemble mod"], ["emit_amm_lua", "AMM script"],
  ["emit_photomode", "Photo Mode files"], ["package", "Package zip"],
];
window.screens.build = {
  timer: null,
  starts: {},
  async start(resume) {
    const s = store.state;
    store.set({ build: { running: true, stages: {}, log: "", error: null,
                         outputDir: null, progress: 0 } });
    this.starts = {};
    const out = await Api.call("start_build", {
      save_path: s.save.path, npv_name: s.npvName, output_dir: s.outputDir,
      clear_cache: false, resume: !!resume,
    });
    if (!out.ok) {
      store.set({ build: { ...store.state.build, running: false,
                           error: out.error + "\n" + (out.remediation || "") } });
      return;
    }
    this.timer = setInterval(() => this.poll(), 200);
  },
  async poll() {
    const events = await Api.call("poll_events");
    if (!events.length) return;
    const b = { ...store.state.build };
    for (const ev of events) {
      if (ev.kind === "log") b.log += ev.text;
      else if (ev.kind === "progress") b.progress = ev.value;
      else if (ev.kind === "stage") {
        if (ev.status === "started") this.starts[ev.stage] = Date.now();
        const secs = this.starts[ev.stage]
          ? ((Date.now() - this.starts[ev.stage]) / 1000).toFixed(0) + "s" : "";
        b.stages = { ...b.stages,
          [ev.stage]: { status: ev.status, message: ev.message, time: secs } };
      } else if (ev.kind === "done") {
        b.running = false; b.outputDir = ev.output_dir;
        clearInterval(this.timer);
        store.set({ build: b,
          stepsDone: { ...store.state.stepsDone, build: true },
          screen: "install" });
        return;
      } else if (ev.kind === "error") {
        b.running = false; b.error = ev.message;
        clearInterval(this.timer);
      }
    }
    store.set({ build: b });
  },
  render(el, s) {
    const b = s.build;
    el.innerHTML = `<h1>Build</h1><p class="subtitle">Building “${s.npvName}”</p>`;
    const grid = document.createElement("div");
    grid.className = "build-grid";
    const left = document.createElement("div");
    for (const [key, label] of STAGE_DEFS) {
      const st = (b.stages || {})[key];
      const cls = !st ? "pending"
        : st.status === "started" ? "running"
        : st.status === "failed" ? "failed"
        : st.status;  // completed | skipped
      const mark = { pending: "○", running: "●", completed: "✓",
                     skipped: "✓", failed: "✗" }[cls];
      const div = document.createElement("div");
      div.className = "stage " + cls;
      div.innerHTML = `${mark} ${label}<span class="time">${st ? st.time : ""}</span>` +
        (st && st.status === "started"
          ? `<div class="progress"><div style="width:${(b.progress * 100) | 0}%"></div></div>
             <div class="muted" style="font-size:12px">${st.message}</div>` : "") +
        (st && st.status === "failed"
          ? `<div class="err" style="font-size:12px">${st.message}</div>` : "");
      left.appendChild(div);
    }
    if (b.error) {
      const errCard = document.createElement("div");
      errCard.className = "card error-card";
      errCard.innerHTML = `<span class="err">${b.error}</span>`;
      left.appendChild(errCard);
      const retry = document.createElement("button");
      retry.textContent = "Retry from failed stage";
      retry.onclick = () => this.start(true);
      left.appendChild(retry);
    } else if (b.running) {
      const cancel = document.createElement("button");
      cancel.className = "secondary"; cancel.textContent = "Cancel";
      cancel.onclick = () => Api.call("cancel_build");
      left.appendChild(cancel);
    } else if (!b.outputDir) {
      const startBtn = document.createElement("button");
      startBtn.textContent = "Start build";
      startBtn.onclick = () => this.start(false);
      left.appendChild(startBtn);
    }
    const log = document.createElement("div");
    log.className = "log"; log.textContent = b.log || "";
    grid.appendChild(left); grid.appendChild(log);
    el.appendChild(grid);
    log.scrollTop = log.scrollHeight;
  },
};
```

- [ ] **Step 3: Verify manually with a scripted mock**

http.server + `window.__mockApi` where `start_build` returns `{ok:true}` and successive `poll_events` calls replay a canned build (stage started/completed for each stage, log lines, then `done`) followed by an error variant. Expected: timeline advances with timers, log streams, done → Install screen; error variant shows red stage + Retry.

- [ ] **Step 4: Commit**

```bash
git add npv_build/webui/js/appearance.js npv_build/webui/js/build.js
git commit -m "feat(webui): appearance summary placeholder + build timeline/log screen"
```

---

### Task 7: Install screen + Library screen

**Files:**
- Modify: `npv_build/webui/js/install.js`, `npv_build/webui/js/library.js`

**Interfaces:**
- Install consumes `store.state.build.outputDir`, `Api.call("list_mods")`, `Api.call("install_mod", mod_id)`; "Build another" resets flow state. Library consumes `list_mods`/`install_mod`/`uninstall_mod`.

- [ ] **Step 1: Implement install screen**

```js
// npv_build/webui/js/install.js
"use strict";
window.screens = window.screens || {};
window.screens.install = {
  render(el, s) {
    el.innerHTML = "<h1>Done</h1>" +
      `<p class="subtitle">“${s.npvName}” built successfully.</p>`;
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<div class="row"><span>Output</span>` +
      `<strong>${s.build.outputDir || ""}</strong></div>` +
      `<div class="muted">The mod zip inside is ready for AMM: spawn it from ` +
      `Appearance Menu Mod → Custom Entities after installing.</div>`;
    el.appendChild(card);
    const row = document.createElement("div");
    row.className = "row"; row.style.marginTop = "16px";
    const install = document.createElement("button");
    install.textContent = "Install to game";
    install.onclick = async () => {
      const mods = await Api.call("list_mods");
      const mine = mods.find((m) => s.build.outputDir &&
        m.archive_path.startsWith(s.build.outputDir));
      const out = mine ? await Api.call("install_mod", mine.mod_id)
                       : { ok: false, error: "Build not found in library." };
      install.textContent = out.ok ? "Installed ✓" : "Failed";
      if (!out.ok) install.classList.add("err");
    };
    const again = document.createElement("button");
    again.className = "secondary"; again.textContent = "Build another";
    again.onclick = () => store.set({
      save: null, npvName: "", outputDir: "",
      stepsDone: { source: false, appearance: false, build: false },
      build: { running: false, stages: {}, log: "", error: null, outputDir: null },
      screen: "source",
    });
    row.appendChild(install); row.appendChild(again);
    el.appendChild(row);
  },
};
```

- [ ] **Step 2: Implement library screen**

```js
// npv_build/webui/js/library.js
"use strict";
window.screens = window.screens || {};
window.screens.library = {
  mods: null,
  async load() { this.mods = await Api.call("list_mods"); store.set({}); },
  render(el) {
    if (this.mods === null) {
      el.innerHTML = "<h1>My NPVs</h1><p class='subtitle'>Loading…</p>";
      this.load();
      return;
    }
    el.innerHTML = "<h1>My NPVs</h1>" +
      "<p class='subtitle'>Built NPVs found in your output directory.</p>";
    const grid = document.createElement("div");
    grid.className = "grid";
    for (const mod of this.mods) {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `<strong>${mod.mod_id}</strong>` +
        `<div style="margin:8px 0"><span class="badge">` +
        `${mod.installed ? "installed" : "built"}</span></div>`;
      const btn = document.createElement("button");
      btn.className = mod.installed ? "secondary" : "";
      btn.textContent = mod.installed ? "Uninstall" : "Install";
      btn.onclick = async () => {
        const method = mod.installed ? "uninstall_mod" : "install_mod";
        const out = await Api.call(method, mod.mod_id);
        if (out.ok) this.load();
        else btn.textContent = out.error;
      };
      card.appendChild(btn);
      grid.appendChild(card);
    }
    if (!this.mods.length) {
      grid.innerHTML = "<p class='muted'>Nothing built yet.</p>";
    }
    el.appendChild(grid);
  },
};
```

- [ ] **Step 3: Verify manually with mocks; commit**

Expected: install screen buttons work against mock; library refreshes state after install/uninstall (fixes the old stale-tab bug by re-fetching on every action).

```bash
git add npv_build/webui/js/install.js npv_build/webui/js/library.js
git commit -m "feat(webui): install and library screens with live refresh"
```

---

### Task 8: Settings screen + onboarding

**Files:**
- Modify: `npv_build/webui/js/settings.js`

**Interfaces:**
- Consumes: `store.state.appState`, `Api.call("save_config", cfg)`, `Api.call("get_state")`. Onboarding = same screen with a banner when `appState.needs_onboarding`; saving valid config with all deps green clears it (re-fetch `get_state`).

- [ ] **Step 1: Implement**

```js
// npv_build/webui/js/settings.js
"use strict";
window.screens = window.screens || {};
window.screens.settings = {
  render(el, s) {
    const st = s.appState || { settings: {}, deps: {}, needs_onboarding: false };
    el.innerHTML = "<h1>Settings</h1>";
    if (st.needs_onboarding) {
      const banner = document.createElement("div");
      banner.className = "card";
      banner.innerHTML = "<strong>Welcome!</strong> " +
        "<span class='muted'>Point npv-build at your Cyberpunk 2077 install " +
        "to get started.</span>";
      el.appendChild(banner);
    }
    const deps = document.createElement("div");
    deps.className = "card";
    deps.innerHTML = Object.entries(st.deps).map(([name, ok]) =>
      `<div class="row"><span>${name}</span>` +
      `<span class="${ok ? "ok" : "err"}">${ok ? "✓ found" : "✗ missing"}</span></div>`
    ).join("");
    el.appendChild(deps);
    const form = document.createElement("div");
    form.innerHTML = `
      <label>Cyberpunk 2077 game directory</label>
      <input type="text" id="cfg-game-dir" value="${st.settings.game_dir || ""}">
      <label>Default output directory</label>
      <input type="text" id="cfg-output-dir" value="${st.settings.output_dir || ""}">`;
    el.appendChild(form);
    const err = document.createElement("p");
    err.className = "err";
    const save = document.createElement("button");
    save.textContent = "Save settings";
    save.style.marginTop = "16px";
    save.onclick = async () => {
      const out = await Api.call("save_config", {
        game_dir: document.getElementById("cfg-game-dir").value.trim() || null,
        output_dir: document.getElementById("cfg-output-dir").value.trim() || null,
      });
      if (!out.ok) { err.textContent = out.errors.join("; "); return; }
      store.set({ appState: await Api.call("get_state") });
    };
    el.appendChild(save);
    el.appendChild(err);
  },
};
```

- [ ] **Step 2: Verify manually with mocks; commit**

Expected: dep lamps render, save round-trips, validation errors display, onboarding banner clears after a valid save.

```bash
git add npv_build/webui/js/settings.js
git commit -m "feat(webui): settings screen with dependency lamps and onboarding banner"
```

---

### Task 9: pywebview shell + entrypoint swap

**Files:**
- Create: `npv_build/webui_shell.py`
- Modify: `pyproject.toml` (gui-scripts + gui extra)
- Test: `tests/test_webui_shell.py`

**Interfaces:**
- Produces: `webui_shell.main()` — checks webview availability, creates `webview.create_window("NPV Build", <webui/index.html>, js_api=WebUiApi())`, `webview.start()`. `webui_dir() -> Path` resolves the static dir (works installed and from source). `[project.gui-scripts] npv-build-gui = "npv_build.webui_shell:main"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_webui_shell.py
from pathlib import Path


def test_webui_dir_exists_and_has_index():
    from npv_build.webui_shell import webui_dir

    d = webui_dir()
    assert (d / "index.html").is_file()
    assert (d / "app.css").is_file()
    assert (d / "js" / "main.js").is_file()


def test_main_reports_missing_webview(monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def no_webview(name, *a, **kw):
        if name == "webview":
            raise ImportError("No module named 'webview'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_webview)
    from npv_build.webui_shell import main

    assert main() == 1
    out = capsys.readouterr().err
    assert "pywebview" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_webui_shell.py -v`
Expected: FAIL — no module `npv_build.webui_shell`

- [ ] **Step 3: Implement**

```python
# npv_build/webui_shell.py
"""pywebview entry point for the npv-build GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from .webui_api import WebUiApi


def webui_dir() -> Path:
    return Path(__file__).parent / "webui"


def main() -> int:
    try:
        import webview
    except ImportError:
        print(
            "npv-build-gui needs pywebview (and WebKitGTK on Linux).\n"
            "Install with: uv sync --extra gui\n"
            "On Debian/Ubuntu also: sudo apt install gir1.2-webkit2-4.1",
            file=sys.stderr,
        )
        return 1
    webview.create_window(
        "NPV Build",
        url=str(webui_dir() / "index.html"),
        js_api=WebUiApi(),
        width=1200,
        height=800,
        min_size=(900, 600),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

In `pyproject.toml`: change `[project.gui-scripts] npv-build-gui = "npv_build.gui:main"` → `"npv_build.webui_shell:main"`; add `pywebview>=5.0` to the `gui` extra (keep `customtkinter`/`tkinterdnd2` until Task 10). Ensure `npv_build/webui/**` ships in the wheel: with hatchling defaults package data is included; verify `uv build && unzip -l dist/*.whl | grep webui` lists the files, else add a `[tool.hatch.build]` include (or the equivalent for the configured backend — check `[build-system]` in pyproject.toml).

- [ ] **Step 4: Run tests, sync, launch for real**

Run: `uv run pytest tests/test_webui_shell.py -v && uv sync --extra gui && uv run npv-build-gui`
Expected: tests PASS; a native window opens with the rail + source screen listing real saves. Do a real end-to-end build through the new GUI (this is the parity gate — verify build runs, log streams, install works).

- [ ] **Step 5: Commit**

```bash
git add npv_build/webui_shell.py pyproject.toml uv.lock tests/test_webui_shell.py
git commit -m "feat(webui): pywebview shell; npv-build-gui now launches the web UI"
```

---

### Task 10: Playwright smoke test + CTk removal

**Files:**
- Create: `tests/webui_smoke/test_webui_smoke.py`, `tests/webui_smoke/mock_api.js`
- Delete: `npv_build/gui.py`, `npv_build/gui_views/`, `npv_build/gui_theme.py`, `tests/gui_logic/test_build_view.py`, `tests/gui_logic/test_gui_smoke.py`, `tests/gui_logic/test_gui_parity.py`, `tests/gui_logic/test_gui_theme.py`, `tests/gui_logic/test_no_arial.py`, `tests/gui_logic/test_save_browser_view.py`, `tests/gui_logic/test_wizard.py` (only its view-specific tests — keep `WizardModel` logic tests; check the file and split if mixed)
- Modify: `pyproject.toml` (drop `customtkinter`, `tkinterdnd2`; add `playwright` + `pytest-playwright` to dev group), `.github/workflows/*` (`gui-smoke` job: replace xvfb CTk launch with Playwright run), `tests/test_gui_backend.py` (remove `_STAGES` coupling if `gui.py` import breaks — `gui_backend` itself stays)

**Interfaces:**
- Consumes: the full frontend + `window.__mockApi` seam from Task 4.

- [ ] **Step 1: Write the smoke test**

```js
// tests/webui_smoke/mock_api.js — injected before page scripts
window.__mockApi = {
  get_state: async () => ({
    settings: { game_dir: "/g", output_dir: "/out" },
    deps: { wolvenkit: true, blender: true, npv_inject: true, game_dir_valid: true },
    needs_onboarding: false, version: "test",
  }),
  list_saves: async () => [
    { path: "/saves/a/sav.dat", name: "ManualSave-3", mtime: 1752800000, thumbnail: null },
  ],
  preview_save: async () => ({ ok: true, body_rig: "pwa", skin_tone: "03",
    hair_style: "bob", hair_color: "copper", selections_count: 152 }),
  start_build: async () => ({ ok: true }),
  _polls: 0,
  poll_events: async function () {
    this._polls += 1;
    if (this._polls === 1) return [
      { kind: "stage", stage: "parse_save", status: "started", message: "Parsing" },
      { kind: "log", text: "[parse_save] Parsing...\n" },
      { kind: "stage", stage: "parse_save", status: "completed", message: "ok" },
    ];
    if (this._polls === 2) return [{ kind: "done", output_dir: "/out/v" }];
    return [];
  },
  list_mods: async () => [{ mod_id: "v_abc", archive_path: "/out/v/v_abc.archive",
                            installed: false }],
  install_mod: async () => ({ ok: true }),
  cancel_build: async () => ({ ok: true }),
};
```

```python
# tests/webui_smoke/test_webui_smoke.py
"""End-to-end flow through the static frontend with a mocked bridge.

Requires: uv run playwright install chromium
"""
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

WEBUI = Path(__file__).parents[2] / "npv_build" / "webui"
MOCK = Path(__file__).parent / "mock_api.js"


@pytest.fixture
def webui_server():
    handler = partial(SimpleHTTPRequestHandler, directory=str(WEBUI))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_full_flow_source_to_install(webui_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(path=str(MOCK))
        page.goto(webui_server)
        expect(page.locator(".rail-title")).to_have_text("NPV BUILD")
        page.locator(".card.selectable").click()
        expect(page.locator(".preview")).to_contain_text("pwa")
        page.fill("#npv-name", "TestV")
        page.fill("#output-dir", "/out/v")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Appearance")
        page.click("text=Continue →")
        expect(page.locator("h1")).to_have_text("Build")
        page.click("text=Start build")
        expect(page.locator("h1")).to_have_text("Done", timeout=5000)
        page.click("text=Install to game")
        expect(page.locator("text=Installed ✓")).to_be_visible()
        browser.close()
```

Note: the mock's `preview_save` must also set the preview line — extend `source.js` pick() renders `body_rig` into `.preview` on success:

```js
    // in source.js pick(), after store.set on success:
    card.querySelector(".preview").textContent =
      `${preview.body_rig} · skin ${preview.skin_tone} · ${preview.hair_style}`;
```

- [ ] **Step 2: Run the smoke test**

Run: `uv add --dev playwright pytest-playwright && uv run playwright install chromium && uv run pytest tests/webui_smoke/ -v`
Expected: PASS

- [ ] **Step 3: Delete the CTk GUI**

Remove files listed above. Check `tests/gui_logic/test_wizard.py`, `test_modmanager.py`, `test_settings.py`, `test_discovery.py` — they test `gui_logic` (keep); delete only tests importing `gui_views` or `gui` or `gui_theme`. `gui_backend.py` keeps `_STAGES` (still used for progress events). Drop `customtkinter` + `tkinterdnd2` from the `gui` extra. Grep before deleting:

Run: `grep -rn "gui_theme\|gui_views\|from .gui import\|from npv_build.gui import" npv_build/ tests/ docs/release-qa.md`
Expected after cleanup: no hits in `npv_build/` or `tests/`.

- [ ] **Step 4: Update CI**

In the workflow with the `gui-smoke` job: replace the xvfb CTk smoke with `playwright install chromium --with-deps` + `uv run pytest tests/webui_smoke/`. Keep xvfb only if the pywebview import-check test needs a display (it does not — it never calls `webview.start()` in CI).

- [ ] **Step 5: Full suite + lint, then commit**

Run: `uv sync --extra gui && uv run pytest -q && uv run ruff check .`
Expected: all PASS, no references to deleted modules

```bash
git add -A
git commit -m "feat(webui)!: retire customtkinter GUI; Playwright smoke covers web UI"
```

---

### Task 11: Docs

**Files:**
- Modify: `CLAUDE.md` (Architecture: replace gui.py/gui_views mentions with webui_shell/webui_api/webui; commands: note `npv-build-gui` launches pywebview), `README.md` (GUI section, Linux webkit2gtk note), `docs/release-qa.md` (QA steps reference new GUI flow)

- [ ] **Step 1: Update the three docs to match the new architecture; commit**

```bash
git add CLAUDE.md README.md docs/release-qa.md
git commit -m "docs: web UI architecture, launch and QA notes"
```

---

## Self-Review Notes

- Spec coverage in THIS plan: architecture/bridge (T1–T3), screens & flow minus inspector (T4–T8), errors inline (T2/T5/T6), shell + distribution basics (T9), testing incl. Playwright + CI (T10), docs (T11). Deliberately deferred to plans 2–4: appearance inspector rows/overrides, presets/`load_preset`, clothing catalog/thumbnails. AppImage/PyInstaller packaging changes land in the existing M6 release work, gated on this plan.
- Verify-before-use notes are embedded where the implementer must confirm a signature (`load_config` name, `NpvError` fields, wheel data inclusion, wizard test split) — these are checks against the real codebase, not open design questions.
