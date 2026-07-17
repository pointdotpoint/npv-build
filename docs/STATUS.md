# npv-build 2.0 — Build Status

*Last updated 2026-07-17. Snapshot of the milestone effort tracked in `docs/superpowers/`.*

## Milestones

| Milestone | State | Notes |
|---|---|---|
| M0 — repo cleanup + tooling | ✅ merged | uv+hatchling+ruff, CI matrix ubuntu+windows |
| M1 — core foundation | ✅ merged | errors/cancel/proc/logging/platform + PipelineService (checkpoint/resume/cancel); CLI+GUI on core; 122 tests |
| M2 — patch currency | ✅ 7/8 merged, T7 gated | see below |
| M3 — ArchiveXL spike | ⏳ through T3; T4 awaits user in-game check | both hypotheses desk-pass |
| M4 — GUI overhaul | 📄 planned | `docs/superpowers/plans/2026-07-17-m4-gui-overhaul.md` |
| M5 — security + tests | 📄 spec only | not yet planned |
| M6 — release bundles | 📄 spec only | not yet planned |

Latest master: 170 tests passing, CI green both OSes.

## Blocked on the user (in-game actions)

### M2 Task 7 — decode current-patch (2.2–2.31) saves
**Why blocked:** every save on this machine is patch 2.13 (build 2310 / struct v3=195); the game install is pre-2.2. T7 must reverse-engineer the character-creation struct from a *real* current-patch save. None exists here and it cannot be synthesized without shipping a decoder that silently corrupts real saves.

**Unblock (you):**
1. Update Cyberpunk 2077 on Steam to the current patch.
2. Launch it once, create one new save (any character).
3. Tell the agent — it runs the runbook.

**First command the agent runs** (already written + verified on a 2.13 save):
```
uv run python scripts/t7_probe_new_save.py "<path to the new sav.dat>"
```
It reports the build number and whether v3 changed, then branches:
- v3 == 195 → register the build in `save_versions.json`, alias the decoder (fast path).
- v3 != 195 → author a new `_decode_cc_v<N>` by diffing against a 2.13 save; add a fixture + golden test.
Then `--mapping-report` against the updated game to author `data/mappings/2.3x.json` + `donors/2.3x.json`, then a full build + in-game spawn check.
Full runbook: `docs/superpowers/plans/2026-07-17-m2-patch-currency.md` Task 7.

Until then, unsupported builds **hard-fail** with a clear error (they don't mis-build).

### M3 Task 4 — in-game verification of the ArchiveXL spike
Two throwaway spike mods are installed in the game dir (all files prefixed `zz_axl_spike_`, listed in `/tmp/claude-1000/axl_spike/installed_files.txt` for exact cleanup at T5):
- `zz_axl_spike_h1` — WolvenKit-round-trip `.app` (tests whether npv-inject can be retired).
- `zz_axl_spike_h2` — ArchiveXL `.xl` patch onto stock `judy.app` (tests whether the donor entity can be retired).

**Unblock (you):** launch the game, open AMM → Spawn, spawn each `zz_axl_spike_*` entry, and report per entry: spawns / correct face / hair+clothing / animates-not-T-pose / no missing-mesh / survives a restart. Screenshots welcome. Result decides ADR 0001 (retire both / retire injector only / keep current design) and M4's scope.

## What's ready to run without the user

- **M4 execution** — plan is complete; needs the user only for the final CI push. Can start on request.
- **M3 T5** — writes the ADR once T4's in-game result is in.
