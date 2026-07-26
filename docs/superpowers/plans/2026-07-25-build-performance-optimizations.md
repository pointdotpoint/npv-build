# NPV Build Performance Optimizations Implementation Plan

> **Goal:** Reduce an unchanged GUI rebuild to under 2 seconds, a warm build
> with changed appearance/clothing to under 2 minutes, and a first cold build
> to under 4 minutes without changing the generated NPV, weakening validation,
> or reusing stale game assets.

**Measured baseline (2026-07-25):**

- Real PWA from-scratch build with one catalog garment:
  - `parse_save` through `resolve_assets`: 25.6 seconds
  - `assemble`: 476.7 seconds
  - Core build total: 502.2 seconds (8 minutes 22 seconds)
  - A just-built clothing catalog adds roughly one minute before the first NPV
    build, explaining the observed end-to-end time above ten minutes.
- Identical build with the existing `resume=True` path: 0.264 seconds.
- The real build contained ten direct part resources plus recipe resources.
  Assembly launched roughly thirty single-resource WolvenKit uncooks, most
  taking 12–14 seconds each.
- `BuildRequest.template_cache` is currently passed through the application but
  is not used for extracted resources.

**Primary diagnosis:** Process startup and repeated archive scans dominate the
build. The implementation repeatedly launches WolvenKit for one `.ent`,
`.mesh`, or `.morphtarget` at a time. The duplicate-looking log lines are
duplicate handlers, not duplicate subprocesses. Clothing-catalog generation is
separate from `start_build` and is already cached.

**Architecture:** Harden checkpoint invalidation first, then make normal GUI
builds incremental by default. Add a content-addressed local uncook cache under
`~/.cache/npv/templates/`, keyed by the source archive and WolvenKit binary
fingerprints. On a cold miss, prefetch known entities in one WolvenKit process,
discover their morphtarget dependencies, and fetch those in a second process.
Keep garment meshes as depot references rather than attempting to parse them as
entity components. Finally, cache thumbnail-derived Photo Mode inputs and
collapse safe conversion/helper calls.

**Non-negotiable invariants:**

- A cache hit must generate the same `npv_components.json`, archive contents,
  Photo Mode resources, and zip layout as a cold build.
- A changed game archive, WolvenKit binary, pipeline/cache schema, rig, CC
  choice, garment, thumbnail, or NPV name must invalidate every affected entry
  or stage.
- Cache files stay local; no CDPR assets are added to the repository or release
  bundles.
- Corrupt, partial, or missing cache entries are misses, never build failures.
- Cancellation and timeouts must still terminate the active external process.
- `Clear cache` must remove all reusable extraction and Photo Mode inputs.
- Performance gates supplement correctness tests; they never replace them.

---

## Task 1: Add a reproducible build benchmark and call-count feedback loop

**Files:**

- Create: `scripts/benchmark_build.py`
- Create: `tests/core/test_build_metrics.py`
- Modify: `npv_build/core/pipeline.py`

### Step 1: Define the benchmark profiles

`scripts/benchmark_build.py` accepts:

```text
uv run python scripts/benchmark_build.py \
  --game-dir "<game>" \
  --preset pwa \
  --thumbnail "<image>" \
  --output-dir "<output>" \
  --profile cold|warm-changed|identical
```

Profiles:

- `cold`: remove only the benchmark output and benchmark-owned template cache.
- `warm-changed`: preserve the template cache, change one garment override, and
  use the same output directory.
- `identical`: preserve output/cache and make the exact same request.

The script must never clear the user's whole `~/.cache/npv`. Its default cache
is a dedicated temporary or explicitly supplied benchmark directory.

### Step 2: Persist stage measurements

Add optional timing information to `BuildResult` without changing existing
event semantics:

```python
@dataclass
class BuildResult:
    ...
    stage_durations: dict[str, float] = field(default_factory=dict)
```

Use `time.monotonic()` around each pipeline stage. Include `package`, even
though it remains non-checkpointed. Do not use wall-clock timestamps for
durations.

### Step 3: Add deterministic unit tests

Tests must prove:

- Every started stage receives one non-negative duration.
- Skipped stages are present and close to zero or explicitly marked skipped.
- The benchmark profile changes only its owned output/cache directories.
- Timing fields remain JSON-serializable.

Elapsed-time assertions do not belong in normal CI. Later unit tests will use
external-call counts as the deterministic regression signal.

### Step 4: Record the baseline

Run the real benchmark once before optimization and save the JSON output under:

```text
docs/research/2026-07-25-build-performance-baseline.json
```

The file may contain timings, counts, versions, and paths, but no game data.

### Gate

```bash
uv run pytest tests/core/test_build_metrics.py tests/core/test_pipeline.py -q
uv run ruff check scripts/benchmark_build.py npv_build/core/pipeline.py
```

---

## Task 2: Make checkpoint reuse safe across application and tool changes

Automatic resume must not be enabled until this task is complete.

**Files:**

- Modify: `npv_build/core/pipeline.py`
- Modify: `tests/core/test_pipeline.py`

### Step 1: Version the manifest

Change `.npv_manifest.json` from an unversioned stage dictionary to:

```json
{
  "format_version": 2,
  "producer_version": "2.0.0",
  "stage_schemas": {
    "parse_save": 1,
    "resolve_assets": 1,
    "assemble": 1,
    "emit_amm_lua": 1,
    "emit_photomode": 1
  },
  "stages": {}
}
```

Requirements:

- Old/unversioned manifests load as an empty manifest.
- Unknown future versions load as empty.
- Corrupt manifests remain clean cache misses.
- `producer_version` comes from one import-safe version helper. In a source
  checkout where the package reports `dev`, stage schema numbers remain the
  authoritative invalidation mechanism.

### Step 2: Include schema/tool identity in hashes

Each stage input hash includes its stage schema. The assemble hash additionally
includes:

- WolvenKit executable fingerprint: resolved path, size, and `mtime_ns`.
- `npv-inject` executable fingerprint.
- Photo Mode helper fingerprint.

Do not execute `--version` on every build. File metadata is sufficient for
local invalidation and avoids another process startup.

### Step 3: Strengthen artifact validation

An assemble checkpoint is reusable only when all expected outputs exist and are
non-empty:

- `archive/pc/mod/<mod_id>.archive`
- `archive/pc/mod/<mod_id>.archive.xl`
- Photo Mode tweak output
- AMM Lua output where applicable

Do not accept “any file exists in the archive directory.”

Store the expected artifact paths in the assemble checkpoint output so they can
be validated directly.

### Step 4: Test every invalidation boundary

Add tests proving:

- Identical request and valid artifacts skip all checkpointed stages.
- Changed garment reruns resolve/assemble but not raw parsing.
- Changed thumbnail reruns assemble/Photo Mode work.
- Changed NPV name reruns every mod-ID-dependent stage.
- Changed tool fingerprint reruns assemble.
- Incremented assemble schema reruns assemble.
- Missing or zero-byte expected archive reruns assemble.
- Version-1/corrupt manifest performs a clean build.

### Gate

```bash
uv run pytest tests/core/test_pipeline.py -q
uv run ruff check npv_build/core/pipeline.py tests/core/test_pipeline.py
```

---

## Task 3: Enable safe incremental builds by default in the GUI

**Files:**

- Modify: `npv_build/webui/js/build.js`
- Modify: `npv_build/webui_api.py`
- Modify: `tests/test_webui_api.py`
- Modify: `tests/webui_smoke/test_webui_smoke.py`

### Step 1: Make normal GUI starts incremental

The frontend sends `resume: true` for both:

- A normal “Start build”
- “Retry from failed stage”

The name `resume` continues to mean “reuse valid unchanged stages,” not “trust
all old output.” Task 2’s hashes and artifact checks decide what actually skips.

Keep CLI behavior explicit for this milestone: `npv-build --resume` remains an
opt-in flag so scripting compatibility does not change unexpectedly.

### Step 2: Surface cache reuse

Existing `stage_skipped` events already reach the build screen. Change the
status copy from generic “skipped” to “Unchanged — reused previous output” so
users understand why a rebuild finished quickly.

### Step 3: Test request and invalidation behavior

Add unit/smoke assertions:

- A fresh GUI build request includes `resume: true`.
- A directory without a manifest still runs every stage.
- An identical rebuild skips every checkpointed stage and still repackages a
  valid zip.
- Changing a garment in the picker invalidates assembly.

### Measured gate

The existing real reference build, repeated identically, must complete in under
2 seconds. Record the actual number in the benchmark JSON.

---

## Task 4: Implement a persistent, content-addressed WolvenKit JSON cache

**Files:**

- Create: `npv_build/core/artifact_cache.py`
- Create: `tests/core/test_artifact_cache.py`
- Modify: `npv_build/wk_cli.py`
- Modify: `npv_build/core/pipeline.py`
- Modify: `tests/test_wk_cli.py`

### Step 1: Define cache identity

Add a small immutable cache-key model:

```python
@dataclass(frozen=True)
class ArchiveFingerprint:
    resolved_path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class ToolFingerprint:
    resolved_path: str
    size: int
    mtime_ns: int
```

An uncook entry key contains:

- Cache schema (`uncook-json-v1`)
- Archive fingerprint
- WolvenKit fingerprint
- Exact depot basename or exact requested resource identifier

Suggested layout:

```text
~/.cache/npv/templates/
  uncook-json-v1/
    <archive-tool-hash>/
      <resource-hash>.json
```

### Step 2: Implement safe reads/writes

`ArtifactCache` exposes:

```python
def load_json(namespace: str, key: object) -> dict | None
def save_json(namespace: str, key: object, value: dict) -> None
def path_for(namespace: str, key: object, suffix: str) -> Path
```

Rules:

- Canonical JSON + SHA-256 keys.
- Atomic unique temporary file followed by `Path.replace`.
- Corrupt/non-dict JSON is deleted or ignored as a miss.
- Cache path derivation cannot escape its root.
- Never cache a failed or missing extraction.

### Step 3: Wire the cache into WolvenKit

Extend `WolvenKitConfig`:

```python
artifact_cache: ArtifactCache | None = None
```

`PipelineService._make_wolvenkit` creates it from
`BuildRequest.template_cache`. `WolvenKit.uncook_json` becomes:

1. Compute archive/tool/resource key.
2. Return cached parsed JSON on a hit.
3. Run the current extraction on a miss.
4. Validate and atomically cache the parsed object.

### Step 4: Test cache behavior at the adapter seam

Tests use a fake `_run` counter and prove:

- First call invokes WolvenKit and caches.
- Second identical call invokes no process.
- Changed archive size/mtime misses.
- Changed WolvenKit binary size/mtime misses.
- Corrupt cache misses and repairs itself.
- Failed extraction creates no cache entry.
- `artifact_cache=None` preserves current behavior.

### Step 5: Confirm Settings cache clearing

`templates` is already a clearable cache directory. Add a web bridge test that
clearing `templates` removes uncook entries and causes the next build to miss.

### Gate

```bash
uv run pytest tests/core/test_artifact_cache.py tests/test_wk_cli.py \
  tests/test_webui_api.py -q
uv run ruff check npv_build/core/artifact_cache.py npv_build/wk_cli.py
```

---

## Task 5: Batch cold extraction in two WolvenKit processes

**Files:**

- Modify: `npv_build/wk_cli.py`
- Modify: `npv_build/wolvenkit.py`
- Modify: `tests/test_wk_cli.py`
- Modify: `tests/test_build_project.py`
- Create: `tests/test_build_prefetch.py`

### Step 1: Add `uncook_json_many`

Interface:

```python
def uncook_json_many(
    self,
    filenames: list[str],
    *,
    archive: Path | None = None,
) -> dict[str, dict]:
    """Return parsed JSON by requested filename.

    Cache hits do not enter the WolvenKit regex. All misses are extracted in
    one process. A missing requested filename is reported distinctly.
    """
```

Implementation:

- Deduplicate and sort names.
- Read cache hits first.
- Build one anchored regex from `re.escape`d missing basenames.
- Use one temporary directory and one `uncook` process.
- Match results by exact basename, not substring.
- Cache each successful result independently.
- Keep command-line length bounded. If the escaped regex exceeds a documented
  limit (for example 24 KiB), split into deterministic chunks.

### Step 2: Prefetch entities, then morphtargets

Refactor `build_project`:

1. Collect every vanilla `.ent` needed by:
   - Stock head
   - `part_entities`
   - Recipe-part entity resources
   - Vanilla hair
2. Call `uncook_json_many` once for entity misses.
3. Parse those entities locally and collect every referenced
   `morphResource` basename.
4. Call `uncook_json_many` once for morphtarget misses.
5. Pass the prepared JSON maps into `_extract_part_components` and
   `_load_vanilla_hair_components`.

Keep single-resource helpers as fallbacks for resources discovered outside the
prefetch set, especially modded archive content.

### Step 3: Stop uncooking garment meshes as component entities

Only `.ent` depot paths enter component-entity extraction. A
catalog-selected `.mesh`:

- Remains in `BuildRequest.garments`
- Is already archive-validated by the clothing catalog
- Is emitted as an `entGarmentSkinnedMeshComponent` by `resolve_clothing`
- Is not passed to `_extract_part_components`

This removes one known 12–14 second no-op from the reference build.

### Step 4: Add deterministic process-count tests

With 10 entity fixtures and 8 morphtarget dependencies:

- Cold cache: at most two WolvenKit uncook calls.
- Warm cache: zero WolvenKit uncook calls.
- One changed/missing entity: one batched entity call plus only required
  morphtarget work.
- A garment `.mesh` causes zero component-extraction calls.

### Step 5: Add output-equivalence coverage

Run the same fixture through the old single-resource extraction reference and
the new prefetched path. Normalize ordering where it is intentionally
deterministic, then assert exact equality for:

- Component type/name
- Mesh and morphtarget paths
- Appearance
- Bind target and chunk mask
- Source labels

For the real reference build, compare the new `npv_components.json` against the
saved baseline. No component may disappear or change except explicitly
documented ordering.

### Measured gate

On an empty template cache, the entity/morphtarget extraction portion must use
no more than two WolvenKit processes and finish in under 60 seconds on the
reference machine.

---

## Task 6: Cache reusable Photo Mode icon inputs and collapse conversion calls

**Files:**

- Modify: `npv_build/photomode.py`
- Modify: `npv_build/wk_cli.py`
- Modify: `npv_build/wolvenkit.py`
- Modify: `tools/npv-photomode/Program.cs`
- Modify: `tests/test_photomode.py`
- Modify: `tests/test_photomode_packaging.py`
- Modify: `tests/test_build_project.py`

### Step 1: Cache thumbnail-derived files at the safe boundary

Only the normalized preview/DDS is reusable across NPVs. XBM and atlas metadata
contain the mod-specific depot path and must not be reused blindly.

Cache key:

- `photomode-icon-v1`
- Thumbnail SHA-256
- `ICON_SIZE`
- Crop centering
- Pillow version

Layout:

```text
~/.cache/npv/templates/photomode-icon-v1/<key>/
  preview.png
  icon.dds
```

On a hit, copy the cached files into the current source tree. On corruption,
regenerate. Pass `BuildRequest.template_cache` down through `_run_assemble`,
`build_project`, and `author_photomode_assets`.

### Step 2: Spike multi-file WolvenKit conversion

Before changing production code, verify whether WolvenKit 8.19 can serialize a
directory containing both the NPV `.app` and `.ent`.

Record the result in the baseline research note.

- If supported: add `WolvenKit.serialize_many`, serialize both in one process,
  patch both JSON files, and deserialize the directory in one process.
- If unsupported: keep two serialize calls but still deserialize both patched
  JSON files in one directory/process.

The output binaries must replace the two copied Photo Mode binaries exactly as
today.

### Step 3: Collapse helper startup

Add one helper command:

```text
npv-photomode author-metadata \
  --dds ... --xbm ... --inkatlas ... --xbm-depot ... \
  --localization ... --key ... --value ...
```

It performs the current `build-icon` and `build-localization` work in one .NET
process. Preserve the old subcommands for compatibility and tests.

### Step 4: Test mod-specific cache safety

Tests prove:

- Same thumbnail SHA reuses PNG/DDS normalization.
- Changed thumbnail misses.
- Changed crop/schema misses.
- Two mod IDs using the same thumbnail receive different correct XBM depot
  paths and localization keys.
- Cached files are never directly packed under another mod's path.
- Missing/corrupt cached DDS regenerates.
- Photo Mode entity/app still contain the correct rig, component, graph,
  animsets, and mod-specific app reference.

### Measured gate

Photo Mode authoring after normal NPV injection must:

- Use no more than three external processes on a cold cache.
- Use no more than two external processes on a warm icon cache.
- Take under 35 seconds on the reference machine.

---

## Task 7: Remove duplicate logging and expose useful cache telemetry

This is not the main speedup, but it makes future measurements trustworthy.

**Files:**

- Modify: `npv_build/core/logging_setup.py`
- Modify: `npv_build/gui_backend.py`
- Modify: `tests/test_logging_setup.py`

### Step 1: Make handler installation idempotent

Repeated calls to `configure_logging` must not attach duplicate console or
callback handlers. Tag NPV-owned handlers and replace/reuse them explicitly.

### Step 2: Add concise cache telemetry

At verbose level, report one summary per build:

```text
[Cache] uncook JSON: 24 hits, 2 misses
[WolvenKit] batched uncook: 2 processes, 26 resources
[Resume] reused 5/5 checkpointed stages
```

Do not log one line per cache hit at normal verbosity.

### Gate

```bash
uv run pytest tests/test_logging_setup.py tests/test_gui_backend.py -q
```

---

## Task 8: Full correctness and real performance gate

### Step 1: Run all automated checks

```bash
node --check npv_build/webui/js/build.js
uv run ruff check .
uv run pytest -q
git diff --check
```

### Step 2: Run three real benchmark profiles

Use the same PWA preset, thumbnail, garment, game install, and WolvenKit binary
as the baseline.

Required gates:

| Profile | Required result |
| --- | ---: |
| Identical incremental rebuild | ≤2 seconds |
| Warm cache, changed garment | ≤2 minutes |
| Empty cache, cold build | ≤4 minutes |
| Entity/morphtarget uncook calls, cold | ≤2 |
| Entity/morphtarget uncook calls, warm | 0 |

If elapsed gates vary due to machine load, repeat three times and use the
median. Process-count gates remain mandatory.

### Step 3: Prove artifact equivalence

For baseline and optimized builds with identical inputs:

- `npv_components.json` is exactly equal after removing no fields.
- Zip member names are exactly equal.
- Both zips pass `unzip -t`.
- Generated archive, `.archive.xl`, AMM Lua, and Photo Mode tweak exist and are
  non-empty.
- The selected garment remains in `npv_components.json`.
- The female reference build still reports `genitals_none`.
- Photo Mode thumbnail resources and localization are present.

Binary archive hashes are not required to match if WolvenKit embeds
nondeterministic metadata, but unpacked logical contents must match.

### Step 4: Record final results

Create:

```text
docs/research/2026-07-XX-build-performance-results.md
```

Include:

- Before/after stage timings
- External process counts
- Cold/warm/identical cache state
- Tool/game versions
- Any deviations from the targets and their cause

Do not claim a target is met from a mocked test; only the real benchmark is
authoritative.

---

## Recommended implementation order

1. Benchmark harness
2. Manifest/invalidation hardening
3. Automatic GUI incremental builds
4. Persistent uncook cache
5. Two-phase batch uncook and garment no-op removal
6. Photo Mode cache/process consolidation
7. Logging cleanup
8. Full real benchmark and artifact-equivalence audit

The first three tasks deliver the immediate 0.26-second identical rebuild path
safely. Tasks 4 and 5 provide the largest improvement for changed and first-time
builds. Task 6 trims the remaining Photo Mode tail.
