# M6 — Release Bundles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship npv-build 2.0.0 as double-clickable bundled apps — a Windows `.zip` and a Linux AppImage, each containing the GUI + CLI with no preinstalled Python — released automatically on a `v*` git tag with `SHA256SUMS`; milestone M6 of `docs/superpowers/specs/2026-07-17-npv-build-2.0-design.md`.

**Architecture:** PyInstaller one-dir builds of the GUI entry (`npv_build.gui:main`), with the CLI reachable as a second console entry in the same bundle. External tools (WolvenKit, Blender) are NOT bundled — the first-run wizard downloads them checksum-verified (M5 SEC-2) into the app data dir, respecting CDPR/tool licensing (NFR-4: no third-party binaries in the artifact). A `.spec` file captures the tricky data collection (`npv_build/data`, customtkinter, tkinterdnd2). A tag-triggered GitHub Actions workflow builds both platforms, generates `SHA256SUMS`, and attaches everything to a draft Release.

**Tech Stack:** PyInstaller, `appimagetool` (Linux), GitHub Actions, uv.

## Global Constraints (from spec)

- Python 3.11 floor; build via `uv`. Gates every code task: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`.
- **PKG-1**: PyInstaller one-dir GUI build; CLI included as a console entry in the same bundle.
- **PKG-2**: Windows artifact = versioned `.zip`; Linux artifact = AppImage. (Inno Setup installer is an explicit non-goal — later follow-up.)
- **PKG-3**: External tools NOT bundled; first-run wizard downloads them checksum-verified into the app data dir. **No third-party binaries (CDPR assets, WolvenKit, Blender, .NET) in the artifact (NFR-4).**
- **PKG-4**: On git tag `v*`, GitHub Actions builds both artifacts, generates `SHA256SUMS`, attaches to a DRAFT GitHub Release with changelog notes.
- **PKG-5**: Version **2.0.0** (semver); `CHANGELOG.md` maintained.
- **PKG-6**: `uv.lock` committed; dev setup documented (`uv sync`).
- **macOS is a non-goal** (spec §1 Non-Goals).
- **No code-signing** in the first release (spec: SmartScreen warning accepted; document it). Don't add signing.
- This machine is **Linux** — the AppImage builds/verifies locally; the Windows `.zip` builds only in CI (windows-latest runner), verified by the CI job succeeding + a smoke launch there.

## PyInstaller pitfalls this plan MUST handle (discovered in survey)

- The app reads bundled data via `importlib.resources.files("npv_build").joinpath("data/...")` (e.g. `save_probe.py:20`, config, mappings). PyInstaller must collect `npv_build/data` (6 files: save_versions, fallback_outfit, blender/bake_head.py, cet_dumper/init.lua, mappings/2.13.json, donors/2.13.json). Use `--collect-data npv_build`.
- `customtkinter` ships its own theme JSON + assets; `tkinterdnd2` ships platform tcl/tkdnd libraries. Both are missed by default — use `--collect-all customtkinter --collect-all tkinterdnd2`.
- Two entry points, one bundle: the GUI is the PyInstaller target; the CLI is exposed by a tiny launcher that dispatches to `cli:main` when invoked with args / a `--cli` flag (see Task 3).

## File Structure

- `packaging/npv-build.spec` (new) — PyInstaller spec (one-dir, both entries, data collection).
- `packaging/entry.py` (new) — unified entry: no args or GUI context → `gui.main()`; args present → `cli.main()`. So one frozen exe serves both.
- `packaging/build_appimage.sh` (new) — wraps the PyInstaller one-dir output into an AppImage.
- `packaging/npv-build.desktop`, `packaging/AppRun` (new) — AppImage metadata + launcher.
- `.github/workflows/release.yml` (new) — tag-triggered build+release.
- `CHANGELOG.md` (new), `pyproject.toml` (version → 2.0.0), `docs/release-qa.md` (new), `README.md` (install-from-release section).

## Plan Roadmap

Plan 7 of 7 (final milestone). Order: T1 version+changelog → T2 PyInstaller spec (Linux one-dir builds locally) → T3 unified entry (GUI+CLI in one exe) → T4 AppImage packaging (builds locally) → T5 release workflow (tag-triggered, both OS) → T6 release QA checklist + docs → T7 milestone gate (tag a test release, verify artifacts). T2-T4 are verifiable on this Linux machine; T5's Windows half is CI-only.

---

### Task 1: Version bump to 2.0.0 + CHANGELOG

**Files:**
- Modify: `pyproject.toml` (version `2.0.0.dev0` → `2.0.0`)
- Create: `CHANGELOG.md`
- Test: `tests/test_version.py`

**Interfaces:**
- Produces: `npv_build.__version__` readable at runtime (add `__version__ = "2.0.0"` to `npv_build/__init__.py` if not present) so the GUI/CLI and release workflow can reference one source of truth.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_version.py
import tomllib
from pathlib import Path

import npv_build


def test_package_version_is_2_0_0():
    assert npv_build.__version__ == "2.0.0"


def test_pyproject_version_matches_package():
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == npv_build.__version__
```

- [ ] **Step 2: RED** — `uv run pytest tests/test_version.py -q` → fails (`__version__` missing / version mismatch).

- [ ] **Step 3: Implement** — set `version = "2.0.0"` in `pyproject.toml`; add to `npv_build/__init__.py`:

```python
__version__ = "2.0.0"
```

(`npv_build/__init__.py` is currently empty — this is its only content.)

- [ ] **Step 4: Create CHANGELOG.md**

```markdown
# Changelog

All notable changes to npv-build are documented here. Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org/).

## [2.0.0] - 2026-07-17

The 2.0 rewrite: a GUI-first, cross-platform npv-build.

### Added
- **GUI-first workflow** — first-run wizard (game-dir detect + guided dependency install), save browser with thumbnails, build view with cancel and retry-from-failed-stage, mod manager (install/uninstall built NPVs), settings, and multi-appearance merge.
- **Resumable builds** — checkpoint manifest; `--resume` / GUI "Retry from failed stage" skip already-completed stages.
- **Current-patch support** — decodes Cyberpunk saves from patch 2.13 through 2.31 (`--probe-save` to inspect any save); unknown builds hard-fail with a clear message.
- **Mod-manager-ready `.zip`** — every build emits an installable zip.
- **Security** — path-traversal-safe archive extraction, SHA-256-verified downloads, absolute tool-path resolution.
- **Bundled apps** — Windows `.zip` and Linux AppImage; no preinstalled Python required.

### Changed
- Core rewrite: typed error hierarchy, structured logging, cancellable subprocess adapter, `PipelineService` orchestration.
- WolvenKit floor raised to 8.19.

### Notes
- WolvenKit and Blender are downloaded (checksum-verified) by the first-run wizard, not bundled.
- Windows binaries are unsigned in this release; SmartScreen may warn on first launch.

[2.0.0]: https://github.com/pointdotpoint/npv-build/releases/tag/v2.0.0
```

- [ ] **Step 5: GREEN + gates** — `uv run pytest tests/test_version.py -q`, then `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`.

- [ ] **Step 6: Commit** — `git add pyproject.toml npv_build/__init__.py CHANGELOG.md tests/test_version.py && git commit -m "release: bump to 2.0.0 + CHANGELOG (spec PKG-5)"`

---

### Task 2: PyInstaller spec — Linux one-dir build

**Files:**
- Create: `packaging/npv-build.spec`, `packaging/entry.py`
- Modify: `pyproject.toml` (add `pyinstaller` to the dev group)
- Test: `tests/test_packaging_entry.py`

**Interfaces:**
- Consumes: `npv_build.gui:main`, `npv_build.cli:main`.
- Produces: `packaging/entry.py` with `run()` dispatching GUI vs CLI; a PyInstaller build producing `dist/npv-build/npv-build` (one-dir). Task 3 refines entry dispatch; Task 4 wraps the dir into an AppImage.

- [ ] **Step 1: Add pyinstaller to dev deps** — in `pyproject.toml` `[dependency-groups] dev`, add `"pyinstaller"`. Run `uv lock && uv sync --extra gui`.

- [ ] **Step 2: Write the entry module**

```python
# packaging/entry.py
"""Unified frozen entry point: dispatch to CLI when args are present, else GUI.

A single PyInstaller executable serves both `npv-build` (CLI) and the GUI:
- launched with command-line arguments  -> CLI (npv_build.cli.main)
- launched with no arguments (double-click) -> GUI (npv_build.gui.main)
"""

import sys


def run() -> None:
    # argv[0] is the exe; real args start at [1]
    if len(sys.argv) > 1:
        from npv_build.cli import main as cli_main

        sys.exit(cli_main())
    from npv_build.gui import main as gui_main

    gui_main()


if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Write the failing test** (the entry dispatch is pure-logic testable):

```python
# tests/test_packaging_entry.py
import sys
from pathlib import Path

# packaging/ is not a package; load entry.py directly
import importlib.util

_ENTRY = Path(__file__).resolve().parents[1] / "packaging" / "entry.py"
_spec = importlib.util.spec_from_file_location("npv_entry", _ENTRY)
entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry)


def test_dispatches_to_cli_when_args(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["npv-build", "--help"])
    monkeypatch.setattr("npv_build.cli.main", lambda: called.setdefault("cli", True) or 0)
    monkeypatch.setattr("npv_build.gui.main", lambda: called.setdefault("gui", True))
    try:
        entry.run()
    except SystemExit:
        pass
    assert called == {"cli": True}


def test_dispatches_to_gui_when_no_args(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["npv-build"])
    monkeypatch.setattr("npv_build.cli.main", lambda: called.setdefault("cli", True) or 0)
    monkeypatch.setattr("npv_build.gui.main", lambda: called.setdefault("gui", True))
    entry.run()
    assert called == {"gui": True}
```

- [ ] **Step 4: RED** — `uv run pytest tests/test_packaging_entry.py -q` → fails (entry.py missing).

- [ ] **Step 5: Write the .spec**

```python
# packaging/npv-build.spec
# PyInstaller one-dir build of npv-build (GUI + CLI in one executable).
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = collect_data_files("npv_build")  # npv_build/data/**
binaries = []
hiddenimports = []
for pkg in ("customtkinter", "tkinterdnd2"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="npv-build",
    console=True,  # keep a console so CLI output is visible; GUI still opens its own window
)
coll = COLLECT(exe, a.binaries, a.datas, name="npv-build")
```

- [ ] **Step 6: Build + smoke on this Linux machine**

Run:
```
cd packaging && uv run pyinstaller --clean --noconfirm npv-build.spec && cd ..
ls packaging/dist/npv-build/npv-build
# CLI smoke through the frozen exe:
./packaging/dist/npv-build/npv-build --probe-save "/home/pdp/.local/share/Steam/steamapps/compatdata/1091500/pfx/drive_c/users/steamuser/Saved Games/CD Projekt Red/Cyberpunk 2077/ManualSave-0/sav.dat"
```
Expected: prints the probe (build 2310, patch 2.31). This proves the frozen exe finds `npv_build/data` (the resources.files path) and the CLI dispatch works. Record the output. (GUI launch under the frozen exe is verified in Task 4's AppImage smoke.)

- [ ] **Step 7: gitignore build output** — add to `.gitignore`: `packaging/build/`, `packaging/dist/`, `*.spec` is KEPT (it's source). Actually keep `packaging/npv-build.spec`; ignore only `packaging/build/` and `packaging/dist/`.

- [ ] **Step 8: GREEN + gates + commit** — `uv run pytest tests/test_packaging_entry.py -q` then full gates; `git add packaging/npv-build.spec packaging/entry.py pyproject.toml uv.lock .gitignore tests/test_packaging_entry.py && git commit -m "build: PyInstaller one-dir spec + unified GUI/CLI entry (spec PKG-1)"`

---

### Task 3: CLI reachable from the bundle (`npv-build --cli` + wrapper)

**Files:**
- Modify: `packaging/entry.py` (robuster dispatch), `README.md` (document invoking CLI from the bundle)
- Test: `tests/test_packaging_entry.py` (extend)

**Interfaces:**
- Consumes: entry.run (Task 2).
- Produces: the frozen exe run with any args → CLI; run with no args → GUI. Documented: `npv-build.exe <save> "Name" ...` (Windows) / `./npv-build <save> "Name" ...` (Linux AppImage) invokes the CLI.

- [ ] **Step 1: Extend the entry test** for an explicit `--gui` override (so a user can force the GUI even with an env that looks CLI-ish):

```python
def test_gui_forced_with_flag(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["npv-build", "--gui"])
    monkeypatch.setattr("npv_build.cli.main", lambda: called.setdefault("cli", True) or 0)
    monkeypatch.setattr("npv_build.gui.main", lambda: called.setdefault("gui", True))
    entry.run()
    assert called == {"gui": True}
```

- [ ] **Step 2: RED → implement** the `--gui` override in `entry.run()`:

```python
def run() -> None:
    args = sys.argv[1:]
    if args == ["--gui"]:
        from npv_build.gui import main as gui_main

        gui_main()
        return
    if args:
        from npv_build.cli import main as cli_main

        sys.exit(cli_main())
    from npv_build.gui import main as gui_main

    gui_main()
```

- [ ] **Step 3: README** — add a "Using the bundled app" section: double-click launches the GUI; from a terminal, pass a save path + name to run the CLI; `--gui` forces the GUI.

- [ ] **Step 4: GREEN + gates + commit** — `git add packaging/entry.py README.md tests/test_packaging_entry.py && git commit -m "build: --gui override + document CLI-from-bundle (spec PKG-1)"`

---

### Task 4: Linux AppImage packaging

**Files:**
- Create: `packaging/build_appimage.sh`, `packaging/npv-build.desktop`, `packaging/AppRun`
- Test: manual (AppImage build + launch on this machine)

**Interfaces:**
- Consumes: the PyInstaller one-dir output `packaging/dist/npv-build/` (Task 2).
- Produces: `packaging/dist/npv-build-2.0.0-x86_64.AppImage`. Task 5's Linux CI job runs this script.

- [ ] **Step 1: Write the .desktop + AppRun**

`packaging/npv-build.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=npv-build
Comment=Cyberpunk 2077 NPV builder
Exec=npv-build
Icon=npv-build
Categories=Utility;
Terminal=false
```

`packaging/AppRun` (executable):
```bash
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/npv-build/npv-build" "$@"
```

- [ ] **Step 2: Write build_appimage.sh**

```bash
#!/usr/bin/env bash
# Build a Linux AppImage from the PyInstaller one-dir output.
# Usage: packaging/build_appimage.sh <version>
set -euo pipefail
VERSION="${1:?usage: build_appimage.sh <version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/packaging"
DIST="$PKG/dist"
APPDIR="$DIST/npv-build.AppDir"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r "$DIST/npv-build" "$APPDIR/usr/bin/npv-build"
cp "$PKG/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp "$PKG/npv-build.desktop" "$APPDIR/npv-build.desktop"
# minimal icon (1x1 png is valid; a real icon can replace it later)
if [ ! -f "$PKG/npv-build.png" ]; then
  printf '\x89PNG\r\n\x1a\n' > "$APPDIR/npv-build.png"  # placeholder
else
  cp "$PKG/npv-build.png" "$APPDIR/npv-build.png"
fi

# fetch appimagetool if not present
TOOL="$DIST/appimagetool.AppImage"
if [ ! -f "$TOOL" ]; then
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$TOOL"
fi

ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" \
  "$DIST/npv-build-${VERSION}-x86_64.AppImage"
echo "built: $DIST/npv-build-${VERSION}-x86_64.AppImage"
```

- [ ] **Step 3: Build + launch smoke on this machine**

Run:
```
chmod +x packaging/AppRun packaging/build_appimage.sh
packaging/build_appimage.sh 2.0.0
ls -la packaging/dist/npv-build-2.0.0-x86_64.AppImage
# CLI smoke through the AppImage:
packaging/dist/npv-build-2.0.0-x86_64.AppImage --probe-save "<ManualSave-0 sav.dat path>"
# GUI smoke (headless, times out fast — just prove it launches without a crash):
timeout 12 packaging/dist/npv-build-2.0.0-x86_64.AppImage --gui || true
```
Expected: the AppImage file exists and is executable; the CLI probe prints patch 2.31; the `--gui` launch opens (or under headless times out cleanly without an import/collection crash). If the GUI crashes with a missing customtkinter/tkinterdnd2 data error, the `.spec`'s `collect_all` for that package needs fixing (Task 2) — iterate. Record the outcome.

- [ ] **Step 4: Commit** — `git add packaging/build_appimage.sh packaging/AppRun packaging/npv-build.desktop && git commit -m "build: Linux AppImage packaging (spec PKG-2)"`

---

### Task 5: Tag-triggered release workflow

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: the `.spec` (T2), `build_appimage.sh` (T4).
- Produces: on push of a `v*` tag, a draft GitHub Release with `npv-build-<ver>-x86_64.AppImage`, `npv-build-<ver>-windows.zip`, and `SHA256SUMS` attached.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/release.yml
name: release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write

jobs:
  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: false
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
      - run: uv sync --locked --extra gui
      - run: sudo apt-get update && sudo apt-get install -y libfuse2
      - run: cd packaging && uv run pyinstaller --clean --noconfirm npv-build.spec
      - run: packaging/build_appimage.sh "${GITHUB_REF_NAME#v}"
      - uses: actions/upload-artifact@v4
        with:
          name: linux
          path: packaging/dist/*.AppImage

  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: false
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
      - run: uv sync --locked --extra gui
      - run: cd packaging; uv run pyinstaller --clean --noconfirm npv-build.spec
      - name: Zip the one-dir bundle
        shell: pwsh
        run: |
          $v = "${env:GITHUB_REF_NAME}".TrimStart("v")
          Compress-Archive -Path packaging/dist/npv-build/* -DestinationPath "packaging/dist/npv-build-$v-windows.zip"
      - uses: actions/upload-artifact@v4
        with:
          name: windows
          path: packaging/dist/*.zip

  release:
    needs: [build-linux, build-windows]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          path: artifacts
      - name: Collect + checksum
        run: |
          mkdir -p release
          find artifacts -type f \( -name "*.AppImage" -o -name "*.zip" \) -exec cp {} release/ \;
          cd release && sha256sum * > SHA256SUMS && cat SHA256SUMS
      - name: Draft release
        uses: softprops/action-gh-release@v2
        with:
          draft: true
          files: release/*
          body_path: CHANGELOG.md
          generate_release_notes: false
```

- [ ] **Step 2: Validate the workflow YAML** — `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` (or `--with pyyaml`). Expected: parses without error.

- [ ] **Step 3: Commit + push** — `git add .github/workflows/release.yml && git commit -m "ci: tag-triggered release — AppImage + Windows zip + SHA256SUMS (spec PKG-4)"` and push to master.

- [ ] **Step 4: Dry-run gate is in Task 7** (tagging a real test release). Do NOT tag here — that's the milestone gate.

---

### Task 6: Release QA checklist + docs

**Files:**
- Create: `docs/release-qa.md`
- Modify: `README.md` (install-from-release section), `CLAUDE.md` (packaging note)

**Interfaces:** none — docs.

- [ ] **Step 1: Write docs/release-qa.md** — a manual, both-OS checklist (TST-7):

```markdown
# Release QA Checklist

Run before publishing a release (both Windows and Linux). Fresh machine / clean user profile ideal.

## Per platform (Windows .zip, Linux AppImage)
- [ ] Artifact downloads and its SHA-256 matches the line in `SHA256SUMS`.
- [ ] Launches by double-click → GUI opens (Windows: dismiss the SmartScreen warning — unsigned is expected).
- [ ] First-run wizard appears; game-dir auto-detect finds the install (or manual browse works).
- [ ] Wizard installs WolvenKit + Blender (checksum-verified) — NOT bundled.
- [ ] Save browser lists saves with thumbnails.
- [ ] Build a real NPV from a current-patch save → succeeds; the `.zip` output is produced.
- [ ] Spawn the NPV in-game via AMM → correct face/clothing/animation, no T-pose.
- [ ] CLI works from a terminal: `npv-build --probe-save <save>` prints the patch.

## Artifact hygiene
- [ ] No third-party binaries in the artifact (no WolvenKit/Blender/.NET/CDPR assets) — inspect the bundle.
- [ ] SHA256SUMS covers every attached artifact.
```

- [ ] **Step 2: README install section** — "Download from Releases": grab the AppImage (Linux, `chmod +x`, run) or the `.zip` (Windows, extract, run `npv-build.exe`); note tools auto-install on first run; note unsigned Windows binary.

- [ ] **Step 3: Commit** — `git add docs/release-qa.md README.md CLAUDE.md && git commit -m "docs: release QA checklist + install-from-release (spec TST-7, PKG)"`

---

### Task 7: Milestone gate — tag a test release, verify artifacts

**Files:** none — this is the end-to-end proof that the release pipeline produces valid artifacts.

- [ ] **Step 1: Full local verification first** — full suite + ruff green; the AppImage built in Task 4 exists, its CLI probe works, and `sha256sum` of it is recorded.

- [ ] **Step 2: Push everything to master; confirm normal CI green** (the release workflow only triggers on tags, so master CI is unaffected — confirm the ci.yml jobs still pass).

- [ ] **Step 3: Tag a real release** — `git tag v2.0.0 && git push origin v2.0.0`. This fires `release.yml`.

- [ ] **Step 4: Watch the release workflow** — `gh run watch` on the release run. Both build jobs (linux, windows) must succeed; the release job must attach the AppImage, the Windows zip, and SHA256SUMS to a DRAFT release. `gh release view v2.0.0` shows the assets.

- [ ] **Step 5: Verify the draft release artifacts**:
  - `gh release view v2.0.0 --json assets` lists exactly: `*-x86_64.AppImage`, `*-windows.zip`, `SHA256SUMS`.
  - Download the AppImage from the draft (`gh release download v2.0.0 -p "*.AppImage"`), verify its sha256 matches SHA256SUMS, and run its `--probe-save` smoke.
  - Confirm the release is a DRAFT (not published) — the user publishes it.

- [ ] **Step 6:** If a build job fails (a PyInstaller collection miss on Windows, an appimagetool/libfuse issue on Linux), fix the `.spec`/script/workflow, delete the tag (`git push --delete origin v2.0.0 && git tag -d v2.0.0`), re-tag, re-run. Iterate until both artifacts build and attach cleanly.

- [ ] **Step 7:** Leave the draft release for the user to publish. Report the draft URL + the verified SHA256SUMS.

---

## Exit Criteria (spec M6)

- PKG-1: PyInstaller one-dir bundle with GUI + CLI in one exe (verified: frozen CLI probe works on Linux).
- PKG-2: Linux AppImage (built + smoke-verified locally); Windows `.zip` (built in CI).
- PKG-3: no third-party binaries in either artifact; tools download on first run (verified by inspecting the bundle for NFR-4 compliance).
- PKG-4: `v*` tag triggers a workflow that attaches AppImage + Windows zip + SHA256SUMS to a DRAFT release.
- PKG-5: version 2.0.0; CHANGELOG.md present.
- PKG-6: uv.lock committed; dev setup documented.
- TST-7: release QA checklist exists.
- A real `v2.0.0` tag produced a draft release with all three assets, checksums verified — left for the user to publish.

## Notes

- **The Windows `.zip` can only be built/verified in CI** (windows-latest). The release workflow's windows job succeeding + the CI test job's windows-latest already-green suite are the verification; a human runs the Windows half of the QA checklist before publishing.
- **appimagetool needs libfuse2** on the runner (`apt-get install -y libfuse2`) — in the workflow. Locally, the `--appimage-extract-and-run` flag in build_appimage.sh avoids the FUSE requirement for building.
- **Icon** is a placeholder PNG — a real icon is a trivial later polish, not an M6 blocker.
- **Do not publish** the release — M6 produces a DRAFT; publishing is the user's call (it's outward-facing distribution).
