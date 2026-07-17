# npv-inject — Component Injection Tool Specification

**Version:** 1.0
**Date:** 2026-05-24
**Status:** Draft
**Depends on:** ADR-0004, SPEC.md §5.4
**Source:** WolvenKit library analysis (CR2WWriter, appearanceAppearanceDefinition,
RedTypeFactory)

## 1. Purpose

`npv-inject` is a .NET console tool that reads a cooked `.app` file, injects
mesh components from a JSON spec, and writes the result back as a valid cooked
`.app` binary. It replaces the manual WolvenKit GUI step described in the
project README.

## 2. Scope

### 2.1 In scope

- Read a cooked `.app` binary (CR2W format).
- Parse a component spec JSON file (`npv_components.json`).
- Create typed RED4 component instances in memory.
- Set all required properties: name, mesh/morphResource depot paths,
  meshAppearance, parentTransform.bindName, skinning.bindName.
- Add components to the first appearance definition's `Components` array.
- Write the modified `.app` back to disk via `CR2WWriter.WriteFile()`,
  which cooks the `CompiledData` buffer automatically.
- Exit 0 on success, non-zero on any failure with a diagnostic message
  on stderr.

### 2.2 Out of scope

- Creating `.app` files from scratch (the Python pipeline already does
  this via `build_app_template()` + `convert deserialize`).
- Modifying `.ent` files (unchanged — donor `.ent` works as-is).
- Archive packing (handled by existing `WolvenKit.CLI pack`).
- Any GUI.

## 3. Invocation

```
npv-inject <app-file> <components-json> [--appearance-index <N>] [--verbose]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `<app-file>` | Yes | Path to the cooked `.app` binary to modify. Modified in place. |
| `<components-json>` | Yes | Path to the component spec JSON. |
| `--appearance-index` | No | Zero-based index into the `appearances` array. Default: `0`. |
| `--verbose` | No | Print per-component progress to stdout. |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success — `.app` written with components injected. |
| 1 | Bad arguments (missing file, unreadable JSON, etc.). |
| 2 | `.app` parse failure (not a valid CR2W file, or not an `appearanceAppearanceResource`). |
| 3 | Component injection failure (unknown component type, invalid depot path). |
| 4 | Write failure (CR2WWriter error, disk full, permissions). |

## 4. Component spec format

The tool reads `npv_components.json`, which the Python pipeline already
produces. The format is unchanged:

```json
{
  "appearance_name": "my_v_abc123_appearance",
  "components": [
    {
      "type": "entMorphTargetSkinnedMeshComponent",
      "name": "MorphTargetSkinnedMesh7243",
      "mesh": "base\\characters\\head\\my_v_abc123_head.mesh",
      "meshAppearance": "01_ca_pale",
      "morphResource": "base\\characters\\head\\my_v_abc123_morphs.morphtarget",
      "bindTo": "root",
      "source": "baked head (face morphs applied)"
    },
    {
      "type": "entSkinnedMeshComponent",
      "name": "hair_mesh_0",
      "mesh": "base\\characters\\hair\\hh_073_wa__zara.mesh",
      "meshAppearance": "red",
      "bindTo": "root",
      "source": "modded hair"
    },
    {
      "type": "entGarmentSkinnedMeshComponent",
      "name": "garment_torso",
      "mesh": "base\\characters\\garment\\player_equipment\\torso\\t1_097_pwa_tank__corset.mesh",
      "meshAppearance": "default",
      "bindTo": "root",
      "source": "garment override"
    }
  ]
}
```

### Field semantics

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | One of: `entMorphTargetSkinnedMeshComponent`, `entSkinnedMeshComponent`, `entGarmentSkinnedMeshComponent`. Unknown types are a hard error. |
| `name` | Yes | Component name (`CName`). Must be unique within the appearance. |
| `mesh` | No | Depot path for the mesh resource. Set on `Mesh` (for `entSkinnedMeshComponent` / `entGarmentSkinnedMeshComponent`) or `Mesh` on morph components. Empty string is valid (morph components may derive the mesh from the morphtarget). |
| `meshAppearance` | Yes | Material variant name (`CName`). Controls skin tone, hair colour, etc. |
| `morphResource` | No | Depot path for the morphtarget resource. Only valid for `entMorphTargetSkinnedMeshComponent`. |
| `bindTo` | Yes | Skeleton bind name. Always `"root"` for NPV components. Applied to both `parentTransform.BindName` and `skinning.BindName`. |
| `source` | No | Human-readable label for diagnostics. Ignored by the tool. |

## 5. Implementation

### 5.1 Project structure

```
npv_project/
  tools/
    npv-inject/
      npv-inject.csproj        # .NET 8.0 console app
      Program.cs               # Entry point, arg parsing, orchestration
      ComponentInjector.cs     # Core injection logic
```

The `.csproj` references WolvenKit NuGet packages (or local project
references during development):

- `WolvenKit.RED4` — CR2W reader/writer, RED4 type system
- `WolvenKit.Common` — `IHashService`, serialization helpers
- `WolvenKit.Core` — archive interfaces, compression

### 5.2 Core algorithm

```
Program.Main(args):
    1. Parse arguments → (appPath, jsonPath, appearanceIndex, verbose)
    2. Read and parse components JSON → List<ComponentSpec>
    3. Read the .app binary:
         using var fs = File.OpenRead(appPath)
         using var reader = new CR2WReader(fs)
         reader.ReadFile(out var cr2w)
    4. Navigate to the target appearance:
         var resource = cr2w.RootChunk as appearanceAppearanceResource
         var appearance = resource.Appearances[appearanceIndex].Chunk
                          as appearanceAppearanceDefinition
    5. For each ComponentSpec:
         a. Instantiate the typed component via RedTypeManager.CreateRedType()
         b. Set properties:
              component.Name = spec.Name
              component.MeshAppearance = spec.MeshAppearance

              // Mesh depot path
              if (spec.Mesh is not empty)
                  component.Mesh = new CResourceAsyncReference<CMesh>(spec.Mesh)

              // MorphResource (only for entMorphTargetSkinnedMeshComponent)
              if (spec.MorphResource is not empty)
                  ((entMorphTargetSkinnedMeshComponent)component).MorphResource
                      = new CResourceAsyncReference<MorphTargetMesh>(spec.MorphResource)

              // Skeleton bindings
              var parentTransform = new entHardTransformBinding()
              parentTransform.BindName = spec.BindTo
              component.ParentTransform = new CHandle<entITransformBinding>(parentTransform)

              var skinning = new entSkinningBinding()
              skinning.BindName = spec.BindTo
              component.Skinning = new CHandle<entSkinningBinding>(skinning)

         c. Add to appearance:
              appearance.Components.Add(component)

    6. Write back:
         using var ws = File.Create(appPath)
         using var writer = new CR2WWriter(ws)
         writer.WriteFile(cr2w)
         // CR2WWriter automatically:
         //   - Runs appearanceAppearanceDefinitionPreProcessor
         //   - Serializes Components into CompiledData via RedPackageWriter
         //   - Writes valid cooked binary

    7. Exit 0, print summary to stdout if verbose.
```

### 5.3 Error handling

- Unknown component `type` → exit 3, message names the bad type.
- `.app` file is not `appearanceAppearanceResource` → exit 2.
- `appearanceIndex` out of range → exit 2.
- Duplicate component `name` within the appearance → exit 3, message names
  the duplicate.
- `CR2WReader` parse failure → exit 2 with the exception message.
- `CR2WWriter` write failure → exit 4.
- All errors go to stderr. Stdout is reserved for progress output.

### 5.4 Dependency initialization

WolvenKit's type system requires one-time initialization:

```csharp
// Register all RED4 types so CreateRedType() works
RedTypeManager.Initialize();

// HashService needed by CR2WReader for depot path resolution
var hashService = new HashService();
hashService.Load();
```

This happens once at startup before any file operations.

## 6. Integration with the Python pipeline

### 6.1 Orchestrator changes

The orchestrator (`orchestrator.py`) currently ends by writing
`npv_components.json` and `README_GUI_STEPS.md`. After this change:

1. The `.app` template is authored as JSON, converted to binary via
   `WolvenKit.CLI convert deserialize` (unchanged — produces a valid but
   empty `.app` binary).
2. **New step:** Call `npv-inject` to inject components into the cooked
   `.app` binary.
3. Call `WolvenKit.CLI pack` to produce the `.archive`.
4. `npv_components.json` and `README_GUI_STEPS.md` are **no longer
   produced** (or optionally kept for debugging with `-vv`).

### 6.2 Pipeline flow (after)

```
sav.dat ──► Save Parser ──► cc_settings.json
                            │
                            ▼
                          Mapping ──────────► asset_paths.json
                                                    │
                                                    ▼
                                            WolvenKit Automation
                                              │           │
                                      build .ent    build .app template
                                      (donor)       (empty components)
                                              │           │
                                              ▼           ▼
                                        convert -d    convert -d
                                        (cooked .ent) (cooked .app)
                                                          │
                                                          ▼
                                                    npv-inject    ◄── NEW
                                                    (inject components
                                                     into cooked .app)
                                                          │
                                                          ▼
                                                    WolvenKit pack
                                                          │
                                                          ▼
                                                    AMM Lua Generator
                                                          │
                                                          ▼
                                                    Mod package
```

### 6.3 Subprocess call

```python
def _inject_components(app_path: Path, components_json: Path, verbosity: int):
    cmd = [NPV_INJECT_BINARY, str(app_path), str(components_json)]
    if verbosity >= 1:
        cmd.append("--verbose")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise WolvenKitError(
            f"npv-inject failed (exit {result.returncode}): {result.stderr.strip()}"
        )
```

`NPV_INJECT_BINARY` resolution follows the same pattern as `CLI_BINARY`:
must be on `PATH`, version is not independently checked (it ships with
this project and is pinned to the WolvenKit library version).

## 7. Distribution

### 7.1 Build

```bash
cd tools/npv-inject
dotnet publish -c Release -r linux-x64 --self-contained true \
  -p:PublishSingleFile=true -o ../../dist/linux-x64/
```

Produces a single self-contained binary (~30-50 MB, includes .NET runtime
and WolvenKit libraries). No separate .NET install required on the user's
machine.

Platform targets: `linux-x64`, `win-x64`.

### 7.2 Bundling

The `npv-inject` binary is distributed alongside the Python package:

```
npv_project/
  dist/
    linux-x64/npv-inject
    win-x64/npv-inject.exe
```

The Python package's `pyproject.toml` includes these as data files. The
orchestrator resolves the binary path relative to the package installation.

Alternatively, users who have .NET 8+ installed can run from source:
`dotnet run --project tools/npv-inject -- <args>`.

## 8. Testing

### 8.1 Unit tests (C#)

- Round-trip test: create an empty `.app` via `build_app_template()` JSON →
  `convert -d` → binary → `npv-inject` with known components → read back
  → verify `Components` array has the right count, types, names, depot
  paths.
- Each component type is tested: `entMorphTargetSkinnedMeshComponent`,
  `entSkinnedMeshComponent`, `entGarmentSkinnedMeshComponent`.
- Error cases: bad JSON, missing `.app`, unknown component type, out-of-range
  appearance index.

### 8.2 Integration tests (Python)

- Extend `test_build_project.py`: after `build_project()`, call
  `_inject_components()` on the produced `.app`, then verify the binary is
  a valid CR2W file (read it back with `WolvenKit.CLI convert serialize`
  and check the output JSON has a non-empty `compiledData`).
- Golden-file comparison: the `compiledData` buffer for a known set of
  components should produce a stable binary (within WolvenKit's determinism
  bounds).

### 8.3 Manual validation

Unchanged from SPEC.md §12: in-game spawn via AMM is a release gate.

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| WolvenKit library API changes | Tool breaks on WolvenKit update | Pin to exact WolvenKit version; tool ships pre-compiled |
| `CompiledData` cooking logic changes | Produced `.app` invalid in-game | Integration test catches this; pinned WolvenKit version |
| Self-contained binary is large (~50 MB) | Download size | Acceptable — WolvenKit GUI itself is ~200 MB |
| .NET runtime conflicts on Windows | User has incompatible .NET | Self-contained publish includes its own runtime |
| `HashService.Load()` slow on first run | Startup latency (~2-3s) | Acceptable for a build tool; not interactive |

## 10. Future

- **Upstream contribution:** propose an `inject-components` command to
  WolvenKit CLI, eliminating the need for a standalone tool.
- **Direct library reference from Python:** if pythonnet or similar
  .NET-from-Python bridges mature, call the libraries directly without
  a subprocess.
- **Component validation:** warn if a depot path doesn't exist in the
  game archives (requires archive index access).
