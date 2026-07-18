# GUI Redesign: pywebview Web UI — Design Spec

**Date:** 2026-07-18
**Status:** Approved (brainstormed with visual companion; user-selected: structure A, inspector A, style B "refined dark", build view B)
**Supersedes:** the customtkinter GUI (`gui.py`, `gui_views/`, `gui_theme.py`) once parity is reached.

## Goal

Replace the customtkinter GUI with a web-based UI (pywebview + static HTML/CSS/JS) that fixes the four identified UX failures — confusing flow, raw log wall, cramped/dated widgets, weak save/mod browsing — and adds two new capabilities:

1. **Appearance inspector/editor** — display every decoded CC setting from the save (face, body, hair, skin, clothing) and allow overrides before building.
2. **From-scratch builds** — build an NPV with no save file, starting from a vendored default-V preset per body rig.
3. **Vanilla clothing catalog** — browse all ~1,485 vanilla clothing items with image previews (sourced from the user's `cyberpunk_mod_list` checkout) and assign them to clothing slots.

## Architecture

- **Shell:** `npv-build-gui` opens a pywebview native window loading bundled static files from `npv_build/webui/` (plain HTML/CSS/JS — no framework, no node toolchain).
- **Kept:** `gui_logic/` (Tk-free, unit-tested), `gui_backend.py` workers (`BuildWorker`, `InstallerWorker`), the whole pipeline.
- **Deleted at parity:** `gui.py`, `gui_views/`, `gui_theme.py`, CTk deps (`customtkinter`, `tkinterdnd2`).
- **Bridge:** one Python class `npv_build/webui_api.py` exposed via pywebview `js_api`:
  - `get_state()` / `save_config()` — config + dependency status (wraps `check_dependencies`, discovery)
  - `list_saves()` / `preview_save(path)` — save discovery + CC preview
  - `get_appearance(source)` — decoded `cc_settings` grouped into inspector rows (save file or preset)
  - `set_override(slot, value)` / `clear_override(slot)` / `clear_all_overrides()`
  - `get_clothing_catalog(rig, slot?)` / `get_thumbnail(item_id)` — catalog + lazy thumbnails
  - `start_build(req)` / `cancel_build()` / `poll_events()` — drives `BuildWorker`; JS polls ~5/s during builds, draining the worker queue (log lines, stage events, progress)
  - `list_mods()` / `install_mod(id)` / `uninstall_mod(id)` — wraps `gui_logic.modmanager`
- **Frontend:** `index.html`, `app.css` (design tokens from refined-dark palette), JS modules per screen (`rail.js`, `source.js`, `appearance.js`, `build.js`, `install.js`, `library.js`, `settings.js`), one plain JS store object; screens render from store state.
- Bridge methods are webview-free and unit-testable with plain pytest.

## Visual language ("refined dark")

Evolved Tokyo Night: `#16161e` background, `#1f2029` surfaces, rounded corners (8–10px), system-ui/Inter type with real hierarchy, single blue accent `#7aa2f7`, amber `#e0af68` reserved for overrides, green/red for success/error. No neon decoration; the palette is the only game nod.

## Screens & flow

**Left rail (persistent):** app name/version; steps **1 Source · 2 Appearance · 3 Build · 4 Install** with state (done ✓ / current ● / locked ○); below a divider: **My NPVs**, **Settings**. Completed steps clickable backward; forward only via Continue. First run shows onboarding (game dir + dependency check; replaces wizard) then lands on Step 1.

**Step 1 — Source.** Two entry modes:
- *From save file:* auto-discovered saves (existing `candidate_save_dirs()`) as cards — save name, rig/hair/skin preview line, patch badge, last-played date, newest first; manual browse + drag-drop. Selecting parses immediately; parse errors render inline on the card with remediation.
- *From scratch:* pick body rig (pwa/pma), which loads the vendored default-V preset for that rig; continue to the inspector with everything at defaults.

**Step 2 — Appearance.** Two-pane inspector: categories left (counts + amber override badges), searchable settings table right. Row = decoded name → human-readable value. Controls: dropdowns (options from mapping tables/part-resolver index), sliders (face morph floats), Browse… (clothing catalog picker). Overridden rows get amber border + one-click revert; "Reset all" in header. NPV name + output dir live on this step. Continue runs a dry-run resolve; `MappingResolutionError` pins to the offending row.

**Step 3 — Build.** Stage timeline left (five stages, per-stage duration, live status line), always-visible log right (monospace, auto-scroll with pause-on-scroll-up, copy button). Cancel while running. On failure: failed stage turns red with structured error + remediation; primary button becomes **Retry from failed stage** (resume path).

**Step 4 — Install.** Success summary (zip path, size, contents), actions: **Install to game**, **Open folder**, **Build another**. Installed NPV appears in My NPVs.

**My NPVs.** Card grid (name, mod id, built date, installed/built state); install/uninstall/rebuild/delete per card; includes the deferred tab-refresh fix.

**Settings.** Game dir, tool paths + auto-install (existing installer worker), `clothing_images_dir`, cache management, version info.

## Appearance data & override model

- New pure module `npv_build/gui_logic/appearance.py`: transforms `cc_settings` → inspector rows `{category, slot_id, label, value_label, value_raw, editable, options[] | range}`.
- Display names from vendored `data/display_names.json` (slot id → human label); unknown slots fall back to raw slot names (never crash).
- **Editable:** slots with resolvable option lists in mapping tables/part-resolver index (hair style/color, eye color, skin tone, brows, beard, clothing slots — subsumes `--garment`); face morph floats via sliders. **Read-only:** body rig and anything unresolvable (lock icon + tooltip). No free-text paths in v1: every override must be buildable.
- Overrides = plain dict `{slot_id: value}`, applied to a *copy* of `cc_settings` before `resolve_assets`. Pipeline unchanged. Mod ID already hashes `(name, cc_settings)` so overridden builds get distinct ids. Overrides persist per-save-file in config.

## From-scratch builds

- `BuildRequest` gains `cc_settings_override` as an alternative to `save_path` (exactly one required). Preset mode replaces `parse_save` with a `load_preset` stage (same checkpoint shape; input hash from the settings dict). Downstream stages untouched. Precedent: existing `--cc-json` flag.
- Vendored presets `data/presets/default_v_pwa.json`, `default_v_pma.json`: complete `cc_settings` decoded (with our parser) from saves made with untouched default V, one per rig. Option IDs/values only — no CDPR bytes.
- Test: each preset resolves cleanly through the mapping (guards patch bumps).
- Boundary: read-only rows stay at preset defaults; from-scratch editing is bounded by mapping coverage (data task to expand, not design change).

## Vanilla clothing catalog

- Source data: user's `~/cyberpunk_mod_list` repo — `data/clothes.json` (1,485 items: TweakDB item ID, display name, image filename) + `static/images/clothes/` (1.3 GB JPEGs).
- **Vendored:** copy of `clothes.json` (strings only). **Never vendored:** images.
- **Catalog build (runtime, user's machine — preserves no-CDPR-bytes):** `clothing_catalog.py` dumps TweakDB clothing records via WolvenKit CLI (item ID → entity/appearance name), joins with vendored `clothes.json`, validates each garment mesh against the part-resolver archive index per rig. Cached at `~/.cache/npv/clothing_catalog.json` with `buildable_pwa`/`buildable_pma` flags. Unresolvable items grey out ("not available for NPCs") — never a broken build.
- **Thumbnails:** `clothing_images_dir` config (defaults to trying `~/cyberpunk_mod_list/static/images/clothes`); ~256px thumbs generated lazily into `~/.cache/npv/thumbs/`; bridge serves them to the webview. Missing dir → text-only rows, feature degrades cleanly.
- **Picker UI:** per clothing slot row, Browse… opens thumbnail grid with name search + slot filter (from item-ID prefix), rig-buildable only by default. Picking sets the slot override to resolved `{mesh, appearance}` — same override dict, same dry-run validation. Works in both source modes.
- **Spike (front-loaded in plan):** dump TweakDB and measure real join coverage per rig across all 1,485 items before wiring UI.

## Error handling

Every `NpvError` renders as an inline card (`user_message` + `remediation`) at the point of failure — never a modal alert. Unexpected exceptions get a "copy details" affordance. Startup checks webview runtime (webkit2gtk on Linux, WebView2 on Windows) with a clear install hint.

## Testing

- `gui_logic/` tests unchanged; new pytest coverage for `appearance.py`, `clothing_catalog.py`, `webui_api.py` (all display-free).
- Preset-resolves-cleanly test per rig.
- One Playwright smoke test drives the real frontend against a mocked bridge in CI; `gui-smoke` xvfb job launches the pywebview shell.

## Distribution

- `gui` extra: + `pywebview`, − `customtkinter`/`tkinterdnd2` (at parity). Static `webui/` ships inside wheel/PyInstaller bundle.
- Linux AppImage: webkit2gtk declared runtime dep, checked at startup. Windows: WebView2 (default on Win 10/11).

## Out of scope (v1)

- Face preview renders (separate plan: `2026-07-17-face-preview.md`)
- Free-text asset-path overrides
- Modded (non-vanilla) clothing in the catalog
- Multi-appearance merge UI beyond existing modmanager hook
