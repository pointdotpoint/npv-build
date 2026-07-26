# Roadmap — pending features

Status as of 2026-07-19. Shipped so far: M0–M6 (npv-build 2.0.0 draft release), web UI shell + parity
(GUI redesign plan 1/4, `4bfc5e8`), full GUI build flow QA'd end-to-end on a real save.
Design spec for the GUI items: `docs/superpowers/specs/2026-07-18-gui-redesign-webui-design.md`.

## GUI redesign — remaining plans

Dispatchable implementation plans exist for everything in this section and the
perf item (written 2026-07-19, superpowers plan format — executable task-by-task
via subagent-driven-development or executing-plans):

| Work | Plan file |
| --- | --- |
| Plan 2 — Appearance inspector | `docs/superpowers/plans/2026-07-19-webui-appearance-inspector.md` |
| Plan 3 — From-scratch builds | `docs/superpowers/plans/2026-07-19-from-scratch-presets.md` |
| Plan 4 — Clothing catalog | `docs/superpowers/plans/2026-07-19-clothing-catalog.md` |
| Assemble scan cache (perf) | `docs/superpowers/plans/2026-07-19-assemble-scan-cache.md` |

Execution order: plan 2 → plan 4 (depends on plan 2's row/override contract);
plan 3 and the scan cache are independent and can run any time. Plan 3's preset
data and plan 4's in-game garment check are user-gated; everything else is
agent-dispatchable as-is.

### Plan 2 — Appearance inspector with overrides *(next up)*

Two-pane inspector (categories + searchable settings table), dropdowns from mapping tables,
sliders for face morphs, amber override badges + one-click revert, "Reset all", overrides dict
applied to a copy of `cc_settings`, persisted per-save, dry-run resolve on Continue with
`MappingResolutionError` pinned to the offending row.

- New pure module `gui_logic/appearance.py` + vendored `data/display_names.json`
- Subsumes CLI `--garment` in the GUI
- Also moves NPV name + output dir from Source to this step (per spec)
- **Added 2026-07-19:** modded hair (CCXL) input — pick a hair mod file
  (.archive/.zip/.7z/.rar), it installs into the game dir and overrides the
  NPV's hair via the existing CCXL pipeline branch
  (research: `docs/research/2026-07-19-ccxl-hair-input.md`)

### Plan 3 — From-scratch builds

Replaces the greyed-out "From scratch — coming soon" card on Source:

- Body-rig picker (pwa/pma)
- Vendored presets `data/presets/default_v_pwa.json` / `default_v_pma.json`
- `BuildRequest.cc_settings_override`; `load_preset` pipeline stage replacing `parse_save`
- Preset-resolves-cleanly test per rig (guards patch bumps)

### Plan 4 — Vanilla clothing catalog

- `clothing_catalog.py`: TweakDB dump via WolvenKit joined with `~/cyberpunk_mod_list`
  `clothes.json` (1,485 items), cached at `~/.cache/npv/clothing_catalog.json` with per-rig
  buildable flags
- Lazy ~256px thumbnails from `clothing_images_dir`; degrades to text-only rows if missing
- Browse… picker grid per clothing slot (name search, slot filter, rig-buildable only)
- **Front-loaded spike:** dump TweakDB and measure real join coverage per rig before wiring UI

## Smaller spec items missing from the current shell — ✅ ALL SHIPPED 2026-07-19 (`77f1309`)

- **Source:** manual browse + drag-drop; patch badge on save cards
- **Build:** log copy button; pause-on-scroll-up
- **Install/Done:** "Open folder" action; zip size + contents summary
- **My NPVs:** built date; rebuild + delete actions (only install/uninstall exist)
- **Settings:** tool paths + auto-install UI; `clothing_images_dir`; cache management
- **Startup:** webview-runtime check with install hint; full first-run onboarding flow
  (currently just a banner)

## Outstanding from older plans (user-gated or blocked)

- **M5-T8 — retire npv-inject:** user builds with `NPV_PY_INJECT=1` and confirms the NPV spawns
  in-game via AMM → then delete `tools/npv-inject` and drop the .NET dependency
- **Photomode Task 4 spike (.ent/.app variant):** was BLOCKED on real photomode depot paths —
  partly due to a stale `game_dir` in config, which is now valid, so this is unblockable
  (ground truth via WolvenKit "Add Photomode Files" output or grepping local base-game archives)
- **Face preview** (`docs/superpowers/plans/2026-07-17-face-preview.md`): headless Blender render
  of the baked head — plan written, nothing built
- **M3 H2-v2:** optional donor-entity retirement re-test
- **Multi-appearance "Add appearance…" UI hook** (deferred since M5)
- **Cross-distribution Linux release QA:** the AppImage now bundles Qt WebEngine
  and CI launches the GUI under Xvfb; continue spot-checking releases on a
  non-Ubuntu desktop.

## Known perf improvement (from 2026-07-19 GUI QA)

- Assemble stage rescans every installed mod archive per head-mesh layer (~6s per archive per
  layer); caching the scan result per build would cut minutes off large mod setups.
  Plan: `docs/superpowers/plans/2026-07-19-assemble-scan-cache.md`
