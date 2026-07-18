# npv-build UI/UX Polish — Design Spec

*Status: approved · Date: 2026-07-17 · Follows M0–M6 (npv-build 2.0.0 shipped). Post-release visual polish, not a release blocker.*

---

## 1. Background & Goals

The npv-build GUI (customtkinter, 5 views behind a `CTkTabview`) is functionally complete after M4 but reads as bare-bones: flat thin frames, hardcoded `("Arial", N)` fonts scattered across ~30+ widget definitions, cramped spacing, weak visual hierarchy, and empty-looking output areas. User feedback: "too bare bones and not very pretty," and "switch to a more common font for readability."

### Goals

- **G1** — A refined-dark visual identity: deeper background, card-style panels with subtle borders, one accent color, generous spacing, clear hierarchy. Modern and clean, not gamer-y.
- **G2** — A single, readable, cross-platform font: the native system UI font stack (Segoe UI on Windows, system sans on Linux), applied consistently.
- **G3** — Centralize theme (colors + fonts + spacing) in one module so the ~30 scattered font calls and ad-hoc color constants become one source of truth.
- **G4** — Polish all 5 views (Build, Save Browser, Build/Progress, Mod Manager, Settings, Wizard).

### Non-Goals

- No new features or workflow changes — this is pure presentation.
- No layout *restructuring* that moves inputs between views (GUI-1 parity is preserved).
- No bundled fonts (system stack chosen — zero bundling, no license/PyInstaller-collection concerns).
- No light-mode toggle (refined dark only; a toggle is a possible later follow-up).

## 2. Decisions (confirmed with user)

| # | Decision | Choice |
|---|---|---|
| D1 | Aesthetic direction | **Refined dark** — polished dark, one accent, card panels, generous spacing |
| D2 | Font | **System UI stack** — native per-OS via a font stack, no bundling |
| D3 | Scope | **Full theme + layout** — central theme module + restyle all 5 views |

## 3. Architecture

### 3.1 The theme module (`npv_build/gui_theme.py`) — new, single source of truth

A Tk-free-where-possible module holding the palette, font helper, and spacing scale. It is the ONLY place colors/fonts/spacing are defined; every view references it.

- **THEME-1 — Palette** (refined dark; exact hexes are the implementer's to tune within this direction, these are the anchors):
  - `BG` background `#1a1b26` (near-black, deep)
  - `SURFACE` card/panel `#24283b` (elevated)
  - `SURFACE_ALT` inset (log box, entries) `#1f2335`
  - `BORDER` subtle card border `#2f3549`
  - `ACCENT` primary (buttons, active tab, focus) `#7dcfff` (cyan)
  - `ACCENT_HOVER` `#5fb8e8`
  - `TEXT` primary `#c0caf5`
  - `TEXT_MUTED` secondary/hints `#787c99`
  - `SUCCESS` `#9ece6a`, `WARNING` `#e0af68`, `ERROR` `#f7768e` (dependency lamps, build status, error labels)
- **THEME-2 — Font helper**: `system_font(size: int, weight: str = "normal") -> ctk.CTkFont` returning a `CTkFont` over the native stack. customtkinter/Tk resolves an unknown family to the system default, so passing a family list isn't directly supported by `CTkFont` — instead the module picks the best available family at startup (`_resolve_ui_family()`: try Segoe UI, then a Linux sans like "DejaVu Sans"/"Noto Sans"/system default via `tkinter.font.families()`), caches it, and `system_font()` builds `CTkFont(family=_FAMILY, size=size, weight=weight)`. This must run after a Tk root exists (font families need a root) — so the resolver is lazy/called from `App.__init__`.
- **THEME-3 — Spacing scale**: named constants `PAD_XS=4, PAD_S=8, PAD_M=12, PAD_L=20, PAD_XL=32` used for all `padx`/`pady` — replaces the current ad-hoc mix. Section headers, field labels, and muted hints get named font sizes: `FONT_TITLE=(18,"bold")`, `FONT_HEADER=(14,"bold")`, `FONT_LABEL=(12,"bold")`, `FONT_BODY=(12,"normal")`, `FONT_HINT=(11,"normal")` — exposed as helper calls `title_font()`, `header_font()`, etc.
- **THEME-4 — Apply function**: `apply_theme()` sets `ctk.set_appearance_mode("dark")` and, where a customtkinter color theme helps, either a bundled JSON color theme (`npv_build/data/ctk_theme.json`) via `set_default_color_theme()` OR per-widget `fg_color`/`text_color` from the palette. Prefer per-widget palette application for control (the JSON theme route is optional if it cleanly covers buttons/tabs/entries). Document which was used.

### 3.2 View restyling (consumes the theme module)

Each of the 5 views + the app shell is updated to: (a) replace every `("Arial", …)` with `system_font(...)`/the named font helpers; (b) replace ad-hoc `TEXT_MUTED`/`TEXT_WHITE` (currently in gui.py) with theme palette references; (c) use the spacing scale for padding; (d) apply card framing (`SURFACE` fg + `BORDER` border_width=1 + corner_radius) to section frames; (e) accent the primary action (Build button → `ACCENT`).

- **VIEW-1 — App shell / Build tab (`gui.py`)**: the biggest surface. Configuration Panel and its sections (System Dependencies, Character & Input Data) become cards; the Build button is the accent CTA; the Build Progress & Output area gets a placeholder empty state ("Select a save and click Build NPV Mod") instead of a blank void; dependency lamps use `SUCCESS`/`ERROR` palette; consistent section headers.
- **VIEW-2 — Save browser (`gui_views/save_browser_view.py`)**: rows become card-style (surface bg, border, hover accent); the thumbnail + name + timestamp laid out cleanly; empty state ("No saves found — Browse…") styled.
- **VIEW-3 — Build view (`gui_views/build_view.py`)**: progress bar accent color; log box uses `SURFACE_ALT`; error label uses `ERROR`; cancel/retry buttons styled (retry = accent).
- **VIEW-4 — Mod manager (`gui_views/modmanager_view.py`)**: mod rows as cards with install/uninstall/open buttons; empty state.
- **VIEW-5 — Settings (`gui_views/settings_view.py`)**: form fields aligned, section grouping, save button accent.
- **VIEW-6 — Wizard (`gui_views/wizard_view.py`)**: the two `("Arial", …)` here → theme; step panes get card framing + the accent for the primary "next/finish" action; dependency lamps use palette.

## 4. Constraints (carried from the project)

- **C1 — GUI-1 parity**: every `BuildRequest`-settable input stays reachable and functional. The existing `test_gui_parity.py` must still pass (it asserts each field is gathered). No input is removed or relocated between views.
- **C2 — GUI-8**: no raw tracebacks surface; error paths keep the `NpvError` user_message+remediation display and the sanctioned `# noqa: BLE001` view-boundary guards.
- **C3 — Headless smoke stays green**: `tests/gui_logic/test_gui_smoke.py` (full-app instantiate + navigate) and all `gui_logic` view smokes must still pass under xvfb/DISPLAY. The theme resolver must not crash when instantiated headlessly.
- **C4 — Cross-platform**: the font stack renders on both Windows and Linux (the two release targets). `_resolve_ui_family()` degrades to the Tk default if no preferred family is found (never crashes, never blank text).
- **C5 — Python 3.11; `uv run` gates**: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` all green after every task.
- **C6 — No new dependencies**: system fonts only (no Pillow-beyond-what's-there, no font packages). customtkinter's own theming is used.

## 5. Testing Strategy

- **T-1 — Theme module unit tests** (`tests/gui_logic/test_gui_theme.py`): palette constants exist and are valid hex; `_resolve_ui_family()` returns a non-empty family string (given a Tk root) and degrades gracefully; `system_font()`/the named helpers return `CTkFont` instances with the expected size/weight; spacing constants are ints. These are the Tk-free-ish testable core.
- **T-2 — Parity + smoke regression**: `test_gui_parity.py` and `test_gui_smoke.py` stay green — proves no input lost and the app still launches/navigates after restyling.
- **T-3 — Visual verification (manual, this machine)**: before/after screenshots on DISPLAY :1 for each view. The "before" is captured (`/tmp/claude-1000/gui_before.png`). Each restyling task produces an "after" screenshot the implementer inspects (a real head/face — i.e. a real rendered UI, not a crash) to confirm the polish landed. This is the "is it actually prettier" gate — recorded per task, judged by eye.
- **T-4 — No `("Arial"` remains**: a guard test (like M1's no-print guard) asserting no hardcoded `("Arial"` font tuple remains in `gui.py`/`gui_views/*.py` — every font goes through the theme module.

## 6. Milestones / Task shape (for the plan)

1. **Theme module** — `gui_theme.py` (palette, font resolver, spacing, apply) + unit tests + the no-Arial guard test (RED against current code).
2. **App shell + Build tab** — the largest view; restyle gui.py to the theme; before/after screenshot.
3. **Build view + Save browser** — restyle; screenshots.
4. **Mod manager + Settings + Wizard** — restyle; screenshots.
5. **Gate** — no-Arial guard green, parity + smoke green, all-views after-screenshots captured, gates + CI green.

## 7. Risks

- **R1 — Font family resolution needs a Tk root**: `tkinter.font.families()` requires a root window. Mitigation: lazy resolution called from `App.__init__` (a root exists by then); the unit test creates a root before calling the resolver; headless smoke has a root under xvfb.
- **R2 — customtkinter theming quirks**: per-widget `fg_color`/`text_color` is reliable; the JSON `set_default_color_theme` route can be finicky across ctk versions. Mitigation: prefer per-widget palette application (D-THEME-4); only use a JSON theme if it cleanly covers the widget set.
- **R3 — Restyling accidentally drops an input** (breaks GUI-1). Mitigation: `test_gui_parity.py` is the guard; run it after every view task.

## 8. Traceability

| Goal / feedback | Spec item |
|---|---|
| "not very pretty" / bare-bones | D1, THEME-1/3/4, VIEW-1..6 |
| "more common font for readability" | G2, D2, THEME-2 |
| centralize scattered fonts/colors | G3, §3.1, T-4 |
| polish all views | G4, VIEW-1..6 |
| don't break the working app | C1–C3, T-2, R3 |
