# M5 — Security, Tests, and npv-inject Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the security gaps (safe extraction, checksum-verified downloads, absolute-path tool invocation), add real test coverage (save fixtures, e2e marker, GUI CI smoke), and retire the `npv-inject` .NET binary per ADR 0001 (Branch A'); milestone M5 of `docs/superpowers/specs/2026-07-17-npv-build-2.0-design.md`.

**Architecture:** Security work centralizes into one `core/safe_extract.py` + a checksum layer on the existing `installer.download_file`. Test work adds fixtures + a pytest `e2e` marker + a headless GUI smoke to CI. The npv-inject retirement is the deep, risky task — it replaces the `_inject_components` .NET subprocess with the WolvenKit serialize→edit-JSON→deserialize round-trip that M3-H1 proved faithful, GATED behind an in-game verification before the .NET tool is deleted.

**Tech Stack:** stdlib (zipfile/tarfile/hashlib), py7zr, the M1 core layer (errors, proc, WolvenKit adapter), pytest.

## Global Constraints (from spec)

- Python 3.11 floor; run everything via `uv run`. Gates every task: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` (run format-check — it has tripped CI before).
- **SEC-1**: one safe-extraction helper validates member paths for zip/tar/7z (and rar) before extraction; regression tests include crafted zip-slip archives.
- **SEC-2**: every download is checksum-verified; verification failure → `SecurityError`, **never a silent fallback**.
- **SEC-3**: external binaries invoked by absolute, validated path only.
- **ADR 0001 (Branch A')**: npv-inject is retired — `_inject_components` becomes an in-process WolvenKit round-trip; `tools/npv-inject/` and the .NET dependency are removed. Donor entity is KEPT (H2 failed).
- Game depot paths keep Windows backslashes; no CDPR bytes in repo.
- 2.13 AND current-patch (2.31, build 2310) saves must keep building end-to-end (regression bar: the real build gate).
- `SecurityError` and `NpvError` subclasses already exist in `core/errors.py` — use them.
- Do not modify the `WolvenKit/` submodule.

## File Structure

- `npv_build/core/safe_extract.py` (new) — `safe_extract_zip/tar/7z`, member-path validation, one code path for all archive types.
- `npv_build/core/checksums.py` (new) — `verify_sha256(path, expected) -> None` (raises SecurityError), `fetch_expected_sha256()` helpers per source.
- `npv_build/installer.py` (modify) — route downloads through checksum verification; route Blender extract through safe_extract.
- `npv_build/hair_mod_helper.py` (modify) — route 7z/rar extract through safe_extract.
- `npv_build/wolvenkit.py` (modify) — replace `_inject_components` with the round-trip; SEC-3 absolute-path tool resolution.
- `tests/fixtures/` (new) — real (scrubbed) save fixtures.
- `pyproject.toml` (modify) — `e2e` pytest marker; drop `.NET` mention once npv-inject gone.
- `.github/workflows/ci.yml` (modify) — GUI headless smoke job.

## Plan Roadmap

Plan 6 of 7. Order: T1 safe-extract → T2 checksums → T3 wire installer/hair to both → T4 SEC-3 absolute paths → T5 save fixtures + e2e marker → T6 GUI CI smoke → T7 npv-inject round-trip replacement (deep, gated) → T8 delete npv-inject + drop .NET (only after T7's in-game gate) → T9 milestone gate. T1-T6 are independent of the npv-inject work and low-risk; T7-T8 are the risky sequence with a user-gated checkpoint.

---

### Task 1: Safe extraction helper (`core/safe_extract.py`) — SEC-1

**Files:**
- Create: `npv_build/core/safe_extract.py`
- Test: `tests/core/test_safe_extract.py`

**Interfaces:**
- Consumes: `SecurityError` (core.errors).
- Produces: `is_safe_member(name: str, dest: Path) -> bool` (True iff the resolved target stays within dest); `safe_extract_zip(archive: Path, dest: Path) -> None`; `safe_extract_tar(archive: Path, dest: Path) -> None`; `safe_extract_7z(archive: Path, dest: Path, targets: list[str] | None = None) -> None`. Each validates every member before extracting and raises `SecurityError` naming the offending member on any traversal (`..`, absolute paths, symlink escapes). Tasks 3 consumes these.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_safe_extract.py
import tarfile
import zipfile
from pathlib import Path

import pytest

from npv_build.core.errors import SecurityError
from npv_build.core.safe_extract import (
    is_safe_member, safe_extract_tar, safe_extract_zip,
)


def test_is_safe_member_accepts_normal(tmp_path):
    assert is_safe_member("a/b/c.txt", tmp_path) is True


def test_is_safe_member_rejects_traversal(tmp_path):
    assert is_safe_member("../../etc/passwd", tmp_path) is False
    assert is_safe_member("/abs/path", tmp_path) is False


def test_safe_extract_zip_normal(tmp_path):
    arc = tmp_path / "ok.zip"
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("dir/file.txt", "hi")
    dest = tmp_path / "out"
    safe_extract_zip(arc, dest)
    assert (dest / "dir" / "file.txt").read_text() == "hi"


def test_safe_extract_zip_rejects_zipslip(tmp_path):
    arc = tmp_path / "evil.zip"
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("../escape.txt", "pwned")
    dest = tmp_path / "out"
    with pytest.raises(SecurityError) as ei:
        safe_extract_zip(arc, dest)
    assert "escape.txt" in str(ei.value)
    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_tar_rejects_traversal(tmp_path):
    payload = tmp_path / "p.txt"
    payload.write_text("x")
    arc = tmp_path / "evil.tar"
    with tarfile.open(arc, "w") as t:
        t.add(payload, arcname="../escape.txt")
    dest = tmp_path / "out"
    with pytest.raises(SecurityError):
        safe_extract_tar(arc, dest)
```

- [ ] **Step 2: RED** — `uv run pytest tests/core/test_safe_extract.py -q` → module not found.

- [ ] **Step 3: Implement**

```python
# npv_build/core/safe_extract.py
"""Path-traversal-safe archive extraction (spec SEC-1)."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from .errors import SecurityError


def is_safe_member(name: str, dest: Path) -> bool:
    dest_resolved = dest.resolve()
    target = (dest_resolved / name).resolve()
    try:
        target.relative_to(dest_resolved)
    except ValueError:
        return False
    return True


def _reject(name: str, dest: Path) -> None:
    raise SecurityError(
        f"Archive member escapes the extraction directory: {name!r}",
        remediation="The archive may be malicious or corrupt; do not extract it.",
        details=f"dest={dest}",
    )


def safe_extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not is_safe_member(name, dest):
                _reject(name, dest)
        z.extractall(dest)


def safe_extract_tar(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as t:
        for member in t.getmembers():
            if not is_safe_member(member.name, dest):
                _reject(member.name, dest)
            if member.islnk() or member.issym():
                # link targets can escape too
                if not is_safe_member(member.linkname, dest):
                    _reject(member.name, dest)
        t.extractall(dest)


def safe_extract_7z(archive: Path, dest: Path, targets: list[str] | None = None) -> None:
    import py7zr

    dest.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(archive, "r") as z:
        for name in z.getnames():
            if not is_safe_member(name, dest):
                _reject(name, dest)
        if targets is not None:
            z.extract(path=dest, targets=targets)
        else:
            z.extractall(path=dest)
```

- [ ] **Step 4: GREEN** — `uv run pytest tests/core/test_safe_extract.py -q` → all pass.

- [ ] **Step 5: Commit** — `git add npv_build/core/safe_extract.py tests/core/test_safe_extract.py && git commit -m "feat(core): path-traversal-safe archive extraction (spec SEC-1)"`

---

### Task 2: Checksum verification (`core/checksums.py`) — SEC-2

**Files:**
- Create: `npv_build/core/checksums.py`
- Test: `tests/core/test_checksums.py`

**Interfaces:**
- Consumes: `SecurityError`.
- Produces: `sha256_of(path: Path) -> str`; `verify_sha256(path: Path, expected: str) -> None` (raises `SecurityError` on mismatch, case-insensitive hex compare); `verify_from_sums(path: Path, sums_text: str, filename: str) -> None` (parse a `SHA256SUMS`-style text — lines `<hex>  <name>` — find `filename`, verify; raise `SecurityError` if the filename isn't listed). Task 3 consumes these.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_checksums.py
import hashlib
from pathlib import Path

import pytest

from npv_build.core.checksums import sha256_of, verify_from_sums, verify_sha256
from npv_build.core.errors import SecurityError


def _write(tmp_path, data=b"hello"):
    p = tmp_path / "f.bin"
    p.write_bytes(data)
    return p, hashlib.sha256(data).hexdigest()


def test_sha256_of(tmp_path):
    p, h = _write(tmp_path)
    assert sha256_of(p) == h


def test_verify_ok(tmp_path):
    p, h = _write(tmp_path)
    verify_sha256(p, h)  # no raise
    verify_sha256(p, h.upper())  # case-insensitive


def test_verify_mismatch_raises(tmp_path):
    p, _ = _write(tmp_path)
    with pytest.raises(SecurityError) as ei:
        verify_sha256(p, "0" * 64)
    assert "checksum" in str(ei.value).lower()


def test_verify_from_sums_ok(tmp_path):
    p, h = _write(tmp_path)
    sums = f"{h}  f.bin\n{'a'*64}  other.bin\n"
    verify_from_sums(p, sums, "f.bin")


def test_verify_from_sums_missing_filename_raises(tmp_path):
    p, h = _write(tmp_path)
    with pytest.raises(SecurityError):
        verify_from_sums(p, f"{h}  other.bin\n", "f.bin")
```

- [ ] **Step 2: RED**

- [ ] **Step 3: Implement**

```python
# npv_build/core/checksums.py
"""SHA-256 verification for downloaded artifacts (spec SEC-2)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .errors import SecurityError

_CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    actual = sha256_of(path)
    if actual.lower() != expected.strip().lower():
        raise SecurityError(
            f"Checksum mismatch for {path.name}.",
            remediation="The download may be corrupt or tampered; delete it and retry.",
            details=f"expected={expected.lower()} actual={actual}",
        )


def verify_from_sums(path: Path, sums_text: str, filename: str) -> None:
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            verify_sha256(path, parts[0])
            return
    raise SecurityError(
        f"No published checksum found for {filename}.",
        remediation="Cannot verify the download; refusing to proceed.",
    )
```

- [ ] **Step 4: GREEN** — `uv run pytest tests/core/test_checksums.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(core): SHA-256 download verification (spec SEC-2)"`

---

### Task 3: Wire installer + hair_mod_helper to safe-extract + checksums

**Files:**
- Modify: `npv_build/installer.py` (Blender extract → safe_extract; Blender download → verify against blender.org SHA256SUMS)
- Modify: `npv_build/hair_mod_helper.py` (7z/rar extract → safe_extract)
- Modify: `tests/test_installer.py`, `tests/test_hair_mod_helper.py`

**Interfaces:**
- Consumes: safe_extract (T1), checksums (T2).
- Produces: no signature changes; extraction/download internals now hard-fail on unsafe members / bad checksums.

- [ ] **Step 1: Read the current sites.** `installer.py:195` (`zip_ref.extractall`) and `:198` (`tar_ref.extractall`) → replace with `safe_extract_zip`/`safe_extract_tar`. `installer.py` Blender download (find `install_blender`) — after download, fetch blender.org's `.sha256`/`SHA256SUMS` for the release and `verify_from_sums` (blender.org publishes a `<file>.sha256` next to each download — fetch it via the existing `download_file` into a temp path, read, verify). `hair_mod_helper.py:120` (`sz.extract`) → `safe_extract_7z`; the rar path (uses `unrar` subprocess) → extract to a temp dir then validate members are within it before use (rar can't be pre-validated via py7zr; validate post-extract by checking no file resolved outside the temp dir, else SecurityError + cleanup).

- [ ] **Step 2: Write failing tests** — append to `tests/test_installer.py`:

```python
def test_blender_extract_uses_safe_extract(monkeypatch, tmp_path):
    """A zip-slip Blender archive must raise SecurityError, not extract."""
    import zipfile

    import npv_build.installer as inst
    from npv_build.core.errors import SecurityError

    arc = tmp_path / "blender.zip"
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("../escape.txt", "x")
    with pytest.raises(SecurityError):
        inst._extract_blender_archive(arc, tmp_path / "dest")  # extract helper (create if inline today)
```

(If the Blender extract is inline in `install_blender`, refactor it into a small `_extract_blender_archive(archive, dest)` helper that dispatches to safe_extract_zip/tar by suffix — makes it testable. Note the refactor in your report.)

Add the analogous zip-slip test for the hair 7z path in `tests/test_hair_mod_helper.py`.

- [ ] **Step 3: RED → implement** the wiring. For the Blender checksum: `install_blender` downloads the archive, then downloads `<archive>.sha256` from the same blender.org URL, then `verify_from_sums` (or `verify_sha256` if the `.sha256` is a bare hash) before extracting. If blender.org's checksum URL 404s for the pinned version, `SecurityError` (never skip). Keep the version/URL pinning already in installer.

- [ ] **Step 4: GREEN** — `uv run pytest tests/test_installer.py tests/test_hair_mod_helper.py -q`

- [ ] **Step 5: Commit** — `git commit -m "refactor(installer,hair): safe extraction + Blender checksum verification (spec SEC-1/2)"`

---

### Task 4: SEC-3 — absolute, validated tool paths

**Files:**
- Modify: `npv_build/wk_cli.py` (binary resolution returns an absolute, existing path), `npv_build/blender_module.py`, `npv_build/hair_mod_helper.py` (unrar)
- Test: `tests/core/test_tool_resolution.py`

**Interfaces:**
- Consumes: existing binary-resolution logic.
- Produces: a shared `core.toolpaths.resolve_tool(name, candidates) -> Path` that returns an absolute, existing path or raises `ToolError`; used by wk_cli's `_run`, blender, and unrar resolution. No PATH-relative bare-name invocation of external tools.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_tool_resolution.py
import pytest

from npv_build.core.errors import ToolError
from npv_build.core.toolpaths import resolve_tool


def test_resolve_tool_returns_absolute_existing(tmp_path):
    fake = tmp_path / "mytool"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    resolved = resolve_tool("mytool", [fake])
    assert resolved.is_absolute() and resolved.exists()


def test_resolve_tool_missing_raises(tmp_path):
    with pytest.raises(ToolError) as ei:
        resolve_tool("ghost", [tmp_path / "nope"])
    assert "ghost" in str(ei.value)
```

- [ ] **Step 2: RED → implement** `npv_build/core/toolpaths.py`:

```python
# npv_build/core/toolpaths.py
"""Resolve external tools to absolute, existing paths (spec SEC-3)."""

from __future__ import annotations

import shutil
from pathlib import Path
from collections.abc import Iterable

from .errors import ToolError


def resolve_tool(name: str, candidates: Iterable[Path]) -> Path:
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c).resolve()
    which = shutil.which(name)
    if which:
        return Path(which).resolve()
    raise ToolError(
        f"{name}: executable not found.",
        tool=name,
        remediation=f"Install {name} or configure its path in settings.",
    )
```

- [ ] **Step 3:** Route `wk_cli._run`'s binary resolution (PATH-then-cache), `blender_module`'s blender resolution, and `hair_mod_helper`'s `unrar` through `resolve_tool` (pass the cache/candidate paths first, bare name for PATH fallback). Each now hands `run_tool` an absolute path.

- [ ] **Step 4: GREEN** — `uv run pytest tests/core/test_tool_resolution.py tests/test_wk_cli.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(core): resolve external tools to absolute validated paths (spec SEC-3)"`

---

### Task 5: Real save fixtures + e2e marker (TST-2/3)

**Files:**
- Create: `tests/fixtures/` (a scrubbed real save + a golden cc_settings JSON), `tests/core/test_save_golden.py`
- Modify: `pyproject.toml` (add `e2e` marker), `tests/conftest.py` (fixture path helper)

**Interfaces:**
- Produces: a checked-in real 2.31 save fixture (scrubbed — personal name fields blanked; it's user save data, no CDPR assets) + golden `cc_settings` JSON; `test_save_golden` parses the fixture and asserts key fields match the golden; the `e2e` marker registers `pytest -m e2e` for game-install-gated tests (excluded from CI).

- [ ] **Step 1: Create the fixture from a real save (this machine has one).** Copy the newest real save's `sav.dat` to `tests/fixtures/sample_2.31.sav.dat` (it's ~small; user save data, no CDPR bytes). If any embedded player-name string is sensitive, note it — the CC node doesn't contain names, so the sav is fine to commit; confirm by `--probe-save` showing only nodes/CC data. Generate the golden: `uv run python -c "import json; from pathlib import Path; from npv_build.save_parser import parse_save; d=parse_save(Path('tests/fixtures/sample_2.31.sav.dat')); Path('tests/fixtures/sample_2.31.cc.json').write_text(json.dumps({k:d[k] for k in ('patch','body_rig')}, indent=2))"`.

- [ ] **Step 2: Write the golden test**

```python
# tests/core/test_save_golden.py
import json
from pathlib import Path

from npv_build.save_parser import parse_save

_FIX = Path(__file__).resolve().parents[1] / "fixtures"


def test_golden_2_31_save_parses():
    d = parse_save(_FIX / "sample_2.31.sav.dat")
    golden = json.loads((_FIX / "sample_2.31.cc.json").read_text())
    for k, v in golden.items():
        assert d[k] == v
    assert d["patch"] == "2.31"
    assert "selections" in d and len(d["selections"]) > 0
```

- [ ] **Step 3: Register the e2e marker** — in `pyproject.toml` `[tool.pytest.ini_options]` add:

```toml
markers = [
    "e2e: end-to-end build tests requiring a real game install (excluded from CI; run with -m e2e)",
]
```

- [ ] **Step 4: GREEN** — `uv run pytest tests/core/test_save_golden.py -q`; confirm `uv run pytest -q` still excludes nothing unintended and `uv run pytest -m e2e -q` collects 0 (no e2e tests yet, just the marker registered — no "unknown marker" warning).

- [ ] **Step 5: Commit** — `git add tests/fixtures tests/core/test_save_golden.py pyproject.toml tests/conftest.py && git commit -m "test: real 2.31 save fixture + golden parse test + e2e marker (spec TST-2/3)"`

---

### Task 6: GUI headless smoke in CI (TST-4)

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:** none — adds a CI job that instantiates the app headlessly.

- [ ] **Step 1: Read `.github/workflows/ci.yml`.** Add a `gui-smoke` job (ubuntu, xvfb) that runs the full-app smoke. The test already exists (`tests/gui_logic/test_gui_smoke.py`) but is DISPLAY-guarded/skipped in CI — the job provides a display so it actually runs.

- [ ] **Step 2: Add the job**

```yaml
  gui-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
      - run: sudo apt-get update && sudo apt-get install -y xvfb
      - run: uv sync --locked --extra gui
      - run: xvfb-run -a uv run pytest tests/gui_logic/test_gui_smoke.py -q
```

- [ ] **Step 3:** Verify locally the smoke runs under a virtual display: `xvfb-run -a uv run pytest tests/gui_logic/test_gui_smoke.py -q` (install xvfb if absent) → passes, and the skip-guard doesn't skip when DISPLAY is set.

- [ ] **Step 4: Commit + push** — `git commit -m "ci: headless GUI smoke job under xvfb (spec TST-4)"` and push the branch so CI exercises it; confirm the gui-smoke job goes green.

---

### Task 7: Replace `_inject_components` with WolvenKit round-trip — DEEP, GATED

**Files:**
- Create: `npv_build/core/app_inject.py` (the Python injector)
- Modify: `npv_build/wolvenkit.py` (call the new path; keep npv-inject as a fallback until the gate passes)
- Test: `tests/core/test_app_inject.py`

**Interfaces:**
- Consumes: WolvenKit adapter (serialize/deserialize), `NpvError`.
- Produces: `inject_components(wk, app_path, components_json, *, donor_app=None, face_rig=None, facial_setup=None, face_graph=None, hair_dangle_graph=None) -> None` — serializes the cooked `.app` to JSON, builds the component objects in WolvenKit's JSON representation from `components_json` (mirroring `tools/npv-inject/ComponentInjector.cs`'s logic: typed component per spec, name/mesh/meshAppearance, parentTransform+skinning bindName from BindTo, donor-sourced face rig/facial-setup/face-graph/hair-dangle handles), appends them to `appearances[0].components`, deserializes back to the cooked `.app`. This is the pure-Python equivalent of the .NET tool.

**RISK / GATE (read before starting):** `ComponentInjector.cs` uses WolvenKit's RED4 typed library to construct components with correct CRUID/handle wiring — replicating that in raw JSON is genuinely hard (M3-H1 proved the *round-trip* is faithful, NOT that hand-authoring components in JSON produces valid handles). **Two-attempt rule:** try to build the components in the serialized JSON and produce an `.app` that (a) deserializes without error and (b) serializes back to a component set structurally matching an npv-inject reference `.app` (use the M1/M3 e2e artifacts as the reference). If after two genuine, root-caused attempts the JSON-authored components don't round-trip cleanly (handle/CRUID errors the round-trip can't resolve), **STOP** and report: keep npv-inject as the active path, mark this task BLOCKED-needs-spike, and record exactly where it broke. Do NOT ship a Python injector that produces subtly-wrong `.app` files — a broken injector ships broken NPVs. The .NET tool stays until the Python path is proven.

- [ ] **Step 1: Study the reference.** Read `tools/npv-inject/ComponentInjector.cs` fully + `docs/legacy/SPEC-inject.md`. Serialize a real npv-inject-produced `.app` (from `/tmp/claude-1000/npv_t7_231` — the 2.31 build) to JSON and study the exact shape of an injected component (type, name, mesh depot-path-hash, meshAppearance, parentTransform/skinning handles). Document the target JSON shape in your report.

- [ ] **Step 2: Write the failing tests** (JSON-level, mock wk.serialize/deserialize to file-in/file-out on JSON):

```python
# tests/core/test_app_inject.py
import json
from pathlib import Path

import pytest

from npv_build.core.app_inject import build_component_json, InjectError


def test_build_component_mesh_type():
    spec = {"type": "entSkinnedMeshComponent", "name": "head", "mesh": r"base\x\head.mesh",
            "meshAppearance": "default", "bindTo": "root"}
    comp = build_component_json(spec)
    assert comp["Data"]["$type"] == "entSkinnedMeshComponent"
    assert comp["Data"]["name"]["$value"] == "head"
    assert comp["Data"]["parentTransform"]["Data"]["bindName"]["$value"] == "root"


def test_build_component_unknown_type_raises():
    with pytest.raises(InjectError):
        build_component_json({"type": "entNotAComponent", "name": "x", "mesh": "", "meshAppearance": "", "bindTo": "root"})
```

(build_component_json is the pure per-component builder — the piece most like the C# `BuildComponent`. Test it in isolation; the full inject_components file orchestration is validated by the in-game gate, not a unit test, since it needs real WolvenKit.)

- [ ] **Step 3: RED → implement** `build_component_json` + `inject_components`. Keep `build_component_json` pure/testable. `inject_components` does the serialize→append→deserialize with the WolvenKit adapter.

- [ ] **Step 4: Wire as opt-in in wolvenkit.py** — add a flag/env (`NPV_PY_INJECT=1`) that routes `_inject_components`'s caller to the new `inject_components` instead of the .NET tool. Default stays .NET until the gate passes. This lets the gate compare both.

- [ ] **Step 5: THE GATE (real build, both paths).** Run a full real build with the .NET injector (baseline) and one with `NPV_PY_INJECT=1`, from the 2.31 save. Serialize both output `.app`s and diff (jq -S) — structural equality modulo CruidDict/metadata = PASS-pending-in-game. Then INSTALL the `NPV_PY_INJECT=1` build and ask the user for an in-game spawn check (gated like M3-T4: spawns / face / clothing / no T-pose / no missing mesh). Only a passing in-game check clears Task 8.

- [ ] **Step 6: GREEN unit + commit** — `git commit -m "feat(core): pure-Python component injection via WolvenKit round-trip (opt-in; ADR 0001 A')"`. If BLOCKED per the two-attempt rule, commit the partial + BLOCKED report and STOP the npv-inject removal (skip Task 8).

---

### Task 8: Delete npv-inject + drop .NET — ONLY after Task 7's in-game gate passes

**Files:**
- Delete: `tools/npv-inject/`
- Modify: `npv_build/wolvenkit.py` (remove `_inject_components`/`_resolve_inject_binary`, make `inject_components` the only path), `npv_build/installer.py` (remove `install_dotnet_*`, `build_npv_inject`, `.NET` from `auto_install_missing`), `npv_build/gui_backend.py` (remove `npv_inject` from `check_dependencies`), `CLAUDE.md`, `README.md`, `docs/legacy/SPEC-inject.md` (mark superseded)
- Test: update `tests/test_installer.py` (drop .NET tests), `tests/test_gui_backend.py` (check_dependencies no longer has npv_inject)

**GATE:** Do NOT start this task unless Task 7's in-game gate PASSED (user confirmed the `NPV_PY_INJECT=1` build spawns correctly). If Task 7 is BLOCKED, skip Task 8 entirely — npv-inject stays.

- [ ] **Step 1: Make Python injection the default** — remove the `NPV_PY_INJECT` flag, delete `_inject_components`/`_resolve_inject_binary`, route the caller straight to `inject_components`.
- [ ] **Step 2: Remove .NET from installer** — delete `install_dotnet_windows/linux`, `build_npv_inject`, and their calls in `auto_install_missing`; remove the dotnet-install download/execute paths (this also retires the SEC-2 dotnet-script concern entirely — note it).
- [ ] **Step 3: Remove npv_inject from `check_dependencies`** — GUI dependency check now WolvenKit + Blender only (matches M4's wizard, and removes the last GUI `npv_inject` reference).
- [ ] **Step 4: Delete `tools/npv-inject/`** and update docs (CLAUDE.md "External tools", README, SPEC-inject.md → superseded-by-ADR-0001 note).
- [ ] **Step 5: Update tests** — drop the dotnet-install tests; assert `check_dependencies` has no `npv_inject` key.
- [ ] **Step 6: Full real build gate** — a fresh build from the 2.31 save with NO .NET installed/available must succeed end-to-end (proves .NET is truly gone from the path). Then gates + commit — `git commit -m "feat: retire npv-inject and .NET dependency (ADR 0001 Branch A')"`.

---

### Task 9: Milestone gate

- [ ] **Step 1:** Full suite + ruff check + ruff format --check green.
- [ ] **Step 2:** Real build from BOTH a 2.13-era save and the 2.31 save succeeds end-to-end (regression bar). If Task 8 ran, both use the Python injector with no .NET present.
- [ ] **Step 3:** Security regression tests (SEC-1 zip-slip, SEC-2 checksum-mismatch) all present and green; grep confirms no bare `extractall(` outside safe_extract and no un-verified download executes.
- [ ] **Step 4:** Push branch; CI green on both OSes incl. the new gui-smoke job.
- [ ] **Step 5: Commit** any final doc/ledger updates.

---

## Exit Criteria (spec M5)

- SEC-1: all archive extraction goes through safe_extract; zip-slip regression tests green; no bare `extractall` remains.
- SEC-2: all downloads checksum-verified; mismatch → SecurityError (regression-tested); no silent fallback.
- SEC-3: external tools invoked by absolute validated path.
- TST: real save fixture + golden test; e2e marker registered; GUI smoke runs in CI under xvfb.
- ADR 0001 A': npv-inject retired IF Task 7's in-game gate passed (else BLOCKED + documented, npv-inject stays — the security/test work still ships).
- 2.13 and 2.31 saves both build end-to-end; CI green both OSes.

## Notes

- **Task 7 is the one that can block.** Everything else (T1-T6) is independent and ships regardless. If T7 blocks, M5 still delivers all security + test work; npv-inject retirement becomes its own follow-up spike. Sequence T1-T6 first so the milestone has value even if T7-T8 stall.
- **SEC-2 dotnet-script concern:** if Task 8 runs, the dotnet-install script download/execute is deleted entirely, mooting that part of SEC-2. If Task 8 is blocked (npv-inject stays), Task 3 must ALSO pin+verify the dotnet-install scripts (version + hash before execution) — add that to Task 3's scope only in the blocked case.
