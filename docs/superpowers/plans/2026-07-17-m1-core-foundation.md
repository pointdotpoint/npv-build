# M1 — Core Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `npv_build/core/` layer — typed errors, logging, cancellable subprocess adapter, platform discovery, and a checkpointing `PipelineService` — and rewire the CLI and GUI backend onto it; milestone M1 of `docs/superpowers/specs/2026-07-17-npv-build-2.0-design.md`.

**Architecture:** New `npv_build/core/` package with five modules (`errors`, `cancel`, `proc`, `logging_setup`, `platform`) plus `pipeline.py`. Existing pipeline functions (`parse_save`, `resolve_assets`, `build_project`, …) keep their signatures; the service wraps them as named stages with a checkpoint manifest. All subprocess calls migrate to one `run_tool()` with timeouts and cancellation. All `print()` calls migrate to `logging`. All blind excepts are eliminated (ruff `BLE001` becomes a CI gate).

**Tech Stack:** stdlib only for core (threading, subprocess, logging, hashlib, json); pytest; ruff.

## Global Constraints (from spec)

- Python floor **3.11**; run everything via `uv run <cmd>`.
- **Hard-fail policy (ERR-2):** no handler may silently continue with degraded output. The ONLY sanctioned catch-and-continue sites are scans of *optional third-party mod archives* (explicitly listed in Task 5), which must log a WARNING naming the archive and skip only that archive.
- Game depot paths keep Windows backslashes in string content — never alter them.
- **No CDPR game bytes** in the repo.
- Mod ID stays a deterministic hash of `(npv_name, cc_settings)` (NFR-5) — do not change `compute_mod_id`.
- Do not modify the `WolvenKit/` submodule.
- Every task leaves `uv run pytest -q`, `uv run ruff check .`, and `uv run ruff format --check .` green (test count grows from the current 69 passed / 1 skipped).
- Public signatures of existing pipeline functions (`parse_save`, `resolve_assets`, `bake_head`, `resolve_clothing`, `build_project`, `write_components_json`, `write_readme`, `build_app_template`, `build_ent_from_donor`) must NOT change in M1.
- Timeout defaults (ADP-2): WolvenKit operations 600 s; Blender 900 s; dotnet install/build 900 s; unrar 300 s; everything else 120 s.
- New core modules get full type hints; `ty`/mypy adoption is deferred, but write hints as if it were on.

## Plan Roadmap

Plan 2 of 7 (M0 merged as `ab66f9a..bb83041`). Tasks 1–3 are pure additions (safe order). Tasks 4–9 migrate existing modules onto core. Tasks 10–13 add platform + pipeline service and rewire the frontends. Task 14 is docs. Sequential execution; no task may be reordered past one it consumes interfaces from.

---

### Task 1: Error hierarchy (`core/errors.py`)

**Files:**
- Create: `npv_build/core/__init__.py` (empty)
- Create: `npv_build/core/errors.py`
- Test: `tests/core/test_errors.py` (create `tests/core/__init__.py` empty too)

**Interfaces:**
- Consumes: nothing.
- Produces: `NpvError(user_message, *, remediation="", details="", module_name="")` with attributes of the same names and `__str__` returning `user_message` (plus `"\n" + details` when details is non-empty). Subclasses (same signature): `SaveFormatError`, `UnsupportedPatchError`, `MappingResolutionError`, `ToolError` (adds kwargs `tool=""`, `argv=()`, `exit_code=None`), `ToolTimeoutError(ToolError)`, `BakeVerificationError`, `InstallError`, `SecurityError`, `PipelineCancelled`. Every later task imports from `npv_build.core.errors`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_errors.py
import pytest

from npv_build.core.errors import (
    InstallError,
    NpvError,
    PipelineCancelled,
    SaveFormatError,
    SecurityError,
    ToolError,
    ToolTimeoutError,
    UnsupportedPatchError,
)


def test_npv_error_fields_and_str():
    e = NpvError("Save file unreadable", remediation="Re-copy the save", details="bad header", module_name="Save Parser")
    assert e.user_message == "Save file unreadable"
    assert e.remediation == "Re-copy the save"
    assert e.module_name == "Save Parser"
    assert str(e) == "Save file unreadable\nbad header"


def test_str_without_details():
    assert str(NpvError("boom")) == "boom"


def test_tool_error_fields():
    e = ToolError("WolvenKit failed", tool="WolvenKit.CLI", argv=["WolvenKit.CLI", "pack"], exit_code=3)
    assert e.tool == "WolvenKit.CLI"
    assert e.argv == ["WolvenKit.CLI", "pack"]
    assert e.exit_code == 3
    assert isinstance(e, NpvError)


def test_hierarchy():
    assert issubclass(ToolTimeoutError, ToolError)
    for cls in (SaveFormatError, UnsupportedPatchError, InstallError, SecurityError, PipelineCancelled):
        assert issubclass(cls, NpvError)


def test_catchable_as_exception():
    with pytest.raises(NpvError):
        raise UnsupportedPatchError("build 3000 unsupported")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_errors.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'npv_build.core'`

- [ ] **Step 3: Write the implementation**

```python
# npv_build/core/errors.py
"""Typed error hierarchy for the npv-build pipeline (spec ERR-1).

Every error carries a user-facing message, an optional remediation hint,
and optional technical details. Frontends render user_message/remediation;
details go to the log.
"""

from __future__ import annotations

from collections.abc import Sequence


class NpvError(Exception):
    def __init__(
        self,
        user_message: str,
        *,
        remediation: str = "",
        details: str = "",
        module_name: str = "",
    ) -> None:
        self.user_message = user_message
        self.remediation = remediation
        self.details = details
        self.module_name = module_name
        super().__init__(user_message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.user_message}\n{self.details}"
        return self.user_message


class SaveFormatError(NpvError):
    pass


class UnsupportedPatchError(NpvError):
    pass


class MappingResolutionError(NpvError):
    pass


class ToolError(NpvError):
    def __init__(
        self,
        user_message: str,
        *,
        tool: str = "",
        argv: Sequence[str] = (),
        exit_code: int | None = None,
        **kwargs: str,
    ) -> None:
        self.tool = tool
        self.argv = list(argv)
        self.exit_code = exit_code
        super().__init__(user_message, **kwargs)


class ToolTimeoutError(ToolError):
    pass


class BakeVerificationError(NpvError):
    pass


class InstallError(NpvError):
    pass


class SecurityError(NpvError):
    pass


class PipelineCancelled(NpvError):
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_errors.py -q`
Expected: 5 passed.

- [ ] **Step 5: Full gates, then commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: all green (74 passed, 1 skipped).

```bash
git add npv_build/core/ tests/core/
git commit -m "feat(core): typed NpvError hierarchy (spec ERR-1)"
```

---

### Task 2: Cancellation + subprocess adapter (`core/cancel.py`, `core/proc.py`)

**Files:**
- Create: `npv_build/core/cancel.py`
- Create: `npv_build/core/proc.py`
- Test: `tests/core/test_proc.py`

**Interfaces:**
- Consumes: `ToolError`, `ToolTimeoutError`, `PipelineCancelled` from Task 1.
- Produces:
  - `CancelToken` with `.cancel()`, `.cancelled` (bool property), `.raise_if_cancelled()` (raises `PipelineCancelled("Build cancelled")`).
  - `ToolResult` frozen dataclass: `argv: list[str]`, `returncode: int`, `stdout: str`, `stderr: str`.
  - `run_tool(argv, *, tool, timeout, cancel=None, cwd=None, allow_exit_codes=(), logger=None) -> ToolResult` — raises `ToolError` on missing binary or bad exit (message includes last 1500 chars of combined output), `ToolTimeoutError` on timeout, `PipelineCancelled` on cancellation. Logs start/finish at DEBUG on the passed logger.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_proc.py
import sys
import threading
import time

import pytest

from npv_build.core.cancel import CancelToken
from npv_build.core.errors import PipelineCancelled, ToolError, ToolTimeoutError
from npv_build.core.proc import run_tool


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_success_captures_output():
    res = run_tool(_py("import sys; print('out'); sys.stderr.write('err')"), tool="python", timeout=30)
    assert res.returncode == 0
    assert "out" in res.stdout
    assert "err" in res.stderr


def test_nonzero_exit_raises_tool_error_with_tail():
    with pytest.raises(ToolError) as ei:
        run_tool(_py("import sys; print('breadcrumb'); sys.exit(3)"), tool="python", timeout=30)
    assert ei.value.exit_code == 3
    assert ei.value.tool == "python"
    assert "breadcrumb" in str(ei.value)


def test_allow_exit_codes():
    res = run_tool(_py("import sys; sys.exit(2)"), tool="python", timeout=30, allow_exit_codes=(2,))
    assert res.returncode == 2


def test_missing_binary_raises_tool_error():
    with pytest.raises(ToolError) as ei:
        run_tool(["npv-definitely-not-a-real-binary"], tool="ghost", timeout=5)
    assert ei.value.tool == "ghost"
    assert ei.value.remediation != ""


def test_timeout_kills_process():
    start = time.monotonic()
    with pytest.raises(ToolTimeoutError):
        run_tool(_py("import time; time.sleep(60)"), tool="python", timeout=1)
    assert time.monotonic() - start < 30


def test_cancel_terminates_process():
    token = CancelToken()
    timer = threading.Timer(0.5, token.cancel)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(PipelineCancelled):
            run_tool(_py("import time; time.sleep(60)"), tool="python", timeout=120, cancel=token)
    finally:
        timer.cancel()
    assert time.monotonic() - start < 30


def test_token_raise_if_cancelled():
    token = CancelToken()
    token.raise_if_cancelled()  # no-op
    token.cancel()
    assert token.cancelled
    with pytest.raises(PipelineCancelled):
        token.raise_if_cancelled()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_proc.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'npv_build.core.cancel'`

- [ ] **Step 3: Write the implementations**

```python
# npv_build/core/cancel.py
"""Cooperative cancellation token shared by frontends and the pipeline."""

from __future__ import annotations

import threading

from .errors import PipelineCancelled


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise PipelineCancelled("Build cancelled")
```

```python
# npv_build/core/proc.py
"""Single subprocess entry point for all external tools (spec ADP-1/2).

Every external invocation goes through run_tool(): enforced timeout,
cooperative cancellation, structured ToolError on failure.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from collections.abc import Sequence
from dataclasses import dataclass, field

from .cancel import CancelToken
from .errors import ToolError, ToolTimeoutError

_POLL_INTERVAL_S = 0.25
_TERMINATE_GRACE_S = 5.0
_OUTPUT_TAIL_CHARS = 1500


@dataclass(frozen=True)
class ToolResult:
    argv: list[str] = field(default_factory=list)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _stop_process(proc: subprocess.Popen[str]) -> tuple[str, str]:
    proc.terminate()
    try:
        return proc.communicate(timeout=_TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.communicate()


def run_tool(
    argv: Sequence[str],
    *,
    tool: str,
    timeout: float,
    cancel: CancelToken | None = None,
    cwd: Path | None = None,
    allow_exit_codes: tuple[int, ...] = (),
    logger: logging.Logger | None = None,
) -> ToolResult:
    log = logger or logging.getLogger(__name__)
    argv = [str(a) for a in argv]
    log.debug("run_tool start: %s (timeout=%ss)", " ".join(argv), timeout)

    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError as e:
        raise ToolError(
            f"{tool}: executable not found: {argv[0]}",
            tool=tool,
            argv=argv,
            remediation=f"Install {tool} or add it to PATH.",
        ) from e

    deadline = time.monotonic() + timeout
    while True:
        if cancel is not None and cancel.cancelled:
            _stop_process(proc)
            cancel.raise_if_cancelled()
        try:
            stdout, stderr = proc.communicate(timeout=_POLL_INTERVAL_S)
            break
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                out, err = _stop_process(proc)
                raise ToolTimeoutError(
                    f"{tool} timed out after {timeout:.0f}s: {' '.join(argv)}",
                    tool=tool,
                    argv=argv,
                    details=((out or "") + (err or ""))[-_OUTPUT_TAIL_CHARS:],
                    remediation="Re-run; if it persists, raise the timeout in settings.",
                ) from None

    duration = time.monotonic() - (deadline - timeout)
    log.debug("run_tool done: %s exit=%d in %.1fs", tool, proc.returncode, duration)

    ok_codes = {0} | set(allow_exit_codes)
    if proc.returncode not in ok_codes:
        tail = ((stderr or "") + (stdout or ""))[-_OUTPUT_TAIL_CHARS:]
        raise ToolError(
            f"{tool} exited with code {proc.returncode}.",
            tool=tool,
            argv=argv,
            exit_code=proc.returncode,
            details=tail,
        )

    return ToolResult(argv=argv, returncode=proc.returncode, stdout=stdout or "", stderr=stderr or "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_proc.py -q`
Expected: 7 passed (the timeout/cancel tests take a few seconds — that's the polling; fine).

- [ ] **Step 5: Full gates, then commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`

```bash
git add npv_build/core/ tests/core/
git commit -m "feat(core): run_tool subprocess adapter with timeout + cancellation (spec ADP-1/2, CORE-4)"
```

---

### Task 3: Logging setup (`core/logging_setup.py`)

**Files:**
- Create: `npv_build/core/logging_setup.py`
- Test: `tests/core/test_logging_setup.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `configure_logging(verbosity=0, log_file=None, extra_handler=None) -> logging.Logger` — configures the `"npv_build"` package logger (console level WARNING/INFO/DEBUG for verbosity 0/1/≥2; console format is bare `%(message)s`; if `log_file` is a Path, add a `FileHandler(encoding="utf-8")` at DEBUG with format `%(asctime)s %(levelname)s %(name)s: %(message)s`; `extra_handler`, if given, is attached at DEBUG). Idempotent: clears previously-added handlers on re-call. Sets the package logger level to DEBUG and `propagate = False`.
  - `CallbackHandler(fn)` — `logging.Handler` calling `fn(formatted_string)` per record.
  - Convention for all later tasks: module-level `logger = logging.getLogger(__name__)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_logging_setup.py
import logging

from npv_build.core.logging_setup import CallbackHandler, configure_logging


def test_verbosity_levels(capsys):
    configure_logging(verbosity=0)
    log = logging.getLogger("npv_build.sample")
    log.info("info-msg")
    log.warning("warn-msg")
    out = capsys.readouterr()
    assert "info-msg" not in out.err + out.out
    assert "warn-msg" in out.err + out.out

    configure_logging(verbosity=1)
    log.info("info-2")
    out = capsys.readouterr()
    assert "info-2" in out.err + out.out


def test_reconfigure_does_not_duplicate(capsys):
    configure_logging(verbosity=1)
    configure_logging(verbosity=1)
    logging.getLogger("npv_build.sample").info("once")
    combined = "".join(capsys.readouterr())
    assert combined.count("once") == 1


def test_log_file_gets_debug(tmp_path):
    f = tmp_path / "build.log"
    configure_logging(verbosity=0, log_file=f)
    logging.getLogger("npv_build.sample").debug("deep-detail")
    for h in logging.getLogger("npv_build").handlers:
        h.flush()
    assert "deep-detail" in f.read_text(encoding="utf-8")


def test_callback_handler():
    seen: list[str] = []
    configure_logging(verbosity=0, extra_handler=CallbackHandler(seen.append))
    logging.getLogger("npv_build.sample").info("to-gui")
    assert any("to-gui" in s for s in seen)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_logging_setup.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# npv_build/core/logging_setup.py
"""Logging configuration for CLI and GUI frontends (spec LOG-1..3)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from collections.abc import Callable

_PACKAGE = "npv_build"
_CONSOLE_LEVELS = {0: logging.WARNING, 1: logging.INFO}


class CallbackHandler(logging.Handler):
    def __init__(self, fn: Callable[[str], None]) -> None:
        super().__init__(level=logging.DEBUG)
        self._fn = fn
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._fn(self.format(record))
        except Exception:  # noqa: BLE001 - logging must never crash the pipeline
            self.handleError(record)


def configure_logging(
    verbosity: int = 0,
    log_file: Path | None = None,
    extra_handler: logging.Handler | None = None,
) -> logging.Logger:
    pkg = logging.getLogger(_PACKAGE)
    pkg.setLevel(logging.DEBUG)
    pkg.propagate = False
    for handler in list(pkg.handlers):
        pkg.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(_CONSOLE_LEVELS.get(verbosity, logging.DEBUG))
    console.setFormatter(logging.Formatter("%(message)s"))
    pkg.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        pkg.addHandler(file_handler)

    if extra_handler is not None:
        extra_handler.setLevel(logging.DEBUG)
        pkg.addHandler(extra_handler)

    return pkg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core/test_logging_setup.py -q`
Expected: 4 passed.

- [ ] **Step 5: Full gates, then commit**

```bash
git add npv_build/core/logging_setup.py tests/core/test_logging_setup.py
git commit -m "feat(core): logging setup with verbosity, file, and GUI callback handlers (spec LOG-1..3)"
```

---

### Task 4: Migrate `wk_cli.py` onto core

**Files:**
- Modify: `npv_build/wk_cli.py`
- Modify: `tests/test_wk_cli.py` (extend)

**Interfaces:**
- Consumes: `run_tool`, `ToolError`, `CancelToken` (Tasks 1–2).
- Produces: `WolvenKitError` is now `class WolvenKitError(ToolError)` — constructor signature UNCHANGED: `WolvenKitError(message, *, operation="", exit_code=-1)`; it forwards `exit_code=exit_code` and sets `self.operation` and `self.module_name = "WolvenKit Automation"`. `WolvenKitConfig` gains fields `timeout_s: float = 600.0` and `cancel: "CancelToken | None" = None` (frozen dataclass — add with defaults at the end). All WolvenKit invocations (including `list_archive` and `check_version`, which today bypass `_run`) go through `_run`, which delegates to `run_tool`.

- [ ] **Step 1: Write failing tests for the new behavior**

Append to `tests/test_wk_cli.py`:

```python
import npv_build.core.proc as core_proc
from npv_build.core.cancel import CancelToken
from npv_build.core.errors import ToolError
from npv_build.core.proc import ToolResult
from npv_build.wk_cli import WolvenKit, WolvenKitConfig, WolvenKitError


def test_wolvenkit_error_is_tool_error():
    assert issubclass(WolvenKitError, ToolError)
    e = WolvenKitError("boom", operation="pack", exit_code=3)
    assert e.operation == "pack"
    assert e.exit_code == 3
    assert e.module_name == "WolvenKit Automation"


def test_run_routes_through_run_tool(monkeypatch, tmp_path):
    calls = {}

    def fake_run_tool(argv, *, tool, timeout, cancel=None, cwd=None, allow_exit_codes=(), logger=None):
        calls["argv"] = list(argv)
        calls["timeout"] = timeout
        calls["cancel"] = cancel
        return ToolResult(argv=list(argv), returncode=0, stdout="8.19.0\n", stderr="")

    monkeypatch.setattr("npv_build.wk_cli.run_tool", fake_run_tool)
    token = CancelToken()
    wk = WolvenKit(WolvenKitConfig(game_dir=tmp_path, timeout_s=123.0, cancel=token))
    wk.check_version()
    assert calls["argv"][1:] == ["--version"] or "--version" in calls["argv"]
    assert calls["timeout"] == 123.0
    assert calls["cancel"] is token


def test_list_archive_routes_through_run_tool(monkeypatch, tmp_path):
    seen = []

    def fake_run_tool(argv, **kwargs):
        seen.append(list(argv))
        return ToolResult(argv=list(argv), returncode=0, stdout="a.ent\nb.app\n", stderr="")

    monkeypatch.setattr("npv_build.wk_cli.run_tool", fake_run_tool)
    wk = WolvenKit(WolvenKitConfig(game_dir=tmp_path))
    archive = tmp_path / "x.archive"
    archive.write_bytes(b"")
    names = wk.list_archive(r".*\.(ent|app)", archive=archive)
    assert seen, "list_archive must go through run_tool"
    assert names == ["a.ent", "b.app"] or all(isinstance(n, str) for n in names)
```

(The last assertion tolerates `list_archive`'s existing output-parsing; keep its parsing logic unchanged — only the process invocation moves.)

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/test_wk_cli.py -q`
Expected: new tests FAIL (`WolvenKitError` not a `ToolError`; no `run_tool` attribute to patch; no `timeout_s` field).

- [ ] **Step 3: Implement the migration**

In `npv_build/wk_cli.py`:

1. Add imports: `from .core.cancel import CancelToken`, `from .core.errors import ToolError`, `from .core.proc import run_tool` and `import logging` + module-level `logger = logging.getLogger(__name__)`.
2. Rebase the error class, preserving its public signature:

```python
class WolvenKitError(ToolError):
    def __init__(self, message: str, *, operation: str = "", exit_code: int = -1):
        super().__init__(message, exit_code=exit_code, module_name="WolvenKit Automation")
        self.operation = operation
```

3. Extend the config dataclass (append fields, keep frozen):

```python
    timeout_s: float = 600.0
    cancel: CancelToken | None = None
```

4. Rewrite `_run` to delegate: keep the existing binary-resolution block (PATH check + cache fallback) verbatim, keep the `verbosity >= 2` streaming behavior (after `run_tool` returns, write `result.stdout`/`result.stderr` to `sys.stdout`/`sys.stderr` when streaming), then:

```python
        try:
            result = run_tool(
                cmd,
                tool=self._cfg.cli_binary,
                timeout=self._cfg.timeout_s,
                cancel=self._cfg.cancel,
                allow_exit_codes=tuple(allow_exit_codes),
                logger=logger,
            )
        except WolvenKitError:
            raise
        except ToolError as e:
            raise WolvenKitError(
                f"{operation}: {self._cfg.cli_binary} {args[0]} failed: {e.user_message}"
                + (f"\n{e.details}" if e.details else ""),
                operation=operation,
                exit_code=e.exit_code if e.exit_code is not None else -1,
            ) from e
```

   Return a `subprocess.CompletedProcess(cmd, result.returncode, result.stdout, result.stderr)` so every existing caller keeps working unchanged. (`PipelineCancelled` propagates — do not catch it.)
5. Reroute the two direct `subprocess.run` call sites through `_run`: `list_archive` (lines ~93–108) and `check_version` (lines ~266–270). Keep their parsing/validation logic identical; only the invocation changes. Remove the now-unused `import subprocess` only if nothing else in the module uses it (the `CompletedProcess` construction still needs it — keep it).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_wk_cli.py -q`
Expected: all pass (old + new).

- [ ] **Step 5: Full gates, then commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`

```bash
git add npv_build/wk_cli.py tests/test_wk_cli.py
git commit -m "refactor(wk_cli): route all WolvenKit calls through core run_tool with timeout+cancel"
```

---

### Task 5: Migrate `part_resolver.py` subprocess sites + hard-fail audit

**Files:**
- Modify: `npv_build/part_resolver.py`
- Test: `tests/core/test_part_resolver_fallback.py` (create)

**Interfaces:**
- Consumes: `run_tool`, `ToolError` (Tasks 1–2); logging convention (Task 3).
- Produces: no public signature changes; `ResolverError` becomes `class ResolverError(NpvError)` keeping its constructor.

Site inventory (from current master) and required disposition — this is the ERR-2 judgment task:

| Site (approx. line) | Today | Required behavior |
|---|---|---|
| L62 `subprocess.run` list base archive | `check=True`, raise ResolverError | `run_tool(..., tool="WolvenKit.CLI", timeout=600)`; on `ToolError` raise `ResolverError` (base-game path → HARD FAIL) |
| L103 uncook base archive | `check=True`, on any Exception rmtree+re-raise | `run_tool` same; keep the rmtree cleanup in `except BaseException: ... raise` form (cleanup then re-raise; not a swallow) |
| L296 uncook (recipe extraction from a THIRD-PARTY mod archive) | `except Exception` → returns empty | SANCTIONED skip: catch `ToolError` only, `logger.warning("Skipping mod archive %s: %s", archive, e)`, return empty |
| L380 uncook (third-party mod archive) | swallowed by surrounding try | SANCTIONED skip: same pattern — catch `ToolError` only, warn, return |
| L513 list .app in mod archives loop | `except Exception: continue` | SANCTIONED skip: catch `ToolError` only, `logger.warning(...)`, `continue` |
| L557 uncook hair components (third-party mod archive) | `except Exception` → empty tuple | SANCTIONED skip: catch `ToolError` only, warn, return empty tuple |

All six `subprocess.run` calls are replaced with `run_tool(cmd, tool="WolvenKit.CLI", timeout=600.0, logger=logger)`. Beyond these six, this module has ~20 `except Exception` sites (ruff `BLE001` will list them in Task 9); in THIS task fix only the six above plus any blind except that directly wraps them.

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_part_resolver_fallback.py
import logging

import pytest

import npv_build.part_resolver as pr
from npv_build.core.errors import NpvError, ToolError


def test_resolver_error_is_npv_error():
    assert issubclass(pr.ResolverError, NpvError)


def test_mod_archive_scan_skips_broken_archive_with_warning(monkeypatch, tmp_path, caplog):
    """Third-party mod archives are the ONLY sanctioned skip: ToolError -> warn + skip."""

    def exploding_run_tool(argv, **kwargs):
        raise ToolError("corrupt archive", tool="WolvenKit.CLI")

    monkeypatch.setattr(pr, "run_tool", exploding_run_tool)
    broken = tmp_path / "broken_hair_mod.archive"
    broken.write_bytes(b"not an archive")
    with caplog.at_level(logging.WARNING, logger="npv_build.part_resolver"):
        result = pr.extract_recipes_from_archive(broken, verbosity=0)
    assert result == {"parts": [], "overrides": []}
    assert any("broken_hair_mod" in rec.message for rec in caplog.records)
```

Note for the implementer: `extract_recipes_from_archive` is the function containing site L296; if its actual name differs, adapt the test to the real public function that scans a single mod archive for recipes (find it by reading the module) and say so in your report. The behavioral contract in the test is what matters: ToolError from a mod archive → empty result + WARNING naming the archive.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_part_resolver_fallback.py -q`
Expected: FAIL (`ResolverError` not an `NpvError`; module has no `run_tool` attribute).

- [ ] **Step 3: Implement**

1. Imports: `import logging`, `from .core.errors import NpvError, ToolError`, `from .core.proc import run_tool`; module-level `logger = logging.getLogger(__name__)`.
2. `class ResolverError(NpvError):` — keep existing constructor/attributes (check what it sets today; preserve `module_name` if present, else pass `module_name="Part Resolver"`).
3. Replace the six `subprocess.run` sites with `run_tool` per the inventory table. Base-game sites (L62, L103) raise on failure; mod-archive sites (L296, L380, L513, L557) use exactly this pattern:

```python
        try:
            run_tool(cmd, tool="WolvenKit.CLI", timeout=600.0, logger=logger)
        except ToolError as e:
            logger.warning("Skipping mod archive %s: %s", archive_path.name, e.user_message)
            return {"parts": [], "overrides": []}
```

   (adjust the return value / `continue` to each site's existing empty-result shape).
4. Remove `import subprocess` if no site remains.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/core/test_part_resolver_fallback.py tests/test_mapping.py -q`
Expected: pass.

- [ ] **Step 5: Full gates, then commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`

```bash
git add npv_build/part_resolver.py tests/core/test_part_resolver_fallback.py
git commit -m "refactor(part_resolver): run_tool migration; hard-fail base-game paths, warn-skip mod archives (spec ERR-2/ADP-1)"
```

---

### Task 6: Migrate `wolvenkit.py` + `blender_module.py` subprocess sites

**Files:**
- Modify: `npv_build/wolvenkit.py`
- Modify: `npv_build/blender_module.py`
- Test: `tests/core/test_adapter_migration.py` (create)

**Interfaces:**
- Consumes: `run_tool`, `ToolError` (Tasks 1–2).
- Produces: `BlenderError` becomes `class BlenderError(ToolError)` (constructor unchanged); no other signature changes.

Site dispositions:

| Site | Today | Required |
|---|---|---|
| `wolvenkit.py` L72 npv-inject call | manual returncode check → WolvenKitError | `run_tool(cmd, tool="npv-inject", timeout=120.0, logger=logger)`; catch `ToolError` and re-raise as `WolvenKitError(...)` preserving the current message text |
| `wolvenkit.py` L346 uncook garment meshes | `except Exception: return []` | This reads the USER'S OWN target mod archive (required input, not optional third-party): HARD FAIL — `run_tool`, let `ToolError` propagate wrapped in `WolvenKitError` |
| `wolvenkit.py` L365 uncook morphtarget | return value unchecked, no try | `run_tool` (raises on failure — the unchecked-failure hole closes itself) |
| `blender_module.py` L97 `_run` helper | manual returncode → BlenderError | delegate to `run_tool(cmd, tool="blender", timeout=900.0, logger=logger)`; catch `ToolError as e` → `raise BlenderError(str(e)) from e` keeping the `error_prefix` in the message |

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_adapter_migration.py
import pytest

import npv_build.blender_module as bm
import npv_build.wolvenkit as wkmod
from npv_build.core.errors import ToolError
from npv_build.blender_module import BlenderError
from npv_build.wk_cli import WolvenKitError


def test_blender_error_is_tool_error():
    assert issubclass(BlenderError, ToolError)


def test_no_direct_subprocess_in_migrated_modules():
    import inspect

    for mod in (bm, wkmod):
        src = inspect.getsource(mod)
        assert "subprocess.run(" not in src, f"{mod.__name__} still calls subprocess.run directly"
        assert "subprocess.Popen(" not in src, f"{mod.__name__} still calls subprocess.Popen directly"


def test_blender_run_wraps_tool_error(monkeypatch):
    def exploding(argv, **kwargs):
        raise ToolError("blender exploded", tool="blender", exit_code=1)

    monkeypatch.setattr(bm, "run_tool", exploding)
    with pytest.raises(BlenderError):
        bm._run(["blender", "--background"], 0, "Bake failed")
```

(If `blender_module._run`'s real signature differs from `(cmd, verbosity, error_prefix)`, adapt the call — the extraction report says it is `_run(cmd, verbosity, error_prefix)`.)

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/core/test_adapter_migration.py -q`
Expected: FAIL on all three.

- [ ] **Step 3: Implement per the disposition table**

Add to both modules: `import logging`, `logger = logging.getLogger(__name__)`, `from .core.proc import run_tool`, `from .core.errors import ToolError`. Apply the table. In `wolvenkit.py` L346's function, the old `except Exception: return []` around the uncook becomes: no blanket except — `ToolError` propagates as `WolvenKitError` via:

```python
        try:
            run_tool(cmd, tool="WolvenKit.CLI", timeout=600.0, logger=logger)
        except ToolError as e:
            raise WolvenKitError(
                f"Failed to uncook garment meshes from {target_archive.name}: {e.user_message}",
                operation="uncook",
                exit_code=e.exit_code if e.exit_code is not None else -1,
            ) from e
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/core/test_adapter_migration.py tests/test_build_project.py tests/test_head_bake.py tests/test_byo_head.py -q`
Expected: pass.

- [ ] **Step 5: Full gates, then commit**

```bash
git add npv_build/wolvenkit.py npv_build/blender_module.py tests/core/test_adapter_migration.py
git commit -m "refactor(wolvenkit,blender): migrate subprocess sites to run_tool; close unchecked-failure hole"
```

---

### Task 7: Migrate `installer.py` + `hair_mod_helper.py` subprocess sites

**Files:**
- Modify: `npv_build/installer.py`
- Modify: `npv_build/hair_mod_helper.py`
- Modify: `tests/test_installer.py`, `tests/test_hair_mod_helper.py` (extend)

**Interfaces:**
- Consumes: `run_tool`, `InstallError`, `ToolError` (Tasks 1–2).
- Produces: installer failures raise `InstallError` (was `RuntimeError`). `gui.py`/`gui_backend.py` catch sites that reference `RuntimeError` from installer keep working because `InstallError` is raised where `RuntimeError` was — grep for `except RuntimeError` in `npv_build/` and widen those specific handlers to `except (RuntimeError, InstallError)`.

Sites: installer L56 (powershell dotnet-install, timeout 900), L80 (bash dotnet-install, 900), L114 (dotnet tool install WolvenKit.CLI, 900 — keep the "already installed" allowance by catching `ToolError` and checking its `details` for `"already installed"` before re-raising as `InstallError`), L140 (dotnet build npv-inject, 900); hair_mod_helper L137 (`unrar x`, timeout 300 — keep the existing `shutil.which("unrar")` guard, raise `InstallError` instead of `RuntimeError` when missing, and let `ToolError` propagate on extraction failure).

- [ ] **Step 1: Write failing tests** — append to `tests/test_installer.py`:

```python
from npv_build.core.errors import InstallError, ToolError


def test_dotnet_install_failure_raises_install_error(monkeypatch, tmp_path):
    import npv_build.installer as inst

    def exploding(argv, **kwargs):
        raise ToolError("script failed", tool="dotnet-install", exit_code=1)

    monkeypatch.setattr(inst, "run_tool", exploding)
    with pytest.raises(InstallError):
        inst.install_dotnet(tmp_path, lambda msg, pct: None)
```

(Adapt the function name `install_dotnet`/callback signature to the module's real public API — the extraction report shows a `progress_cb(msg, pct)` convention; state the real name in your report.) Add the analogous test in `tests/test_hair_mod_helper.py` asserting a missing `unrar` raises `InstallError`.

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/test_installer.py tests/test_hair_mod_helper.py -q`
Expected: new tests FAIL.

- [ ] **Step 3: Implement** — replace the five `subprocess.run` sites with `run_tool` (tool names: `"dotnet-install"`, `"dotnet"`, `"unrar"`); convert the listed `RuntimeError` raises to `InstallError` with a `remediation` string each (e.g. `remediation="Check your network connection and re-run the installer."`); widen the `except RuntimeError` call sites found by `grep -rn "except RuntimeError" npv_build/`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_installer.py tests/test_hair_mod_helper.py -q`
Expected: pass.

- [ ] **Step 5: Full gates, then commit**

```bash
git add npv_build/installer.py npv_build/hair_mod_helper.py tests/test_installer.py tests/test_hair_mod_helper.py
git commit -m "refactor(installer,hair): run_tool migration; typed InstallError with remediation"
```

---

### Task 8: print → logging migration (pipeline modules)

**Files:**
- Modify: `npv_build/orchestrator.py` (15 prints), `npv_build/save_parser.py` (1), `npv_build/mapping.py` (9), `npv_build/clothing.py` (2), `npv_build/head_bake.py` (16), `npv_build/part_resolver.py` (17), `npv_build/wolvenkit.py` (29), `npv_build/blender_module.py` (5), `npv_build/wk_cli.py` (2)

**Interfaces:**
- Consumes: logging convention (Task 3).
- Produces: pipeline modules emit ONLY via `logging`; the `verbosity` parameters on these functions become dead for output-gating (keep the parameters — signatures frozen — but stop branching on them for prints). Task 12's `configure_logging` call makes `-v` control what the console shows.

Exact transformation rules (apply mechanically; no other edits):

1. Each listed module gets `import logging` and module-level `logger = logging.getLogger(__name__)` if not already added by Tasks 4–6.
2. `if verbosity > 0: print(X)` and `if verbosity >= N: print(X)` → `logger.info(X)` (drop the gate).
3. Unconditional progress/status `print(X)` → `logger.info(X)`.
4. Warning-flavored prints (message contains `WARNING`/`Warning`, e.g. orchestrator L168–182 ext_deps/unresolved block, save_parser L109) → `logger.warning(X)` with the literal `"WARNING: "` prefix stripped from the message text.
5. `print(..., file=sys.stderr)` → `logger.error(...)`.
6. f-strings inside prints stay f-strings (do NOT convert to %-style — consistency with the codebase beats logging micro-optimization).
7. `traceback.print_exc()` in orchestrator (L234–237) → `logger.debug("Traceback:", exc_info=True)`.
8. wk_cli's `verbosity >= 2` command-echo print (`[WolvenKit] $ ...`) → `logger.debug(...)`, and its post-hoc stdout/stderr streaming writes become `logger.debug(...)` calls.

- [ ] **Step 1: Write the failing guard test (scoped to these modules)**

```python
# tests/core/test_no_prints.py
import re
from pathlib import Path

PIPELINE_MODULES = [
    "orchestrator.py", "save_parser.py", "mapping.py", "clothing.py",
    "head_bake.py", "part_resolver.py", "wolvenkit.py", "blender_module.py", "wk_cli.py",
]
_PRINT_RE = re.compile(r"(?<![\w.])print\(")


def test_pipeline_modules_do_not_print():
    pkg = Path(__file__).resolve().parents[2] / "npv_build"
    offenders = []
    for name in PIPELINE_MODULES:
        for i, line in enumerate((pkg / name).read_text(encoding="utf-8").splitlines(), 1):
            if _PRINT_RE.search(line) and "# print-ok" not in line:
                offenders.append(f"{name}:{i}")
    assert not offenders, f"print() in pipeline modules (use logging): {offenders}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/core/test_no_prints.py -q`
Expected: FAIL listing ~96 offender lines.

- [ ] **Step 3: Apply the transformation rules to all nine modules**

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: all pass including the guard. If an existing test asserted on stdout (capsys) from these modules, convert that test to `caplog`.

- [ ] **Step 5: Full gates, then commit**

```bash
git add npv_build/ tests/
git commit -m "refactor: pipeline modules emit via logging, not print (spec LOG-1)"
```

---

### Task 9: Blind-except elimination + ruff gate

**Files:**
- Modify: `pyproject.toml` (ruff select)
- Modify: every module ruff lists (expect: `mapping.py`, `head_bake.py`, `save_parser.py`, `config_editor.py`, `gui.py`, `gui_backend.py`, `installer.py`, plus any residue in Task 5–7 modules)

**Interfaces:**
- Consumes: error types (Task 1), sanctioned-skip policy (Task 5).
- Produces: `ruff check .` enforces `BLE` + `E722` repo-wide — the permanent ERR-2 gate.

- [ ] **Step 1: Turn on the gate**

In `pyproject.toml` `[tool.ruff.lint]`, change `select` to `["E", "F", "I", "B", "UP", "BLE"]` (E722 is already in `E`).

Run: `uv run ruff check npv_build/ --statistics`
Expected: ~35 `BLE001` findings listed (this is the work list; paste it into your report).

- [ ] **Step 2: Fix every finding by policy**

Per-site policy, in priority order:
  a. If the try-body can only plausibly raise specific exceptions (OSError, KeyError, json.JSONDecodeError, ToolError, …): narrow to those.
  b. If the handler cleans up and re-raises: keep as `except BaseException: cleanup; raise` or narrow — never swallow.
  c. If the site is a sanctioned third-party-mod-archive skip (Task 5 list): `except ToolError` + `logger.warning` — already done in Task 5; residue here means you missed one.
  d. GUI event-loop protection in `gui.py`/`gui_backend.py` (a crash in a callback must not kill the mainloop): `except Exception as e:  # noqa: BLE001 - GUI event loop must survive` + `logger.exception(...)` and surface the error to the user (existing queue `("error", ...)` path). The noqa comment must carry that exact justification format.
  e. Anything else: delete the try/except entirely and let it propagate (hard-fail).
  Every `# noqa: BLE001` needs a trailing justification comment; target ≤ 5 noqas repo-wide.

- [ ] **Step 3: Run gates**

Run: `uv run ruff check . && uv run pytest -q`
Expected: 0 findings; suite green.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: eliminate blind excepts, enforce BLE001 in ruff (spec ERR-2)"
```

---

### Task 10: Platform discovery (`core/platform.py`)

**Files:**
- Create: `npv_build/core/platform.py`
- Modify: `npv_build/gui.py` (browse_save_file default dir L670; game-dir placeholder L104)
- Test: `tests/core/test_platform.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `steam_root_candidates() -> list[Path]`, `steam_libraries(steam_roots=None) -> list[Path]`, `candidate_save_dirs(home=None, steam_roots=None) -> list[Path]` (existing dirs only, ordered best-first), `find_game_dirs(steam_roots=None) -> list[Path]`, `is_valid_game_dir(p: Path) -> bool` (`(p / "archive" / "pc" / "content").is_dir()`), `GAME_STEAM_APPID = "1091500"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_platform.py
from pathlib import Path

from npv_build.core import platform as plat


def _make_windows_save(tmp_path: Path) -> Path:
    d = tmp_path / "home" / "Saved Games" / "CD Projekt Red" / "Cyberpunk 2077"
    d.mkdir(parents=True)
    return d


def _make_steam_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    steam = tmp_path / "steam"
    lib2 = tmp_path / "lib2"
    (steam / "steamapps").mkdir(parents=True)
    (lib2 / "steamapps").mkdir(parents=True)
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    vdf.write_text(
        '"libraryfolders"\n{\n'
        f'\t"0"\n\t{{\n\t\t"path"\t\t"{steam}"\n\t}}\n'
        f'\t"1"\n\t{{\n\t\t"path"\t\t"{lib2}"\n\t}}\n'
        "}\n",
        encoding="utf-8",
    )
    save = (
        lib2 / "steamapps" / "compatdata" / plat.GAME_STEAM_APPID / "pfx" / "drive_c"
        / "users" / "steamuser" / "Saved Games" / "CD Projekt Red" / "Cyberpunk 2077"
    )
    save.mkdir(parents=True)
    game = lib2 / "steamapps" / "common" / "Cyberpunk 2077"
    (game / "archive" / "pc" / "content").mkdir(parents=True)
    return steam, save, game


def test_is_valid_game_dir(tmp_path):
    assert not plat.is_valid_game_dir(tmp_path)
    (tmp_path / "archive" / "pc" / "content").mkdir(parents=True)
    assert plat.is_valid_game_dir(tmp_path)


def test_steam_libraries_parses_vdf(tmp_path):
    steam, _, _ = _make_steam_tree(tmp_path)
    libs = plat.steam_libraries(steam_roots=[steam])
    assert len(libs) == 2


def test_candidate_save_dirs_windows_layout(tmp_path):
    d = _make_windows_save(tmp_path)
    dirs = plat.candidate_save_dirs(home=tmp_path / "home", steam_roots=[])
    assert d in dirs


def test_candidate_save_dirs_proton(tmp_path):
    steam, save, _ = _make_steam_tree(tmp_path)
    dirs = plat.candidate_save_dirs(home=tmp_path / "nohome", steam_roots=[steam])
    assert save in dirs


def test_find_game_dirs(tmp_path):
    steam, _, game = _make_steam_tree(tmp_path)
    assert plat.find_game_dirs(steam_roots=[steam]) == [game]


def test_missing_dirs_excluded(tmp_path):
    assert plat.candidate_save_dirs(home=tmp_path / "ghost", steam_roots=[]) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_platform.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# npv_build/core/platform.py
"""Cross-platform discovery of saves and game installs (spec PLT-1/2)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

GAME_STEAM_APPID = "1091500"
_SAVE_SUFFIX = Path("Saved Games") / "CD Projekt Red" / "Cyberpunk 2077"
_VDF_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')


def steam_root_candidates() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        candidates = [Path("C:/Program Files (x86)/Steam")]
    else:
        candidates = [
            home / ".steam" / "steam",
            home / ".local" / "share" / "Steam",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        ]
    return [c for c in candidates if (c / "steamapps").is_dir()]


def steam_libraries(steam_roots: list[Path] | None = None) -> list[Path]:
    roots = steam_root_candidates() if steam_roots is None else steam_roots
    libraries: list[Path] = []
    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        for raw in _VDF_PATH_RE.findall(vdf.read_text(encoding="utf-8", errors="replace")):
            lib = Path(raw.replace("\\\\", "\\"))
            if (lib / "steamapps").is_dir() and lib not in libraries:
                libraries.append(lib)
    return libraries


def candidate_save_dirs(
    home: Path | None = None,
    steam_roots: list[Path] | None = None,
) -> list[Path]:
    home = Path.home() if home is None else home
    found: list[Path] = []
    native = home / _SAVE_SUFFIX
    if native.is_dir():
        found.append(native)
    for lib in steam_libraries(steam_roots):
        proton = (
            lib / "steamapps" / "compatdata" / GAME_STEAM_APPID / "pfx" / "drive_c"
            / "users" / "steamuser" / _SAVE_SUFFIX
        )
        if proton.is_dir() and proton not in found:
            found.append(proton)
    return found


def is_valid_game_dir(path: Path) -> bool:
    return (path / "archive" / "pc" / "content").is_dir()


def find_game_dirs(steam_roots: list[Path] | None = None) -> list[Path]:
    found: list[Path] = []
    for lib in steam_libraries(steam_roots):
        candidate = lib / "steamapps" / "common" / "Cyberpunk 2077"
        if is_valid_game_dir(candidate) and candidate not in found:
            found.append(candidate)
    return found
```

- [ ] **Step 4: Wire the GUI to it**

In `npv_build/gui.py`:
- `browse_save_file` (L670 area): replace `saved_games = Path.home() / "Saved Games" / ...` with:

```python
        from .core.platform import candidate_save_dirs

        candidates = candidate_save_dirs()
        saved_games = candidates[0] if candidates else Path.home()
```

- Game-dir entry placeholder (L104): replace the hardcoded Windows string with a platform-aware one:

```python
        _gd_placeholder = (
            "e.g. C:\\Steam\\steamapps\\common\\Cyberpunk 2077"
            if sys.platform == "win32"
            else "e.g. ~/.steam/steam/steamapps/common/Cyberpunk 2077"
        )
```

  and use `placeholder_text=_gd_placeholder` (add `import sys` if missing).

- [ ] **Step 5: Run tests, gates, commit**

Run: `uv run pytest tests/core/test_platform.py -q && uv run pytest -q && uv run ruff check .`

```bash
git add npv_build/core/platform.py npv_build/gui.py tests/core/test_platform.py
git commit -m "feat(core): cross-platform save/game-dir discovery; GUI uses it (spec PLT-1/2)"
```

---

### Task 11: Pipeline service with checkpoints (`core/pipeline.py`)

**Files:**
- Create: `npv_build/core/pipeline.py`
- Modify: `npv_build/orchestrator.py` (extract lua-writing into `write_amm_lua`, add service delegation)
- Test: `tests/core/test_pipeline.py`

**Interfaces:**
- Consumes: errors (Task 1), `CancelToken` (Task 2), logging (Task 3); existing `parse_save`, `resolve_assets`, `compute_mod_id`, `build_project`, `WolvenKit`, `WolvenKitConfig`.
- Produces:

```python
@dataclass
class BuildRequest:
    save_path: Path | None
    npv_name: str
    output_dir: Path
    game_dir: Path
    template_cache: Path
    clear_cache: bool = False
    cc_json_path: Path | None = None
    hair_override: str | None = None
    skin_override: str | None = None
    garments: list[str] = field(default_factory=list)
    user_head_glb: Path | None = None
    user_head_mesh: Path | None = None
    user_heb_mesh: Path | None = None
    restore_head_materials: bool = True
    resume: bool = False

@dataclass(frozen=True)
class PipelineEvent:
    kind: str          # "stage_started" | "stage_completed" | "stage_skipped" | "failed" | "finished"
    stage: str | None
    message: str

@dataclass
class BuildResult:
    output_dir: str
    mod_id: str
    stages_run: list[str]
    stages_resumed: list[str]

class PipelineService:
    STAGES = ("parse_save", "resolve_assets", "assemble", "emit_amm_lua")
    def build(self, req: BuildRequest, on_event=None, cancel: CancelToken | None = None) -> BuildResult
```

  Also `orchestrator.write_amm_lua(mod_id: str, npv_name: str, body_rig: str, output_dir: Path) -> Path` (the extracted lua block), and `run_orchestrator(...)` keeps its exact signature but delegates to `PipelineService` (no `resume` — old behavior).

**Design (implementer context):** Stage granularity is deliberately coarser than spec CORE-2's seven names: `assemble` wraps `build_project` whole because M3's ArchiveXL decision will rewrite that internals anyway — splitting it now would refactor code slated for replacement. This deviation is recorded in the plan; do not "improve" it. Checkpointing: manifest at `output_dir / ".npv_manifest.json"` mapping stage name → `{"input_hash": str, "completed_at": iso, "output": json-serializable}`. A stage is skipped on `resume=True` when its recorded `input_hash` equals the freshly computed one AND every later-needed artifact exists (for `assemble`: the packed `.archive` under `output_dir / "archive" / "pc" / "mod"` exists). Input hashes: sha256 of `json.dumps(..., sort_keys=True)` over: parse_save → (str(save_path), save file size+mtime, str(cc_json_path)); resolve_assets → (cc_settings, hair_override, garments); assemble → (asset_paths, mod_id, skin_override, garments, str(user_head_glb), str(user_head_mesh), str(user_heb_mesh), restore_head_materials); emit_amm_lua → (mod_id, npv_name, body_rig). `cancel.raise_if_cancelled()` runs before each stage. On any exception the service emits `PipelineEvent("failed", stage, str(e))` and re-raises. The service builds the `WolvenKit` adapter itself with `WolvenKitConfig(game_dir=req.game_dir, verbosity=0, cancel=cancel)` — passing the token down so in-flight tool calls die on cancel.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_pipeline.py
import json
from pathlib import Path

import pytest

import npv_build.core.pipeline as pl
from npv_build.core.cancel import CancelToken
from npv_build.core.errors import PipelineCancelled
from npv_build.core.pipeline import BuildRequest, PipelineService


@pytest.fixture
def fake_stages(monkeypatch, tmp_path):
    calls: list[str] = []
    monkeypatch.setattr(pl, "_make_wolvenkit", lambda req, cancel: object())
    monkeypatch.setattr(pl, "parse_save", lambda p: calls.append("parse_save") or {"patch": "2.13", "body_rig": "pwa"})
    monkeypatch.setattr(
        pl, "resolve_assets",
        lambda cc, game_dir, hair_override, garments, wk: calls.append("resolve_assets") or {"head": "x"},
    )
    monkeypatch.setattr(pl, "_run_assemble", lambda req, wk, mod_id, asset_paths, cc: calls.append("assemble"))
    monkeypatch.setattr(pl, "write_amm_lua", lambda mod_id, npv_name, body_rig, output_dir: calls.append("emit_amm_lua") or output_dir / "x.lua")
    return calls


def _req(tmp_path, **kw) -> BuildRequest:
    save = tmp_path / "sav.dat"
    if not save.exists():  # keep mtime stable across calls — parse_save's input hash includes it
        save.write_bytes(b"fake")
    out = tmp_path / "out"
    defaults = dict(
        save_path=save, npv_name="My V", output_dir=out, game_dir=tmp_path,
        template_cache=tmp_path / "cache",
    )
    defaults.update(kw)
    return BuildRequest(**defaults)


def test_runs_all_stages_in_order(fake_stages, tmp_path):
    result = PipelineService().build(_req(tmp_path))
    assert fake_stages == ["parse_save", "resolve_assets", "assemble", "emit_amm_lua"]
    assert result.stages_run == list(PipelineService.STAGES)
    manifest = json.loads((tmp_path / "out" / ".npv_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == set(PipelineService.STAGES)


def test_events_emitted(fake_stages, tmp_path):
    events = []
    PipelineService().build(_req(tmp_path), on_event=events.append)
    kinds = [e.kind for e in events]
    assert kinds.count("stage_started") == 4
    assert kinds.count("stage_completed") == 4
    assert kinds[-1] == "finished"


def test_resume_skips_unchanged_stages(fake_stages, tmp_path, monkeypatch):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()
    # archive artifact must exist for assemble skip
    arch = tmp_path / "out" / "archive" / "pc" / "mod"
    arch.mkdir(parents=True, exist_ok=True)
    (arch / "fake.archive").write_bytes(b"a")
    result = svc.build(_req(tmp_path, resume=True))
    assert "parse_save" not in fake_stages
    assert "resolve_assets" not in fake_stages
    assert result.stages_resumed  # at least one stage skipped


def test_resume_reruns_on_changed_input(fake_stages, tmp_path):
    svc = PipelineService()
    svc.build(_req(tmp_path))
    fake_stages.clear()
    req2 = _req(tmp_path, hair_override="hair_02", resume=True)
    svc.build(req2)
    assert "resolve_assets" in fake_stages  # input hash changed -> re-run


def test_cancel_before_stage(fake_stages, tmp_path):
    token = CancelToken()
    token.cancel()
    with pytest.raises(PipelineCancelled):
        PipelineService().build(_req(tmp_path), cancel=token)
    assert fake_stages == []


def test_failed_event_on_stage_error(fake_stages, tmp_path, monkeypatch):
    def boom(cc, game_dir, hair_override, garments, wk):
        raise RuntimeError("resolver died")

    monkeypatch.setattr(pl, "resolve_assets", boom)
    events = []
    with pytest.raises(RuntimeError):
        PipelineService().build(_req(tmp_path), on_event=events.append)
    assert any(e.kind == "failed" and e.stage == "resolve_assets" for e in events)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_pipeline.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `core/pipeline.py`**

Module structure (the test above pins the seams — `_make_wolvenkit`, `parse_save`, `resolve_assets`, `_run_assemble`, `write_amm_lua` must be module-level names so monkeypatch works):

```python
# npv_build/core/pipeline.py
"""Checkpointing pipeline service both frontends drive (spec CORE-1..4)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable

from .cancel import CancelToken

logger = logging.getLogger(__name__)

MANIFEST_NAME = ".npv_manifest.json"
```

then imports of the stage functions at module level (`from ..save_parser import parse_save`, `from ..mapping import resolve_assets`, and lazy accessor `write_amm_lua` imported from `..orchestrator` at module level AFTER Step 4's extraction — to avoid a circular import, orchestrator must import pipeline lazily inside `run_orchestrator`, not at module top). `_make_wolvenkit(req, cancel)` constructs the adapter; `_run_assemble(req, wk, mod_id, asset_paths, cc_settings)` calls `build_project(wk, mod_id, req.output_dir, asset_paths, 0, garment_overrides=req.garments, skin_override=req.skin_override, user_head_glb=req.user_head_glb, user_head_mesh=req.user_head_mesh, user_heb_mesh=req.user_heb_mesh, restore_head_materials=req.restore_head_materials)`. Implement `PipelineService.build` as: load manifest (if exists and `req.resume`), for each stage compute input hash → emit `stage_started` → `cancel.raise_if_cancelled()` → skip if resumable (emit `stage_skipped`, record in `stages_resumed`) else run + write manifest entry (atomic: write `.tmp` then `Path.replace`) → emit `stage_completed`; wrap the loop body so any exception emits `failed` then re-raises; end with `finished` event and return `BuildResult`. The `parse_save` stage handles the `cc_json_path` branch the same way `orchestrator.run_orchestrator` does today (read the CET dump JSON instead of the save when given) — move that branch logic into the stage function `_run_parse(req)`.

- [ ] **Step 4: Extract `write_amm_lua` in orchestrator and delegate**

In `npv_build/orchestrator.py`: move the lua-writing block (L240–253) into a module-level `def write_amm_lua(mod_id: str, npv_name: str, body_rig: str, output_dir: Path) -> Path:` producing the identical file at the identical path. Rewrite `run_orchestrator` to build a `BuildRequest` from its parameters and call `PipelineService().build(req)` (import inside the function body to avoid the import cycle), preserving: the `dump_head_glb` early branch exactly as-is (it stays pre-service), the `OrchestratorError` wrapping behavior (catch `NpvError` subclasses and re-wrap as today), and the `str(output_dir)` return.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/core/test_pipeline.py tests/test_orchestrator.py -q`
Expected: pass.

- [ ] **Step 6: Full gates, then commit**

```bash
git add npv_build/core/pipeline.py npv_build/orchestrator.py tests/core/test_pipeline.py
git commit -m "feat(core): PipelineService with checkpoint manifest, events, resume, cancel (spec CORE-1..4)"
```

---

### Task 12: CLI rewire (`--resume`, `--log-file`, logging init)

**Files:**
- Modify: `npv_build/cli.py`
- Test: `tests/core/test_cli.py` (create)

**Interfaces:**
- Consumes: `configure_logging` (Task 3), `PipelineService`/`BuildRequest` (Task 11), `NpvError` (Task 1).
- Produces: CLI contract — existing flags unchanged; new `--resume` (store_true) and `--log-file <path>`; `-v/-vv` now ALSO controls logging via `configure_logging(verbosity=args.v, log_file=...)` called first thing in `main()` after parsing; every build writes a timestamped log file `output_dir / "logs" / "build-<YYYYmmdd-HHMMSS>.log"` even without `--log-file` (LOG-2). On `NpvError`: print `user_message` (and `remediation` on a second line when present) to stderr, `sys.exit(1)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_cli.py
import pytest

from npv_build import cli
from npv_build.core.errors import NpvError


def test_new_flags_parse(monkeypatch, tmp_path, capsys):
    called = {}

    class FakeService:
        def build(self, req, on_event=None, cancel=None):
            called["resume"] = req.resume
            raise NpvError("stop here", remediation="do the thing")

    monkeypatch.setattr(cli, "PipelineService", FakeService)
    save = tmp_path / "sav.dat"
    save.write_bytes(b"x")
    argv = [str(save), "My V", "--output", str(tmp_path / "out"), "--game-dir", str(tmp_path), "--resume", "--log-file", str(tmp_path / "x.log")]
    with pytest.raises(SystemExit) as ei:
        cli.main(argv)
    assert ei.value.code == 1
    assert called["resume"] is True
    err = capsys.readouterr().err
    assert "stop here" in err
    assert "do the thing" in err
```

Note: if `cli.main` currently takes no argv parameter, add `def main(argv: list[str] | None = None)` and pass `argv` to `parser.parse_args(argv)` — backward compatible (entry point calls it with no args).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_cli.py -q`
Expected: FAIL (no `--resume` flag / no `PipelineService` in cli namespace).

- [ ] **Step 3: Implement**

In `npv_build/cli.py`: add the two arguments; add `from .core.logging_setup import configure_logging`, `from .core.pipeline import BuildRequest, PipelineService`, `from .core.errors import NpvError`; after arg parsing call `configure_logging(verbosity=args.v, log_file=Path(args.log_file) if args.log_file else _default_log_file(output_dir))` where `_default_log_file(output_dir)` returns `output_dir / "logs" / f"build-{datetime.now():%Y%m%d-%H%M%S}.log"`; replace the `run_orchestrator(...)` call with constructing `BuildRequest(..., resume=args.resume)` and `PipelineService().build(req)` (keep the dump-head-glb branch going through `run_orchestrator` as before, since that path bypasses the service). Error handling: `except NpvError as e:` print `e.user_message` + optional remediation to stderr, exit 1; keep the generic fallback for non-NpvError.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/core/test_cli.py -q && uv run pytest -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add npv_build/cli.py tests/core/test_cli.py
git commit -m "feat(cli): rewire onto PipelineService; add --resume and --log-file (spec CLI-1, LOG-2)"
```

---

### Task 13: GUI backend rewire (events + cancel)

**Files:**
- Modify: `npv_build/gui_backend.py`
- Modify: `npv_build/gui.py` (only the two lines noted below)
- Modify: `tests/test_gui_backend.py` (extend)

**Interfaces:**
- Consumes: `PipelineService`/`BuildRequest`/`PipelineEvent` (Task 11), `CallbackHandler`+`configure_logging` (Task 3), `CancelToken` (Task 2).
- Produces: `BuildWorker` public API — `__init__(self, log_queue)`, `start(self, **kwargs)` (same kwargs the GUI passes today), `cancel(self)` (new), `is_alive` — posting the SAME queue tuple protocol the GUI already polls: `("log", text)`, `("progress", float)`, `("done", out_dir)`, `("error", message)`. `LogRedirector` is deleted (stdout redirection gone — logging CallbackHandler replaces it).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_gui_backend.py`:

```python
import queue as queue_mod

from npv_build import gui_backend
from npv_build.core.errors import NpvError
from npv_build.core.pipeline import PipelineEvent


def _drain(q):
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue_mod.Empty:
            return items


def test_build_worker_success_posts_done(monkeypatch, tmp_path):
    class FakeService:
        def build(self, req, on_event=None, cancel=None):
            on_event(PipelineEvent(kind="stage_started", stage="parse_save", message="Parsing save"))
            on_event(PipelineEvent(kind="stage_completed", stage="parse_save", message="ok"))
            class R:
                output_dir = str(tmp_path)
            return R()

    monkeypatch.setattr(gui_backend, "PipelineService", FakeService)
    q = queue_mod.Queue()
    w = gui_backend.BuildWorker(q)
    save = tmp_path / "s.dat"
    save.write_bytes(b"x")
    w.start(save_path=save, npv_name="V", output_dir=tmp_path, game_dir=tmp_path, template_cache=tmp_path, clear_cache=False)
    w._thread.join(timeout=10)
    items = _drain(q)
    assert ("done", str(tmp_path)) in items
    assert any(kind == "log" and "parse_save" in str(val) or "Parsing" in str(val) for kind, val in items)


def test_build_worker_error_posts_error(monkeypatch, tmp_path):
    class FakeService:
        def build(self, req, on_event=None, cancel=None):
            raise NpvError("bad save", remediation="pick another")

    monkeypatch.setattr(gui_backend, "PipelineService", FakeService)
    q = queue_mod.Queue()
    w = gui_backend.BuildWorker(q)
    save = tmp_path / "s.dat"
    save.write_bytes(b"x")
    w.start(save_path=save, npv_name="V", output_dir=tmp_path, game_dir=tmp_path, template_cache=tmp_path, clear_cache=False)
    w._thread.join(timeout=10)
    items = _drain(q)
    errs = [val for kind, val in items if kind == "error"]
    assert errs and "bad save" in errs[0] and "pick another" in errs[0]


def test_build_worker_cancel_sets_token(monkeypatch, tmp_path):
    q = queue_mod.Queue()
    w = gui_backend.BuildWorker(q)
    w.cancel()  # before start: must not raise
    assert w._make_token().cancelled is False  # fresh token per start
```

(The `_thread`/`_make_token` names bind the implementation: `BuildWorker` stores its thread as `self._thread` and creates a fresh `CancelToken` per `start()` via `self._make_token()`; `cancel()` sets the current token if one exists.)

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/test_gui_backend.py -q`
Expected: new tests FAIL.

- [ ] **Step 3: Implement**

Rewrite `BuildWorker` in `npv_build/gui_backend.py`:

```python
class BuildWorker:
    def __init__(self, log_queue: queue.Queue):
        self.queue = log_queue
        self._thread: threading.Thread | None = None
        self._token: CancelToken | None = None

    def _make_token(self) -> CancelToken:
        return CancelToken()

    def start(self, **kwargs):
        self._token = self._make_token()
        self._thread = threading.Thread(target=self._run, kwargs=kwargs, daemon=True)
        self._thread.start()

    def cancel(self):
        if self._token is not None:
            self._token.cancel()

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self, **kwargs):
        stages = list(PipelineService.STAGES)

        def on_event(ev):
            if ev.kind == "stage_started":
                self.queue.put(("log", f"[{ev.stage}] {ev.message}\n"))
                self.queue.put(("progress", stages.index(ev.stage) / len(stages)))
            elif ev.kind in ("stage_completed", "stage_skipped"):
                self.queue.put(("progress", (stages.index(ev.stage) + 1) / len(stages)))
            elif ev.kind == "failed":
                self.queue.put(("log", f"[{ev.stage}] FAILED: {ev.message}\n"))

        handler = CallbackHandler(lambda line: self.queue.put(("log", line + "\n")))
        configure_logging(verbosity=2, extra_handler=handler)
        try:
            req = BuildRequest(resume=kwargs.pop("resume", False), **_request_kwargs(kwargs))
            result = PipelineService().build(req, on_event=on_event, cancel=self._token)
            self.queue.put(("done", result.output_dir))
        except PipelineCancelled:
            self.queue.put(("error", "Build cancelled."))
        except NpvError as e:
            msg = e.user_message + (f"\n{e.remediation}" if e.remediation else "")
            self.queue.put(("error", msg))
        except Exception as e:  # noqa: BLE001 - GUI event loop must survive
            logger.exception("Unexpected build failure")
            self.queue.put(("error", str(e)))
```

with `_request_kwargs(kwargs)` a small helper mapping the GUI's existing kwarg names onto `BuildRequest` fields (they already match `run_orchestrator`'s parameter names; drop `verbosity` if present). Delete `LogRedirector` and its use; remove the stdout/stderr redirection block. Update imports accordingly (`from .core.cancel import CancelToken`, `from .core.errors import NpvError, PipelineCancelled`, `from .core.logging_setup import CallbackHandler, configure_logging`, `from .core.pipeline import BuildRequest, PipelineService`, `import logging` + `logger = logging.getLogger(__name__)`). `InstallerWorker` keeps its callback design but its `LogRedirector` usage (if any) is removed the same way. In `npv_build/gui.py`: the build kwargs dict (L926-947) no longer needs changes (backend ignores/receives same names); no new GUI widgets in M1 (Cancel button UI lands in M4) — but verify `poll_queue` still handles all tuple kinds (it does; protocol unchanged).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_gui_backend.py -q && uv run pytest -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add npv_build/gui_backend.py npv_build/gui.py tests/test_gui_backend.py
git commit -m "feat(gui): BuildWorker drives PipelineService with events, logging handler, cancel (spec CORE-1)"
```

---

### Task 14: Documentation refresh

**Files:**
- Modify: `README.md`, `CLAUDE.md`

**Interfaces:** none — closes the two M0-deferred doc nits plus M1's new surface.

- [ ] **Step 1: Update README.md**

Replace `pip install -e .` instructions with the uv workflow (`uv sync --extra gui`, `uv run npv-build ...`, `uv run npv-build-gui`); document `--resume` and `--log-file`; document that logs are always written to `<output>/logs/`.

- [ ] **Step 2: Update CLAUDE.md**

In Commands: `pip install -e .` → `uv sync --extra gui`; `pytest` → `uv run pytest`; add `uv run ruff check .`. In Architecture: add a `core/` bullet describing `errors/cancel/proc/logging_setup/platform/pipeline` and note the pipeline is now resumable via the checkpoint manifest (update the "No subcommands, no resumability" line to reflect `--resume`).

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest -q && uv run ruff check .`

```bash
git add README.md CLAUDE.md
git commit -m "docs: uv workflow, core layer, resume/log-file flags"
```

---

## Exit Criteria (spec M1)

- GUI and CLI both drive `PipelineService` (Tasks 12–13); `run_orchestrator` is a thin compatibility wrapper.
- Cancel: `CancelToken` kills in-flight tool processes (Task 2) and `BuildWorker.cancel()` is wired (Task 13).
- Resume: `--resume` / manifest checkpoints skip unchanged stages (Tasks 11–12).
- Zero `print()` in pipeline modules (guard test, Task 8); zero blind excepts (`ruff BLE001` gate, Task 9).
- Every subprocess call goes through `run_tool` with a timeout (Tasks 4–7).
- CI green on both OSes; suite grown by ~25 tests.
