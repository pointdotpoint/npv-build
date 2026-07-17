# NPV Automation — v1 Specification

**Version:** 1.0
**Date:** 2026-05-22
**Status:** Draft, post-grill
**Source documents:** `CONTEXT.md`, `docs/adr/0001`, `docs/adr/0002`,
`docs/adr/0003`. Where this spec and those documents disagree, those documents
win — fix this spec.

## 1. Purpose

`npv-build` is a Windows + Linux/Proton command-line tool that turns a
Cyberpunk 2077 save file into an installable Appearance Menu Mod (AMM)
package: the user's V appears in-game as a standalone spawnable NPC.

## 2. Scope

### 2.1 In scope (v1)

- Read the CC (Character Creation) block from one `sav.dat`.
- Replicate the **head, hair, and skin tone** of the V described by that CC
  block onto an NPC.
- Produce a Mod package (`.archive` + AMM `.lua`) laid out as a partial mirror
  of the Cyberpunk install tree.
- Register the NPV as a **standalone spawnable NPC** in AMM.
- Support exactly two body rigs: `pwa` (player woman average) and `pma`
  (player man average).
- Run on Windows native and on Linux for Proton-managed installs.

### 2.2 Out of scope (v1, deferred)

- Cyberware, makeup, teeth, scars, tattoos, eye colour, nails, eyebrows,
  facial hair, piercings, nipples, genitals.
- Salon edits or any post-CC appearance state (live in-game extraction).
- Custom modded assets / clothing.
- AMM **appearance-swap** registration (applying the NPV's look to an
  existing NPC).
- A GUI.
- macOS as a build host.
- Body-rig variants beyond `pwa` and `pma` (athletic, heavy, etc.).
- Byte-stable reproducible builds (identity-stable only — see §6.2).
- CI-side end-to-end packing / in-engine validation.
- Auto-detection of Steam/GOG/EGS/Proton install paths.

## 3. Invocation

One command, one shot. No subcommands.

```
npv-build <sav.dat> "<NPV name>" --output <dir> [--game-dir <path>]
                                                [--template-cache <dir>]
                                                [--clear-cache]
                                                [-v | -vv]
```

- `<sav.dat>` — path to the source save file.
- `<NPV name>` — user-facing label (shown in AMM). Used to derive the Mod ID
  (§6.1) and to slug internal filenames.
- `--output <dir>` — root of the produced Mod package install tree.
- `--game-dir <path>` — first run only; persisted to the User config file
  thereafter. On later runs, overrides and re-persists.
- `--template-cache <dir>` — override the OS-conventional Template cache
  location.
- `--clear-cache` — wipe the Template cache before running.
- `-v` / `-vv` — Verbosity (§9).

Intermediate JSONs (`cc_settings.json`, `asset_paths.json`) may be written to
the output directory for diagnostic purposes. They are **not** separately
producible — there is no resume-from-intermediate flow in v1.

## 4. Architecture

```
sav.dat ──► Save Parser ──► cc_settings.json
                            │
                            ▼
                          Mapping ────────────► asset_paths.json
                            │                          │
                            ▼                          ▼
                       (CC scope filter)         WolvenKit Automation
                                                       │
                                                       ▼
                                              (uncook donor → Template cache)
                                                       │
                                                       ▼
                                              Config Editor (in-process)
                                                       │
                                                       ▼
                                              convert -d  +  pack
                                                       │
                                                       ▼
                                              AMM Lua Generator
                                                       │
                                                       ▼
                                                 Mod package
```

No Blender module (per ADR-0002). Mapping feeds WolvenKit Automation
directly; morph weights ride as numeric values in `asset_paths.json` and are
written into the `.app`/`.ent` JSON for the engine to blend at runtime.

## 5. Modules

### 5.1 Orchestrator

- Entry point for the CLI.
- Loads the User config file; resolves `--game-dir`.
- Reads the WolvenKit CLI version at startup and aborts on mismatch.
- Runs Save Parser → Mapping → WolvenKit Automation → AMM Lua Generator →
  Packaging in sequence.
- Tags every error with the failing module name and the offending input
  (§10).

### 5.2 Save Parser

- Depends on the **Save parser library** — a pinned, third-party
  CyberCAT-derived Python library (e.g. `fmwviormv/CyberpunkPythonHacks` or
  a maintained fork). Version is pinned in the project's lockfile.
- Reads two things from `sav.dat`:
  - The game patch version, from the save header.
  - The CC block.
- Emits `cc_settings.json`. All CC fields the library exposes are written to
  the JSON for diagnostic value; downstream uses only the v1 scope (§2.1).
- Hard-fails if the patch version cannot be read.

### 5.3 Mapping

- Loads the Mapping table matching the save's patch version
  (`mappings/<patch>.json`, vendored in-repo).
- Hard-fails with `MappingNotFoundError` if no matching table is vendored
  ("save is patch 2.14; no mapping vendored").
- Translates the v1-scope subset of `cc_settings.json` (body rig, eyes,
  nose, mouth, jaw, ears, hair style, hair colour, skin tone) into
  `asset_paths.json` — a structure containing:
  - Asset paths (meshes, morphtargets, material instances, textures) the
    NPV references.
  - **Morph weights** as numeric values, ready to write into the `.app`/`.ent`
    (ADR-0002).
  - The chosen body rig (`pwa` | `pma`).
- Aggregates unknown CC option IDs into a single warning line, never an
  error.

### 5.4 WolvenKit Automation

- Resolves the WolvenKit CLI path; aborts on missing or version-mismatched
  binary.
- **Template resolution** (ADR-0003):
  - Looks up the donor specification for the save's patch
    (`donors/<patch>.json`, vendored in-repo). The donor spec lists the
    base-game resource paths of two donor NPCs, one per body rig.
  - Checks the Template cache (§5.4.1) for already-uncooked templates of
    the resolved body rig.
  - On miss, invokes WolvenKit CLI `uncook` + `convert -s` against the
    user's game install, writes the resulting JSON into the Template cache,
    then proceeds.
- **Config Editor** (in-process, not a separate module):
  - Loads the cached Template JSON for the resolved body rig.
  - Writes asset paths and morph weights from `asset_paths.json` into the
    `.app` (appearance definition, morph targets and weights, components)
    and the `.ent` (root entity, appearance reference, internal IDs).
  - Substitutes every internal identifier with the Mod-ID-scoped form
    (§6.1): entity record name, appearance name, archive name, AMM key,
    `.ent` filename. No identifier escapes scoping.
- Runs WolvenKit CLI `convert -d` to turn the modified JSON back into
  binary `.ent` / `.app`.
- Runs WolvenKit CLI `pack` to produce `<mod-id>.archive`.

#### 5.4.1 Template cache

Filesystem layout:

```
<cache-root>/templates/<patch>/
    npv_pwa.ent.json
    npv_pwa.app.json
    npv_pma.ent.json
    npv_pma.app.json
```

`<cache-root>` defaults to:
- Windows: `%LOCALAPPDATA%\npv\`
- Linux: `$XDG_CACHE_HOME/npv/` (or `~/.cache/npv/`)

Override via `--template-cache <dir>`. Wipe via `--clear-cache`. Never
auto-evicted.

### 5.5 AMM Lua Generator

- Renders a single `.lua` from a string template.
- Inputs: the user-supplied NPV name, the Mod ID, and the relative archive
  path the NPV's root `.ent` resolves to.
- Registers the NPV as a **standalone spawnable NPC** in AMM only. No
  appearance-swap registration in v1.

### 5.6 Packaging

- Lays the produced files into a **Mod package** rooted at `--output`:

  ```
  <output>/
    archive/pc/mod/<mod-id>.archive
    bin/x64/plugins/cyber_engine_tweaks/mods/AppearanceMenuMod/Collabs/Custom Entities/<mod-id>.lua
  ```

- On Linux/Proton build hosts the **on-disk tree is identical** (the layout
  mirrors the game's Windows-shaped install tree even when the player runs
  under Proton); the user copies into the Proton prefix's emulated Windows
  drive root rather than a native Linux path. The tool does not relocate
  files into the Proton prefix itself.

## 6. Identity and reproducibility

### 6.1 Mod ID

Format: `<slug(NPV name)>_<hash>` where `slug` is a deterministic lowercase
ASCII slugifier and `hash` is a short content-derived hex digest.

Hash inputs: **the canonical JSON encoding of `(NPV name, CC settings)` only**.
Mapping table version and resolved asset paths are deliberately excluded so
that the same V keeps a stable Mod ID across game patches and across Mapping
updates.

The Mod ID is suffixed onto every internal identifier the package ships:
entity record name, appearance name, `.archive` filename, AMM registration
key, `.ent` filename.

### 6.2 Reproducibility

Identity-stable, **not** byte-stable. Given the same `(NPV name, CC
settings)`, two builds produce the same Mod ID and the same in-game
appearance, but `sha256(.archive)` may differ between runs (file ordering,
embedded timestamps, and WolvenKit-internal non-determinism are not
controlled in v1).

## 7. Configuration and state

### 7.1 User config file

Per-user TOML, hand-editable, created on first successful `--game-dir`.

```
# Windows
%APPDATA%\npv\config.toml
# Linux
$XDG_CONFIG_HOME/npv/config.toml  # default ~/.config/npv/config.toml
```

Contents (v1):

```toml
game_dir = "C:/Program Files (x86)/Steam/steamapps/common/Cyberpunk 2077"
```

### 7.2 Template cache

See §5.4.1.

### 7.3 Vendored in-repo

- `mappings/<patch>.json` — Mapping tables, one per supported Cyberpunk
  patch. Hand-curated from Redmodding Wiki cheat sheets and NoraLee's NPV
  Part Picker (ADR-0001).
- `donors/<patch>.json` — Donor NPC resource paths per patch (ADR-0003).
  Contains paths only; no extracted game content.

## 8. External tools and dependencies

- **WolvenKit CLI** — exact version pinned in the README; the Orchestrator
  verifies `wolvenkit.cli --version` at startup and aborts on mismatch.
  Not bundled.
- **Python 3.x**, version range declared in `pyproject.toml`.
- **Save parser library** — third-party CyberCAT-derived Python package,
  pinned in the lockfile.

No CDPR-owned bytes ship in this repository or in any produced Mod package
(see License, §11).

## 9. Verbosity

- Default — quiet. On success, one line: the absolute path of the output
  directory. On failure, the module-tagged error message (§10).
- `-v` — per-module progress (start + end per module).
- `-vv` — additionally streams full stdout/stderr from WolvenKit CLI and any
  other external tools.

No file logging in v1.

## 10. Failure mode

Hard-fail on first error. No best-effort partial mode. No silent skipping of
unknown CC options.

On failure:
- Partial outputs and intermediate JSONs are **left on disk** for inspection.
- The error message names the failing module — one of: Save Parser, Mapping,
  WolvenKit Automation, AMM Lua Generator, Packaging — and the offending
  input.
- Exit code is non-zero.

Known structured errors:
- `MappingNotFoundError` — no Mapping table vendored for the save's patch.
- `WolvenKitVersionMismatchError` — installed WolvenKit CLI is not the
  pinned version.
- `GameDirNotConfiguredError` — first run with no `--game-dir`.
- `GameDirInvalidError` — passed `--game-dir` is not a Cyberpunk install.
- `UncookFailedError` — WolvenKit `uncook` against the user's game install
  failed; carries the relevant CLI stderr.

## 11. License posture

- The project's own source code is **MIT-licensed**.
- Upstream tool licenses (WolvenKit CLI, the Save parser library, AMM) are
  documented in the README but not subsumed; none of those tools are
  redistributed.
- **No CDPR-owned bytes ship in this repository or in any produced Mod
  package.** Vendored Mapping tables and the donor specification contain
  only path strings, structural JSON, and morph weights derived by the
  maintainer from public modding documentation.

## 12. Testing

- **Unit tests** cover the pure-Python modules: Save Parser, Mapping, AMM Lua
  Generator. Pytest, fast, run on every change.
- **Integration tests** stop at *"the modified `.app`/`.ent` JSON matches a
  committed golden file."* They do not call `convert -d` or `pack`, and do
  not produce a real `.archive` in CI.
- **Manual in-game validation** is a **release gate**, owned by the
  maintainer, not part of CI. Every released version is spawned in-game
  against its supported patch before tagging.

The opaque binary stages (WolvenKit `pack`, in-engine morph blending) are
deliberately outside the automated test surface.

## 13. Data structures

### 13.1 `cc_settings.json` (v1-scope view)

```json
{
  "patch": "2.13",
  "body_rig": "pwa",
  "head": {
    "eyes":  { "shape_id": "02", "morph_weights": { "...": 0.0 } },
    "nose":  { "shape_id": "05", "morph_weights": { "...": 0.0 } },
    "mouth": { "shape_id": "03", "morph_weights": { "...": 0.0 } },
    "jaw":   { "shape_id": "01", "morph_weights": { "...": 0.0 } },
    "ears":  { "shape_id": "04", "morph_weights": { "...": 0.0 } }
  },
  "hair": { "style_id": "07", "colour_id": "red" },
  "skin": { "tone_id":  "light" }
}
```

Fields outside the v1 scope (cyberware, makeup, tattoos, etc.) may appear in
the file as the Save parser library exposes them, but are not consumed
downstream.

### 13.2 `asset_paths.json`

```json
{
  "patch": "2.13",
  "body_rig": "pwa",
  "head_mesh":          "base\\characters\\head\\player_base_heads\\player_female_average\\h0_000_pwa_c__basehead.mesh",
  "head_morphtargets":  ["base\\characters\\...\\eyes_02.morphtarget", "..."],
  "morph_weights":      { "eyes_02": 1.0, "nose_05": 1.0, "...": 0.0 },
  "hair_mesh":          "base\\characters\\hair\\hair_07.mesh",
  "skin_material_instance": "base\\characters\\skin\\skin_light_01.mi",
  "donor": {
    "ent_path": "base\\characters\\entities\\....ent",
    "app_path": "base\\characters\\appearances\\....app"
  }
}
```

## 14. Future enhancements (deferred from §2.2)

- Live appearance extraction via CET Lua scripting (covers salon edits).
- Expansion of CC scope to cyberware, makeup, body details, tattoos.
- Generated Mapping tables, produced by walking uncooked base-game factory
  files instead of hand curation.
- Byte-stable reproducible builds.
- A GUI.
- AMM appearance-swap registration.
- Bundled WolvenKit CLI (pending license clearance).
