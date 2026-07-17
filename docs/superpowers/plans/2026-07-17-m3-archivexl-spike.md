# M3 — ArchiveXL Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer, with in-game evidence, whether npv-build's two most fragile subsystems can be retired — the `npv-inject` .NET binary injector and the donor-NPC entity hack — and record the decision as an ADR that fixes M4's scope (spec AX-1..5).

**Architecture:** This is a SPIKE, not a feature build: throwaway artifacts, permanent knowledge. Two independent hypotheses, tested separately so a partial win still simplifies the pipeline:
- **H1 (replaces npv-inject):** WolvenKit.CLI can `deserialize` a JSON-authored .app (with the full inlined component array) into a valid cooked .app — no binary injection needed.
- **H2 (replaces the donor .ent):** an ArchiveXL `.xl` resource patch can attach our appearance to a **stock** NPC's .app/.ent at load time, so AMM spawns the stock entity with our appearance — no authored donor entity needed.

Decision matrix → ADR: H1∧H2 = Branch A (retire both); H1 only = Branch A′ (retire npv-inject, keep donor); neither = Branch B (keep current design).

**Tech Stack:** WolvenKit.CLI (serialize/deserialize/pack), ArchiveXL `.xl` YAML, AMM lua, the M1 E2E build's artifacts as donor material. No production npv_build code changes in this plan (except the final ADR + spec notes).

## Ground Truth (measured on this machine, 2026-07-17)

- Game: patch 2.13 install at `~/.local/share/Steam/steamapps/common/Cyberpunk 2077`.
- Runtime mods LIVE in that install: **ArchiveXL** (DLL dated 2026-01-28), TweakXL, Codeware, red4ext, CET, **AMM**, Appearance Creator Mod, npv_dumper. Other installed mods already ship `.xl` files (`AMM_PlayerBodyTag.xl`, `Adshield_Harness_Top.xl`) — ArchiveXL loading demonstrably works here.
- A complete working NPV mod exists from the M1 gate: `/tmp/claude-1000/npv_e2e_out` (packed archive `e2e_test_v_244d1527.archive`, AMM lua, plus uncooked sources under `source/`). Its `.app`/`.ent`/meshes are the spike's raw material. If that tmp dir has been cleaned, regenerate with one `uv run npv-build <QuickSave-1 sav.dat> "E2E Test V" --output <dir>` run (~13 min).
- **Caveat recorded up front:** the spike runs on patch 2.13 + the installed ArchiveXL version. Resource-patching semantics on 2.3x/latest ArchiveXL must be re-confirmed after the game updates (ties to M2 Task 7); the ADR must state this validity bound.

## Global Constraints

- **Timebox:** the whole spike is ≤ 2 working sessions of effort (spec AX-1 says ≤ 1 week; we are far under). If an hypothesis hits a wall twice in a row (two distinct root-caused failures), stop iterating and record the failure as evidence — a spike that ends in "no" is a successful spike.
- **In-game verification requires the user** (launch game, spawn via AMM, judge visually). Every in-game step is a user-assisted gate: prepare everything, give the user a one-screen checklist, wait.
- No changes to `npv_build/` production code. Spike artifacts live in a scratch dir (`/tmp/claude-1000/axl_spike/`) and installed mods go into the game's `archive/pc/mod/` with the prefix `zz_axl_spike_` so they sort last and are trivially removable.
- No CDPR bytes in the repo: spike notes/ADR may contain paths, JSON key names, and YAML, never asset dumps.
- Every game-dir install/uninstall of spike files is logged in the notes file so cleanup is exact. Full cleanup (remove all `zz_axl_spike_*` files) is part of Task 5, verified by `ls`.
- AX-2 success criteria (both hypotheses): NPV spawns via AMM, full animation (no T-pose), head morphs + clothing render correctly, survives a game restart.

## Plan Roadmap

Plan 4 of 7. T1 (desk research) → T2 (H1 artifact) and T3 (H2 artifact) independently → T4 (in-game gate, user-assisted, tests both) → T5 (ADR + cleanup). M3 can run before, during, or after M2 execution — no code dependency (M2's WolvenKit 8.19 bump changes the CLI used here; note in results which WolvenKit version the spike used).

---

### Task 1: Desk research + spike notes scaffold

**Files:**
- Create: `docs/research/2026-07-17-archivexl-spike-notes.md` (running log; committed)

- [ ] **Step 1:** Determine the installed ArchiveXL version: check `red4ext/plugins/ArchiveXL/` for a version resource or changelog file; if absent, note the DLL date (2026-01-28) and find the matching release on `github.com/psiberx/cp2077-archive-xl/releases` (WebSearch/WebFetch) for a game-2.13-compatible line. Record: version, and whether **resource patching** (`resource:` / patching section in .xl) is supported in that version per the release notes / wiki.
- [ ] **Step 2:** Capture the exact `.xl` resource-patching syntax from the REDmodding wiki (`wiki.redmodding.org` ArchiveXL pages) into the notes file: how to declare a patch target (.app appearance append), constraints (cooked vs uncooked, appearance name collisions), and one worked example from an existing mod if the wiki shows one. Also skim one of the INSTALLED `.xl` files (`archive/pc/mod/AMM_PlayerBodyTag.xl`) as a live syntax sample — quote it in the notes (it's YAML config, not CDPR assets).
- [ ] **Step 3:** Pick the H2 patch target: a stock NPC whose entity AMM already lists and whose body rig matches the E2E NPV (pwa → Judy per `data/donors/2.13.json` — reuse the donor table's depot paths as the target picker). Record target `.app`/`.ent` depot paths in the notes.
- [ ] **Step 4:** Commit — `git add docs/research/ && git commit -m "docs(spike): ArchiveXL research notes scaffold (M3/T1)"`

**Exit:** notes file answers: installed AXL version, resource patching available yes/no (if NO on this version: record whether a newer AXL still supporting game 2.13 has it; if resource patching is simply unavailable for 2.13, H2 is BLOCKED-BY-ENVIRONMENT — record and let H1 proceed; H2 then re-runs after the game update, folded into M2/T7's gate).

---

### Task 2: H1 artifact — cooked .app via WolvenKit deserialize (no npv-inject)

**Files:**
- Scratch: `/tmp/claude-1000/axl_spike/h1/`
- Notes: append results to the research notes file

The current pipeline authors an uncooked .app template, then `npv-inject` (.NET) injects the component array into the COOKED .app binary. H1 asks: is that still necessary, or can WolvenKit.CLI round-trip it?

- [ ] **Step 1:** Recover the inputs from the E2E build: the final component specs (`npv_components.json` in the e2e output), the authored .app (uncooked, under `source/`), and the npv-inject-produced cooked .app from inside the packed archive (unpack with `wk.extract`/`unbundle` from `/tmp/claude-1000/npv_e2e_out/archive/pc/mod/e2e_test_v_244d1527.archive` into the scratch dir). Read `npv_build/wolvenkit.py`'s `_inject_components` + `docs/legacy/SPEC-inject.md` first to understand exactly WHAT npv-inject writes (which chunks/fields) — record the summary in the notes; this defines what "equivalent output" means.
- [ ] **Step 2:** Produce the H1 candidate: serialize the npv-inject-produced cooked .app to JSON (`wk.serialize`), confirm the components are visible in JSON, then `wk.deserialize` that JSON back to a cooked .app in a fresh dir. If deserialize errors: that's a data point — record the exact error, then try the harder variant: serialize the PRE-injection template .app, add the component array in JSON (mirroring what npv-inject does, per Step 1's analysis), deserialize. Two root-caused failures → H1 = NO, record and stop.
- [ ] **Step 3:** Compare candidate vs npv-inject output: `wk.serialize` both and diff the JSON (`diff <(jq -S . a.json) <(jq -S . b.json)`) — structural equality modulo irrelevant metadata is a PASS-pending-game-check. Byte-level differences alone are fine if JSON-equal.
- [ ] **Step 4:** Build the installable H1 test mod: replace the .app inside a copy of the e2e mod's source tree with the H1 candidate, `wk.pack` to `zz_axl_spike_h1.archive`, copy to the game's `archive/pc/mod/` together with a RENAMED copy of the AMM lua (new unique_identifier `zz_axl_spike_h1`, entity_path unchanged) so it appears as a separate AMM entry. Log installed files in the notes.
- [ ] **Step 5:** Append H1 desk results to notes; commit notes.

**Exit:** either `zz_axl_spike_h1.archive` installed and awaiting the in-game gate, or H1 recorded as NO with two root-caused failures.

---

### Task 3: H2 artifact — ArchiveXL resource patch onto a stock NPC (no donor .ent)

**Files:**
- Scratch: `/tmp/claude-1000/axl_spike/h2/`
- Notes: append results

Blocked-by-environment short-circuit: if T1 found resource patching unavailable on this install, skip to writing that in the notes and mark H2 DEFERRED (re-test post-game-update); do not fake it.

- [ ] **Step 1:** Author a minimal mod that adds ONE new appearance to the stock target NPC's .app via `.xl` patch, per T1's captured syntax. The appearance definition lives in OUR own .app file (from the e2e sources — the appearance chunk referencing our meshes); the `.xl` declares the patch attaching it to the stock .app. Pack our .app + meshes as `zz_axl_spike_h2.archive` + `zz_axl_spike_h2.archive.xl` (match the naming convention of the installed examples like `Adshield_Harness_Top.xl`).
- [ ] **Step 2:** AMM lua for H2: entity_path = the STOCK NPC's .ent depot path, appearance = our patched-in appearance name, unique_identifier `zz_axl_spike_h2`. (Read the wiki's AMM-custom-NPC page captured in T1 for the exact lua fields; the e2e build's generated lua is the template.)
- [ ] **Step 3:** Static validation: `wk.serialize` our .app candidate (valid JSON round-trip), YAML-lint the `.xl` (`uv run python -c "import yaml, sys; yaml.safe_load(open('...'))"` — py7zr's env may lack pyyaml; if so `uvx --from pyyaml python ...` or plain visual check against the live samples), install files into the game dir, log them.
- [ ] **Step 4:** Append H2 desk results; commit notes.

**Exit:** H2 test mod installed awaiting the in-game gate, or H2 recorded DEFERRED/NO with reasons.

---

### Task 4: In-game verification — USER-ASSISTED GATE

- [ ] **Step 1:** Prepare and present the user a single checklist message:
  1. Launch Cyberpunk 2077 (normal modded launch), load any save.
  2. Open AMM → Spawn → look for entries `zz_axl_spike_h1` and/or `zz_axl_spike_h2`.
  3. Spawn each. For each, check: spawns at all / correct face (morphs) / correct hair + clothing / animates and follows idle behavior (NOT frozen in T-pose) / no missing-mesh checkerboard.
  4. Quit the game fully, relaunch, spawn again (survives restart).
  5. Report what you saw per entry (screenshots welcome).
- [ ] **Step 2:** WAIT for the user's report. Do not proceed on assumption. If a hypothesis fails in-game: one root-cause + fix iteration is in-budget (adjust artifact, ask for a re-test); a second in-game failure = NO for that hypothesis.
- [ ] **Step 3:** Record verbatim user observations in the notes; commit.

**Exit:** H1 and H2 each carry an evidenced verdict: YES / NO / DEFERRED(environment).

---

### Task 5: ADR, decision, cleanup (AX-3/4/5)

**Files:**
- Create: `docs/adr/0001-archivexl-vs-donor-injection.md`
- Modify: `docs/superpowers/specs/2026-07-17-npv-build-2.0-design.md` (AX outcome note in §4.2 — one paragraph, not a rewrite)

- [ ] **Step 1:** Write the ADR: context (why donor+injector exist), the two hypotheses, evidence (desk + in-game, with the notes file linked), decision per the matrix (A / A′ / B / partially-deferred), consequences for M4 scope (what gets deleted, what gets kept, what re-tests after the 2.3x game update), validity bound (patch 2.13 + tested AXL/WolvenKit versions).
- [ ] **Step 2:** Update the spec's §4.2 with the outcome reference; if Branch A or A′: add explicit M4 backlog lines (retire `tools/npv-inject/`, remove `_inject_components`, drop .NET from installer/deps — as M4 tasks, NOT done now).
- [ ] **Step 3:** Cleanup: remove every logged `zz_axl_spike_*` file from the game dir; verify with `ls "$GD/archive/pc/mod/" | grep zz_axl_spike` → empty. The user may ask to keep a working spike NPV — if so, note it and leave it, but record that it's unsupported scratch output.
- [ ] **Step 4:** Full gates (`uv run pytest -q && uv run ruff check . && uv run ruff format --check .` — should be trivially green, no production code touched), commit ADR + spec note + final notes, push.

**Exit:** ADR merged; M4's scope is now determined; game dir clean.

---

## Exit Criteria (spec M3)

- AX-1: spike executed within timebox, on real game + real AMM.
- AX-2: success criteria applied via the user's in-game checklist, evidence recorded.
- AX-3/4: branch decision (A / A′ / B) made — or explicitly partially-deferred to post-game-update where the environment blocked a hypothesis, with the re-test folded into M2/T7's gate.
- AX-5: ADR committed at `docs/adr/0001-archivexl-vs-donor-injection.md`; spec updated.
