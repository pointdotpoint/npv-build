# ADR-0003: Templates are uncooked on the user's machine, never vendored

**Status:** Accepted
**Date:** 2026-05-22
**Reverses:** an earlier interview decision that vendored uncooked
`.ent`/`.app` templates per patch alongside the Mapping tables.
**Relates to:** ADR-0001 (Mapping tables are vendored and patch-pinned).

## Context

The pipeline needs a starting `.ent`/`.app` pair per body rig (pwa, pma) to
specialise into an NPV. Three options for sourcing these were considered:

1. **Vendor the uncooked JSON in this repo, one set per patch.**
2. **Hand-author a minimal JSON skeleton with no CDPR-derived content.**
3. **Uncook on the user's machine, against the user's own game install,
   cached locally per patch.**

Option 1 was the initial choice for its zero-runtime-cost ergonomics. It
later collided with the project's license posture (ADR-pending in glossary,
"no CDPR-owned bytes ship in this repository or in any produced Mod
package"): uncooked `.ent`/`.app` JSON, even though textual, is a direct
translation of CDPR's game files, not original authorship. The two decisions
could not both hold.

Option 2 sidesteps the licensing issue but loses donor fidelity — we'd be
hand-authoring a JSON skeleton hoping it carries every field the engine
silently requires, with no way to validate short of in-game testing. Past
modding experience (and the donor-NPC concept of ADR-Q9 itself) suggests
this is brittle.

Option 3 preserves both the license stance and the donor-fidelity story:
the user already legitimately owns the game files; the tool simply executes
WolvenKit CLI's `uncook`/`convert -s` against them on first run.

## Decision

Templates are uncooked **on the user's machine**, on demand, against the
user's own legitimate game install, and **cached locally per game patch**
(default: `~/.cache/npv/templates/<patch>/...`). They are **not vendored in
this repository**.

What *is* vendored is the **donor specification** — a small JSON per patch
that names the base-game resource paths to uncook for each body rig
(`donors/<patch>.json`). The donor spec ships paths and metadata only, no
CDPR-derived binary or JSON content.

## Consequences

**Positive**

- The repository ships **no CDPR-owned bytes**, in any form, including
  JSON-translated forms. The license posture in `CONTEXT.md` holds without
  qualification.
- Templates always match the user's installed patch exactly — we no longer
  depend on the maintainer having re-uncooked between a patch dropping and
  a user trying to build.
- Aligns with WolvenKit's own distribution norm (the tool never bundles
  game bytes).

**Negative**

- First run on a given patch is slower: WolvenKit `uncook` against the
  base archive is not cheap. Cached afterwards.
- The tool now has a hard dependency on the user owning a legitimate
  Cyberpunk install at build time — not just at install time. This was
  already implicitly true (the resulting mod is useless without one), but
  the build-time coupling is new.
- Cache invalidation across patch updates is now a real concern; the cache
  is keyed by patch version (which we already read from the save header per
  ADR-0001), so the mechanism exists, but cache poisoning by a stale entry
  from a hand-edited cache is a possible support-ticket vector.

**Reversibility**

Re-introducing vendored templates would require a license-posture rewrite
in `CONTEXT.md` and a fresh evaluation of CDPR's modding-tools norms. Not
a code change — a policy change. The current arrangement is the reversibility
floor; we will not move further away from it.
