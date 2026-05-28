# ADR-0002: No Blender in v1 — morph weights live in `.app`/`.ent`

**Status:** Accepted
**Date:** 2026-05-22
**Supersedes:** §3.4 of *Technical Implementation Specification: Cyberpunk
2077 NPV Automation* (the "Blender Automation Module")

## Context

The original spec routed mesh shaping through Blender: a headless `bpy` script
would load template `.blend` files containing base `.morphtarget` meshes,
apply shapekey values derived from CC settings, and export the deformed
meshes as `.fbx`/`.glb` for WolvenKit to re-import.

Examining the Cyberpunk 2077 character pipeline, head appearance is already
expressed declaratively in `.app`/`.ent` files via morphtarget references and
weight arrays. The engine blends these at runtime against the rigged base
head. Pre-deforming meshes externally and re-importing them as static
geometry:

- bypasses the runtime blending the engine is designed around,
- risks losing vertex order/rig binding required by the head morphtargets,
- introduces a `.blend`/`.fbx`/`.glb` round-trip with its own failure modes
  (Blender install, addon versions, headless export quirks),
- adds a module's worth of code and a heavy runtime dependency (Blender) for
  a problem the engine already solves.

## Decision

V1 does not invoke Blender. The Mapping Module emits morph weights as numeric
values in `asset_paths.json`; the WolvenKit Automation Module writes those
weights directly into the `.app`/`.ent` JSON before re-converting to binary.
All mesh deformation happens in-engine at NPV spawn time.

The system architecture loses one node: the Blender Automation Module is
removed, and the Mapping Module feeds the WolvenKit Automation Module
directly.

## Consequences

**Positive**

- One fewer external tool to install, version, and orchestrate.
- No `.fbx`/`.glb` intermediate format to debug.
- Morph behaviour at runtime matches what the player sees in CC, because
  it *is* the runtime blend.
- Smaller surface area for v1; faster to a working end-to-end pipeline.

**Negative**

- Any appearance combination that cannot be expressed as a weighted sum of
  existing morphtargets (e.g. a fused mesh required by a slot that accepts
  only a single morphtarget) is not reachable in v1. If we hit such a case
  we must either accept the limitation or reintroduce Blender narrowly for
  that asset class.
- We are tightly coupled to the `.app`/`.ent` schema for head morphs; if a
  game patch changes the schema, the WolvenKit module breaks rather than
  Blender masking the change.

**Reversibility**

Adding Blender back later is straightforward: insert it between Mapping and
WolvenKit, have it consume `asset_paths.json` and emit shaped meshes plus a
trimmed weight set. The `asset_paths.json` contract is the seam.
