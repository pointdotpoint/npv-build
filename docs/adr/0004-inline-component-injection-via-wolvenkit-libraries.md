# ADR-0004: Inline component injection via WolvenKit libraries

**Status:** Proposed
**Date:** 2026-05-24

## Context

The current pipeline produces an empty `.app` file and a `npv_components.json`
spec, then asks the user to manually add ~15-20 mesh components in WolvenKit
GUI. This is the only manual step; eliminating it makes the tool fully
automated.

The manual step exists because of a misunderstanding of the boundary between
WolvenKit's CLI and its libraries. The CLI's `convert deserialize` command
reads JSON and writes CR2W binary, but the `Components` property on
`appearanceAppearanceDefinition` is marked `[REDProperty(IsIgnored = true)]`
— the JSON deserializer silently drops it. Components must live in the
`CompiledData` buffer (a `RedPackage`), which is cooked automatically by
`CR2WWriter.WriteFile()` when `Components` is populated **in memory**.

The GUI works because it creates component objects in memory, adds them to the
`Components` array, and calls `CR2WWriter.WriteFile()`. The JSON round-trip
path cannot do this — but a small C# program referencing the same libraries
can.

## Decision

Build a standalone .NET console tool (`npv-inject`) that:

1. Reads a cooked `.app` binary via `Red4ParserService`.
2. Reads `npv_components.json`.
3. Creates typed component instances (`entMorphTargetSkinnedMeshComponent`,
   `entSkinnedMeshComponent`, `entGarmentSkinnedMeshComponent`) in memory.
4. Adds them to `appearanceAppearanceDefinition.Components`.
5. Writes the file back with `CR2WWriter.WriteFile()`, which automatically
   cooks the `CompiledData` buffer.

The Python orchestrator calls this tool as a subprocess, the same way it
calls `WolvenKit.CLI`.

## Consequences

**Positive**

- The manual GUI step is eliminated. `npv-build` becomes fully automated.
- The tool uses the exact same code path as the GUI for component cooking —
  no reimplementation, no format guessing.
- The `.app` binary is identical to what the GUI would produce.

**Negative**

- Adds a .NET build dependency (the tool must be compiled or distributed as
  a self-contained binary).
- Couples to WolvenKit's internal library API, which has no stability
  guarantee. Pinned to the same WolvenKit version the project already
  requires.

**Alternatives considered**

- *Patch WolvenKit CLI to add an `inject-components` command.* More correct
  long-term, but requires upstreaming or maintaining a fork. The standalone
  tool is faster to ship and can be contributed upstream later.
- *JSON manipulation + `convert deserialize`.* Does not work — `IsIgnored`
  causes components to be silently dropped.
- *Binary patching of the `.app` file.* Fragile, version-dependent, and
  reimplements what `CR2WWriter` already does.
