# Assemble-Stage Archive-Scan Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop re-listing every installed mod archive once per head-mesh layer during a build — one listing per archive per build, filtered in Python — cutting minutes off builds on mod-heavy installs.

**Architecture:** The `WolvenKit` adapter gains a per-instance archive-entry cache: `archive_entries(archive_path)` lists an archive once with a broad regex and callers filter the returned names locally. The existing `list_archive(path, pattern)` call sites in the mod-scan loops switch to it. The adapter instance already lives for exactly one build (`_make_wolvenkit` in `core/pipeline.py`), so instance-level caching gives correct per-build scoping for free.

**Tech Stack:** Python 3.11+, pytest.

**Context (measured 2026-07-19, ~30 installed mod archives):** the QA build log shows, per mod archive: one `archive -l --regex .*\.app$` scan (~6s) during resolve, then one `archive -l --regex ...h0_000_pwa_c__basehead\.mesh$` scan (~6s) AND one `...heb_000_pwa_c__basehead\.mesh$` scan (~6s) during assemble — i.e. every archive listed 3× ≈ 9 minutes of pure re-listing.

## Global Constraints

- No behavior change: the same archives must match the same patterns before/after (pure perf).
- Hard-fail policy unchanged: listing errors still raise `ToolError`.
- `uv run ruff check .` + `uv run pytest -q` green per task.

---

### Task 1: Verify call sites (read-only, 15 min)

**Files:** none modified.

- [ ] **Step 1:** Locate every per-archive listing loop:

```bash
grep -rn "list_archive\|archive.*-l.*--regex\|\.app\$" npv_build/wolvenkit.py npv_build/part_resolver.py npv_build/head_bake.py npv_build/wk_cli.py | grep -v test
```

Record for each hit: which pattern it lists (`.*\.app$` vs a specific mesh
regex), what it does with the result, and whether it iterates all mod archives.
Expected (from the build log): a recipe/hair scan in `part_resolver.py`
(pattern `.*\.app$`) and a head-texture-override scan (specific mesh regex per
layer) in `wolvenkit.py` or `head_bake.py`.

- [ ] **Step 2:** Note the exact `WolvenKit.list_archive` signature in
`npv_build/wk_cli.py` (parameter names, return type — lines of stdout vs parsed
list). Tasks 2–3 must match it exactly; update their code stubs if reality
differs before implementing.

---

### Task 2: `WolvenKit.archive_entries` with per-instance cache

**Files:**
- Modify: `npv_build/wk_cli.py`
- Test: `tests/test_wk_cli.py` (append)

**Interfaces:**
- Produces: `WolvenKit.archive_entries(archive_path: Path) -> list[str]` — all `.app` and `.mesh` depot paths in the archive, from one `archive -l --regex .*\.(app|mesh)$` run, cached in `self._entries_cache: dict[str, list[str]]` keyed by `str(archive_path)`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_wk_cli.py — mirror the file's existing _run-stubbing style
def test_archive_entries_lists_once_and_caches(monkeypatch, tmp_path):
    from npv_build.wk_cli import WolvenKit, WolvenKitConfig

    wk = WolvenKit(WolvenKitConfig(game_dir=tmp_path))
    calls = []

    def fake_list(path, pattern):
        calls.append((str(path), pattern))
        return ["base\\a\\x.app", "base\\b\\y.mesh"]

    monkeypatch.setattr(wk, "list_archive", fake_list)
    first = wk.archive_entries(tmp_path / "m.archive")
    second = wk.archive_entries(tmp_path / "m.archive")
    assert first == second == ["base\\a\\x.app", "base\\b\\y.mesh"]
    assert len(calls) == 1
    assert calls[0][1] == r".*\.(app|mesh)$"
    # different archive -> its own listing
    wk.archive_entries(tmp_path / "n.archive")
    assert len(calls) == 2
```

**Verify before use (from Task 1):** `list_archive`'s real parameter name for
the regex (`pattern` vs `regex`) and whether it returns parsed paths or raw
stdout lines — adjust the fake and the implementation to match.

- [ ] **Step 2: Run red**, then implement:

```python
    def archive_entries(self, archive_path: Path) -> list[str]:
        """All .app/.mesh depot paths in the archive; one listing per archive
        per adapter instance (== per build)."""
        key = str(archive_path)
        if key not in self._entries_cache:
            self._entries_cache[key] = self.list_archive(
                archive_path, r".*\.(app|mesh)$")
        return self._entries_cache[key]
```

with `self._entries_cache: dict[str, list[str]] = {}` in `__init__`.

- [ ] **Step 3: Run green, gate, commit**

```bash
uv run pytest tests/test_wk_cli.py -q && uv run ruff check . && uv run pytest -q
git add npv_build/wk_cli.py tests/test_wk_cli.py
git commit -m "feat(wk_cli): per-build archive entry cache"
```

---

### Task 3: Switch the mod-scan loops to the cache

**Files:**
- Modify: the call sites recorded in Task 1 (`npv_build/part_resolver.py`, `npv_build/wolvenkit.py` and/or `npv_build/head_bake.py`)
- Test: extend the nearest existing test of each loop (they stub the adapter — swap the stubs from `list_archive` to `archive_entries` and assert the *filtering* still selects the same archives)

- [ ] **Step 1:** For each loop, replace

```python
matches = wk.list_archive(archive, pattern=SPECIFIC_REGEX)
```

with

```python
rx = re.compile(SPECIFIC_REGEX)
matches = [e for e in wk.archive_entries(archive) if rx.search(e)]
```

keeping `SPECIFIC_REGEX` byte-for-byte identical (backslashes and all) so the
selection semantics cannot drift. Where the old call's regex was anchored with
`$`, `re.search` + the same `$` keeps the anchor.

- [ ] **Step 2:** Update the loops' unit tests to stub `archive_entries` and add
one regression assertion per loop: an entry that matches the specific regex is
kept, a non-matching `.app`/`.mesh` entry from the broad listing is filtered out.

- [ ] **Step 3:** Gate + commit

```bash
uv run ruff check . && uv run pytest -q
git add npv_build/ tests/
git commit -m "perf(assemble): one archive listing per mod archive per build"
```

---

### Task 4: Measure (manual gate)

- [ ] Run a real GUI build via the QA harness (memory note `gui-qa-harness`) on this machine and compare wall-clock of the resolve+assemble stages against the 2026-07-19 baseline (~102s resolve, multi-minute assemble scans). Expected: per-archive listings drop from 3× to 1×; record the numbers in the commit message or `docs/ROADMAP.md`'s perf line.

## Self-review notes

- No behavior change by construction: identical regexes, applied to a superset listing.
- Cache scope = adapter instance = one build (`_make_wolvenkit` per `PipelineService.build` call) — no cross-build staleness when the user installs new mods between builds.
