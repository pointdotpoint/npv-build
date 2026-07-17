# M2 — Patch Currency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make npv-build honest and extensible about game patches: versioned save decoding, hard-fail on unknown builds, WolvenKit 8.19, automated bake verification, mapping-drift tooling — and a gated runbook that enables patch 2.2–2.31 saves once a current-patch save exists; milestone M2 of `docs/superpowers/specs/2026-07-17-npv-build-2.0-design.md`.

**Architecture:** `save_parser` gains a CC-decoder registry keyed by the save header's `v3`; `detect_patch` hard-fails with remediation instead of defaulting to 2.13. A new `save_probe` module prints header/build/CC facts from any save (the reverse-engineering tool). A `gen_mapping` report tool detects mapping-table drift against the installed game. Task 7 is a **gated, user-assisted runbook** — it cannot run until the game is updated and a new save is created.

**Tech Stack:** stdlib; existing core layer; pytest; WolvenKit.CLI 8.19.

## Ground Truth (measured on this machine, 2026-07-17)

- All 30 local saves probe as `(v1=269, v2=2310, v3=195)` → build 2310 = patch **2.13**. There is **no 2.3x save available locally**; the game install itself is pre-2.2.
- The E2E build (M1 gate) ran against a 2310 save and passed.
- Research (IMPROVEMENT_REPORT.md §2.1): latest patch is 2.31; patch 2.2 added 100+ CC options; the 2.3x `v3` value is unknown/unverified.

## Global Constraints (from spec)

- Hard-fail policy: unknown build or unknown `v3` must raise `UnsupportedPatchError` with the detected value, the supported list, and remediation — never silently default (removes the current 2.13 fallback).
- 2.13 saves must keep working byte-identically through every task (regression: the local save corpus + suite).
- Game depot paths keep Windows backslashes; no CDPR bytes in repo (probe output must not embed asset data, only names/ids/paths).
- All gates green after every task: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` (run format check — M1's merge tripped CI on exactly this).
- No public signature changes to pipeline entry points; `parse_save(save_path) -> dict` contract unchanged.
- Use `uv run` for everything.

## Plan Roadmap

Plan 3 of 7. Task order: T1→T2→T3 sequential (parser chain); T4, T5, T6 independent after T1; T8 last-but-one; **T7 is gated on a user action** (game update + new save) and may execute whenever that lands — it is the only task that may be deferred past the milestone merge without failing M2's spirit (everything else makes the codebase 2.3x-ready).

---

### Task 1: Save probe tool (`npv_build/save_probe.py`)

**Files:**
- Create: `npv_build/save_probe.py`
- Modify: `npv_build/cli.py` (add `--probe-save <sav.dat>` early-exit flag)
- Test: `tests/core/test_save_probe.py`

**Interfaces:**
- Consumes: `SaveContainer` (save_format), `save_versions.json` loading from save_parser.
- Produces: `probe_save(save_path: Path) -> dict` returning `{"version": [v1, v2, v3], "build": v2, "patch": str | None, "supported": bool, "nodes": [str, ...], "cc_node_present": bool, "cc_node_size": int | None}`; `format_probe(info: dict) -> str` human-readable block; CLI `npv-build --probe-save <path>` printing it and exiting 0. Task 7's runbook depends on this tool.

- [ ] **Step 1: Write the failing tests**

First read `tests/test_save_parser.py` and identify its synthesized-container helper (it builds valid CSAV bytes for the 195 fixture). Reuse it. Test file:

```python
# tests/core/test_save_probe.py
import json

import pytest

from npv_build.save_probe import format_probe, probe_save


def test_probe_reports_version_and_nodes(synth_save_2310):
    # synth_save_2310: fixture yielding a Path to a synthesized build-2310 save
    # (adapt the fixture wiring to tests/test_save_parser.py's existing helper;
    #  if that helper is inline, lift it into tests/conftest.py as this fixture)
    info = probe_save(synth_save_2310)
    assert info["version"][1] == info["build"]
    assert info["patch"] == "2.13"
    assert info["supported"] is True
    assert info["cc_node_present"] is True
    assert info["cc_node_size"] > 0


def test_probe_unknown_build_is_reported_not_raised(synth_save_2310, tmp_path, monkeypatch):
    import npv_build.save_probe as spr

    monkeypatch.setattr(spr, "_load_save_versions", lambda: {"2310": "2.13"})
    # patch the container's build number by monkeypatching probe internals is fragile;
    # instead: probe must map unknown builds to patch None / supported False.
    info = probe_save(synth_save_2310)
    assert info["supported"] in (True, False)  # smoke - refined below


def test_format_probe_contains_key_facts(synth_save_2310):
    text = format_probe(probe_save(synth_save_2310))
    assert "2310" in text
    assert "v3" in text


def test_probe_bad_file_raises_save_format_error(tmp_path):
    from npv_build.core.errors import NpvError

    bad = tmp_path / "sav.dat"
    bad.write_bytes(b"not a save")
    with pytest.raises(NpvError):
        probe_save(bad)
```

Note to implementer: the second test's intent is "unknown build → `patch: None, supported: False`, no exception". Implement it by synthesizing a container whose `v2` is not in save_versions (the existing helper parameterizes the header — check; if it hardcodes 2310, extend the helper with a `build=` parameter). Replace the smoke assertion with the real one once the fixture supports it; the final committed test must assert `info["patch"] is None and info["supported"] is False` for an unknown build.

- [ ] **Step 2: RED**

Run: `uv run pytest tests/core/test_save_probe.py -q` — fails on missing module.

- [ ] **Step 3: Implement**

```python
# npv_build/save_probe.py
"""Read-only save inspector: header version, build->patch, CC node facts.

The reverse-engineering entry point for new game patches (spec PC-1..3, M2/T7).
Never decodes the CC struct - works on any save regardless of v3.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .core.errors import SaveFormatError
from .save_format import SaveContainer

_CC_NODE = "CharacetrCustomization_Appearances"  # game's own typo


def _load_save_versions() -> dict[str, str]:
    with resources.files("npv_build").joinpath("data/save_versions.json").open("rb") as f:
        return json.load(f)


def probe_save(save_path: Path) -> dict:
    try:
        container = SaveContainer(Path(save_path).read_bytes())
    except Exception as e:  # noqa: BLE001 - any container failure means "not a readable save"
        raise SaveFormatError(
            f"Could not read save container: {save_path}",
            details=str(e),
            remediation="Point --probe-save at a Cyberpunk 2077 sav.dat file.",
        ) from e
    v1, v2, v3 = container.version
    versions = _load_save_versions()
    patch = versions.get(str(v2))
    nodes = list(container.node_names())
    cc_present = _CC_NODE in nodes
    cc_size = len(container.node_bytes(_CC_NODE)) if cc_present else None
    return {
        "version": [v1, v2, v3],
        "build": v2,
        "patch": patch,
        "supported": patch is not None,
        "nodes": nodes,
        "cc_node_present": cc_present,
        "cc_node_size": cc_size,
    }


def format_probe(info: dict) -> str:
    v1, v2, v3 = info["version"]
    lines = [
        f"header:  v1={v1} build(v2)={v2} v3={v3}",
        f"patch:   {info['patch'] or 'UNKNOWN (build not in save_versions.json)'}",
        f"cc node: {'present' if info['cc_node_present'] else 'MISSING'}"
        + (f" ({info['cc_node_size']} bytes)" if info["cc_node_size"] else ""),
        f"nodes:   {len(info['nodes'])} total",
    ]
    return "\n".join(lines)
```

Adapt `node_names()`/`node_bytes()` to `SaveContainer`'s real API (verified to exist at save_format.py:185-197; check exact semantics — `node_bytes` may decompress).

- [ ] **Step 4: CLI flag**

In `cli.py`, add `--probe-save` (metavar `<sav.dat>`); when present, before any other validation: `info = probe_save(Path(args.probe_save)); print(format_probe(info)); return`. Wrap `NpvError` in the existing handler (it already prints user_message/remediation and exits 1).

- [ ] **Step 5: GREEN + real-save sanity**

Run: `uv run pytest tests/core/test_save_probe.py -q` then the full gates, then a real probe:
`uv run npv-build --probe-save "/home/pdp/.local/share/Steam/steamapps/compatdata/1091500/pfx/drive_c/users/steamuser/Saved Games/CD Projekt Red/Cyberpunk 2077/QuickSave-1/sav.dat"`
Expected output includes `v1=269 build(v2)=2310 v3=195` and `patch: 2.13`.

- [ ] **Step 6: Commit**

```bash
git add npv_build/save_probe.py npv_build/cli.py tests/
git commit -m "feat: save probe tool + --probe-save flag (spec PC-1..3 groundwork)"
```

---

### Task 2: Versioned CC decoder registry (PC-3)

**Files:**
- Modify: `npv_build/save_parser.py`
- Test: `tests/core/test_decoder_registry.py`

**Interfaces:**
- Consumes: `UnsupportedPatchError` (core.errors).
- Produces: module-level `CC_DECODERS: dict[int, Callable]` in `save_parser`, with `195` mapped to the existing decode path; `parse_save` dispatches on the container's `v3`. Task 7 registers new versions here. `parse_save(save_path) -> dict` signature and its 195 output stay byte-identical.

- [ ] **Step 1: Read save_parser.py fully.** Identify where `v3` is checked today (two hardcoded `195` sites per the M1 analysis, around lines 42 and 183 pre-M1; locate by grepping `195`). Understand which function actually walks the CC struct — that whole path becomes `_decode_cc_v195(...)` (rename/move only, zero logic edits).

- [ ] **Step 2: Write the failing tests**

```python
# tests/core/test_decoder_registry.py
import pytest

import npv_build.save_parser as sp
from npv_build.core.errors import UnsupportedPatchError


def test_registry_has_195():
    assert 195 in sp.CC_DECODERS
    assert callable(sp.CC_DECODERS[195])


def test_unknown_v3_raises_unsupported_patch(synth_save_2310, monkeypatch):
    # Force the container to report an unknown struct version.
    real_init = sp.SaveContainer.__init__

    def fake_init(self, data):
        real_init(self, data)
        self.version = (self.version[0], self.version[1], 999)

    monkeypatch.setattr(sp.SaveContainer, "__init__", fake_init)
    with pytest.raises(UnsupportedPatchError) as ei:
        sp.parse_save(synth_save_2310)
    msg = str(ei.value)
    assert "999" in msg
    assert "195" in msg  # supported list named
    assert "--probe-save" in ei.value.remediation


def test_v195_still_parses(synth_save_2310):
    result = sp.parse_save(synth_save_2310)
    assert isinstance(result, dict)
```

(`synth_save_2310` is the conftest fixture from Task 1.)

- [ ] **Step 3: RED**, then implement: extract the existing decode body into `_decode_cc_v195`, add

```python
CC_DECODERS: dict[int, Callable[..., dict]] = {195: _decode_cc_v195}


def _resolve_decoder(v3: int):
    decoder = CC_DECODERS.get(v3)
    if decoder is None:
        supported = ", ".join(str(k) for k in sorted(CC_DECODERS))
        raise UnsupportedPatchError(
            f"This save's character-customization struct version (v3={v3}) is not supported "
            f"(supported: {supported}).",
            remediation=(
                "The game patch is newer than this npv-build release. "
                "Run `npv-build --probe-save <sav.dat>` and open an issue with the output."
            ),
            module_name="Save Parser",
        )
    return decoder
```

and dispatch in `parse_save`. Keep any pre-existing `SaveParserError` raising for structurally-broken 195 saves unchanged.

- [ ] **Step 4: GREEN** (`uv run pytest tests/core/test_decoder_registry.py tests/test_save_parser.py -q`), full gates, and re-probe-parse a real save: `uv run python -c "from pathlib import Path; from npv_build.save_parser import parse_save; d = parse_save(Path('<QuickSave-1 sav.dat path>')); print(sorted(d)[:8])"` — must print the same keys as before the refactor.

- [ ] **Step 5: Commit** — `git commit -m "refactor(save_parser): CC decoder registry keyed by v3 (spec PC-3)"`

---

### Task 3: Hard-fail patch detection (PC-1/PC-2)

**Files:**
- Modify: `npv_build/save_parser.py` (`detect_patch`)
- Modify: `npv_build/data/save_versions.json` (documented seed)
- Test: extend `tests/core/test_decoder_registry.py`

**Interfaces:**
- Consumes: `UnsupportedPatchError`.
- Produces: `detect_patch(version: tuple) -> str` now RAISES `UnsupportedPatchError` for unknown builds (no more 2.13 default + warning). `save_versions.json` stays `{"2310": "2.13"}` — new builds are added only with empirical confirmation (Task 7); do NOT guess build numbers from the internet.

- [ ] **Step 1: Failing tests** (append to test_decoder_registry.py):

```python
def test_detect_patch_known():
    assert sp.detect_patch((269, 2310, 195)) == "2.13"


def test_detect_patch_unknown_build_raises():
    with pytest.raises(UnsupportedPatchError) as ei:
        sp.detect_patch((269, 9999, 195))
    assert "9999" in str(ei.value)
    assert "2310" in str(ei.value)
    assert ei.value.remediation
```

- [ ] **Step 2: RED → implement.** Replace the fallback block in `detect_patch` (the `logger.warning` + `return "2.13"` path) with an `UnsupportedPatchError` naming the build, the supported builds/patches, and the same `--probe-save` remediation. Check callers: grep `detect_patch(` — every caller sits on the parse path and must let the error propagate (no new catches).

- [ ] **Step 3: GREEN + full gates + commit** — `git commit -m "feat(save_parser): hard-fail unknown game builds (spec PC-1)"`

---

### Task 4: WolvenKit 8.19 floor (PC-5)

**Files:**
- Modify: `npv_build/wk_cli.py` (version policy)
- Modify: `npv_build/installer.py` (install 8.19.x)
- Test: extend `tests/test_wk_cli.py`

**Interfaces:**
- Consumes: existing `check_version` (routes through `_run` since M1).
- Produces: `MIN_WK_VERSION = (8, 19, 0)` and `TESTED_WK_PREFIX = "8.19."` in wk_cli; `check_version()` parses the reported version, raises `WolvenKitError` with remediation if below MIN, logs a warning if above TESTED prefix, returns the version string. Installer pins `--version 8.19.0` (replacing 8.18.1).

- [ ] **Step 1: Failing tests** (mock `run_tool` as the existing wk_cli tests do):

```python
def test_check_version_below_minimum_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "npv_build.wk_cli.run_tool",
        lambda argv, **kw: ToolResult(argv=list(argv), returncode=0, stdout="8.18.1\n", stderr=""),
    )
    wk = WolvenKit(WolvenKitConfig(game_dir=tmp_path))
    with pytest.raises(WolvenKitError) as ei:
        wk.check_version()
    assert "8.18.1" in str(ei.value)
    assert "8.19" in str(ei.value)


def test_check_version_newer_warns_not_raises(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(
        "npv_build.wk_cli.run_tool",
        lambda argv, **kw: ToolResult(argv=list(argv), returncode=0, stdout="8.20.2\n", stderr=""),
    )
    wk = WolvenKit(WolvenKitConfig(game_dir=tmp_path))
    with caplog.at_level(logging.WARNING, logger="npv_build.wk_cli"):
        assert wk.check_version() == "8.20.2"
    assert any("8.20.2" in r.message for r in caplog.records)
```

Adapt the existing `test_check_version_mismatch_warns` test to the new policy (a below-minimum version now raises — that old test's expectation changes; note it in the report).

- [ ] **Step 2: RED → implement.** Version parse: `tuple(int(x) for x in re.match(r"(\d+)\.(\d+)\.(\d+)", text).groups())`; unparseable → warn and return (don't brick on exotic version strings). Update installer.py's WolvenKit pin to `8.19.0`.

- [ ] **Step 3: Upgrade THIS machine's WolvenKit and prove the pipeline still works on 8.19.** Check current: `WolvenKit.CLI --version`. If below 8.19: `uv run python -c "from pathlib import Path; from npv_build.config import get_cache_dir; from npv_build.installer import install_wolvenkit; install_wolvenkit(get_cache_dir()/'tools', lambda m, p: print(f'[{p}%] {m}'))"` — then confirm the resolved binary (`wk_cli`'s PATH-then-cache logic) reports ≥ 8.19.0. Then run a REAL rebuild as the 8.19 compatibility gate: `uv run npv-build <QuickSave-1 sav.dat path> "WK819 Gate" --output /tmp/claude-1000/npv_wk819_gate -v` (fresh output dir → full pipeline; expect success in ~10-15 min; this validates uncook/export/import/pack against 8.19). If the build breaks on 8.19-specific behavior, STOP and report BLOCKED with the failing stage log — do not paper over.

- [ ] **Step 4: GREEN + full gates + commit** — `git commit -m "feat(wk): enforce WolvenKit >= 8.19, install 8.19.0 (spec PC-5)"`

---

### Task 5: Bake verification (PC-6)

**Files:**
- Modify: `npv_build/head_bake.py`
- Modify: `npv_build/data/blender/bake_head.py`
- Test: `tests/core/test_bake_verification.py`

**Interfaces:**
- Consumes: `BakeVerificationError` (core.errors), `WolvenKit.serialize`.
- Produces: `verify_morphtarget(wk, morphtarget_path: Path, expected_min_targets: int = 1) -> int` in head_bake (returns target count), called after the WolvenKit import step of the bake flow; raises `BakeVerificationError` (with the file, found count, expected count, and remediation naming WolvenKit issue #849) when morphs were dropped.

- [ ] **Step 1: Read `head_bake.py`'s bake flow** (find where WolvenKit `import_mesh`/import produces the final `.morphtarget`) and read one REAL serialized morphtarget to learn the JSON shape: `uv run python -c "..."` calling `wk.serialize()` on the morphtarget produced by the M1 e2e build (`/tmp/claude-1000/npv_e2e_out/source/.../*_morphs.morphtarget` — if the e2e staging dir no longer holds one, extract from the packed archive or re-derive; document what you used). Identify the field that counts morph targets (WolvenKit's MorphTargetMesh JSON — likely `numTargets` or the `targets` array length under RootChunk). The verification reads THAT field.

- [ ] **Step 2: Failing tests** — mock `wk.serialize` to return crafted JSON:

```python
# tests/core/test_bake_verification.py
import json

import pytest

from npv_build.core.errors import BakeVerificationError
from npv_build.head_bake import verify_morphtarget


class FakeWk:
    def __init__(self, payload):
        self._payload = payload

    def serialize(self, cr2w_file, *, dest):
        out = dest / (cr2w_file.name + ".json")
        out.write_text(json.dumps(self._payload), encoding="utf-8")
        return out


def _payload(n_targets):
    # Shape must match what Step 1 found in real WolvenKit output - adjust key path,
    # keep these tests updated to the real structure and note it in your report.
    return {"Data": {"RootChunk": {"numTargets": n_targets}}}


def test_verify_passes_with_targets(tmp_path):
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    assert verify_morphtarget(FakeWk(_payload(35)), mt) == 35


def test_verify_raises_on_zero_targets(tmp_path):
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    with pytest.raises(BakeVerificationError) as ei:
        verify_morphtarget(FakeWk(_payload(0)), mt)
    assert "849" in ei.value.remediation
```

- [ ] **Step 3: RED → implement** `verify_morphtarget` (serialize into a TemporaryDirectory, json.load, walk to the count per Step 1's real shape, compare, raise/return) and call it at the end of the bake flow. Blender script: in `data/blender/bake_head.py`, before glTF export add Basis normal recompute + custom-split-normals strip on the exported object(s) (`mesh.calc_normals_split()` era APIs differ in 4.x — use `bpy.ops.mesh.customdata_custom_splitnormals_clear()` guarded by object mode/selection; keep edits minimal and comment why: prevents last-edited-shapekey normals leaking into the export).

- [ ] **Step 4: Real-data gate.** Re-run a fresh build (`--output /tmp/claude-1000/npv_bakegate`) OR, if Task 4's 8.19 gate build is recent, run only its bake stage against the same inputs by deleting `.npv_manifest.json`'s assemble entry... simplest honest gate: full fresh build. Verify the new verification passes on real output (and that its target count lands in the log).

- [ ] **Step 5: GREEN + gates + commit** — `git commit -m "feat(bake): verify morphtargets survive import; normals hygiene in Blender export (spec PC-6)"`

---

### Task 6: Mapping drift report (`gen_mapping`) (PC-4)

**Files:**
- Create: `npv_build/gen_mapping.py`
- Modify: `npv_build/cli.py` (add `--mapping-report` flag, early-exit like `--probe-save`)
- Test: `tests/core/test_gen_mapping.py`

**Interfaces:**
- Consumes: `part_resolver`'s index (`generate_index` / cached index structure — read part_resolver.py to bind to the real index shape), vendored `data/mappings/2.13.json`.
- Produces: `mapping_report(game_dir: Path, mapping_patch: str = "2.13", wk=None) -> dict` returning `{"missing_assets": [...], "unmapped_candidates": [...], "checked": int}` where `missing_assets` = mapping entries whose depot path is absent from the game index (stale after a game update) and `unmapped_candidates` = head-related index entries (.ent under the head/character paths the mapping covers) absent from the mapping (new CC options). CLI `npv-build --mapping-report` prints a summary. This is the semi-automation for authoring `2.3x.json`: it tells you exactly what to add/remove.

- [ ] **Step 1: Read `data/mappings/2.13.json` and part_resolver's index format.** Bind the report's set logic to the real key/path shapes (mapping values are depot path strings; index maps appearance/e nt paths). Document both shapes in your report.

- [ ] **Step 2: Failing tests** — pure-function tests with fake index + fake mapping dicts (no game needed):

```python
# tests/core/test_gen_mapping.py
from npv_build.gen_mapping import diff_mapping


def test_diff_finds_missing_and_unmapped():
    mapping_paths = {r"base\characters\head\a.ent", r"base\characters\head\gone.ent"}
    index_paths = {r"base\characters\head\a.ent", r"base\characters\head\new.ent"}
    missing, unmapped = diff_mapping(mapping_paths, index_paths)
    assert missing == {r"base\characters\head\gone.ent"}
    assert unmapped == {r"base\characters\head\new.ent"}
```

Plus one test that `mapping_report` composes extract→diff correctly with monkeypatched index/mapping loaders. `diff_mapping(mapping_paths: set[str], index_paths: set[str]) -> tuple[set[str], set[str]]` is the pure core; keep it dumb.

- [ ] **Step 3: RED → implement** (`diff_mapping` + loaders + `mapping_report` + `format_report`; CLI flag mirrors `--probe-save`). Path comparison must be backslash-literal (no normalization — depot convention).

- [ ] **Step 4: Real-data sanity**: `uv run npv-build --mapping-report` on this machine (2.13 game vs 2.13 mapping) — expect zero/near-zero missing_assets; record the number of unmapped_candidates as the baseline noise floor in your report.

- [ ] **Step 5: GREEN + gates + commit** — `git commit -m "feat: mapping drift report tool (spec PC-4)"`

---

### Task 7: 2.3x enablement runbook — GATED on user action

**Files (when unblocked):**
- Modify: `npv_build/data/save_versions.json`, possibly `npv_build/save_parser.py` (new decoder), `npv_build/data/mappings/2.3x.json`, `npv_build/data/donors/2.3x.json`, `npv_build/data/save_versions.json`
- Test: fixtures + decoder tests mirroring Task 2's pattern

**GATE:** requires the game updated to the current patch (Steam) and at least one NEW save created in-game afterward. This is a user action — the controller must confirm with the user before this task runs, and the task is NOT a merge blocker for M2 (all infrastructure above ships without it).

**Runbook (execute in order once gated):**

- [ ] **Step 1:** `uv run npv-build --probe-save <new save>` → record `(v1, v2, v3)`. 
- [ ] **Step 2:** Add `"<v2>": "2.3x"` (use the real patch string, e.g. `"2.31"`) to `save_versions.json`.
- [ ] **Step 3 — struct fork:**
  - If `v3 == 195`: register the alias (`CC_DECODERS` untouched), run `parse_save` on the new save; if it parses cleanly and the extracted `cc_settings` fields look sane (body_rig, morphs count), the decoder work is DONE — record this outcome loudly.
  - If `v3 != 195`: copy `_decode_cc_v195` to `_decode_cc_v<N>`, then diff empirically: hexdump the CC node bytes (`probe_save` gives the node; add a `--dump-cc <out.bin>` debug flag if needed), compare against a 2310 save's structure field-by-field (the 195 decoder's read sequence is the map), adjust reads until parse succeeds and the extracted settings match what the character actually looks like in-game (user confirms visually). Register in `CC_DECODERS`. Add a REAL 2.3x save fixture (a fresh save with a simple character; saves are user data, no CDPR assets) under `tests/fixtures/` plus a golden-file test for its extracted cc_settings.
- [ ] **Step 4 — mapping:** run `--mapping-report` against the UPDATED game install. Author `data/mappings/2.3x.json` starting from a copy of `2.13.json`: delete `missing_assets` entries, add mappings for `unmapped_candidates` that correspond to the patch-2.2 CC additions (cross-reference the community NPV resources named in IMPROVEMENT_REPORT.md §2.4). Verify donor entities (Judy/Thompson paths in `donors/2.13.json`) still exist in the updated archives (`wk.list_archive`); copy to `donors/2.3x.json` (adjust only if moved).
- [ ] **Step 5 — end-to-end:** full build from the new save via GUI backend; then in-game spawn check via AMM (user confirms appearance/animation).
- [ ] **Step 6:** Commit per sub-step with messages `feat(patch): ...`; the milestone's spec row (M2 exit) is only fully satisfied here.

---

### Task 8: Deferred M2 minors + milestone gate

**Files:**
- Modify: `npv_build/part_resolver.py` (ResolverError message detail), `npv_build/core/pipeline.py` (game_dir typing), tests as below.

- [ ] **Step 1 — wk-branch hard-fail test:** in `tests/core/test_part_resolver_fallback.py`, add a test driving `extract_recipe`'s `wk`-adapter branch with a fake `wk` whose method raises `WolvenKitError` (a `ToolError` subclass) and assert `ResolverError` propagates — mirrors the existing subprocess-branch test.
- [ ] **Step 2 — ResolverError detail plumbing:** where part_resolver wraps `ToolError` into `ResolverError`, append the tail: `ResolverError(f"...: {e.user_message}", details=e.details)` so frontends surface the tool output tail (verify `ResolverError.__init__` forwards kwargs to `NpvError`; adjust if it doesn't). Update the affected test asserts minimally.
- [ ] **Step 3 — platform tests:** (a) VDF fixture containing a Windows-style escaped path line (`"path"\t\t"C:\\\\Games\\\\SteamLibrary"`) asserting the unescape produces `C:\Games\SteamLibrary` (assert on the returned Path's string; the library-existence check needs monkeypatched `Path.is_dir` or restructure `steam_libraries` to take an `_exists=` test seam — prefer monkeypatch, no production change); (b) `steam_root_candidates` win32 branch via `monkeypatch.setattr(sys, "platform", "win32")` — confirm platform.py reads `sys.platform` at call time (it does — module-level import, call-time check) and assert the Program Files candidate logic runs without error and filters non-existent dirs.
- [ ] **Step 4 — BuildRequest.game_dir typing:** change to `game_dir: Path | None`, and add an explicit guard at the top of `PipelineService.build`: `if req.game_dir is None: raise NpvError("No game directory configured", remediation="Set --game-dir or configure it in the GUI settings.")`. Add a test.
- [ ] **Step 5 — milestone gate:** full suite + ruff check + **ruff format --check** green; fresh full build on this machine (may reuse Task 5's gate build if no code changed since); push branch, CI green on both OSes.
- [ ] **Step 6: Commit** — `git commit -m "test,fix: M2 deferred minors (wk-branch coverage, error details, platform tests, game_dir typing)"`

---

## Exit Criteria (spec M2, adjusted to ground truth)

- Unknown builds and unknown CC struct versions hard-fail with actionable errors (PC-1, PC-3 registry) — verified by tests and by probing a doctored save.
- `--probe-save` and `--mapping-report` tools exist and run against the real install.
- WolvenKit floor is 8.19 with the local install upgraded and a full real build passing on it (PC-5).
- Bake verification guards WK#849 with a real-build pass (PC-6).
- 2.13 saves still build end-to-end (regression gate).
- CI green (lint incl. format-check + both OS test jobs).
- **Task 7 (actual 2.3x decoding + tables) executes when the user updates the game and provides a new save** — until then M2 ships "2.3x-ready" infrastructure; this gate and its user dependency are called out to the user at milestone close.
