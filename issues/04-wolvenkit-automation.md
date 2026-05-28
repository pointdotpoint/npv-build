# WolvenKit Automation: Template Cache & Uncooking

## What to build
Implement template resolution to prepare the base files required to assemble the mod. The Orchestrator must validate the WolvenKit CLI version at startup. The process will resolve the donor paths from `donors/<patch>.json`, check the local Template cache, and if missing, invoke WolvenKit `uncook` and `convert -s` against `--game-dir` to populate the cache with base `.app.json` and `.ent.json`.

## Acceptance criteria
- [ ] Orchestrator aborts if WolvenKit CLI is missing or mismatched.
- [ ] `donors/<patch>.json` is used to look up the correct base game files for the body rig.
- [ ] Checks the correct Template cache directory (respecting `--template-cache` and OS conventions).
- [ ] Executes WolvenKit `uncook` and `convert -s` when cache is missed, storing the resulting JSON in the cache.
- [ ] Respects the `--clear-cache` flag to wipe the Template cache before running.
- [ ] Emits `UncookFailedError` with CLI stderr if uncooking fails.

## Blocked by
- issues/03-mapping-and-asset-resolution.md