# Save Parser Integration & Identity

## What to build
Integrate the pinned Save Parser library to read `sav.dat`. Extract the game patch version and the CC (Character Creation) block. Write `cc_settings.json` to the output directory for diagnostics. Compute the real, deterministic Mod ID (`<slug>_<hash>`) based strictly on the NPV name and the canonical JSON encoding of the CC settings.

## Acceptance criteria
- [ ] Save Parser library correctly extracts the game patch version and CC block from a valid `sav.dat`.
- [ ] Program hard-fails gracefully if the patch version cannot be read or the parser fails.
- [ ] `cc_settings.json` is correctly dumped into the output directory.
- [ ] Mod ID is deterministically generated from `(NPV name, CC settings)` and used for filenames.
- [ ] The generated AMM `.lua` and `.archive` from Issue 1 use the real computed Mod ID.

## Blocked by
- issues/01-basic-e2e-scaffolding.md