# Photo Mode registration for npv-build — design

**Date:** 2026-07-17
**Status:** Superseded by `docs/specs/complete-photomode-support.md` on 2026-07-25.

This document records the original YAML-only design and fallback discussion.
Do not implement from it. The replacement specification incorporates the
confirmed PhotoMode-EX registration failure, thumbnail assets, localization,
ArchiveXL scope, and full `.ent`/`.app` conversion.

## Goal

Every NPV build gains a second, independent registration: an entry for **Photomode NPCs Extended** (Nexus 18837, by xbaebsae; runtime dependency **PhotoMode-EX**, Nexus 18839, by psiberx). The result is that a single build makes V both **AMM-spawnable** (unchanged, existing behavior) and **selectable in the base game's Photo Mode character picker**, with no extra steps for the user.

## Non-goals

- Not replacing or altering the AMM path. AMM emission is untouched; existing builds keep working byte-for-byte.
- Not shipping our own copy of Photomode NPCs Extended / PhotoMode-EX. These are user-installed runtime dependencies, documented like ArchiveXL/TweakXL/Codeware already are.
- Not solving in-game photo-mode facial expression *authoring* (blend spaces, expression sliders). Scope is "V shows up, is posable, and animates without T-posing."

## Background research

Photomode NPCs Extended registers a puppet via a **TweakXL `Character` record** whose `persistentName` is `PhotomodePuppet`, plus an ArchiveXL `.archive.xl` control file, plus a dedicated **photomode-flavored `.ent`/`.app` variant**. The variant differs from an AMM entity in two ways that matter:

1. The **animgraph** is swapped to the photomode animation rig (`npc-animations` family) so the puppet responds to Photo Mode's pose system instead of AI locomotion.
2. The **facial-animation components** (`man_face_base_animations` / `face_rig`) are swapped for the photomode-compatible variants so the face animates rather than freezing.

The registration yaml is trivial and certain; the `.ent`/`.app` variant is the genuine unknown. This mirrors the WolvenKit "Add Photomode Files" wizard, which performs the same animgraph/face-component swap.

Sources: the REDmodding "NPV to Photomode" documentation and the Photomode NPCs Extended / PhotoMode-EX mod pages. No CDPR bytes are copied — all assets are uncooked from the user's own install at build time, as everywhere else in the pipeline.

## Architecture — parallel the existing AMM emission

`orchestrator.write_amm_lua()` (`npv_build/orchestrator.py:33`) is the model. The feature adds a sibling emitter, `write_photomode_files()`, driven from the same data the AMM lua already uses (`mod_id`, display name, body rig, `.ent` depot path, `asset_paths`). It is called unconditionally alongside `write_amm_lua()` — **both file sets are emitted on every build**. The two are file-disjoint and non-conflicting.

Per build, `write_photomode_files()` produces three artifacts into the mod's source tree:

### 1. TweakXL `Character` record (cheap, certain)

Written under the mod's TweakXL yaml path. Templated directly from build data:

```yaml
Character.<mod_id>_Photomode_Puppet:
  $type: Character
  entityTemplatePath: <ent depot path>
  displayName: <npv display name>
  persistentName: PhotomodePuppet
  attachmentSlots: [ AttachmentSlots.WeaponRight, AttachmentSlots.WeaponLeft ]
```

`entityTemplatePath` points at the **photomode variant `.ent`** when the spike succeeds (see below), or at the existing NPV `.ent` in the fallback mode. Backslash depot-path convention is preserved, matching all other authored paths.

### 2. `<mod_id>.archive.xl` (cheap, certain)

The ArchiveXL control file that loads the display-name resource and marks the entity animation-enabled, per the Photomode NPCs Extended convention.

### 3. Photomode `.ent`/`.app` variant (the spike — hard, uncertain)

A clone of the donor-based NPV entity with:
- the **animgraph** repointed to the photomode animation rig, and
- the **`.app`'s facial-animation components** swapped for the photomode-compatible variants.

Authored by patching the same donor entity the AMM path already uses (Judy for pwa, Thompson for pma), reusing the existing serialize → edit-JSON → deserialize round-trip mechanism (`npv_build/core/app_inject.py`). This is the only new *asset-authoring* work; everything else is templating.

## The spike-first plan, and its fallback (the honesty)

The `.ent`/`.app` variant is a real unknown. The feature is built spike-first and **gated on an in-game Photo Mode check**: the user spawns V in Photo Mode and confirms it appears, poses, and animates with no T-pose and a live face.

- **Spike succeeds** → the pipeline auto-generates the full photomode variant and the yaml points at it. The user gets working photo-mode V with no manual steps.
- **Spike fails** (component swap proves too fiddly to make reliable across body rigs) → fall back to **yaml + `.archive.xl` only, pointing at the existing NPV `.ent`**. This may partially work (puppet selectable and posable, but possibly without the photomode facial rig). It ships as a **documented "experimental" mode**, clearly labeled, rather than shipping something subtly broken and unlabeled.

The decision between the two branches is made by the human after the in-game check — not by the pipeline guessing.

## Guardrails

- **Additive only.** No change to `write_amm_lua()` or any existing output. The photomode files live in disjoint paths.
- **Dependencies documented.** ArchiveXL (≥ the floor Photomode NPCs Extended requires), TweakXL, Codeware, and PhotoMode-EX added to the mod's dependency notes / README, consistent with how AMM deps are already listed.
- **No CDPR bytes in repo.** The variant is uncooked from the user's install at build time.
- **Hard-fail policy preserved.** If the spike is enabled and variant authoring fails, the build fails loudly — it does not silently degrade to the fallback. The fallback is a deliberate, separately-selected mode, not an error path.

## Testing

- Unit: `write_photomode_files()` emits the three artifacts with correct templated values (mod_id, display name, `entityTemplatePath`, `persistentName: PhotomodePuppet`) — pure-function test, no WolvenKit needed, mirroring the AMM lua tests.
- Unit: fallback mode points `entityTemplatePath` at the NPV `.ent`; spike mode points it at the variant `.ent`.
- Integration (spike): variant `.ent`/`.app` round-trips through the serialize/deserialize mechanism and contains the swapped animgraph + face components.
- Manual gate: in-game Photo Mode check (the human's spike verdict) decides spike-vs-fallback shipping.

## Roadmap

Spec now. Execute as its own milestone **after** the current user-gated items: publish the v2.0.0 draft release and the npv-inject deletion (M5-T8). No dependency on either — sequenced, not blocked.
