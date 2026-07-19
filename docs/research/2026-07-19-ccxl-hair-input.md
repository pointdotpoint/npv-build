# CCXL modded-hair input for the appearance inspector

Research date: 2026-07-19. Sources: REDmodding wiki "CCXL: Hairs" (fetched from
the CDPR-Modding-Documentation GitHub mirror, last doc edit 2026-03-01), local
codebase audit.

## What a CCXL hair mod is (external format)

A CCXL (ArchiveXL character-creator) hair mod ships as **one `.archive` + one
`.archive.xl` yaml sidecar** (often wrapped in zip/7z/rar). Inside the archive:

- `.app` file(s) with **one appearance** (ArchiveXL extrapolates all color
  variants); components are `entSkinnedMeshComponent`s (+ optional
  `entAnimatedComponent` for physics; non-animated meshes bind
  `parentTransform`/`skinning` to `root` — same rule our own components use).
- `.mesh` files with `<appearance>@<material>` chunk appearances (e.g.
  `black_carbon@long`), `.mi` material templates, an `.inkcharcustomization`
  file adding the hairstyle switcher entry, and a localization `.json`.
- **No `.ent` files** — CCXL projects delete them; the hair is attached by
  appearance reference, not part entity.
- The `.xl` yaml declares everything, e.g.:

```yaml
customizations:
  female: modder\ccxl\addition\_pwa.inkcharcustomization
localization:
  onscreens: {en-us: modder\ccxl\addition\localization\hair__local.json}
resource:
  scope:
    player_wa_hair.app:
      - modder\ccxl\addition\appearances\your_hair_wa.app
    player_wa_hair.mesh:
      - modder\ccxl\addition\meshes\your_hair_wa.mesh
```

So the `.xl` sidecar names the hair `.app` depot paths directly, and a save
made with a CCXL hair stores selections like `label: "winona_2_hair"` /
`hair.style_id: "winona_2"` (verified on the user's real save).

## What the codebase already has (all verified working, 2026-07-19)

1. **`hair_mod_helper.install_hair_mod(source_path, game_dir)`** — copies the
   mod's `.archive` + `.xl` into `<game>/archive/pc/mod/` from `.archive`,
   `.zip`, `.7z`, or `.rar` input (traversal-safe, CVE-2022-30333-hardened),
   returns `(derived_token, installed_paths)`. Orphaned since the Tk GUI was
   retired — no current caller.
2. **`part_resolver.extract_hair_components(game_dir, token, body_rig, wk=)`**
   — finds the mod's hair `.app` across installed archives (pre-filters
   candidates by filename tokens AND `.xl` sidecar content, so it typically
   lists 1 archive ≈ 6s, not all of them), returns
   `(components, source_archive, app_depot, app_name)`.
3. **`mapping.resolve_assets`** hair branches:
   - `hair_override` param: vanilla number | modded token | "none".
   - **CCXL-native branch**: when `cc_settings["hair"]["raw"].endswith("_hair")`
     with a `style_id`, it calls `extract_hair_components(style_id)` and
     attaches `asset_paths["hair_app"] / hair_appearance_name /
     hair_components` + an external-dependency note "modded hair from <archive>
     (must stay installed)". This is the path a save that used CCXL hair takes
     automatically.
4. **`wolvenkit.build_project`** consumes `hair_app`/`hair_appearance_name`
   (attach by cooked-.app appearance ref, rig graph intact; component-copy
   fallback).

## Design decision for the GUI feature

**Emulate a save that used the CCXL hair.** The inspector's overrides dict gets
a `hair_mod: <token>` slot; `apply_overrides` maps it to
`cc["hair"] = {"style_id": token, "raw": token + "_hair"}`, which drives the
existing CCXL-native branch end-to-end. Consequences, all free:

- mod id changes (it hashes `cc_settings`) → distinct builds per hair mod;
- resolve-stage checkpoint hash changes → correct resume behavior;
- no new `BuildRequest` field, no new pipeline stage.

File input flow: bridge `add_hair_mod(path)` = `install_hair_mod()` into the
game dir (the mod must be installed anyway — it is a **runtime dependency** of
the built NPV) + a validation probe via `extract_hair_components` on the fresh
install; no hair `.app` found → structured error ("not a CCXL/hair mod").
UI surfaces the external-dependency warning verbatim: the NPV needs the hair
mod to stay installed.

Rejected alternatives:
- Parsing the `.xl` yaml ourselves to get `.app` paths: duplicate of what
  `extract_hair_components` already does (it reads `.xl` sidecars in its
  candidate filter); adds a yaml dependency for no coverage gain.
- `BuildRequest.hair_override` pass-through: works, but bypasses `cc_settings`
  so the mod id would NOT change per hair — collision between two builds of the
  same save with different modded hair. The emulation approach avoids this.
