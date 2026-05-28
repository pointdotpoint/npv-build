# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

`npv-build` is a CLI tool that reads a Cyberpunk 2077 save file, extracts the player's character creation (CC) data, and produces a ready-to-install mod that spawns V as an NPC via Appearance Menu Mod (AMM). The pipeline: parse save → resolve CC options to game assets → bake face morphs in Blender → author .ent/.app files → inject mesh components → pack .archive.

## Commands

```bash
# Install (editable)
pip install -e .

# Run tests
pytest

# Run a single test
pytest tests/test_save_parser.py::test_parse_save_binary

# Run the CLI
npv-build <sav.dat> "My V" --output ./my_v_mod --game-dir "/path/to/Cyberpunk 2077" -v

# Build the .NET component injector
dotnet build tools/npv-inject -c Release
```

## Architecture

The pipeline is a single-shot linear flow orchestrated by `orchestrator.py`. No subcommands, no resumability.

### Module pipeline (in execution order)

1. **`cli.py`** — Argument parsing, config load/save, invokes `run_orchestrator()`
2. **`config.py`** — User config (`~/.config/npv/config.toml`) and cache dir (`~/.cache/npv/`) management. Uses `tomli`/`tomllib` for reading, `tomli_w` for writing.
3. **`wk_cli.py`** — WolvenKit CLI adapter. All WolvenKit subprocess calls go through this module. `WolvenKitConfig` (frozen dataclass: game_dir, cli_binary, verbosity) and `WolvenKit` class with typed methods: `uncook_json()` (hero — returns parsed dict), `list_archive()`, `uncook_many()`, `serialize()`, `deserialize()`, `extract()`, `unbundle()`, `export()`, `import_mesh(allow_exit_codes)`, `pack()`, `check_version()`. Single `_run()` internally.
4. **`save_format.py`** — Low-level sav.dat container parser. Ported from PixelRick/CyberpunkSaveEditor. Handles CSAV header, LZ4-compressed chunks (XLZ4), NODE descriptors. Produces decompressed node data blob.
5. **`save_parser.py`** — Reads the `CharacetrCustomization_Appearances` node (yes, that typo is in the game). Decodes CC struct (Groups → Slots → Selections + Links). Extracts head/eyes/teeth/hair/skin/face morphs into `cc_settings` dict.
6. **`mapping.py`** — Resolves CC settings to concrete game asset depot paths (part .ent files). Uses a vendored mapping table (`data/mappings/2.13.json`) plus a runtime index built by `part_resolver`. Handles vanilla hair, modded hair, garment overrides. Accepts optional `wk` adapter.
7. **`part_resolver.py`** — Indexes `basegame_4_appearance.archive` via WolvenKit CLI adapter to build a lookup of all head-related .ent/.app files and their appearance names. Cached at `~/.cache/npv/index/<patch>.json`. Also extracts "recipes" and hair components from mod archives. Accepts optional `wk` adapter (falls back to direct subprocess if None).
8. **`config_editor.py`** — Authors the uncooked .app template (empty appearance with no components) and builds the .ent by patching a donor NPC entity (Judy for pwa, Thompson for pma). Only replaces appearances list and defaultAppearance; all donor infrastructure (animation rig, AI, locomotion) passes through.
9. **`head_bake.py`** — Bakes V's face morphs into a head mesh and creates a mod-scoped morphtarget. Owns its own staging directory. Takes a `WolvenKit` adapter. Public interface: `bake_head()`, `find_stock_head_part()`, `swap_head_part()`.
10. **`blender_module.py`** — Blender headless integration: extract morphtarget → WolvenKit export to .glb → Blender applies shapekeys → WolvenKit import --keep rebuilds .mesh. Uses WolvenKit adapter when provided, falls back to direct subprocess.
11. **`clothing.py`** — Resolves NPV clothing: loads fallback outfit from `data/fallback_outfit.json`, applies user `--garment` overrides by slot prefix. Pure function: `resolve_clothing(body_rig, overrides) -> list[dict]`.
12. **`wolvenkit.py`** — Assembles the full mod: extracts part components from stock .ent files, applies recipe material overrides, calls head_bake and clothing modules, calls `npv-inject` (.NET tool) to inject components into cooked .app, packs final .archive. Takes a `WolvenKit` adapter instance.
13. **`project_writer.py`** — Serializes component specs to `npv_components.json` for `npv-inject`.

### Key design decisions

- **No `AppearanceParts` visualTag** — Using it causes T-pose. All mesh components are inlined directly in the .app's components array instead of using partsValues.
- **Components bind to `root`** — Every mesh component needs `parentTransform.bindName = root` and `skinning.bindName = root`. Missing either causes floating parts.
- **Donor NPC entity** — The .ent is a real NPC's cooked entity (Judy/Thompson) with only the appearance list swapped. This preserves the full animation rig (~101 components).
- **No CDPR bytes in repo** — All game assets are uncooked from the user's own install at build time. Mapping tables contain only path strings and option IDs.
- **Hard-fail policy** — Pipeline stops on first error. No partial/degraded output.
- **Mod ID** — Deterministic hash of `(npv_name, cc_settings)`. Stable across game patches so reinstalls overwrite in place.

### External tools (called via subprocess)

- `WolvenKit.CLI` (8.18.x) — uncook, convert, export, import, pack
- `npv-inject` (.NET 8.0, in `tools/npv-inject/`) — injects component array into cooked .app binary
- `blender` (4.x, headless) — face morph baking via `data/blender/bake_head.py`

### Data files (`npv_build/data/`)

- `mappings/2.13.json` — CC option → asset path lookup, per game patch
- `donors/2.13.json` — Donor NPC config per body rig (uncook regex, .app path)
- `save_versions.json` — Game build number → patch version
- `fallback_outfit.json` — Default clothing per body rig
- `blender/bake_head.py` — Blender script for shapekey baking
- `cet_dumper/init.lua` — CET script for dumping CC data (alternative to save parsing)

### Save format internals

The sav.dat binary format uses length-prefixed strings (packed int64 length, negative = Latin-1, positive = UTF-16-LE), LZ4 block compression, and a node tree. The CC struct version is tracked by `v3` in the header tuple `(v1, v2, v3)` — the parser currently targets `v3=195`. Depot paths use Windows backslashes (`base\characters\...`) even on Linux; this is the game's convention and must be preserved in all authored files.
