# npv-build

Turn your Cyberpunk 2077 save into an AMM-spawnable NPC clone of V.

`npv-build` reads your save file, extracts V's character creation data (face
morphs, skin tone, eyes, makeup, hair, cyberware), bakes the face geometry,
and produces a **ready-to-install mod** — no manual steps required.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| [WolvenKit CLI](https://github.com/WolvenKit/WolvenKit) | 8.18.x | Must be on `PATH` |
| [Blender](https://www.blender.org/) | 4.x+ | For face morph baking (headless) |
| Python | 3.9+ | Runtime |
| .NET 8.0 SDK | 8.x | For building `npv-inject` (or use pre-built binary) |
| [AMM](https://www.nexusmods.com/cyberpunk2077/mods/790) | Any | Required in-game |

## Installation

```bash
cd npv_project
python -m venv venv
source venv/bin/activate    # Linux/macOS
# venv\Scripts\activate     # Windows
pip install -e .

# Build the component injector
dotnet build tools/npv-inject -c Release
```

## Quick Start

```bash
npv-build /path/to/sav.dat "My V" \
  --output ./my_v_mod \
  --game-dir "/path/to/Cyberpunk 2077" \
  --hair zara \
  --garment 'base\characters\garment\player_equipment\torso\t1_097_pwa_tank__corset_doll_prostitute.ent' \
  -v
```

This produces a ready-to-install mod at `./my_v_mod/`. Copy the `archive/`
and `bin/` folders into your game directory and spawn via AMM.

### Save file locations

- **Windows:** `%USERPROFILE%\Saved Games\CD Projekt Red\Cyberpunk 2077\`
- **Linux/Proton:** `~/.steam/steam/steamapps/compatdata/1091500/pfx/drive_c/users/steamuser/Saved Games/CD Projekt Red/Cyberpunk 2077/`

## CLI Reference

```
npv-build <sav.dat> <NPV name> --output <dir> [options]
```

| Flag | Description |
|------|-------------|
| `<sav.dat>` | Path to your Cyberpunk 2077 save file |
| `<NPV name>` | Display name for the NPC in AMM |
| `--output <dir>` | Where to write the WolvenKit project |
| `--game-dir <path>` | Cyberpunk 2077 install directory (saved after first use) |
| `--hair <id>` | Hair override: modded name (`zara`), vanilla number (`1`), or `none` |
| `--garment <path>` | Garment .ent depot path (repeatable for multiple items) |
| `--cc-json <path>` | Use a CET CC dump instead of parsing the save |
| `-v` / `-vv` | Verbose / very verbose output |

## What the CLI Produces

```
my_v_mod/
  archive/pc/mod/<mod_id>.archive       # Packed mod archive (ready to install)
  bin/.../Custom Entities/<mod_id>.lua   # AMM custom entity script
  source/archive/                        # Intermediate cooked files (for debugging)
  npv_components.json                    # Component specs (for debugging)
  cc_settings.json                       # Parsed CC data (for debugging)
  asset_paths.json                       # Resolved asset paths (for debugging)
```

The CLI automates the entire NPV creation process:
- Parses your save and extracts all CC data
- Resolves the exact material variants (skin tone, eye colour, makeup)
- Bakes V's face shape into the head mesh via Blender
- Creates a mod-scoped morphtarget
- Copies and configures the donor NPC entity (animation rig)
- Injects all mesh components into the `.app` cooked binary (`npv-inject`)
- Packs the final `.archive`
- Generates the AMM spawn script

## Install

Copy the `archive/` and `bin/` folders from the output into your game
directory:

```bash
cp -r my_v_mod/archive/ "/path/to/Cyberpunk 2077/"
cp -r my_v_mod/bin/ "/path/to/Cyberpunk 2077/"
```

Launch the game. Open the CET overlay > **AMM** > **Custom Entities** > select
your NPV name > **Spawn**.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| NPC T-poses | `AppearanceParts` tag in .app | Do NOT add `AppearanceParts` to visualTags. The template .app is correct as-is. |
| Head/parts floating | Missing skeleton bindings | Set both `parentTransform.bindName` and `skinning.bindName` to `root` on every component |
| Blurry/dark face | Wrong component type | Head must be `entMorphTargetSkinnedMeshComponent` with `morphResource`, not plain `entSkinnedMeshComponent` |
| Wrong skin tone | Incorrect meshAppearance | Double-check `meshAppearance` matches `npv_components.json` exactly |
| NPC invisible | Components not added | Open .app in WolvenKit GUI and verify the components array is populated |
| Bald NPC | Hair components missing | Add all hair entries from `npv_components.json` (usually 3-4 mesh + 1 shadow) |
| Wrong face shape | Morph bake issue | Verify the morphtarget `DepotPath` points to `<mod_id>_morphs.morphtarget` |

## How It Works

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

5. **Donor entity** — Copies Judy's cooked `.ent` (101 components including
   animation controllers, AI, rig, locomotion). Only the appearance list is
   swapped to point at our `.app`.

6. **Component spec generation** — Uncooks each stock part-ent, extracts mesh
   component details (type, name, depot paths, material variants), applies
   recipe overrides, and serializes to `npv_components.json`.

## Modded Dependencies

If your V uses modded hair, body replacers, or custom garments, those mods
must remain installed. `npv-build` references their assets by depot path — it
does not redistribute them. The CLI warns about external dependencies during
the build.

## Current Limitations

- **Clothing from save** — Not yet automated. Use `--garment` flags with depot
  paths.
- **Hair auto-resolve** — Use `--hair` flag. Automatic resolution from the
  save's hair name is planned.
- **Static hair** — Modded hair renders without dangle physics.
- **No facial expressions** — Face morphs are baked into static geometry. Shape
  is correct but won't animate.
- **Female V only** — Male V (`pma` rig) is untested but likely works with
  minor changes.
