# Basic E2E Scaffolding & AMM Lua Generation

## What to build
Set up the CLI orchestrator to handle the standard invocation, validate arguments (`--output`, `--game-dir`, etc.), and persist user configuration. Establish the module sequence scaffolding. Implement the AMM Lua Generator to output a valid standalone spawnable NPC `.lua` file using a hardcoded Mod ID and dummy `.archive` path, generating the required partial mirror install tree in the target output directory.

## Acceptance criteria
- [ ] CLI accepts `npv-build <sav.dat> "<NPV name>" --output <dir>` and optional flags.
- [ ] User config (`config.toml`) is created on first run and reads/persists `--game-dir`.
- [ ] Orchestrator runs modules in sequence and handles basic error tagging.
- [ ] Mod package layout is correctly produced in the `--output` directory (e.g., `archive/pc/mod/<mod-id>.archive` and `bin/x64/.../<mod-id>.lua`).
- [ ] A valid `.lua` file for a standalone spawnable NPC is generated.
- [ ] A dummy/empty `.archive` file is generated.

## Blocked by
None - can start immediately