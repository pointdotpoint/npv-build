# Cyberpunk 2077 NPV Automation — Glossary

This document defines the canonical vocabulary of the project. Implementation
details live in code and ADRs, not here.

## Terms

### NPV (Non-Playable V)
A custom NPC in Cyberpunk 2077 that visually replicates a player's V character.
Spawned in-world via Appearance Menu Mod (AMM), not played by the user.

### sav.dat
The on-disk Cyberpunk 2077 save file. Contains many blocks; this project reads
only the **CC block** from it.

### CC block (Character Creation block)
The section of `sav.dat` written during the initial character-creator flow. It
holds the morph/option IDs the player picked at game start. **This is the sole
source of truth for v1.** Salon edits and later appearance changes are out of
scope; see [[future-live-appearance-extraction]].

### Save parser library
The third-party Python library used to read the CC block and the game-version
header from `sav.dat`. V1 uses an **existing CyberCAT-derived Python library**
(e.g. `fmwviormv/CyberpunkPythonHacks` or a maintained fork), pinned to one
exact version. Writing our own binary parser is the documented fallback if no
maintained library covers the supported patch, but is not the v1 plan.

### CC settings
The structured, human-readable representation of the CC block. Materialised as
`cc_settings.json`. One CC settings document describes one V.

**V1 scope** is deliberately narrow — only the following CC fields participate
in mod generation:
- Body rig selector (gender / body type → pwa or pma)
- Head: eyes, nose, mouth, jaw, ears (shape IDs and morph weights)
- Hair: style, colour
- Skin: tone

Everything else the CC block carries (cyberware, makeup, teeth, scars,
tattoos, eye colour, nails, eyebrows, facial hair, piercings, nipples,
genitals, etc.) is **read but ignored** in v1. The Save Parser still emits
those fields into `cc_settings.json` for diagnostic purposes, but the Mapping
Module drops them on the floor. Unknown CC option IDs that fall outside the
v1-scope set produce a single aggregated warning line, not an error.

### Mapping table
A hand-curated lookup that translates CC option IDs into game asset paths
(meshes, morphtargets, material instances, appearance names). Vendored in the
repo as JSON and **versioned per Cyberpunk 2077 patch** (e.g.
`mappings/2.13.json`). Updated manually when the game patches; not scraped at
runtime. Source material: Redmodding Wiki cheat sheets and NoraLee's NPV Part
Picker.

### Asset paths
The output of the Mapping Module. The concrete set of in-game resource paths
required to construct one NPV, materialised as `asset_paths.json`. Derived
from CC settings + Mapping table.

### Template (`.ent` / `.app`)
A pair of JSON-converted entity and appearance files that describe a generic
NPC skeleton (rig, base components, slot layout) which the NPV pipeline then
specialises. Templates are **uncooked on the user's machine**, on demand,
against the user's own legitimate game install, and **cached locally per
game patch**. They are **never vendored in this repository** — that is the
project's hard line against shipping CDPR-derived content.

### Game install path
The filesystem path to the user's Cyberpunk 2077 install root (the directory
containing `bin/`, `archive/`, etc.). Required at build time so the tool can
uncook Templates against the user's own base archive (see ADR-0003).

Resolution policy:
- **First run:** the user passes `--game-dir <path>` explicitly. The tool
  validates that the directory looks like a Cyberpunk install and persists
  the path in a user config file.
- **Subsequent runs:** the persisted path is reused. `--game-dir` on a
  subsequent run overrides and re-persists.
- **No auto-detection** of Steam/GOG/EGS/Proton install locations in v1.

### User config file
Per-user TOML file holding persisted settings (currently just the Game
install path). Locations:
- Windows: `%APPDATA%\npv\config.toml`
- Linux: `$XDG_CONFIG_HOME/npv/config.toml` (defaulting to
  `~/.config/npv/config.toml`)

Hand-editable. Not shipped — created on first successful `--game-dir`.

### Template cache
The on-disk cache holding uncooked templates between runs. Lives in the
**OS-conventional user cache directory**:
- Windows: `%LOCALAPPDATA%\npv\templates\<patch>\`
- Linux: `$XDG_CACHE_HOME/npv/templates/<patch>/` (defaulting to
  `~/.cache/npv/templates/<patch>/`)

The tool **never auto-evicts** entries; old patch caches persist until the
user clears them. CLI controls:
- `--clear-cache` wipes the cache before running.
- `--template-cache <dir>` overrides the default location.

### Donor NPC
The base-game NPC whose `.ent`/`.app` are uncooked to produce a Template. The
project uses **two donors** — one rigged for the female-V body, one for the
male-V body — both **named-but-simple** NPCs (full head rig, no quest hooks,
no scripted behaviours, no unique cyberware). The donor identities (resource
paths within the player's base archive) are **specified in the repo** (e.g.
`donors/2.13.json`); the resolved binary content stays on the user's machine
after uncooking.

### Body rig
The skeletal/mesh rig family an NPV is built on. V1 supports exactly two:
- **pwa** — *player woman average*, female-V head + body
- **pma** — *player man average*, male-V head + body

Any further body variation the game's CC may expose (athletic, heavy, etc.)
is collapsed onto the corresponding rig in v1. The CC block's gender/body
field selects between pwa and pma; nothing else changes the rig choice.

### NPV name
The user-facing label for an NPV, supplied at tool invocation. Appears in AMM
as the player sees it (e.g. "JaneV"). Never used directly as an internal
identifier.

### License posture
The project's own source code is **MIT-licensed**. Upstream tool licenses
(WolvenKit CLI, the chosen CyberCAT-derived save-parser library, AMM) are
documented in the README but not subsumed — none of those tools are
redistributed by this project.

**No CDPR-owned bytes ship in this repository or in any produced Mod
package.** The vendored Mapping tables and Templates contain only path
strings, structural JSON, and morph weights derived by the maintainer from
public modding documentation; they carry no extracted game assets.

### Test boundary
What is and isn't covered by automated tests in v1:

- **Unit tests** cover the pure-Python modules: Save Parser, Mapping, AMM Lua
  Generator. Standard pytest, fast, run on every change.
- **Integration tests** stop at "the modified `.app`/`.ent` JSON matches a
  committed golden file." They do not call WolvenKit `convert -d` or `pack`,
  and they do not produce a real `.archive` in CI.
- **Manual in-game validation** is a **release-gate** owned by the
  maintainer, not part of CI. Every released version is spawned in-game
  against the supported patch before tagging.

The opaque binary stages (WolvenKit pack, in-engine morph blending) are
deliberately outside the automated test surface — the cost of mocking them
exceeds the regressions they would catch.

### Verbosity
Default output is **quiet**: on success, one line naming the output
directory; on failure, the module-tagged error message (see Failure mode).
- `-v` adds per-module progress (Save Parser → Mapping → WolvenKit
  Automation → AMM Lua Generator → Packaging).
- `-vv` additionally streams full stdout/stderr from WolvenKit CLI and any
  other external tools.

No file logging in v1.

### Failure mode
The pipeline **hard-fails on the first error**. No recovery, no skipping of
unmapped options, no degraded-fidelity output. On failure:
- Partial outputs and intermediate JSONs are **left on disk** for inspection.
- The error message names the failing module (Save Parser, Mapping, WolvenKit
  Automation, AMM Lua Generator, WolvenKit Packaging) and the offending
  input.
- Exit code is non-zero.

Producing a "best-effort partial NPV" is explicitly out of scope — silent
fidelity loss is worse than a loud failure for this tool's audience.

### Supported platform
V1 supports **Windows and Linux** as build hosts. macOS is unsupported (no
real-world Cyberpunk install target).

The install-tree output layout is **host-aware**:
- On Windows, the output mirrors the native Cyberpunk install tree directly
  (`archive/pc/mod/...`, `bin/x64/plugins/...`).
- On Linux, the output is adjusted for **Proton's compatdata layout**, so
  the user copies into the Proton prefix's emulated Windows tree rather than
  a native Linux path. The on-disk paths the user sees still look
  Windows-shaped, just rooted inside the Proton prefix.

Both hosts are first-class: testing, bug intake, release validation.

### Invocation
The tool is **one command, one shot**: `npv-build <sav.dat> <npv-name>
--output <dir>`. No subcommands, no separately-runnable extraction or mapping
steps. Intermediate JSONs (`cc_settings.json`, `asset_paths.json`) may be
written to disk as run artefacts for debugging, but they are not first-class
producible outputs — the user cannot resume from one of them.

### Mod package
The final on-disk deliverable for one NPV. Laid out as a **partial mirror of
the Cyberpunk 2077 install tree**, so the user installs by copying the
contents of the output directory over their game install root. The package
contains:

- `archive/pc/mod/<mod-id>.archive` — the packed mod archive
- `bin/x64/plugins/cyber_engine_tweaks/mods/AppearanceMenuMod/Collabs/Custom Entities/<mod-id>.lua` — the AMM registration

No single-folder "dump both files, read the README" layout; the install-tree
mirror is the contract.

### AMM registration
The Lua entry, generated by the tool, that exposes the NPV inside Appearance
Menu Mod. V1 registers exactly one kind of entry: a **standalone spawnable
NPC** — the NPV appears in AMM's spawnable-NPCs list and can be placed
anywhere in the world by the player. Appearance-swap registration (applying
the NPV's look to an existing NPC) is **not** supported in v1.

### Mod ID
A short content-derived hash suffixed onto every internal identifier the mod
ships — entity record name, appearance name, `.archive` filename, AMM
registration key, `.ent` filename. Guarantees two NPVs built from different
inputs never collide when installed together; guarantees the same inputs
always produce the same mod.

**Hash inputs:** `NPV name + CC settings` only. The Mapping table version and
the resolved Asset paths are deliberately **excluded** so that the same V
keeps a stable Mod ID across game patches. Reinstalling after a patch upgrade
overwrites the previous build in place rather than creating a parallel NPV.

**Reproducibility:** the Mod ID is **identity-stable, not byte-stable**.
Given the same `(NPV name, CC settings)`, two builds — on different machines,
different days, or after a Mapping update — produce the same Mod ID and the
same in-game appearance, but the resulting `.archive` files are not
guaranteed to have identical bytes (file ordering, embedded timestamps, and
WolvenKit-internal non-determinism are not controlled in v1).

Format: `<slug(NPV name)>_<hash>`.

### WolvenKit CLI
An external, third-party command-line tool used to uncook game assets,
convert `.ent`/`.app` between binary and JSON, and pack the final `.archive`.
Pinned to one exact version per release of this tool, documented in the
README. The orchestrator verifies the installed version at startup and
refuses to run on mismatch.

### Morph weight
A scalar value applied to one of the game's head/face morphtargets at runtime.
The NPV's facial shape is expressed as a set of morph weights written into
the `.app`/`.ent` files; the **game engine** does the blending. The tool does
not pre-deform meshes and does not produce `.fbx`/`.glb` intermediates in v1.

### Game patch version
The Cyberpunk 2077 build the save was produced under, read from the `sav.dat`
header. Selects which Mapping table is loaded. A save whose patch has no
vendored mapping is a hard error, not a warning — the tool refuses to run
rather than silently produce a broken NPV.
