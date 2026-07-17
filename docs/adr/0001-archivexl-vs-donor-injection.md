# ADR 0001 — ArchiveXL resource patching vs. donor entity + binary injection

- **Status:** Accepted
- **Date:** 2026-07-17
- **Milestone:** M3 (ArchiveXL spike)
- **Deciders:** project owner + implementing agent
- **Supersedes/relates:** the "No AppearanceParts / inline components / donor NPC entity / npv-inject" design decisions in CLAUDE.md and `docs/superpowers/specs/2026-07-17-npv-build-2.0-design.md` §4.2.

## Context

npv-build's mod-assembly rests on two hand-built mechanisms the spec flagged as its most fragile:

1. **`npv-inject`** — a .NET 8 binary that injects the mesh-component array into the *cooked* `.app` (because the uncooked→cooked round-trip was historically believed lossy). It adds a .NET SDK dependency to every install.
2. **The donor NPC entity** — the `.ent` is a real cooked NPC (Judy/Thompson) with only its appearance list swapped, to inherit the ~101-component animation rig. Fragile across game patches (donor paths can move).

M3 tested two hypotheses to retire them, on **game patch 2.13 + ArchiveXL 1.14.0 + WolvenKit.CLI 8.19.0**:

- **H1:** WolvenKit.CLI can serialize→deserialize the cooked `.app` round-trip faithfully, making `npv-inject` unnecessary.
- **H2:** an ArchiveXL `.xl` resource patch can attach our appearance to a *stock* NPC's `.app` at load time, making the donor entity unnecessary.

## Evidence

### H1 — WolvenKit round-trip replaces npv-inject: **CONFIRMED**

- **Desk (T2):** extracted the npv-inject-produced cooked `.app` from the real M1 E2E build, `serialize`→`deserialize` round-tripped it with **exit 0, no errors**. Re-serialized diff vs. the original was 3 hunks, all WolvenKit-internal metadata (`CruidDict` handle-UID table, filename, timestamp) — **zero difference in component types, names, mesh/morph depot-path hashes, meshAppearance, or bind names**.
- **In-game (T4):** `zz_axl_spike_h1` spawned V, fully animated (no T-pose), face morphs applied, hair + clothing present.
- **Defect investigation:** the one reported in-game defect (overlapping eye colors) was root-caused to the **pre-existing `cc_selections` modded-eye-suppression gap** that the E2E NPV already had (visible in the original build log's "unresolved selection" warnings), **not** an H1 round-trip loss. Proof: the round-trip candidate and the npv-inject reference have **identical component populations** (1948 typed objects, 54 skinned-mesh refs each); the sole JSON diff is the semantically-irrelevant `CruidDict`. The round-trip drops nothing. Wrong piercings / missing tattoos are likewise pre-existing mapping-resolution gaps, out of scope for H1.
- **Verdict: H1 = YES.** WolvenKit 8.19 round-trip is a faithful functional equivalent of `npv-inject`.

### H2 — ArchiveXL patch replaces the donor entity: **FAILED as-built (not disproven)**

- **Desk (T1/T3):** ArchiveXL 1.14 resource patching (`resource: patch:`) supports appending appearances to a `.app` per the REDmodding wiki, and a live installed mod (`rm_acc_wrist_rolex.xl`) uses the exact `.app`→`.app` shape. Patch `.app` authored and packed with `.xl` + AMM lua targeting stock `judy.ent`.
- **In-game (T4):** `zz_axl_spike_h2` spawned **stock naked Judy, not V**. ArchiveXL logged loading `zz_axl_spike_h2.archive.xl` but produced **no `[ResourcePatch]` action** for our patch — the patch was a parsed no-op, so the appearance was never attached.
- **Likely cause:** the T1-flagged untested caveat — the patch `.app` was custom-pathed under `base\` (wiki says keep patch files *outside* `base`), and/or the `resource: patch:` declaration didn't match AXL 1.14's expected shape for a `.app` appearance patch. The file resolved (no "doesn't exist" error), so this is a patch-declaration/path issue, not a missing artifact.
- **Verdict: H2 = FAILED as-built.** The mechanism is real and used by other mods here, but this artifact did not apply. Reaching a true YES/NO needs a second iteration (move patch out of `base\`; match a known-working `.app`-patch example; re-test).

## Decision

**Adopt Branch A′ (partial): retire `npv-inject`; keep the donor entity for now.**

- **H1 confirmed → schedule npv-inject removal.** The WolvenKit round-trip replaces it faithfully. This deletes the .NET 8 dependency from the installer/runtime and removes `tools/npv-inject` + `_inject_components`.
- **H2 failed-as-built → keep the donor entity, log a follow-up.** Do not retire the donor mechanism on an unproven patch. Re-test H2 in a scoped second spike (H2-v2) before committing.

## Consequences

### Now (recorded, executed in M4/M5, not in this ADR)
- **M4/M5 backlog — retire npv-inject (Branch A′):**
  - Replace `wolvenkit.py::_inject_components` (the npv-inject subprocess call) with an in-process `serialize`→edit-JSON→`deserialize` step using the WolvenKit adapter (the exact mechanism T2 proved).
  - Remove `tools/npv-inject/` (.NET project) and its build step.
  - Drop the .NET SDK from `installer.py` dependency install + the GUI wizard's dependency check (spec GUI-2 already says ".NET only in branch B" — Branch A′ means .NET leaves the wizard).
  - Update `docs/legacy/SPEC-inject.md` status and CLAUDE.md's "npv-inject" architecture notes.
  - Regression-gate: a full real build using the round-trip path must spawn correctly in-game (same bar as this spike).
- **Keep** the donor entity, `config_editor.build_ent_from_donor`, and `data/donors/*.json` unchanged.

### Follow-up spike (H2-v2, unscheduled)
- Re-author the H2 patch with the `.app` outside `base\`, cross-referenced against `rm_acc_wrist_rolex.xl`'s working `.app`-patch syntax; re-test in-game. If it applies, H2 graduates and the donor entity can also be retired (full Branch A) — a larger simplification. If it fails again with a root cause, record H2 = NO.

## Validity bound

All results are for **game patch 2.13 + ArchiveXL 1.14.0 + WolvenKit.CLI 8.19.0**. The round-trip fidelity (H1) and resource-patching semantics (H2) must be **re-confirmed after the game updates to 2.3x** (ties to M2 Task 7's gate). Do not treat H1's "retire npv-inject" as validated on a newer patch until a post-update real build passes in-game.

## Spike artifact cleanup

The `zz_axl_spike_*` files installed in the game dir for T4 are removed in M3 T5 (tracked in `/tmp/claude-1000/axl_spike/installed_files.txt`). Research log: `docs/research/2026-07-17-archivexl-spike-notes.md`.
