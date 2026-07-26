# Spec: Complete Photo Mode support for built NPVs

**Status:** Implementation-ready
**Date:** 2026-07-25
**Supersedes:** `docs/superpowers/specs/2026-07-17-photomode-design.md`

## 1. Outcome

Every successful NPV build produces two independent, fully supported ways to
use the same V:

1. the existing AMM custom entity, unchanged; and
2. a selectable Photo Mode character with the NPV's name, a user-visible
   thumbnail, working body poses, and working facial animation.

The Photo Mode entry must work for both supported body rigs:

- `pwa` → woman-average Photo Mode scope and animation setup;
- `pma` → man-average Photo Mode scope and animation setup.

Photo Mode is part of the build contract, not an experimental best-effort
output. A build that cannot author or validate every required Photo Mode
artifact fails loudly and does not report success.

## 2. Why the current output fails

The current `write_photomode_files()` implementation emits only:

- a TweakXL `Character` record; and
- an `.archive.xl` file containing an `archive:` placeholder.

It does not emit the sibling `PhotoModeSticker` record, `.inkatlas`, `.xbm`,
localization resource, ArchiveXL resource scope, or a converted Photo Mode
`.ent`/`.app`.

PhotoMode-EX therefore discovers the character record and rejects it:

```text
Cannot register character "Character.default_v_7bf52f45_Photomode_Puppet":
icon is not defined.
```

The ordinary NPV appearance also still uses the paperdoll facial graph and the
ordinary donor entity has no `PhotoModePlayerEntityComponent`. Adding only an
icon would make the picker tile register, but would leave posing and facial
behavior unreliable.

The implementation must follow the complete artifact shape produced by
WolvenKit's “Add Photo Mode Files” workflow, not the current YAML-only fallback:

- [REDmodding NPV Photo Mode guide](https://wiki.redmodding.org/cyberpunk-2077-modding/modding-guides/npcs/npv-v-as-custom-npc/npv-amm-nibbles-replacer)
- [WolvenKit Photo Mode generator](https://github.com/WolvenKit/WolvenKit/blob/bf1ecc9fc4da3a3909c1b84be2ecdf0b41a668c0/WolvenKit.App/ViewModels/Shell/AppViewModel.ComplexFiles.cs#L44-L178)
- [WolvenKit TweakXL template](https://github.com/WolvenKit/WolvenKit/blob/bf1ecc9fc4da3a3909c1b84be2ecdf0b41a668c0/WolvenKit/Resources/TemplateFiles/yaml/photomode_npc_template.yaml)

## 3. Scope

### In scope

- Photo Mode thumbnail selection and preview in the web UI.
- Automatic use of a save's `screenshot.png` as the initial thumbnail when
  available.
- Thumbnail normalization and cooking to `.xbm`.
- A one-part `.inkatlas` that exposes the thumbnail to PhotoMode-EX.
- A complete TweakXL character and icon record.
- A cooked localization resource for the NPV's display name.
- A correct ArchiveXL localization and body-rig resource scope.
- A dedicated Photo Mode `.ent` and `.app`.
- Photo Mode body and facial animation conversion for `pwa` and `pma`.
- CLI support for selecting a thumbnail.
- Build, package, install, uninstall, rebuild, and coexistence support.
- Automated structural tests and an in-game release gate.

### Out of scope

- Custom Photo Mode poses or pose packs.
- Authoring new facial expressions or animation assets.
- Body rigs other than `pwa` and `pma`.
- Capturing or rendering a new portrait of the NPV inside the builder.
- Editing the thumbnail after the build has completed without rebuilding.
- Bundling PhotoMode-EX, Photomode NPCs Extended, ArchiveXL, TweakXL, Codeware,
  or redscript.

## 4. Product behavior

### 4.1 Appearance screen

Add a **Photo Mode thumbnail** card below the appearance inspector and above
the NPV name/output fields.

The card contains:

- a square preview;
- **Choose image…** / **Replace image…**;
- a compact drag-to-reposition crop control;
- **Reset crop**;
- source text such as `Using save screenshot` or the selected filename; and
- explanatory copy:
  `Required for the Photo Mode character picker. The image will be cropped to
  a square and embedded in the mod.`

Accepted inputs are static PNG, JPEG, and WebP images. Animated images are
rejected. The decoded input must be at least 200×200 pixels and no more than
32 megapixels.

When a selected save has a sibling `screenshot.png`, the UI loads it as the
initial candidate and shows the actual crop preview. The user may keep or
replace it. From-scratch presets have no implicit image, so the card begins as
an empty drop target.

**Continue is disabled until a valid thumbnail is loaded.** Its disabled label
is `Add a Photo Mode thumbnail to continue`. Image decoding happens immediately;
an unreadable or unsupported image produces an inline error on the card.

The existing whole-screen file drop handler must no longer interpret every
dropped file as a hair mod. Drop routing becomes target-specific:

- files dropped on the thumbnail card are handled as images;
- files dropped on the modded-hair row are handled as hair mods;
- unrelated drops are ignored with an inline explanation.

### 4.2 Crop model

The stored crop is a normalized focal point:

```json
{
  "focus_x": 0.5,
  "focus_y": 0.5
}
```

Both values are finite floats in `[0, 1]`. The backend uses them when performing
an aspect-fill square crop. There is no freeform rotation, filter, or arbitrary
aspect ratio.

The final working image is:

- 200×200 pixels;
- RGBA;
- sRGB/gamma-correct;
- aspect-fill cropped without stretching.

The browser preview and Pillow output must use the same crop calculation.
Golden-image tests cover center and edge focal points so the preview cannot
silently disagree with the packed texture.

### 4.3 CLI

Add:

```text
--photomode-thumbnail <png|jpg|webp>
```

Resolution order is:

1. explicit `--photomode-thumbnail`;
2. `<sav.dat parent>/screenshot.png`, when building from a save;
3. otherwise fail before expensive build work.

The CLI always center-crops (`focus_x = focus_y = 0.5`). The GUI passes its
selected focal point through the same backend contract.

There is no YAML-only fallback and no hidden generated placeholder. The picker
thumbnail represents the user's NPV, so the user must supply or accept a real
image.

## 5. Build request and persisted metadata

Extend `BuildRequest` with:

```python
photomode_thumbnail_path: Path | None = None
photomode_thumbnail_focus_x: float = 0.5
photomode_thumbnail_focus_y: float = 0.5
```

Add a pure `resolve_photomode_thumbnail(req) -> PhotoModeThumbnail` preflight
which:

1. applies the explicit/save-screenshot resolution order;
2. validates the path and decoded image;
3. validates the focal point;
4. calculates the source file's SHA-256;
5. returns immutable source metadata; and
6. raises `NpvError` with actionable remediation on failure.

Preflight runs before `resolve_assets` or WolvenKit work.

`build_meta.json` gains:

```json
{
  "photomode_thumbnail": {
    "path": "/absolute/source/path.png",
    "focus_x": 0.5,
    "focus_y": 0.5,
    "sha256": "..."
  }
}
```

The source image itself is not copied into `build_meta.json` and is not placed
in the install tree. Rebuild checks that the source still exists and prompts
for a replacement in the GUI if it does not.

## 6. Artifact model and paths

Introduce a frozen `PhotoModeArtifacts` value object in
`npv_build/photomode.py`. It is the single source of truth for record names,
depot paths, source paths, scope name, localization key, and icon part name.

For `mod_id = default_v_7bf52f45`, the generated source archive contains:

```text
source/archive/base/npv-build/default_v_7bf52f45/photomode/
  default_v_7bf52f45_photomode.ent
  default_v_7bf52f45_photomode.app
  default_v_7bf52f45_photomode_icon.xbm
  default_v_7bf52f45_photomode_icon.inkatlas
  default_v_7bf52f45_photomode_i18n.json
```

The install tree additionally contains:

```text
archive/pc/mod/default_v_7bf52f45.archive
archive/pc/mod/default_v_7bf52f45_photomode.archive.xl
r6/tweaks/npv_build/default_v_7bf52f45_photomode.yaml
```

The existing ordinary files remain:

```text
base/npv-build/default_v_7bf52f45/default_v_7bf52f45.ent
base/npv-build/default_v_7bf52f45/default_v_7bf52f45.app
```

Photo Mode authoring must clone those completed ordinary files after component
injection. It must never modify them in place; AMM behavior is a regression
boundary.

An unpacked normalized PNG may be retained at:

```text
<output>/intermediate/photomode/default_v_7bf52f45_icon.png
```

`intermediate/` is diagnostic build output and must not be packed or installed.

## 7. Thumbnail assets

### 7.1 XBM

The cooked XBM must have:

- width and height `200`;
- texture group `TEXG_Generic_UI`;
- compression `TCM_DXTAlpha`;
- gamma enabled;
- streaming disabled;
- mip chain disabled; and
- the normalized RGBA image as its only texture.

### 7.2 Ink atlas

The `.inkatlas` contains one texture slot pointing at the generated XBM and one
part:

```text
part name: custom_icon
texture slot: 0
UV rectangle: full image (0,0 → 1,1)
```

`custom_icon` is a constant shared by the atlas and TweakXL record.

### 7.3 Authoring implementation

Add a narrow .NET helper at `tools/npv-photomode/`, built and installed by the
same tool-management path as `npv-inject`.

It references the existing WolvenKit RED4/Common/Core/Modkit projects and
exposes:

```text
npv-photomode build-icon
  --png <normalized.png>
  --xbm <output.xbm>
  --inkatlas <output.inkatlas>
  --xbm-depot <depot path>
  --part custom_icon

npv-photomode convert-entity
  --source-ent <ordinary.ent>
  --source-app <ordinary.app>
  --output-ent <photomode.ent>
  --output-app <photomode.app>
  --app-depot <photomode app depot path>
  --rig pwa|pma
  --mod-id <mod id>

npv-photomode build-localization
  --output <photomode_i18n.json>
  --key <secondary key>
  --value <NPV display name>
```

`build-icon` uses WolvenKit's import APIs with an explicit
`GpuWrapApieTextureGroup.TEXG_Generic_UI`; it does not depend on WolvenKit
CLI's default texture group.

The atlas and localization resources are authored from RED4 types. Do not
vendor WolvenKit's binary `single_item_template.xbm`, its generated templates,
or CDPR assets. The helper must be an independent implementation using the
already-pinned libraries and project-authored inputs.

Every command reopens and validates its outputs before exiting zero. A partial
or structurally invalid CR2W file is a non-zero error.

## 8. Photo Mode entity and appearance conversion

### 8.1 Clone point

Conversion runs after `_do_inject_components()` has finished authoring the
ordinary NPV `.app`, and after the ordinary `.ent` has been cooked, but before
`wk.pack(source_dir, ...)`.

This ordering guarantees that:

- the Photo Mode appearance contains the same final component set as AMM;
- converted assets are inside `<mod_id>.archive`; and
- the registration files never point at files missing from the archive.

The current post-pack `emit_photomode` stage is too late for binary asset
authoring. It remains responsible only for external TweakXL and ArchiveXL
registration.

### 8.2 Entity conversion

`convert-entity` copies the ordinary `.ent` to the Photo Mode path, then:

1. repoints every appearance mapping/resource reference to the Photo Mode
   `.app`;
2. adds exactly one `PhotoModePlayerEntityComponent` named
   `PhotoModePlayerEntity`;
3. gives that component a deterministic non-zero CRUID derived from
   `SHA-256("<mod_id>:PhotoModePlayerEntity")`;
4. replaces the `root` animated component's gameplay animation list with the
   correct `pwa` or `pma` Photo Mode list;
5. replaces the gameplay lists on `Character Entity Animation Setup` and
   `Special Locomotion Setup` with their correct rig-specific lists; and
6. for `pwa`, adds the required `Ultimate Edition Animsets` extension if it is
   absent.

Missing required `root` or animation-setup components are hard errors. The
conversion must not silently emit a partially converted entity.

Animation path lists live in a project-owned, reviewed data file:

```text
npv_build/data/photomode_animation_sets.json
```

The lists are pinned to the supported Cyberpunk patch and have separate `pwa`
and `pma` entries. They reference base-game and declared dependency resources
by depot path only; no animation bytes are copied.

### 8.3 Appearance conversion

The ordinary `.app` is copied to the Photo Mode path after all NPV mesh and
infrastructure injection has completed. For every appearance definition:

- every `entAnimatedComponent` named `face_rig` switches to:
  - `player_woman_photomode_sermo.animgraph` for `pwa`; or
  - `player_man_photomode_sermo.animgraph` for `pma`;
- every relevant `entAnimationSetupExtensionComponent` receives the
  rig-appropriate Photo Mode facial animation entries with priority `200`; and
- the NPV appearance name and all visual mesh components remain unchanged.

The helper validates that it changed at least one `face_rig` and at least one
animation setup. A zero-change conversion is an error.

### 8.4 Structural postconditions

Before packing, Python requests an inspection result from the helper and asserts:

- ordinary and Photo Mode `.ent`/`.app` all exist;
- the ordinary app still uses its paperdoll facial graph;
- the Photo Mode app uses the expected Photo Mode facial graph;
- the Photo Mode entity has exactly one named Photo Mode player component;
- the Photo Mode entity contains the rig's idle and action Photo Mode sets;
- the Photo Mode entity points to the Photo Mode app;
- the app still contains the expected NPV appearance and component count; and
- the icon and localization resources reopen successfully.

Any failed assertion raises `WolvenKitError(operation="author_photomode")`.

## 9. TweakXL registration

Use a record identifier whose first character is capitalized so the custom NPV
sorts above Photomode NPCs Extended's lowercase `aa_` records. File/depot paths
and the canonical `mod_id` remain lowercase and unchanged.

Example for `pwa`:

```yaml
Character.Default_v_7bf52f45_Photomode_Puppet:
  $type: Character
  entityTemplatePath: base\npv-build\default_v_7bf52f45\photomode\default_v_7bf52f45_photomode.ent
  displayName: LocKey#npv_build_default_v_7bf52f45_photomode_name
  persistentName: PhotomodePuppet
  attachmentSlots: [ AttachmentSlots.WeaponRight, AttachmentSlots.WeaponLeft ]

Character.Default_v_7bf52f45_Photomode_Puppet.icon:
  $type: PhotoModeSticker
  atlasName: base\npv-build\default_v_7bf52f45\photomode\default_v_7bf52f45_photomode_icon.inkatlas
  imagePartName: custom_icon
```

For `pma`, append:

```yaml
  visualTags: [ !append ManAverage ]
```

The `pwa` record has no `visualTags` row, matching the WolvenKit template.

YAML values are produced through a YAML serializer or strict scalar-escaping
helper. Do not assemble user-controlled display text into YAML manually.

## 10. Localization and ArchiveXL

The helper authors a cooked `JsonResource` whose root is
`localizationPersistenceOnScreenEntries`. It contains one
`localizationPersistenceOnScreenEntry`:

```text
SecondaryKey: npv_build_<mod_id>_photomode_name
FemaleVariant: <NPV name>
```

The `.archive.xl` must be:

```yaml
localization:
  onscreens:
    en-us: base\npv-build\<mod_id>\photomode\<mod_id>_photomode_i18n.json

resource:
  scope:
    photomode_wa.ent:
      - base\npv-build\<mod_id>\photomode\<mod_id>_photomode.ent
```

For `pma`, use `photomode_ma.ent`.

The existing `archive: customIsHidden/enabled` placeholder is removed. It does
not provide the required resource scope.

## 11. Pipeline and checkpoint behavior

Add `npv_build/photomode.py` with:

- `PhotoModeThumbnail`;
- `PhotoModeArtifacts`;
- `resolve_photomode_thumbnail()`;
- `normalize_thumbnail()`;
- `author_photomode_assets()`; and
- `write_photomode_registration()`.

The pipeline flow becomes:

```text
validate Photo Mode thumbnail
→ parse CC
→ resolve assets
→ assemble ordinary NPV
→ author Photo Mode assets
→ pack the combined archive
→ emit AMM registration
→ emit Photo Mode TweakXL/ArchiveXL registration
→ package install zip
```

It is acceptable for `author Photo Mode assets` to remain an explicit internal
substage of `assemble` initially, provided it emits its own log prefix and runs
before packing. It must not remain in the current post-pack emitter.

The assemble checkpoint hash gains:

- thumbnail source SHA-256;
- focal point;
- body rig;
- Photo Mode animation-set data version;
- Photo Mode helper version; and
- Photo Mode artifact schema version.

The registration checkpoint hash gains the complete `PhotoModeArtifacts`
record plus the NPV display name.

Manifest output for Photo Mode registration is a list of every external file,
not one tweak path. Resume skips only when every listed file exists and the
input hash matches.

Changing only the thumbnail must rerun Photo Mode asset authoring, repack the
archive, repackage the zip, and leave the `mod_id` unchanged. The thumbnail is
presentation, not NPV identity.

## 12. Web UI and API changes

### `npv_build/webui_api.py`

Add:

```text
browse_for_photomode_thumbnail()
validate_photomode_thumbnail(path, focus_x, focus_y)
thumbnail_preview(path, focus_x, focus_y)
```

All methods return JSON-serializable results and catch bridge-boundary errors.
`thumbnail_preview` returns a bounded 200×200 PNG data URL; it must not expose
arbitrary filesystem contents.

`start_build(req)` validates:

- `photomode_thumbnail.path`;
- focal point values; and
- source existence

before starting `BuildWorker`.

### Frontend store

Add:

```javascript
photoModeThumbnail: {
  path: null,
  previewDataUrl: null,
  focusX: 0.5,
  focusY: 0.5,
  sourceLabel: null,
  valid: false
}
```

Reset it when the selected save/preset changes. A save screenshot may seed it,
but a thumbnail selected for one NPV must never leak into another source.

### Build screen

Change the existing stage label from `Photo Mode files` to
`Photo Mode registration`. During assembly, log distinct progress lines:

```text
[Photo Mode] Preparing thumbnail...
[Photo Mode] Converting entity and appearance...
[Photo Mode] Validating generated assets...
```

### My NPVs

Store the selected thumbnail metadata in `build_meta.json`. Rebuild reuses it
when the file still exists. If missing, the rebuild action returns to Appearance
with the thumbnail card marked `Source image moved or deleted`.

## 13. Dependencies and installation

Build-time dependencies:

- Pillow moves from the `gui` extra to the core dependencies because both the
  GUI and headless CLI normalize thumbnails;
- `tools/npv-photomode`;
- the pinned WolvenKit libraries used to build that helper.

Runtime dependencies documented in the generated README and Install screen:

- ArchiveXL;
- TweakXL;
- PhotoMode-EX;
- Photomode NPCs Extended;
- Codeware and redscript as required by the installed PhotoMode-EX version.

Dependency checks are warnings at build time because a user may build for
another installation. The Install screen must show missing Photo Mode runtime
dependencies separately from AMM dependencies and must not claim the NPV is
Photo Mode-ready when they are absent.

Install/uninstall continues copying the complete `archive/`, `bin/`, and `r6/`
trees. Multiple NPVs coexist because every filename, depot path, record,
localization key, and atlas path contains the content-derived `mod_id`.

## 14. Failure behavior

These are hard failures:

- missing/invalid thumbnail;
- image below minimum dimensions or above decode limit;
- unsupported/animated image;
- XBM not `TEXG_Generic_UI`;
- missing or unreadable XBM/inkatlas/localization output;
- icon part/path mismatch;
- missing entity animation infrastructure;
- no converted face rig;
- wrong rig scope;
- missing Photo Mode asset before pack;
- registration record missing its sibling `.icon`; or
- generated YAML/ArchiveXL failing parse validation.

No branch may silently point Photo Mode at the ordinary AMM entity. Partial
outputs remain on disk for diagnosis, consistent with the project hard-fail
policy.

## 15. Testing

### Unit tests

- Thumbnail resolution: explicit path, save screenshot fallback, and missing
  source.
- Image validation for type, dimensions, animation, megapixel limit, and focal
  bounds.
- Crop golden tests for center and edge focal points.
- `PhotoModeArtifacts` paths for both rigs.
- TweakXL contains both character and sibling icon records.
- `pma` adds `ManAverage`; `pwa` omits visual tags.
- ArchiveXL uses `photomode_wa.ent`/`photomode_ma.ent` correctly.
- Localization keys are stable and names with quotes/non-ASCII survive.
- Checkpoint hashes change for thumbnail bytes, focus, rig-data version, and
  helper version, but `mod_id` does not.
- Packaging includes archive, `.archive.xl`, and tweak YAML.

### .NET helper tests

- Build and reopen a 200×200 Generic UI XBM.
- Build and reopen an atlas with one `custom_icon` part and correct XBM path.
- Build and reopen localization with the expected secondary key/value.
- Convert fixture `.ent`/`.app` for `pwa` and `pma`.
- Idempotence: running conversion twice still produces exactly one Photo Mode
  player component.
- Failure fixtures missing `root`, `face_rig`, or animation setup return
  non-zero with a specific message.

Fixture CR2W files are produced from the test owner's local game during fixture
refresh and are not committed if they contain CDPR data. CI structural coverage
uses project-authored minimal CR2W documents.

### Python integration tests

- Build source tree contains all five Photo Mode archive resources before pack.
- Packed archive listing contains all five depot paths.
- Ordinary `.ent`/`.app` hashes are unchanged by Photo Mode conversion.
- Photo Mode inspection asserts component, animation, app link, facial graph,
  atlas, XBM, and localization postconditions.
- Resume skips only when all expected outputs exist.
- Replacing only the thumbnail repacks without changing `mod_id`.
- Two different NPVs package and install without filename/record collisions.

### Frontend tests

- Save screenshot appears as the default preview.
- Preset mode blocks Continue until an image is selected.
- Invalid image renders inline failure.
- Crop dragging updates the preview and request focal point.
- Dropping an image does not invoke hair-mod loading.
- Dropping a hair archive does not replace the thumbnail.
- Changing source clears the prior thumbnail.
- Build request contains the validated path and focal point.

### Manual in-game release gate

Run once for `pwa` and once for `pma`:

1. Install all declared dependencies and the built NPV.
2. Start the game and inspect the PhotoMode-EX log.
3. Confirm one `Registered new character` line for the NPV and no error for its
   record.
4. Open Photo Mode and confirm the NPV appears in the character picker.
5. Confirm the expected thumbnail and localized display name.
6. Spawn the NPV.
7. Cycle multiple idle/action poses.
8. Exercise facial expression controls and confirm the face is not frozen.
9. Confirm hair, cyberware, clothing, morph-baked face, skin, eyes, and other
   appearance components match the AMM version.
10. Spawn the ordinary AMM entity and confirm its existing behavior is
    unchanged.
11. Install two independently built NPVs and confirm both picker tiles work.

A release does not pass if the tile merely appears. Spawn, pose, face, visual
parity, and AMM regression checks are all required.

## 16. Implementation order

1. Add failing tests for the confirmed missing icon record and pre-pack asset
   requirement.
2. Implement `PhotoModeArtifacts`, thumbnail validation, normalization, and
   registration rendering.
3. Build `tools/npv-photomode` icon and localization commands with reopen
   validation.
4. Implement entity/app conversion and structural inspection for `pwa`.
5. Add `pma`, then run the local binary integration suite for both rigs.
6. Move binary Photo Mode authoring before archive packing and update checkpoint
   hashes.
7. Wire CLI and web API inputs.
8. Add the Appearance thumbnail card, crop preview, and targeted drop routing.
9. Update dependency checks, generated README, Install screen, build metadata,
   packaging, and My NPVs rebuild behavior.
10. Run automated tests, then the two-rig in-game release gate.

## 17. Definition of done

The feature is complete only when:

- every normal build contains the complete Photo Mode artifact set;
- PhotoMode-EX logs successful registration instead of `icon is not defined`;
- the picker displays the chosen thumbnail and NPV name;
- both rigs spawn, pose, and animate facially;
- Photo Mode and AMM appearances match;
- changing the thumbnail preserves NPV identity;
- multiple NPVs coexist;
- failures are explicit and actionable; and
- the manual two-rig release gate is recorded in `docs/release-qa.md`.
