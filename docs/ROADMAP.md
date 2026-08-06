# Roadmap — pending features

Status as of 2026-08-06. Shipped so far: M0–M6 (v2.0.0), the full GUI redesign
(plans 1–4), Photo Mode support, build performance overhaul, and the v2.0.1 /
v2.0.2 releases with Windows and Linux installers.
Design spec for the GUI: `docs/superpowers/specs/2026-07-18-gui-redesign-webui-design.md`.

## Shipped since the last roadmap (2026-07-19)

| Work | Landed |
| --- | --- |
| Plan 2 — Appearance inspector + CCXL modded hair | `5976618` (2026-07-19) |
| Plan 3 — From-scratch preset builds (tasks 1–5) | `42c0223` (2026-07-25) |
| Preset appearance editing via full inspector (post-plan amendment) | `6d454b5` |
| Vendored default female V preset (`data/presets/default_v_pwa.json`) | `162124a` |
| Plan 4 — Clothing catalog (`gui_logic/clothing_catalog.py`, thumbnails, picker) | `7f0e7ee` |
| Photo Mode complete (registration, packaging, `.ent`/`.app` variant — formerly gated Task 4) | `7f0e7ee` |
| Build performance overhaul (`core/artifact_cache.py`, GUI resume-by-default; supersedes the assemble-scan-cache plan) | `7f0e7ee` |
| QuickSave-4 hair/clothing correctness (exact CCXL hair + garment appearance resolution) | `7f0e7ee` |
| Windows + Linux installers, release CI hardening | `2c59f97`..`55b8d38` |
| Releases v2.0.1 and v2.0.2 published | tags `v2.0.1`, `v2.0.2` |

Plan files for the above live in `docs/superpowers/plans/` (`2026-07-19-*`,
`2026-07-25-*`); specs in `docs/specs/`.

## User-gated (needs the user, not an agent)

- **Male V preset data** — only `default_v_pwa.json` is vendored. User creates an
  untouched default male V save, then `scripts/make_preset.py` generates
  `data/presets/default_v_pma.json`. The pma e2e resolve guard un-skips when the
  file lands.
- **In-game AMM spawn verification** — confirm built NPVs (save-based, preset-based,
  and overridden) spawn correctly via AMM. Gates final plan-3 sign-off.
- **M5-T8 — retire npv-inject:** user builds with `NPV_PY_INJECT=1` and confirms
  the NPV spawns in-game → then delete `tools/npv-inject` and drop the .NET
  dependency.
- **Winona hair mod** — the mod's `.archive` is missing from the game dir (only
  orphaned `.xl` sidecars remain). User should reinstall the mod; nothing to fix
  in npv-build.

## Not started

- ~~Appearance preview render~~ — ✅ shipped 2026-08-06 (branch
  `appearance-preview-render`, plan
  `docs/superpowers/plans/2026-08-06-appearance-preview-render.md`): headless
  Blender clay render of a built NPV (full body + face views), "Render
  preview" button in My NPVs, and golden-image regression via
  `NPV_PREVIEW_BUILD_DIR=<build> [NPV_UPDATE_GOLDENS=1] uv run pytest
  tests/test_appearance_render_e2e.py` (goldens live in
  `~/.cache/npv/preview_goldens/`, never in the repo). Color/texture materials
  remain clay-only until WolvenKit-Linux can uncook `.xbm` textures
  (DirectXTexNet native crash — retest recipe in
  `docs/research/2026-08-06-cp77-addon-headless.md`).
- **M3 H2-v2:** optional donor-entity retirement re-test.
- **Multi-appearance "Add appearance…" UI hook** (deferred since M5).

## Follow-up hardening — ✅ shipped 2026-08-06 (branch `followup-hardening`)

- Body-tattoo appearance now re-keys to the effective skin tone (override-aware).
- Stale `npv-inject` binaries hard-fail at resolution with the rebuild command.
- `appearance_data` bridge parse-failure contract pinned by smoke tests.
- Cross-distribution Linux spot-check procedure added to `docs/release-qa.md`.

## Housekeeping

- Master is one commit past v2.0.2 (`1a91f9a`, new app icon) — unreleased.
- Stale local branches: `plan3-from-scratch-presets`, `fix/head-skin-eyes-lashes`.
