# Mapping and Asset Resolution

## What to build
Implement the Mapping module to translate the CC settings (body rig, head shape choices, hair style/color, skin tone) into concrete base-game asset paths and morph weights. The mappings are loaded from `mappings/<patch>.json`. The result is aggregated into `asset_paths.json` and saved to the output directory.

## Acceptance criteria
- [ ] Mapping table matching the save's patch version is successfully loaded.
- [ ] Hard-fails with `MappingNotFoundError` if no table is found.
- [ ] `asset_paths.json` is successfully produced with correctly resolved paths (mesh, morphtargets, materials), morph weights, and the chosen body rig (`pwa` or `pma`).
- [ ] Unknown CC options are aggregated into a single warning, not an error.

## Blocked by
- issues/02-save-parser-integration.md