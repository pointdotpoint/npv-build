# M0 — Repo Cleanup + Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean the repository of tracked build artifacts and legacy docs, migrate packaging to uv + hatchling + ruff, and stand up a Windows+Linux CI matrix — milestone M0 of `docs/superpowers/specs/2026-07-17-npv-build-2.0-design.md`.

**Architecture:** No production-code changes. Three concerns: git hygiene (untrack artifacts, relocate legacy specs), packaging/tooling (hatchling backend, uv lockfile, ruff lint+format), and CI (GitHub Actions matrix on ubuntu-latest + windows-latest running lint and the existing test suite).

**Tech Stack:** uv, hatchling, ruff, pytest, GitHub Actions.

## Global Constraints (from spec)

- Python floor is **3.11** (NFR-1; the bundled release ships its own Python).
- **No CDPR game bytes** may enter the repo or artifacts (NFR-4).
- Game depot paths keep Windows backslashes even on Linux — never "fix" them (PLT-3).
- Do not modify the `WolvenKit/` submodule; exclude it from all tooling.
- Hard-fail policy: no change may make an error path quieter.
- Version string becomes `2.0.0.dev0` (PKG-5 targets 2.0.0 at release).
- This plan must leave the existing test suite passing (`pytest` green) after every task.

## Plan Roadmap (context for the worker)

This is plan 1 of 7. Milestones M1–M6 from the spec get their own plan documents, authored after this one is executed. Nothing in this plan depends on them.

---

### Task 1: Untrack build-artifact directories and extend .gitignore

The dirs `my_v_mod/`, `external_v_01_mod/`, `test_v_mod/`, `release_test/`, `app_verify/` are tracked in git but are local build outputs (spec NFR-3). They must be untracked but **left on disk** (tests and manual workflows may still read them). `trial_out/`, `latest_v_mod/`, `venv/` are already ignored.

**Files:**
- Modify: `.gitignore`
- Delete from index only (files stay on disk): `my_v_mod/`, `external_v_01_mod/`, `test_v_mod/`, `release_test/`, `app_verify/`
- Delete from disk: `test.sav.dat` (0-byte stub, already gitignored)

**Interfaces:**
- Consumes: nothing.
- Produces: a clean `git status` contract later tasks rely on — artifact dirs show as ignored, not untracked.

- [ ] **Step 1: Untrack the artifact directories (keep them on disk)**

```bash
cd /home/pdp/npv_project
git rm -r --cached --ignore-unmatch my_v_mod external_v_01_mod test_v_mod release_test app_verify
rm -f test.sav.dat
```

- [ ] **Step 2: Append the new ignore rules**

Append this block to the end of `.gitignore`:

```gitignore
# Local mod-build outputs (never tracked)
my_v_mod/
external_v_01_mod/
test_v_mod/
release_test/
app_verify/
*_v_mod/

# Packaging / tooling
dist/
build/
.ruff_cache/
```

- [ ] **Step 3: Verify the dirs are ignored and still on disk**

Run: `git status --short | grep -v '^D ' | head -20 && ls -d my_v_mod test_v_mod`
Expected: the staged `D` (deletion) entries from Step 1 are filtered out; what remains shows NO `??` entries for the five artifact dirs (they are now ignored), and `ls` prints both directory names (still on disk).

- [ ] **Step 4: Verify tests still pass**

Run: `python -m pytest -q`
Expected: same pass count as before this task (all passing).

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: untrack local build artifacts, extend .gitignore"
```

---

### Task 2: Move legacy spec documents under docs/

Six root-level docs predate the 2.0 spec (spec D6). `README.md`, `CLAUDE.md`, `CONTEXT.md`, `IMPROVEMENT_REPORT.md` stay at root.

**Files:**
- Move: `SPEC.md`, `SPEC-app-v2.md`, `SPEC-clothing.md`, `SPEC-inject.md`, `Technical Implementation Specification_ Cyberpunk 2077 NPV Automation.md` → `docs/legacy/`
- Move: `NPV_Creation_Guide.md` → `docs/`

**Interfaces:**
- Consumes: nothing.
- Produces: `docs/legacy/` as the home for superseded design docs.

- [ ] **Step 1: Move the files with git mv**

```bash
cd /home/pdp/npv_project
mkdir -p docs/legacy
git mv SPEC.md SPEC-app-v2.md SPEC-clothing.md SPEC-inject.md docs/legacy/
git mv "Technical Implementation Specification_ Cyberpunk 2077 NPV Automation.md" docs/legacy/
git mv NPV_Creation_Guide.md docs/
```

- [ ] **Step 2: Fix references to the moved files**

Run: `grep -rn --include='*.md' --include='*.py' -e 'SPEC.md' -e 'SPEC-' -e 'NPV_Creation_Guide' README.md CLAUDE.md CONTEXT.md npv_build/ tests/ docs/ | grep -v docs/legacy/`
Expected: zero hits, or a short list of links. For every hit, update the path to `docs/legacy/<name>` (or `docs/NPV_Creation_Guide.md`) with Edit.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: move legacy specs to docs/legacy, guide to docs/"
```

---

### Task 3: Migrate packaging to hatchling + uv

Replace the setuptools backend with hatchling, raise the Python floor to 3.11, add a dev dependency group, and commit a uv lockfile (spec D5, PKG-6). `MANIFEST.in` is setuptools-only and gets deleted — hatchling includes everything inside `npv_build/` (including `data/`) in the wheel automatically.

**Files:**
- Modify: `pyproject.toml` (full replacement below)
- Delete: `MANIFEST.in`
- Create: `uv.lock` (generated)

**Interfaces:**
- Consumes: nothing.
- Produces: `uv run <cmd>` as the canonical dev entry point; dev group provides `pytest` and `ruff` for Tasks 4–5; version string `2.0.0.dev0`.

- [ ] **Step 1: Replace pyproject.toml with the hatchling version**

Full new content of `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "npv-build"
version = "2.0.0.dev0"
description = "Cyberpunk 2077 NPV Automation"
authors = [
    {name = "Maintainer"}
]
requires-python = ">=3.11"
dependencies = [
    "tomli-w",
    "lz4"
]

[project.optional-dependencies]
gui = [
    "customtkinter>=6.0.0",
    "tkinterdnd2>=0.5.0",
    "py7zr>=0.20.0"
]

[project.scripts]
npv-build = "npv_build.cli:main"

[project.gui-scripts]
npv-build-gui = "npv_build.gui:main"

[dependency-groups]
dev = [
    "pytest",
    "ruff",
]

[tool.hatch.build.targets.wheel]
packages = ["npv_build"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Notes: the `tomli; python_version < '3.11'` dependency is dropped because the floor is now 3.11 (stdlib `tomllib`); the old `test` extra is replaced by the `dev` group.

- [ ] **Step 2: Remove MANIFEST.in and any dead tomli imports**

```bash
git rm MANIFEST.in
grep -rn "import tomli\b" npv_build/
```

Expected grep output: only guarded fallbacks like `except ImportError: import tomli as tomllib` (fine to keep — they simply never trigger on 3.11+), or nothing. Do NOT remove guarded fallbacks; only remove an unconditional `import tomli` if one exists (replace with `import tomllib`).

- [ ] **Step 3: Lock and sync**

```bash
uv lock
uv sync --extra gui
```

Expected: `uv.lock` created; environment resolves without errors.

- [ ] **Step 4: Verify the package still installs and runs**

Run: `uv run npv-build --help && uv run python -c "from importlib import resources; print(resources.files('npv_build').joinpath('data/save_versions.json').is_file())"`
Expected: CLI help text prints; final line prints `True` (package data reachable).

- [ ] **Step 5: Verify tests pass under uv**

Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: migrate to hatchling + uv, py3.11 floor, v2.0.0.dev0"
```

---

### Task 4: Add ruff and apply a baseline format/lint pass

Configure ruff in `pyproject.toml`, format the codebase once, autofix what's safe, and make `ruff check` exit clean (spec NFR-2). This is the one intentionally-noisy diff; doing it before the M1 refactor keeps later reviews readable.

**Files:**
- Modify: `pyproject.toml` (append tool section)
- Modify: all `*.py` under `npv_build/`, `tests/`, `data/blender/` (mechanical reformat)

**Interfaces:**
- Consumes: dev group from Task 3.
- Produces: `uv run ruff check .` and `uv run ruff format --check .` exit 0 — the CI contract for Task 5.

- [ ] **Step 1: Append ruff configuration to pyproject.toml**

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = [
    "WolvenKit",
    "my_v_mod",
    "external_v_01_mod",
    "test_v_mod",
    "release_test",
    "app_verify",
    "trial_out",
    "latest_v_mod",
]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]
```

(`E501` stays off: long depot-path strings are domain data. Line length still guides the formatter.)

- [ ] **Step 2: Run the formatter**

Run: `uv run ruff format .`
Expected: prints `N files reformatted, M files left unchanged`.

- [ ] **Step 3: Autofix lint findings**

Run: `uv run ruff check --fix .`
Expected: many fixes applied (import sorting, pyupgrade rewrites).

- [ ] **Step 4: Triage the remainder**

Run: `uv run ruff check . --statistics`

Policy for what's left:
- `F` codes (undefined names, unused imports/variables): fix each one by hand — these are real defects.
- `B` codes (bugbear): fix by hand if the fix is local and obvious; if a finding requires behavioral judgment (e.g. `B008` mutable default used intentionally), suppress that single line with `# noqa: <code>` and keep the rule on.
- `E`/`UP`/`I` leftovers: fix by hand (they're mechanical).

Re-run `uv run ruff check .` until: exit code 0.

- [ ] **Step 5: Verify tests still pass after the mechanical churn**

Run: `uv run pytest -q`
Expected: all tests pass. If a test fails, the formatter/autofix changed behavior — inspect that specific diff hunk (`git diff <file>`) and repair by hand; do not loosen the test.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "style: adopt ruff, apply baseline format and lint fixes"
```

---

### Task 5: GitHub Actions CI matrix (Linux + Windows)

Stand up CI running lint on Linux and the test suite on both OSes (spec TST-6 skeleton; type-check job is added in M1 when `core/` exists). Windows has never run this suite (spec R4) — the task includes a concrete triage mechanism for Windows-only failures.

**Files:**
- Create: `.github/workflows/ci.yml`
- Possibly modify: individual `tests/test_*.py` files (platform skips, mechanism in Step 4)

**Interfaces:**
- Consumes: `uv.lock` + dev group (Task 3), clean ruff state (Task 4).
- Produces: required-check names `lint` and `test (ubuntu-latest)` / `test (windows-latest)` for all later milestones.

- [ ] **Step 1: Create the workflow file**

Full content of `.github/workflows/ci.yml`:

```yaml
name: ci

on:
  push:
    branches: [master]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
      - run: uv sync --locked
      - run: uv run ruff check .
      - run: uv run ruff format --check .

  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    name: test (${{ matrix.os }})
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: false
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
      - run: uv sync --locked --extra gui
      - run: uv run pytest -q
```

- [ ] **Step 2: Run the suite locally one more time before pushing**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: all three exit 0.

- [ ] **Step 3: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint + test matrix on ubuntu and windows"
git push origin master
```

- [ ] **Step 4: Watch the run and triage Windows failures**

Run: `gh run watch --exit-status` (get the run id from `gh run list --limit 1` if needed).

- If all jobs pass: task done, go to Step 5.
- If a test fails **only on windows-latest**: mark that specific test with a skip so the failure is visible-but-deferred (Windows behavior is in scope for M4, spec R4). Exact pattern to add to the failing test:

```python
import sys
import pytest

@pytest.mark.skipif(sys.platform == "win32", reason="Windows parity deferred to M4 (spec R4)")
def test_the_failing_case():
    ...
```

  Keep a list of every skipped test in the commit message. Do NOT skip tests that also fail on Linux — those are real regressions from Tasks 3–4; fix them instead.
- If a job fails for infra reasons (uv install, lock mismatch): fix the workflow/lockfile, not the tests.

Re-push and re-watch until: both OS jobs and lint are green.

- [ ] **Step 5: Final commit (if Step 4 changed tests)**

```bash
git add tests/
git commit -m "test: skip Windows-parity failures pending M4 (list in body)"
git push origin master
```

---

## Exit Criteria (spec M0)

- `git status` clean; artifact dirs on disk but ignored.
- Legacy docs under `docs/legacy/`; root has only README, CLAUDE, CONTEXT, IMPROVEMENT_REPORT.
- `uv sync && uv run pytest` works from a fresh clone (3.11+).
- `ruff check` and `ruff format --check` exit 0.
- GitHub Actions green: `lint`, `test (ubuntu-latest)`, `test (windows-latest)`.
