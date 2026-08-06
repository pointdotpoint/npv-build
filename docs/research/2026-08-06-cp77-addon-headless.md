# CP77 Blender add-on headless automation spike — 2026-08-06

**MATERIALS decision: `clay`.** The add-on installs and imports headlessly
without any interactive step, but WolvenKit cannot uncook the game's `.xbm`
textures on this Linux install, so every material image the add-on wires up
is a `0x0`, no-data placeholder. There is nothing for the add-on to import
that would change a render's appearance. Task 2/3 should render flat/clay
shading and not attempt to load real skin/hair/garment textures.

## Inputs

- Game install: Cyberpunk 2077, local Steam installation on 2026-08-06,
  `game_dir` from `~/.config/npv/config.toml`.
- WolvenKit CLI: 8.19.0 (`cp77tools`, cached at
  `~/.cache/npv/tools/wolvenkit/cp77tools`).
- Blender: 4.2.0 (cached at
  `~/.cache/npv/tools/blender/blender-4.2.0-linux-x64/blender`; not on PATH).
- Probe mesh: a real built NPV head mesh at
  `~/npv_builds/QuickSave-0/source/archive/base/npv-build/quicksave_0_110a165e/quicksave_0_110a165e_head.mesh`.
- CP77 Blender add-on: `github.com/WolvenKit/Cyberpunk-Blender-add-on`.

No game assets, textures, or CDPR bytes are vendored in this repo. This
document contains only paths, commands, and hashes computed against the
user's own install.

## Step 1: WolvenKit material export

`wk.export(mesh, dest=...)` (the plain `export` CLI command,
`WolvenKit.CLI export <path> -o <out> -gp <gamepath>`) failed immediately
against the loose built `.mesh`:

```
[ 0: Error ] - Depot path is not set: Choose a Depot location within Settings for generating materials.
```

Root cause (found in the vendored WolvenKit source at
`/home/pdp/npv_project/WolvenKit/`): `export`'s `MeshExportArgs` is bound
from .NET configuration (`WolvenKit.CLI/GenericHost.cs:69`,
`services.AddOptions<MeshExportArgs>().Bind(...GetSection("MeshExportArgs"))`),
and `withMaterials` defaults to `true`
(`WolvenKit.Common/Model/Arguments/ExportArgs.cs:239`) while `MaterialRepo`
defaults to unset. **`export` exposes no CLI flag to set the material repo
path or disable materials** — `WolvenKit.CLI export --help` only lists
`--path/-p`, `--outpath/-o`, `--gamepath/-gp`, `--uext`, `--forcebuffers/-fb`.

Unblocked via the .NET generic-host environment-variable config convention
(`Section__Property`):

```bash
MeshExportArgs__MaterialRepo="<dest>" MeshExportArgs__withMaterials=true \
  cp77tools export "<mesh>" -o "<dest>" -gp "<game_dir>" -v Detailed
```

This succeeded and produced, next to the `.glb`:
- `<name>.Material.json` — material assignments per submesh: base material
  `.mi`/`.mt` depot paths, numeric/color params (skin tint, roughness bias,
  etc.), and **depot paths to still-cooked `.xbm` texture resources** (e.g.
  `base\characters\head\...\h0_000_pwa_c__basehead_d01.xbm`). No texture
  bytes are embedded here — it's a manifest of what to uncook next.
- A handful of `.mlsetup.json`/`.mltemplate.json` files (multilayer material
  definitions referenced by the mesh's materials), also just JSON, no images.
- The `.glb` itself has one placeholder `"Default"` material with an empty
  `pbrMetallicRoughness: {}` and `images: None`, `textures: None` — **no
  material or texture data is embedded in the glTF**; everything lives in
  the sidecar JSON.

Separately, `uncook`/`extract-and-export` (the archive-oriented command with
`--mesh-export-type WithMaterials` and `--mesh-export-material-repo`) refused
to run against the loose file at all (`"Input file is not an .archive."`) —
it only operates on packed `.archive` files, which the mid-build loose CR2W
tree is not.

**Texture uncooking is broken on this Linux install.** Uncooking any `.xbm`
(tried the skin albedo `h0_000_pwa_c__basehead_d01.xbm` referenced above,
straight from `basegame_4_appearance.archive`) fails every time:

```
[ 0: Error ] - ... And unexpected error occured while uncooking: The type initializer for 'DirectXTexNet.TexHelper' threw an exception.
  at WolvenKit.Common.DDS.DDSUtils.GenerateHeader(DDSInfo info)
  at WolvenKit.RED4.CR2W.RedImage.Create(DDSInfo info, Byte[] imgData)
  at WolvenKit.RED4.CR2W.RedImage.FromXBM(CBitmapTexture bitmapTexture)
...
Uncooked 0/1 files.
```

`DirectXTexNet` is a native interop wrapper around Microsoft's DirectXTex;
this WolvenKit release ships no working Linux native backend for it, so its
static initializer throws on first texture decode and every `.xbm` uncook
fails, regardless of format (`--uext png/dds/tga` all hit the same
initializer). This blocks texture recovery independent of anything the
Blender add-on does.

## Step 2: CP77 add-on headless install + import

### Release selection

Latest release (`2.0.0`, 2026-06-07) declares `bl_info["blender"] = (5, 0, 0)`
— requires Blender ≥ 5.0, incompatible with our cached 4.2.0. The next line
down (`1.8.0`, 2026-01-21) declares `bl_info["blender"] = (4, 5, 0)` — also
incompatible. Releases `1.6.0`–`1.6.2` (2025-08-02 back to 2025-03-16) all
declare `bl_info["blender"] = (4, 0, 0)`, which is compatible. Used the
newest of that line:

- **Release:** `1.6.2` (tag `1.6.2`, published 2025-03-16)
- **Asset:** `Cyberpunk-Blender-Add-On-1.6.2.zip`
- **URL:** `https://github.com/WolvenKit/Cyberpunk-Blender-add-on/releases/download/1.6.2/Cyberpunk-Blender-Add-On-1.6.2.zip`
- **SHA-256:** `ab24f494d6869bc78c7c9ea49828cf1ee7e9eb52cfd1e6534caaa7d45f38016e`
- **Module name:** `i_scene_cp77_gltf`

### Headless install + enable

```bash
blender --background --python-expr "
import bpy
bpy.ops.preferences.addon_install(filepath='<zip>')
bpy.ops.preferences.addon_enable(module='i_scene_cp77_gltf')
bpy.ops.wm.save_userpref()
"
```

Ran clean, no interactive prompts, no errors:

```
Modules Installed (i_scene_cp77_gltf) from '<zip>' into '/home/pdp/.config/blender/4.2/scripts/addons'
-------------------- Cyberpunk IO Suite Starting--------------------
Blender Version:4.2.0
Cyberpunk IO Suite version: 1.6.2
-------------------- Cyberpunk IO Suite Has Started--------------------
Info: Preferences saved
```

Both `addon_install` and `addon_enable` completed and Blender exited 0 —
this half of headless automation is proven and reusable for Task 2.

### Import operator

`io_scene_gltf.cp77` (class `CP77Import` in
`i_scene_cp77_gltf/importers/import_with_materials.py`), invoked from a
second headless run against the Step 1 `.glb`:

```python
props = bpy.context.scene.cp77_panel_props
props.with_materials = True
props.remap_depot = False
bpy.ops.io_scene_gltf.cp77(
    filepath=glb_path,
    directory=glb_dir + '/',
    files=[{'name': glb_basename}],
    image_format='png',
    exclude_unused_mats=True,
    hide_armatures=True,
    import_garmentsupport=True,
    appearances='Default',
)
```

Required inputs beyond the `.glb` path: the operator reads
`<stem>.Material.json` from the same directory as the `.glb` (Step 1's
sidecar) and expects every texture the material JSON references to already
exist as a decoded image file (`png` by default) at a path relative to that
same directory, mirroring the depot tree (e.g.
`<dir>/base/characters/head/.../h0_000_pwa_c__basehead_d01.png`). It does
**not** require the full WolvenKit project/`.cpmodproj` layout for this glTF
path — a flat directory with the `.glb` + `.Material.json` + the depot-shaped
texture tree is sufficient. It does require `cp77_panel_props` to exist on
the scene, which the add-on registers on enable.

Result: `bpy.ops.io_scene_gltf.cp77(...)` returned `{'FINISHED'}` with no
exception — the importer ran fully headless. It built a real shader graph
(`01_ca_pale` material, 40 nodes, 10 image-texture nodes wired into a skin
shader) matching the material JSON's skin material type. But every one of
the 8 real skin texture images it tried to load resolved to
`has_data=False`, `size=(0, 0)` — placeholders — because the corresponding
`.png` files were never produced (Step 1's texture-uncook failure). The
add-on did exactly what was asked; there was no texture data on disk for it
to load.

## Decision

**`clay`.** Both probes ran end-to-end headlessly with no interactive
steps — the add-on install/enable and the material-glb import operator are
individually solid and worth keeping for a future revisit. But the decision
gate requires both probes to pass **and produce real material data**, and
they don't: WolvenKit's texture uncooking is broken on this Linux install
(`DirectXTexNet.TexHelper` static-initializer crash, 0/1 on every `.xbm`
tried), so the add-on's material import has no texture bytes to load. The
resulting Blender materials are structurally correct but visually blank —
rendering them would not usefully differentiate one NPV from another.

### Concrete blockers for a future revisit

1. **DirectXTexNet has no working Linux backend in WolvenKit.CLI 8.19.0.**
   This is the actual blocker — not the add-on, not Blender. Until WolvenKit
   ships (or this install acquires) a working native DDS/texture decode path
   on Linux, no texture-driven material pipeline is possible here, headless
   or otherwise. Candidates for a future spike: a newer WolvenKit release
   that bundles a cross-platform DirectXTex build; running the uncook step
   under Wine/a Windows WolvenKit binary; or a from-scratch `.xbm` texture
   decoder that bypasses `DirectXTexNet` entirely.
2. **Add-on/Blender version pairing is narrow.** Only add-on `1.6.0`–`1.6.2`
   declare `blender: (4, 0, 0)` compatibility matching the cached 4.2.0.
   `1.7.x`/`1.8.0` require ≥4.5, `2.0.0` requires ≥5.0. If the cached Blender
   is ever upgraded, re-check `bl_info["blender"]` in whatever add-on release
   is current at that time before assuming `1.6.2` (now a year+ old) is still
   the right pick.
3. **`export`'s material flags are undocumented/CLI-flag-less.** Anyone
   revisiting this needs the `MeshExportArgs__MaterialRepo`/
   `MeshExportArgs__withMaterials` environment-variable workaround — there is
   no `--material-repo` flag on `export` itself (only on `uncook`, which
   requires a packed `.archive` as input, not a loose CR2W tree).

## What the clay tier can and cannot validate

**Can validate** (geometry-only, from the `.glb`/`.mesh` data WolvenKit
*does* export correctly): presence of every expected mesh part (head, body,
hair, garments, eyes/teeth/etc.), correct placement/transform of each part
relative to the rig, and overall silhouette — e.g. catching a missing
garment component, a part floating off the root bind, or a wrong body rig
being used.

**Cannot validate**: skin tone (the `TintColor`/`TintScale` params exist in
`.Material.json` but there's no texture to apply them to), hair color,
material variant differences (e.g. same mesh with different `.mi` skin
variants would render identically in clay), or anything that depends on
actual texture content (tattoos, makeup, cyberware chrome finish, garment
pattern/print). Two NPVs that differ only in skin tone or hair color will
render as visually identical clay previews.

## Commands run (reference)

```bash
# version checks
uv run python -c "from npv_build.wk_cli import WolvenKit, WolvenKitConfig; ..."  # -> 8.19.0
~/.cache/npv/tools/blender/blender-4.2.0-linux-x64/blender --version              # -> 4.2.0

# Step 1: material export (the working invocation)
MeshExportArgs__MaterialRepo="<dest>" MeshExportArgs__withMaterials=true \
  ~/.cache/npv/tools/wolvenkit/cp77tools export "<head.mesh>" -o "<dest>" \
  -gp "<game_dir>" -v Detailed

# texture uncook probe (fails every time)
~/.cache/npv/tools/wolvenkit/cp77tools uncook "<basegame_4_appearance.archive>" \
  -o "<dest>" -r "h0_000_pwa_c__basehead_d01\.xbm$" -uext png -v Detailed

# Step 2: add-on release enumeration
gh api repos/WolvenKit/Cyberpunk-Blender-add-on/releases --paginate

# Step 2: headless install/enable + import — see script bodies above
```
