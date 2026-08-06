# Follow-up Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four known non-blocking follow-ups from `docs/ROADMAP.md`: body-tattoo appearance ignores skin-tone overrides, stale `npv-inject` binaries fail confusingly mid-build, the `appearance_data` bridge parse-failure path is untested, and the release QA checklist has no cross-distribution Linux procedure.

**Architecture:** Three small independent code fixes plus one doc addition. The tattoo fix re-keys the tattoo appearance to the *effective* skin tone inside `mapping.resolve_assets` (so it covers GUI overrides, presets, and any future CC source uniformly). The staleness check compares source vs binary mtimes at inject-binary resolution time and hard-fails with a rebuild command, per the project's hard-fail policy. The bridge test locks in the existing structured-error contract. Tasks are fully independent — any order, any subset.

**Tech Stack:** Python 3.11, pytest, existing `npv_build` modules only. No new dependencies.

## Global Constraints

- Gates for every task: `uv run ruff check .` clean and `uv run pytest -q` green (baseline before this plan: 405 passed / 4 skipped — skips are user-gated preset/e2e data, do not touch them).
- Hard-fail policy: pipeline stops on first error; no partial/degraded output.
- No CDPR bytes in the repo — tests use synthetic path strings and option IDs only.
- Depot paths use Windows backslashes (`base\characters\...`) even on Linux.
- Bridge (`webui_api.py`) methods must never raise into JS — they return JSON dicts with structured errors.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Body tattoo follows the effective skin tone

**Context:** The save stores the body tattoo as a skin-tone-keyed appearance string, e.g. `w__01_ca_pale` (tone segment `01_ca_pale`). `mapping.resolve_assets` copies that raw string verbatim into `asset_paths["body_tattoo"]["appearance"]` (mapping.py step 1c, ~line 249). When the GUI's appearance inspector overrides `skin_tone`, `gui_logic/appearance.py:apply_overrides` updates `cc["skin"]["tone_id"]` but the tattoo selection's raw stays keyed to the save's original tone — the built NPV renders the tattoo tinted for the wrong skin. Fix: re-key the tone segment of the tattoo appearance to `cc_settings["skin"]["tone_id"]` whenever it is present. For non-overridden builds this is a no-op (the save's tone_id equals the raw's tone segment), so behavior only changes when they diverge.

The tone-segment pattern already exists in `gui_logic/appearance.py:_appearance_matches_rig_and_tone` as `r"__(\d{2}_(?:ca|bl)_[a-z]+)"` — reuse the same shape in mapping.py.

**Files:**
- Modify: `npv_build/mapping.py` (step 1c body-tattoo block, ~lines 249–265; add one module-level compiled regex near the other module constants at the top)
- Test: `tests/test_mapping.py`

**Interfaces:**
- Consumes: `mapping.resolve_assets(cc_settings, ...) -> dict` (existing signature, unchanged).
- Produces: `assets["body_tattoo"]["appearance"]` now carries the effective tone. No signature changes; `_apply_body_tattoo` in wolvenkit.py consumes it unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mapping.py`, next to `test_resolve_assets_body_tattoo` (~line 195). Reuse that test's selection dicts verbatim so field shape stays consistent:

```python
def test_resolve_assets_body_tattoo_follows_effective_skin_tone():
    """When cc_settings carries a skin tone (e.g. after a skin_tone override),
    the tattoo appearance must be re-keyed to that tone, not the save's
    original tone embedded in the selection raw."""
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "skin": {"tone_id": "03_ca_senna"},
        "selections": [
            {
                "slot": "head",
                "prefix": "h0",
                "index": 0,
                "rig": "pwa",
                "group": "basehead",
                "variant": "01_ca_pale",
                "raw": "h0_000_pwa__basehead__01_ca_pale",
                "cname_hash": 1,
            },
            {
                "slot": "TPP_Body",
                "prefix": "",
                "index": 0,
                "rig": "",
                "group": "01_ca_pale",
                "variant": "",
                "raw": "w__01_ca_pale",
                "label": "body_tattoo_02",
                "cname_hash": 2,
            },
        ],
    }

    assets = resolve_assets(cc_settings)

    assert assets["body_tattoo"] == {"shape": "02", "appearance": "w__03_ca_senna"}


def test_resolve_assets_body_tattoo_keeps_raw_without_skin_tone():
    """No skin tone in cc_settings (or empty) -> tattoo raw passes through."""
    cc_settings = {
        "patch": "2.13",
        "body_rig": "pwa",
        "skin": {"tone_id": ""},
        "selections": [
            {
                "slot": "TPP_Body",
                "prefix": "",
                "index": 0,
                "rig": "",
                "group": "01_ca_pale",
                "variant": "",
                "raw": "w__01_ca_pale",
                "label": "body_tattoo_02",
                "cname_hash": 2,
            },
        ],
    }

    assets = resolve_assets(cc_settings)

    assert assets["body_tattoo"]["appearance"] == "w__01_ca_pale"
```

- [ ] **Step 2: Run tests to verify the first fails**

Run: `uv run pytest tests/test_mapping.py -k tattoo -v`
Expected: `test_resolve_assets_body_tattoo_follows_effective_skin_tone` FAILS (appearance is `w__01_ca_pale`); the `keeps_raw` test and the two pre-existing tattoo tests PASS.

- [ ] **Step 3: Implement the re-keying in mapping.py**

Near the top of `npv_build/mapping.py` (with the other module-level definitions, after the imports):

```python
# Skin-tone segment inside tone-keyed appearance names, e.g. the
# "__01_ca_pale" in "w__01_ca_pale". Same shape as
# gui_logic.appearance._appearance_matches_rig_and_tone.
_TONE_SEGMENT_RE = re.compile(r"__\d{2}_(?:ca|bl)_[a-z]+")
```

In step 1c, replace the `asset_paths["body_tattoo"] = ...` assignment block:

```python
    for sel in selections:
        m = re.match(r"^body_tattoo_(\d+)$", sel.get("label", "") or "")
        if m and sel.get("raw"):
            shape = m.group(1).zfill(2)
            appearance = sel["raw"]
            tone_id = (cc_settings.get("skin") or {}).get("tone_id") or ""
            if tone_id:
                rekeyed = _TONE_SEGMENT_RE.sub(f"__{tone_id}", appearance)
                if rekeyed != appearance:
                    logger.info(
                        f"[Mapping] Body tattoo re-keyed to effective skin tone: "
                        f"{appearance} -> {rekeyed}"
                    )
                appearance = rekeyed
            asset_paths["body_tattoo"] = {"shape": shape, "appearance": appearance}
            tx_ent = (
                "base\\characters\\common\\player_base_bodies\\appearances\\entity\\"
                f"tx_000_{body_rig}_base__full_tattoo_{shape}.ent"
            )
            part_entities.append(tx_ent)
            logger.info(f"[Mapping] Body tattoo {shape} -> {appearance}")
            break
```

Note: the pre-existing `test_resolve_assets_body_tattoo` has no `skin` key in its cc_settings, so it must keep passing unchanged (tone_id empty → passthrough).

- [ ] **Step 4: Run the full mapping suite**

Run: `uv run pytest tests/test_mapping.py -v`
Expected: all PASS, including both pre-existing tattoo tests.

- [ ] **Step 5: Full gate**

Run: `uv run ruff check . && uv run pytest -q`
Expected: clean, 407 passed / 4 skipped.

- [ ] **Step 6: Commit**

```bash
git add npv_build/mapping.py tests/test_mapping.py
git commit -m "fix(mapping): re-key body tattoo to effective skin tone

A skin_tone override changed skin.tone_id but the tattoo selection raw
stayed keyed to the save's original tone, tinting the tattoo for the
wrong skin. resolve_assets now rewrites the tone segment from
cc_settings['skin']['tone_id']; no-op when they already match.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Hard-fail on a stale npv-inject binary

**Context:** During the 2026-07-19 live gate, a `tools/npv-inject` binary built in May ran against newer source and failed mid-build with the baffling error `Unknown component type: 'entMorphTargetSkinnedMeshComponent'`. The fix was a manual `dotnet build`. Prevent the recurrence: when `wolvenkit._resolve_inject_binary()` resolves a binary from the local `tools/npv-inject/bin/...` tree, compare its mtime against the newest `.cs`/`.csproj` under `tools/npv-inject` (excluding `bin/` and `obj/`). Source newer than binary → raise `WolvenKitError` with the exact rebuild command, per the hard-fail policy. Binaries found on PATH or via `bundled_tool_path` have no adjacent source tree — skip the check for those.

**Files:**
- Modify: `npv_build/wolvenkit.py` (add two helpers below `_resolve_inject_binary`, ~line 36; wire into the tools-dir candidate loop)
- Test: `tests/test_build_project.py`

**Interfaces:**
- Consumes: `WolvenKitError` from `npv_build.wk_cli` (already imported in wolvenkit.py:29; constructor used as `WolvenKitError(message, operation=...)`).
- Produces: `_check_inject_binary_freshness(binary: Path, project_dir: Path) -> None` (raises `WolvenKitError` when stale) and `_newest_inject_source_mtime(project_dir: Path) -> float | None` — module-private, tested directly.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_build_project.py`:

```python
import os

import pytest

from npv_build.wk_cli import WolvenKitError
from npv_build.wolvenkit import _check_inject_binary_freshness


def _fake_inject_tree(tmp_path, source_mtime, binary_mtime):
    project = tmp_path / "npv-inject"
    (project / "bin" / "Release" / "net8.0").mkdir(parents=True)
    source = project / "Program.cs"
    source.write_text("// source")
    os.utime(source, (source_mtime, source_mtime))
    binary = project / "bin" / "Release" / "net8.0" / "npv-inject"
    binary.write_bytes(b"\x7fELF")
    os.utime(binary, (binary_mtime, binary_mtime))
    return binary, project


def test_stale_inject_binary_hard_fails(tmp_path):
    """Source newer than the built binary must stop the build with a
    rebuild command, not fail later with a confusing component error."""
    binary, project = _fake_inject_tree(tmp_path, source_mtime=2000.0, binary_mtime=1000.0)
    with pytest.raises(WolvenKitError, match="dotnet build tools/npv-inject"):
        _check_inject_binary_freshness(binary, project)


def test_fresh_inject_binary_passes(tmp_path):
    binary, project = _fake_inject_tree(tmp_path, source_mtime=1000.0, binary_mtime=2000.0)
    _check_inject_binary_freshness(binary, project)  # must not raise


def test_freshness_check_skips_without_sources(tmp_path):
    """No .cs/.csproj sources next to the binary (e.g. stripped tree):
    nothing to compare, never block the build."""
    binary, project = _fake_inject_tree(tmp_path, source_mtime=2000.0, binary_mtime=1000.0)
    (project / "Program.cs").unlink()
    _check_inject_binary_freshness(binary, project)  # must not raise


def test_freshness_ignores_bin_and_obj_artifacts(tmp_path):
    """Build artifacts under bin/ and obj/ carry .cs files (AssemblyInfo);
    they are outputs, not sources, and must not trigger staleness."""
    binary, project = _fake_inject_tree(tmp_path, source_mtime=1000.0, binary_mtime=2000.0)
    obj_cs = project / "obj" / "Release" / "AssemblyInfo.cs"
    obj_cs.parent.mkdir(parents=True)
    obj_cs.write_text("// generated")
    os.utime(obj_cs, (3000.0, 3000.0))
    _check_inject_binary_freshness(binary, project)  # must not raise
```

Keep existing imports in the file — only add the missing ones.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_build_project.py -k "inject_binary or freshness" -v`
Expected: FAIL with `ImportError: cannot import name '_check_inject_binary_freshness'`.

- [ ] **Step 3: Implement the helpers and wire them in**

In `npv_build/wolvenkit.py`, below `_resolve_inject_binary`:

```python
_INJECT_SOURCE_SUFFIXES = {".cs", ".csproj"}


def _newest_inject_source_mtime(project_dir: Path) -> float | None:
    """Newest mtime among npv-inject sources, ignoring bin/ and obj/ outputs."""
    newest: float | None = None
    for path in project_dir.rglob("*"):
        if path.suffix not in _INJECT_SOURCE_SUFFIXES:
            continue
        if "bin" in path.parts or "obj" in path.parts:
            continue
        mtime = path.stat().st_mtime
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def _check_inject_binary_freshness(binary: Path, project_dir: Path) -> None:
    """Hard-fail when the locally built npv-inject predates its source.

    A stale binary fails mid-build with misleading errors (seen live:
    'Unknown component type' for a type the newer source handles). Only
    called for binaries resolved from tools/npv-inject/bin — PATH and
    bundled binaries have no adjacent source tree.
    """
    newest_source = _newest_inject_source_mtime(project_dir)
    if newest_source is None or not binary.exists():
        return
    if newest_source > binary.stat().st_mtime:
        raise WolvenKitError(
            f"npv-inject binary is older than its source: {binary}. "
            "Rebuild with: dotnet build tools/npv-inject -c Release",
            operation="inject",
        )
```

Wire into `_resolve_inject_binary` — the tools-dir candidate loop becomes:

```python
    tools_dir = Path(__file__).parent.parent / "tools" / "npv-inject"
    for candidate in [
        tools_dir / "bin" / "Release" / "net8.0" / INJECT_BINARY,
        tools_dir / "bin" / "Debug" / "net8.0" / INJECT_BINARY,
    ]:
        if candidate.exists():
            _check_inject_binary_freshness(candidate, tools_dir)
            return str(candidate)
```

PATH (`shutil.which`) and `bundled_tool_path` returns stay unchecked, as before.

- [ ] **Step 4: Run the new tests**

Run: `uv run pytest tests/test_build_project.py -k "inject_binary or freshness" -v`
Expected: 4 PASS.

- [ ] **Step 5: Full gate**

Run: `uv run ruff check . && uv run pytest -q`
Expected: clean, all green (411 passed / 4 skipped when run after Task 1; counts assume plan order). If any existing test resolves the real repo's `tools/npv-inject` binary and the working tree has source newer than the built binary, the correct fix is to rebuild the binary (`dotnet build tools/npv-inject -c Release`), not to weaken the check — that is the exact situation the check exists for.

- [ ] **Step 6: Commit**

```bash
git add npv_build/wolvenkit.py tests/test_build_project.py
git commit -m "feat(inject): hard-fail when npv-inject binary is stale

A May-built binary running against newer source failed mid-build with
'Unknown component type'. Resolution from tools/npv-inject/bin now
compares binary mtime against the newest .cs/.csproj source and stops
with the rebuild command. PATH/bundled binaries are exempt.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Smoke tests for the appearance_data parse-failure path

**Context:** `webui_api.WebUiApi.appearance_data` (webui_api.py:778) already catches `NpvError` and bare `Exception` and returns `{"ok": False, "error": ..., "remediation": ...}` — the bridge boundary must never raise into JS. That error path has zero test coverage; a refactor could silently break it and crash the frontend. Lock the contract in with two tests. No production code changes expected — if a test exposes a real raise, fix `appearance_data` to return the structured dict instead.

**Files:**
- Test: `tests/test_webui_api.py` (add next to `test_appearance_data_rows_and_overrides`, ~line 701)

**Interfaces:**
- Consumes: `WebUiApi().appearance_data(save_path: str) -> dict` (existing).
- Produces: nothing new — regression coverage only.

- [ ] **Step 1: Write the tests**

```python
def test_appearance_data_missing_file_returns_structured_error(tmp_path):
    """Bridge boundary: a nonexistent save path must come back as a JSON
    error dict, never an exception into JS."""
    result = WebUiApi().appearance_data(str(tmp_path / "does_not_exist.dat"))
    assert result["ok"] is False
    assert result["error"]
    assert "remediation" in result


def test_appearance_data_corrupt_save_returns_structured_error(tmp_path):
    """Garbage bytes (no CSAV magic) must produce a structured parse error."""
    bad_save = tmp_path / "sav.dat"
    bad_save.write_bytes(b"\x00\xff" * 64)
    result = WebUiApi().appearance_data(str(bad_save))
    assert result["ok"] is False
    assert result["error"]
    assert "remediation" in result
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_webui_api.py -k appearance_data -v`
Expected: PASS (the error handling already exists — these are pin-down tests). If either test instead errors or raises, that is a real bridge-contract bug: fix `appearance_data` so both cases return the `{"ok": False, "error": ..., "remediation": ...}` dict, then re-run to green.

- [ ] **Step 3: Full gate**

Run: `uv run ruff check . && uv run pytest -q`
Expected: clean, all green (413 passed / 4 skipped when run after Tasks 1–2; counts assume plan order).

- [ ] **Step 4: Commit**

```bash
git add tests/test_webui_api.py
git commit -m "test(webui): pin appearance_data parse-failure contract

Missing and corrupt saves must return structured {ok: False} dicts at
the bridge boundary, never raise into JS. Path was untested.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Cross-distribution Linux spot-check procedure in release QA

**Context:** The AppImage bundles Qt WebEngine and CI launches the GUI under Xvfb (Ubuntu). Non-Ubuntu breakage would only surface via user reports. `docs/release-qa.md` (sections: "Required release assets", "Per platform and format", "Artifact hygiene") has no cross-distro procedure. Add one so any future release run — human or agent-prepared, human-executed — has an explicit checklist. This is documentation only; actually running the checks on real distros stays a human step.

**Files:**
- Modify: `docs/release-qa.md` (append a new section after "Per platform and format")

**Interfaces:** none — documentation.

- [ ] **Step 1: Add the section**

Append after the "Per platform and format" section:

```markdown
## Cross-distribution Linux spot-check

The AppImage bundles its own Qt WebEngine runtime, but glibc floor, GPU/EGL
stack, and sandbox behavior differ per distro. CI only proves Ubuntu under
Xvfb. Before (or shortly after) publishing, spot-check the release AppImage
on at least one distro from a different family than the last release's check.
Rotate through:

| Family | Example distro | Notes |
| --- | --- | --- |
| Debian-based | Ubuntu LTS (CI-covered), Mint | baseline |
| Fedora/RHEL | Fedora Workstation (current) | newer glibc, Wayland default |
| Arch-based | Arch, EndeavourOS | rolling glibc/Mesa |
| openSUSE | Tumbleweed | rolling, AppArmor default |

Per distro, on a real desktop session (not a container):

1. Download the release `.AppImage` + `SHA256SUMS`; verify
   `sha256sum -c SHA256SUMS` passes for it.
2. `chmod +x` and double-click (or run) with **no arguments** — the GUI must
   open and render the Source screen (no blank/white window, no missing-lib
   dialog).
3. Wayland session if available: confirm the window renders (Qt may fall back
   to XWayland — fallback is acceptable, a blank window is not).
4. From a terminal, run CLI mode against any real save:
   `./npv-build-*.AppImage <sav.dat> "QA V" --output /tmp/qa_v` — it must
   parse the save and report the patch version (full build optional; needs a
   game install).
5. Record distro, version, session type (X11/Wayland), and result in the
   release notes draft.

Failures here are release blockers only if the GUI cannot launch at all on a
mainstream current distro; render glitches get an issue with the distro +
session details instead.
```

- [ ] **Step 2: Verify the doc renders and gates stay green**

Run: `uv run ruff check . && uv run pytest -q`
Expected: unchanged (docs-only change); skim the rendered markdown for table formatting.

- [ ] **Step 3: Commit**

```bash
git add docs/release-qa.md
git commit -m "docs(release-qa): add cross-distro Linux spot-check procedure

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## After all tasks

Update `docs/ROADMAP.md`: remove the four entries from "Follow-up candidates" (the cross-distro entry moves from "keep spot-checking" prose to a pointer at the new release-qa section; the tattoo entry is fixed outright, not deferred to a tattoo feature). Fold that edit into whichever task lands last, or commit separately as `docs(roadmap): follow-up hardening shipped`.

Expected final gate: `uv run ruff check .` clean, `uv run pytest -q` → 413 passed / 4 skipped.
