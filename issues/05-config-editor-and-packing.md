# Config Editor & Mod Packing

## What to build
Implement the in-process Config Editor to stitch everything together. It will load the cached template JSON, inject the asset paths and numeric morph weights from `asset_paths.json`, and substitute all internal identifiers (entity record name, appearance name, archive name, etc.) with the generated Mod ID. Finally, run WolvenKit `convert -d` and `pack` to output the final `.archive`, replacing the dummy from Issue 1.

## Acceptance criteria
- [ ] Config Editor correctly updates the `.app` and `.ent` JSON with asset paths and morph weights.
- [ ] Every internal identifier is successfully scoped with the Mod ID suffix.
- [ ] WolvenKit `convert -d` turns the modified JSONs back into binary `.ent`/`.app` files.
- [ ] WolvenKit `pack` runs successfully to produce the fully assembled `<mod-id>.archive` in the correct output directory.
- [ ] The final output successfully completes the end-to-end Mod package specified in v1.

## Blocked by
- issues/04-wolvenkit-automation.md