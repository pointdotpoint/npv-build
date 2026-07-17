# npv-build — Improvement Report

*Generated 2026-07-17. Sources: full codebase analysis of this repository + online research into the current Cyberpunk 2077 modding ecosystem (patch 2.31, WolvenKit 8.19, ArchiveXL, AMM, NPV community tooling). All external claims are linked.*

---

## Executive Summary

npv-build is architecturally sound — a clean linear pipeline with good module separation and a well-decoupled GUI — but it has three strategic problems and a set of engineering-hygiene gaps:

1. **The tool targets a stale game patch.** The vendored data covers only patch 2.13 (save struct `v3=195`). The game is now on **2.31**, and patch 2.2 (Dec 2024) added 100+ character-creation options that the mapping table cannot resolve. For most current saves, the pipeline likely fails or silently produces wrong output — made worse by `detect_patch()` silently defaulting unknown builds to 2.13.
2. **Two of the project's hardest-won hacks may now be unnecessary.** ArchiveXL 1.5+ resource patching and Dynamic Appearances provide a sanctioned way to add appearances to entities at load time — potentially retiring both the donor-NPC entity hack and the `npv-inject` .NET binary injector.
3. **The two largest, most fragile modules are untested.** `wolvenkit.py` (960 LOC) and `part_resolver.py` (557 LOC) — about 26% of the codebase and the heart of mod assembly — have no direct tests, and there are no real save-file fixtures anywhere.

Additionally: no logging framework (109 bare `print()` calls), 45 broad `except Exception` sites that contradict the documented hard-fail policy, no subprocess timeouts, and real security gaps in the installer (zip-slip, unverified downloads that get executed).

---

## Part 1 — Codebase Assessment

### 1.1 Structure

- 18 modules, ~5,750 LOC in `npv_build/`; tests ~1,390 LOC across 13 files; plus `tools/npv-inject` (.NET 8) and `data/` tables.
- **Hotspots** (~58% of all code): `wolvenkit.py` (960), `gui.py` (929), `head_bake.py` (576), `part_resolver.py` (557), `mapping.py` (335).
- **Repo hygiene:** build artifacts are checked in alongside source (`my_v_mod/`, `latest_v_mod/`, `test_v_mod/`, `trial_out/`, `release_test/`, `external_v_01_mod/`, `app_verify/`), plus `venv/` and six overlapping spec documents at the root. Empty stubs: `npv_build/__init__.py`, `test.sav.dat`.

### 1.2 Code quality

| Issue | Evidence | Impact |
|---|---|---|
| No logging framework | 109 `print()` calls in 10 modules; zero `logging` usage | No log levels, no `--log-file`, GUI can't capture structured progress |
| Broad exception handling | 45 `except Exception` / bare `except:` sites; 20 in `part_resolver.py` alone, several silently swallowing (`part_resolver.py:287,372,452,472,525,549`; `wolvenkit.py:178,189,295,318`) | Directly contradicts the documented **hard-fail policy** — errors can degrade output silently |
| Bypassed subprocess adapter | CLAUDE.md says all WolvenKit calls go through `wk_cli.py`, but `part_resolver.py` (6 sites), `wolvenkit.py` (3), `blender_module.py`, and `installer.py` (4) call `subprocess.run` directly | Inconsistent error reporting; `WolvenKitError` structure only exists on one path |
| No subprocess timeouts | Zero `timeout=` arguments anywhere | A hung WolvenKit / Blender / dotnet / unrar process blocks the pipeline and the GUI worker thread forever |

Positive: no TODO/FIXME/HACK debt markers anywhere; GUI↔CLI coupling is clean (`gui.py` imports only `config` + `gui_backend`, running the pipeline through a worker layer rather than shelling out).

### 1.3 Test coverage

- **Tested:** save_parser, mapping, clothing, wk_cli, hair_mod_helper, head_bake, installer, project_writer, gui_backend, config_editor (template), byo_head, build_project.
- **Untested:** `save_format.py`, `config.py`, `part_resolver.py`, `blender_module.py`, `wolvenkit.py`, `gui.py`. `test_orchestrator.py` is a 14-line stub.
- **No real save-file fixtures** — save parsing is tested only against synthesized bytes; `test.sav.dat` is empty.

### 1.4 Robustness / UX

- Errors surface as prints + raised exceptions wrapped in broad excepts (`cli.py:135`).
- **No resumability**: a failure during Blender bake or final pack discards all prior (expensive) WolvenKit uncook work.
- `gui.py:549` hardcodes the Proton/Steam Linux save path; `gui.py:104` assumes a Steam layout.
- Dependency preflight (WolvenKit/Blender/.NET/npv-inject) lives in the GUI path (`gui_backend.check_dependencies` + `installer.py`); the CLI has weaker preflight.

### 1.5 Packaging

- `pyproject.toml` declares only `tomli`/`tomli-w` as runtime deps; GUI deps are an optional extra — reasonable. External tools (WolvenKit, Blender, .NET, unrar) are undeclared/unpinned; `wk_cli.check_version` is warn-only.
- No lockfile, no lint/format/type-check tooling configured.

### 1.6 Patch coupling (the big architectural risk)

- `save_versions.json` maps exactly **one** build: `{"2310": "2.13"}`.
- `detect_patch()` (`save_parser.py:97`) **silently defaults unknown builds to "2.13"** with only a print warning (`save_parser.py:109`). On a newer save this means wrong mapping/donor data — likely T-pose or wrong assets — with no hard failure.
- The CC parser hardcodes `v3=195` (`save_parser.py:42,183`) and hard-fails other layouts, so post-2.2 saves with a bumped struct version error out.
- Donor entities (Judy/Thompson) and `basegame_4_appearance.archive` are hardcoded per rig in `donors/2.13.json` with no fallback if CDPR moves them.

### 1.7 Security

| Finding | Location | Risk |
|---|---|---|
| Zip-slip: `extractall()` without member-path validation on downloaded archives | `installer.py:179,182` | Path traversal from a malicious/compromised archive |
| No checksum/signature verification on any download; dotnet-install scripts are downloaded then **executed** | `installer.py:37,66,162,165` | Compromised mirror or MITM (behind broken TLS) → arbitrary code execution |
| `.rar` handling shells out to `unrar x` from PATH into a temp dir with no path control | `hair_mod_helper.py:132` | Binary planting / extraction traversal |
| Game/mod paths passed to subprocesses without canonicalization | various | Low (no `shell=True`), but worth normalizing |

---

## Part 2 — External Research Findings

### 2.1 Game and tooling state (mid-2026)

- **Latest patch: 2.31** (July 2026) — AutoDrive/Photo Mode fixes, no CC or save-format changes. ([cyberpunk.net](https://www.cyberpunk.net/en/news/51794/patch-2-31))
- **Patch 2.2 (Dec 2024) expanded character creation** with 100+ new options (cyberware, makeup, eyes) and a randomizer. This is the last CC-relevant change and it postdates the vendored 2.13 tables. ([pushsquare.com](https://www.pushsquare.com/news/2024/12/cyberpunk-2077-patch-2-2-out-now-expands-character-creation-vehicle-customisation-photo-mode))
- **WolvenKit.CLI 8.19.0** (July 2026): mesh import now adds bones correctly; `entAnimatedComponent` support. Repo targets 8.18.x. ([GitHub release](https://github.com/WolvenKit/WolvenKit/releases/tag/8.19.0), [NuGet](https://www.nuget.org/packages/WolvenKit.CLI))
- *Uncertain:* the exact CC struct version (`v3`) on 2.3 saves could not be confirmed online — needs empirical testing against a current save.

### 2.2 ArchiveXL could replace the donor-entity + binary-injection design

- **ArchiveXL 1.5+ resource patching** adds appearances from your own `.app`/`.ent` onto an existing NPC file at load time — no donor entity, no binary edits of cooked files. This is the sanctioned mechanism for exactly npv-build's use case. ([psiberx/cp2077-archive-xl](https://github.com/psiberx/cp2077-archive-xl), [REDmodding wiki](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators-theory/core-mods-explained/archivexl))
- **Dynamic Appearances** (`DynamicAppearance` visualTag) let one template appearance interpolate variants instead of hand-managed per-variant component arrays. ([wiki guide](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators/modding-guides/items-equipment/adding-new-items/archivexl-dynamic-appearances))
- Codeware/RED4ext are not needed here — AMM already handles spawning.

### 2.3 AMM

- Current line **v2.2.4+**; custom NPCs register via a `.lua` descriptor (modder name, unique identifier, appearances array). ([release notes](https://www.cyberpunk2077mod.com/appearance-menu-mod-v2-2-4/), [wiki: AMM custom NPCs](https://wiki.redmodding.org/cyberpunk-2077-modding/modding-guides/npcs/amm-custom-npcs))
- **Appearance Creator Mod** exports AMM-readable appearance files edited in-game — a possible alternative capture path alongside save parsing and the CET dumper. ([Nexus #10795](https://www.nexusmods.com/cyberpunk2077/mods/10795))

### 2.4 Prior art

- **NPV is now a documented first-class modding path** with a wiki section and a full community tutorial (NoraLeeDoes). The canonical manual workflow uses a WolvenKit template project with frame-matched `.app`/`.ent` pairs from "NPV Resources" — the closest thing to a community spec for what npv-build automates. ([wiki: NPV guide](https://wiki.redmodding.org/cyberpunk-2077-modding/modding-guides/npcs/npv-v-as-custom-npc/npv-creating-a-custom-npc), [tutorial](https://noraleedoes.neocities.org/npv/tut/pg00))
- The wiki documents **adding multiple appearances to one NPV** — a feature npv-build lacks (single appearance per build). ([wiki page](https://wiki.redmodding.org/cyberpunk-2077-modding/modding-guides/npcs/npv-v-as-custom-npc/how-to-add-a-new-appearance-to-an-npv))
- **Photomode NPCs Extended** (200+ prebuilt NPCs) is the ecosystem npv-build output plugs into. ([Nexus #18837](https://www.nexusmods.com/cyberpunk2077/mods/18837))
- **Save tooling:** WolvenKit/CyberCAT (C#) exports V's appearance as a `.v2preset` — a higher-level data source worth evaluating; PixelRick/CyberpunkSaveEditor (this repo's ported source) remains the reference for raw parsing. No maintained third-party Python parser surfaced. ([CyberCAT](https://github.com/WolvenKit/CyberCAT), [CyberpunkSaveEditor](https://github.com/PixelRick/CyberpunkSaveEditor))

### 2.5 Python tooling (2026 consensus)

`uv` (lockfile, `--locked` in CI) + `ruff` (lint/format) + `ty` (type check) + hatchling backend; `typer`/`rich` for CLI UX; checkpoint-after-each-stage for pipeline resumability. ([modern tooling overview](https://blog.rajpoot.dev/posts/python/modern-python-tooling-uv-ruff-2026/), [state of packaging 2026](https://repoforge.io/blog/posts/the-state-of-python-packaging-in-2026/))

### 2.6 Blender / morphtarget round-trip pitfalls

- **Known WolvenKit bug:** glTF→`.morphtarget` import historically keeps only the Basis shape key ([WolvenKit#849](https://github.com/WolvenKit/WolvenKit/issues/849)). If `head_bake` needs multiple shape keys to survive the round-trip, verify against 8.19.
- Recompute normals on Basis before glTF export and strip custom split normals — shape-key exports can bake the last-edited shape's normals. ([wiki: morphtargets](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators-theory/3d-modelling/morphtargets), [glTF-Blender-IO#375](https://github.com/KhronosGroup/glTF-Blender-IO/issues/375))
- Morphtarget I/O requires WolvenKit ≥ 8.9.1 and is still flagged experimental.

---

## Part 3 — Prioritized Recommendations

### P0 — Correctness for current players

1. **Support patch 2.2/2.3 saves.** Add save-build entries for post-2.13 builds, determine the current CC struct version empirically from a 2.3 save, and author a `2.3x` mapping/donor table. Until then, most users' saves are unusable or mis-mapped.
2. **Make unknown patches hard-fail.** Replace the silent 2.13 default in `detect_patch()` (`save_parser.py:97-110`) with an error naming the detected build and supported versions. This matches the project's own hard-fail policy and prevents T-pose mystery bugs.
3. **Bump WolvenKit.CLI target to 8.19** and validate the morphtarget multi-shape-key round-trip against issue #849.

### P1 — Architecture

4. **Spike ArchiveXL resource patching / Dynamic Appearances.** If a `.xl` file can attach appearances to an entity at load time, both the donor-entity hack and the `npv-inject` .NET injector can potentially be retired — deleting the most fragile, patch-sensitive parts of the pipeline. Time-boxed prototype recommended before committing.
5. **Add stage checkpointing.** Persist per-stage outputs (uncook, bake, author, inject, pack) so a late-stage failure doesn't discard 10+ minutes of uncook work; `--resume` reuses valid checkpoints.
6. **Multi-appearance NPVs.** The community workflow supports several appearances per NPV; npv-build could accept multiple saves/outfits into one mod.

### P2 — Engineering hygiene

7. **Adopt `logging`** (replace 109 prints), with `-v` mapping to levels and a `--log-file` option; the GUI worker consumes log records instead of stdout.
8. **Enforce the hard-fail policy:** audit the 45 broad excepts (start with `part_resolver.py`'s 20); narrow or re-raise; nothing silently swallows.
9. **Route all subprocess calls through adapters** (`wk_cli.py` pattern) and add timeouts to every call so hung tools can't wedge the GUI.
10. **Test the untested core:** `wolvenkit.py`, `part_resolver.py`, `save_format.py` — plus at least one real (anonymized) save-file fixture; flesh out the orchestrator test stub.
11. **Security fixes:** validate archive member paths before extraction (`installer.py:179,182`), verify checksums on all downloads (especially the executed dotnet-install scripts), pin/verify `unrar` usage.
12. **Repo & packaging cleanup:** gitignore build-artifact directories and `venv/`, consolidate the six root spec docs, adopt `uv` + `ruff` + a lockfile, and consider `typer`/`rich` for CLI UX.

---

## Suggested sequencing

1. P0 items 1–2 (patch support + hard-fail) — unblocks current users.
2. P2 items 7–9 (logging, excepts, subprocess adapter+timeouts) — cheap, makes everything after it debuggable.
3. P1 item 4 (ArchiveXL spike) — outcome decides whether `npv-inject` and donor logic get maintained or deleted.
4. Remaining P1/P2 in order of appetite.
