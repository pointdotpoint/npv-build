# npv-build

**Turn your Cyberpunk 2077 save into an AMM-spawnable NPC clone of V — in one command.**

![version](https://img.shields.io/badge/version-2.0.0-blue)
![python](https://img.shields.io/badge/python-%E2%89%A53.9-blue)
![assets](https://img.shields.io/badge/CDPR%20bytes%20in%20repo-none-green)

`npv-build` reads your save file, extracts V's character creation data (face
morphs, skin tone, eyes, makeup, hair, cyberware, and equipped clothing), bakes
the face geometry in Blender, and produces a **ready-to-install mod** that spawns
V as an NPC via [Appearance Menu Mod (AMM)](https://www.nexusmods.com/cyberpunk2077/mods/790).

> No game files are bundled with this tool. Everything is built from *your own*
> install at build time.

---

## TL;DR

**What you get:** a folder you copy into your game, then spawn your V as an NPC
from the AMM menu. Their face, skin, eyes, makeup, hair, and outfit match your
character.

**What you *don't* have to do:** no manual Blender sculpting, no clicking around
the WolvenKit GUI, no hand-editing `.app`/`.ent` files. The CLI does all of it.

**Jump to:** [Requirements](#requirements) · [Install](#install) ·
[Quick Start](#quick-start) · [CLI Reference](#cli-reference) ·
[Troubleshooting](#troubleshooting) · [Limitations](#limitations) ·
[For developers](#for-developers)

---

## Install from Release

If you'd rather not build from source, download a prebuilt binary:

### Windows
1. Download `npv-build-2.0.0-windows.zip` from [Releases](https://github.com/pointdotpoint/npv-build/releases).
2. Extract the `.zip`.
3. Run `npv-build.exe` (double-click for GUI, or use a terminal for CLI).
4. The first run will auto-download and install WolvenKit and Blender (checksum-verified) — **they are not bundled**.
5. **Note:** Windows binary is unsigned; you may see a SmartScreen warning — this is expected.

### Linux
1. Download `npv-build-2.0.0-x86_64.AppImage` from [Releases](https://github.com/pointdotpoint/npv-build/releases).
2. Make it executable: `chmod +x npv-build-2.0.0-x86_64.AppImage`
3. Run it (double-click for GUI, or use a terminal for CLI): `./npv-build-2.0.0-x86_64.AppImage`
4. The first run will auto-download and install WolvenKit and Blender (checksum-verified) — **they are not bundled**.

Both artifacts include the GUI and CLI in a single executable:
- **Double-click** or run with **no arguments** → launches the GUI.
- **Pass arguments** from a terminal → runs the CLI. Example: `./npv-build <sav.dat> "My V" --output ./my_v_mod --game-dir "..."`
- **`--gui` flag** → forces the GUI even if other arguments are present.

For verification, check the SHA-256 hash of your download against the line in `SHA256SUMS` in the release.

---

## How it works (30-second version)

```
your save  →  resolve assets  →  bake face (Blender)  →  author .ent/.app
   ↓                                                            ↓
parse CC   →  …                                          inject components
                                                                ↓
                                                  pack .archive + AMM spawn script
```

You point the tool at a save and a name; it hands you an installable mod. The
[deep dive](#how-it-works-deep-dive) explains each stage.

---

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| [WolvenKit CLI](https://github.com/WolvenKit/WolvenKit) | 8.18.x | Must be on `PATH`. A different version only **warns** — it won't stop the build, but isn't guaranteed to work. |
| [Blender](https://www.blender.org/) | 4.x | Used headless to bake face morphs. Native `blender` on `PATH`, **or** a Flatpak install (see note below). |
| Python | ≥ 3.9 | `tomli` / `tomli-w` are installed automatically. |
| .NET 8 SDK | 8.x | Needed to build `npv-inject` (the component injector). **Not shipped pre-built** — you build it once. |
| [AMM](https://www.nexusmods.com/cyberpunk2077/mods/790) | any | Required in-game to spawn the NPC. |

> **Flatpak Blender:** if you use the Flatpak (`org.blender.Blender`), grant it
> filesystem access once so it can read the staged mesh files:
> ```bash
> flatpak override --user --filesystem=host org.blender.Blender
> ```
> The tool auto-detects native `blender` first, then falls back to Flatpak.

<details>
<summary>Where to download these</summary>

- **WolvenKit** — [releases](https://github.com/WolvenKit/WolvenKit/releases) (grab the CLI).
- **Blender** — [blender.org/download](https://www.blender.org/download/) or your distro's Flatpak.
- **.NET 8 SDK** — [dotnet.microsoft.com](https://dotnet.microsoft.com/download/dotnet/8.0).
- **AMM** and **Cyber Engine Tweaks (CET)** — from [Nexus Mods](https://www.nexusmods.com/cyberpunk2077/mods/790).

</details>

---

## Install (from source / development)

To build `npv-build` from source, you'll need the development tools above, plus a clone of this repo:

```bash
cd npv_project
uv sync --extra gui

# Build the component injector (one-time)
dotnet build tools/npv-inject -c Release
```

After this, the `npv-build` command is available via `uv run`. The injector is
located automatically in this order: `PATH` → `tools/npv-inject/bin/Release/net8.0/` →
`tools/npv-inject/bin/Debug/net8.0/`.

Verify the install:

```bash
uv run npv-build --help
```

**For end users**, see [Install from Release](#install-from-release) above for prebuilt binaries.

---

## Using the bundled app

When you [package this as a frozen exe](packaging/) (Windows `.exe`, Linux AppImage, or macOS bundle), a **single executable serves both the GUI and CLI**:

- **Double-click** (or run with no args) → launches the **GUI** for interactive mode
- **From a terminal with arguments** → runs the **CLI**: `./npv-build /path/to/sav.dat "My V" --output ./my_v_mod --game-dir "..."`
- **`--gui` flag** → forces the GUI even if other arguments look CLI-ish: `./npv-build --gui`

Example (Linux/macOS):
```bash
# Launch GUI
./npv-build

# Run CLI
./npv-build /path/to/sav.dat "My V" --output ./my_v_mod --game-dir "/path/to/Cyberpunk 2077"

# Force GUI (if you need to)
./npv-build --gui
```

Windows (`.exe`):
```bash
npv-build.exe
npv-build.exe C:\path\to\sav.dat "My V" --output my_v_mod --game-dir "C:\path\to\Cyberpunk 2077"
npv-build.exe --gui
```

---

## Quick Start

### 1. Build the mod

The smallest useful command:

```bash
uv run npv-build /path/to/sav.dat "My V" \
  --output ./my_v_mod \
  --game-dir "/path/to/Cyberpunk 2077"
```

A fuller example with overrides:

```bash
uv run npv-build /path/to/sav.dat "My V" \
  --output ./my_v_mod \
  --game-dir "/path/to/Cyberpunk 2077" \
  --hair zara \
  --skin 01_ca_pale \
  --garment 'base\characters\garment\player_equipment\torso\t1_097_pwa_tank__corset_doll_prostitute.ent' \
  -v
```

> `--game-dir` is **remembered after the first run** (saved to your config), so
> you can omit it on later builds.

### Find your save

| OS | Location |
|----|----------|
| **Windows** | `%USERPROFILE%\Saved Games\CD Projekt Red\Cyberpunk 2077\` |
| **Linux/Proton** | `~/.steam/steam/steamapps/compatdata/1091500/pfx/drive_c/users/steamuser/Saved Games/CD Projekt Red/Cyberpunk 2077/` |

Each save folder contains a `sav.dat` — that's the file you point the tool at.

### Capturing V's *actual* outfit (optional)

The save file records your face, hair, and makeup — but **not** the clothes V is
wearing. To dress the NPC in V's real outfit, use the bundled **CET dumper**:

1. Install the CET script (`npv_build/data/cet_dumper/init.lua`) as a CET mod.
2. Load your game and trigger the dump — it writes a JSON file with V's equipped
   garments.
3. Pass that file with `--cc-json`:

```bash
npv-build /path/to/sav.dat "My V" --output ./my_v_mod \
  --game-dir "/path/to/Cyberpunk 2077" \
  --cc-json /path/to/cc_dump.json
```

With **save + `--cc-json`**, face/hair come from the save (most reliable there)
and the equipped clothing is overlaid from the dump. Without it, a sensible
**fallback outfit** is used. `--garment` overrides layer on top either way.

> **No save?** `--cc-json` can be used on its own — the `<sav.dat>` argument is
> optional when a dump is provided.

### 2. Install and spawn

The build writes everything to `./my_v_mod/`. Copy the two install folders into
your game directory:

```bash
cp -r my_v_mod/archive/ "/path/to/Cyberpunk 2077/"
cp -r my_v_mod/bin/     "/path/to/Cyberpunk 2077/"
```

Launch the game, then open the **CET overlay → AMM → Custom Entities →** select
your NPV name **→ Spawn**.

---

## CLI Reference

```
npv-build [<sav.dat>] <NPV name> --output <dir> [options]
```

`<sav.dat>` is optional **only** when `--cc-json` is supplied.

| Argument / Flag | Required | Description |
|-----------------|----------|-------------|
| `<sav.dat>` | conditional | Path to your save file. Optional if `--cc-json` or `--dump-head-glb` is given. |
| `<NPV name>` | yes | Display name for the NPC in AMM. Optional if `--dump-head-glb` is given. |
| `--output <dir>` | yes | Where to write the mod project. Optional if `--dump-head-glb` is given. |
| `--game-dir <path>` | first run | Cyberpunk 2077 install directory. **Saved after first use**; required again only if it changes. |
| `--cc-json <path>` | — | Use a CET CC dump (face and/or equipped clothing) instead of, or alongside, the save. |
| `--hair <id\|none>` | — | Hair override: vanilla number (`1` → `hh_001`), modded name (`zara`), or `none`. |
| `--skin <tone>` | — | Skin-tone `meshAppearance` override (e.g. `01_ca_pale`). |
| `--garment <depot_path>` | — | Add a garment `.ent` depot path. **Repeatable** — pass once per item. |
| `--head-glb <path>` | — | Option A: Use your own Blender-edited head GLB instead of baking face morphs. We import it to `.mesh` and restore materials/skinning. |
| `--head-mesh <path>` | — | Option B: Use your own finished cooked `.mesh` as V's head. Skips Blender and WolvenKit import. |
| `--heb-mesh <path>` | — | Optional skin-detail (`heb_`) layer to accompany `--head-glb` / `--head-mesh`. Dropped if omitted. |
| `--no-restore-head-materials` | — | Option B only: keep the materials baked into your `.mesh` instead of restoring stock head materials. |
| `--dump-head-glb <path>` | — | Export stock head GLB for editing (then feed back via `--head-glb`) and exit. Requires `--game-dir`. |
| `--template-cache <dir>` | — | Override the template cache location (default: `~/.cache/npv/templates`). |
| `--clear-cache` | — | Wipe the template cache before running. |
| `-v` / `-vv` | — | Verbose / very-verbose output. |

### Resumable builds & logging

Long builds can be interrupted and resumed. After a failure or cancellation, re-run the same
command with `--resume` to skip stages that already completed:

```bash
uv run npv-build /path/to/sav.dat "My V" \
  --output ./my_v_mod \
  --game-dir "/path/to/Cyberpunk 2077" \
  --resume
```

Every build writes one combined, timestamped log to `<output>/logs/build-<timestamp>.log`.
Pass `--log-file <path>` to write the log to a different location instead.

### Custom Head Mesh ("Bring Your Own") Workflow

If you want to edit V's head geometry in Blender yourself or use a custom-sculpted head, `npv-build` supports bypass options:

#### Option A: Blender GLB Workflow (Recommended)
1. Export the base head:
   ```bash
   uv run npv-build --dump-head-glb ./my_base_head.glb --game-dir "/path/to/Cyberpunk 2077"
   ```
2. Edit `./my_base_head.glb` in Blender (sculpt, modify, etc.). Do not change vertex count / topology if you want perfect skinning, though warnings about count mismatches will only warn rather than fail.
3. Build your NPV using the edited GLB:
   ```bash
   uv run npv-build /path/to/sav.dat "My V" --output ./my_v_mod --head-glb ./my_base_head.glb
   ```
This automatically restores game materials/skinning onto your model using WolvenKit's `import --keep`.

#### Option B: Verbatim Mesh Workflow (Power Users)
If you already have a finished `.mesh` file (with custom skinning, materials, etc.):
```bash
uv run npv-build /path/to/sav.dat "My V" --output ./my_v_mod --head-mesh ./custom_head.mesh
```
- By default, materials are restored from the stock head. Pass `--no-restore-head-materials` to keep the custom materials already baked into your `.mesh`.
- **Note:** Skips WolvenKit import entirely. The rig and skinning must already be fully intact and compatible.

#### Skin-Detail (`heb_`) Layer
By default, custom head overrides drop the `heb_` skin-detail component to prevent overlap/glitches. If you have a custom detail layer mesh, pass it with `--heb-mesh <path.mesh>`.

### Config & cache

- **Config:** `~/.config/npv/config.toml` (Linux) · `%APPDATA%\npv\` (Windows).
  Only `game_dir` is persisted.
- **Cache:** `~/.cache/npv/` — uncooked templates plus a per-game-patch asset
  index. Safe to delete; it's rebuilt on demand (or use `--clear-cache`).

### What the build produces

```
my_v_mod/
  archive/pc/mod/<mod_id>.archive          # Packed mod — install this
  bin/.../Custom Entities/<mod_id>.lua      # AMM spawn script — install this
  source/archive/                           # Intermediate cooked files (debug)
  npv_components.json                       # Component specs (debug)
  cc_settings.json                          # Parsed CC data (debug)
  asset_paths.json                          # Resolved asset paths (debug)
```

> **`<mod_id>`** is a deterministic hash of `(NPV name, CC settings)`. Rebuilding
> the same V produces the same ID, so reinstalls overwrite in place rather than
> piling up duplicates.

---

## Advanced / manual workflow

The CLI is the recommended path and handles everything above. If you'd rather
sculpt morphs by hand in Blender, resolve assets manually, or understand the
underlying file formats, see the in-depth walkthrough:

➡️ **[NPV_Creation_Guide.md](docs/NPV_Creation_Guide.md)** — manual save parsing,
asset mapping, Blender morph baking, and fixing common visual glitches.

One detail worth knowing either way: the NPC is built on a **rig-appropriate
donor entity** — `pwa` for the female body rig, `pma` for male — which carries
the full animation infrastructure. The CLI picks the right one for you.

---

## How It Works (deep dive)

<details>
<summary>The full pipeline, stage by stage</summary>

1. **Save parsing** — Reads the CC node from `sav.dat`: face morphs
   (jaw/nose/mouth/eyes/ears), skin tone, eyes, teeth, makeup, hair, cyberware.

2. **Recipe extraction** — For each CC selection, uncooks the matching feature
   `.app` from the game archives and extracts the exact `meshAppearance`
   material variant.

3. **Face morph baking** — Exports the head morphtarget to GLB, applies V's
   shapekeys in Blender (headless), reimports the baked geometry via
   `WolvenKit import --keep`.

4. **Morphtarget authoring** — Copies the stock morphtarget to a mod-scoped
   depot path, redirects its `baseMesh` to the baked head mesh.

5. **Donor entity** — Copies a **rig-appropriate donor's** cooked `.ent`
   (`pwa` for female, `pma` for male) — ~101 components including animation
   controllers, AI, rig, and locomotion. Only the appearance list is swapped to
   point at our `.app`, preserving the full animation infrastructure.

6. **Component spec generation & injection** — Uncooks each stock part-ent,
   extracts mesh component details (type, name, depot paths, material variants),
   applies recipe overrides, serializes to `npv_components.json`, then injects
   the components into the cooked `.app` via `npv-inject`. Finally packs the
   `.archive` and generates the AMM spawn script.

</details>

---

## Troubleshooting

### Build won't start / fails early

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Either <sav.dat> or --cc-json must be provided` | No input given | Pass a save path, or a `--cc-json` dump, or both. |
| `WolvenKit.CLI not found in PATH` | WolvenKit isn't installed/on `PATH` | Install WolvenKit CLI 8.18.x and add it to `PATH`. |
| `Save file not found` / version mismatch | Wrong path, or an unsupported game patch | Check the path; confirm your save matches a supported patch. |
| `game_dir required` mid-build | Head baking needs the game install | Pass `--game-dir` (it's needed once mesh export/import runs). |
| Blender errors when reading staged files | Flatpak sandbox blocks access | Run `flatpak override --user --filesystem=host org.blender.Blender`. |
| `npv-inject not found` | Injector not built | Run `dotnet build tools/npv-inject -c Release`. |

### NPC looks wrong in-game

| Symptom | Cause | Fix |
|---------|-------|-----|
| NPC T-poses | `AppearanceParts` tag in `.app` | Don't add `AppearanceParts` to visualTags. The generated `.app` is correct as-is. |
| Head/parts floating | Missing skeleton bindings | Both `parentTransform.bindName` and `skinning.bindName` must be `root` on every component. |
| Blurry/dark face | Wrong component type | Head must be `entMorphTargetSkinnedMeshComponent` with `morphResource`, not a plain `entSkinnedMeshComponent`. |
| Wrong skin tone | Incorrect `meshAppearance` | Confirm `meshAppearance` matches `npv_components.json` exactly. |
| NPC invisible | Components not added | Open the `.app` in WolvenKit and verify the components array is populated. |
| Bald NPC | Hair components missing | Add all hair entries from `npv_components.json` (usually 3-4 mesh + 1 shadow). |
| Wrong face shape | Morph bake issue | Verify the morphtarget `DepotPath` points to `<mod_id>_morphs.morphtarget`. |

---

## Modded dependencies

If your V uses modded hair, body replacers, or custom garments, those mods must
**remain installed**. `npv-build` references their assets by depot path — it does
not copy or redistribute them. The CLI warns about external dependencies during
the build.

---

## Limitations

- **Clothing** — V's worn outfit is captured via the bundled **CET dumper +
  `--cc-json`** (the save alone contains no clothing). Without a dump, a fallback
  outfit is used. `--garment` overrides are always available.
- **Static hair** — Modded hair renders without dangle physics.
- **No facial expressions** — Face morphs are baked into static geometry. The
  shape is correct but won't animate.
- **Male rig less tested** — The `pma` (male) rig works but has had less testing
  than `pwa` (female).

---

## For developers

- **Architecture overview** — [CLAUDE.md](CLAUDE.md) (module pipeline & design decisions).
- **Glossary / terminology** — [CONTEXT.md](CONTEXT.md).
- **Decision records** — [docs/adr/](docs/adr/).
- **Internal specs** — `docs/legacy/SPEC.md`, `docs/legacy/SPEC-app-v2.md`, `docs/legacy/SPEC-clothing.md`,
  `docs/legacy/SPEC-inject.md` (design references; may lag the code).

Entry point is `npv_build/cli.py` (`main`). Run the test suite with:

```bash
uv run pytest
```

Lint the codebase:

```bash
uv run ruff check .
```
