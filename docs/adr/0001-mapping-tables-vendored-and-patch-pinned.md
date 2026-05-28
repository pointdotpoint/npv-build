# ADR-0001: Mapping tables are vendored and patch-pinned

**Status:** Accepted
**Date:** 2026-05-22

## Context

The CC-option-ID → game-asset-path mapping is the correctness backbone of the
NPV automation tool: every NPV's appearance is determined by it. The mapping
is large (hundreds of head/eye/hair/cyberware entries), drifts when CDPR
patches the game (assets are renamed, moved, added, retired), and is currently
documented only in third-party sources (Redmodding Wiki cheat sheets,
NoraLee's NPV Part Picker).

Three feasible sources for this table were considered:

1. **Vendored JSON, hand-curated, versioned per game patch.**
2. **Runtime scraper that re-fetches from the wikis on demand.**
3. **Generated from uncooked base-game files via WolvenKit.**

A separate but coupled question is how the tool decides which mapping applies
to a given save: trust a user flag, ignore the issue, or read the game build
from the `sav.dat` header.

## Decision

We vendor the mapping table as JSON in-repo, one file per Cyberpunk 2077 patch
(e.g. `mappings/2.13.json`). The Save Parser reads the game build from the
`sav.dat` header. The Mapping Module performs a strict lookup against the
vendored set; a save whose patch has no vendored mapping is a hard error.

V1 source of truth for the table is the CC block of `sav.dat` only — salon
edits and other post-CC appearance state are deliberately out of scope (see
the `CC block` entry in `CONTEXT.md`).

## Consequences

**Positive**

- The tool is fully deterministic and offline: no live dependency on
  third-party wiki HTML or availability.
- Patch skew cannot silently produce broken NPVs — unsupported patches fail
  loudly with a clear error.
- Mapping changes are reviewable diffs in version control.

**Negative**

- Each new game patch requires a manual mapping update before the tool works
  for saves from that patch. Users on a freshly patched game are blocked until
  a mapping is published.
- Curation is labor-intensive and error-prone; transcription mistakes from the
  wiki produce wrong-but-plausible NPVs.

**Reversibility**

Moving later to option 3 (mapping generated from uncooked game files) remains
possible: the consumer contract is the JSON file on disk, so the producer can
be swapped without touching downstream modules. Option 2 (runtime scraping)
is explicitly rejected and not on the reversibility path.
