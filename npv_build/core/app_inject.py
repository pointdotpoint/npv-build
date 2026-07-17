"""Pure-Python component injection via WolvenKit JSON round-trip.

Replaces the .NET `npv-inject` tool (`tools/npv-inject/ComponentInjector.cs`
+ `Program.cs`) with the equivalent operation expressed directly in
WolvenKit's serialized JSON representation: serialize the cooked `.app` to
JSON, append typed component objects to `appearances[0].Data.components`,
deserialize back to a cooked `.app` binary.

Why this works (see docs/research/2026-07-17-archivexl-spike-notes.md H1,
and the Task 7 desk-diff that validated this module): WolvenKit's
`convert deserialize` regenerates the cooked `compiledData` buffer (and its
internal `CruidDict`/`Chunks`/handle-ID tables) from the top-level
`components` array on every write. Hand-authored component objects that
omit `compiledData`-only bookkeeping fields — and that use `{"Data": {...}}`
for nested handle-typed fields (`parentTransform`, `skinning`, `Rig`'s
implicit handles, etc.) without a manual `HandleId`/`HandleRefId` — round
trip cleanly: WolvenKit auto-assigns fresh handle IDs and fills in every
field the component's C# type declares a default for. This mirrors exactly
what `CR2WWriter.WriteFile()` does for npv-inject's in-memory RED4 objects;
we're just constructing the same shape one JSON level up instead of in
typed C#.

Component field shapes are sourced directly from the WolvenKit RED4 type
definitions (WolvenKit/WolvenKit.RED4/Types/Classes/*.cs, submodule at
repo root), not guessed — in particular:
  - entSkinnedMeshComponent / entGarmentSkinnedMeshComponent: `mesh`
    (CResourceAsyncReference<CMesh>), `meshAppearance` (CName), inherited
    `skinning` (CHandle<entSkinningBinding>) from entISkinTargetComponent.
  - entMorphTargetSkinnedMeshComponent: `morphResource`
    (CResourceAsyncReference<MorphTargetMesh>) — this type has NO `mesh`
    field (the mesh is derived from the morphtarget resource at runtime).
  - entAnimatedComponent: `rig` (CResourceReference<animRig>), `graph`
    (CResourceReference<animAnimGraph>), `facialSetup`
    (CResourceAsyncReference<animFacialSetup>), `controlBinding`
    (CHandle<entAnimationControlBinding>).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .errors import NpvError

VALID_TYPES = frozenset(
    {
        "entSkinnedMeshComponent",
        "entGarmentSkinnedMeshComponent",
        "entAnimatedComponent",
        "entMorphTargetSkinnedMeshComponent",
    }
)

# Donor-infrastructure component types copied wholesale from the donor .app
# (animation rig, AI, locomotion support) — mirrors ComponentInjector.cs's
# s_infrastructureTypes. Not built by build_component_json; carried over by
# inject_components when a donor_app is supplied.
INFRASTRUCTURE_TYPES = frozenset(
    {
        "entAnimatedComponent",
        "entAnimationSetupExtensionComponent",
        "entLightBlockingComponent",
        "entSlotComponent",
        "entVisualControllerComponent",
    }
)


class InjectError(NpvError):
    pass


def _cname(value: str) -> dict[str, Any]:
    return {"$type": "CName", "$storage": "string", "$value": value}


def _resource_path(depot_path: str, flags: str = "Default") -> dict[str, Any]:
    return {
        "DepotPath": {
            "$type": "ResourcePath",
            "$storage": "string",
            "$value": depot_path,
        },
        "Flags": flags,
    }


def _handle_binding(bind_type: str, bind_name: str) -> dict[str, Any]:
    """Build an inline-handle field value (parentTransform / skinning).

    No HandleId/HandleRefId — WolvenKit assigns a fresh handle ID on
    deserialize. This is the `{"Data": {...}}` shape confirmed by the
    Task 7 desk round-trip (see module docstring).
    """
    return {
        "Data": {
            "$type": bind_type,
            "bindName": _cname(bind_name),
        }
    }


def build_component_json(spec: dict[str, Any]) -> dict[str, Any]:
    """Build one component object in WolvenKit's serialized JSON shape.

    Pure function: given a component spec dict (the same shape
    `npv_components.json` already carries — `type`, `name`, `mesh`,
    `meshAppearance`, `bindTo`, and for entAnimatedComponent/morph
    components `graph`/`rig`/`morphResource`), returns the JSON object to
    append to `appearances[0].Data.components`.

    Wrapped so callers can append the result to `components` — NOT
    `compiledData.Data.Chunks` (WolvenKit regenerates that buffer from
    `components` on deserialize; leaving it stale is fine, confirmed by
    the Task 7 desk round-trip).
    """
    comp_type = spec.get("type")
    if comp_type not in VALID_TYPES:
        raise InjectError(f"Unknown component type: '{comp_type}'.")

    name = spec.get("name")
    if not name:
        raise InjectError("Component spec missing 'name'.")

    bind_to = spec.get("bindTo") or "root"

    if comp_type == "entAnimatedComponent":
        data: dict[str, Any] = {
            "$type": comp_type,
            "name": _cname(name),
        }
        graph = spec.get("graph")
        if graph:
            data["graph"] = _resource_path(graph, "Obligatory")
        rig = spec.get("rig")
        if rig:
            data["rig"] = _resource_path(rig, "Default")
        data["controlBinding"] = {
            "Data": {
                "$type": "entAnimationControlBinding",
                "bindName": _cname(bind_to),
                "enabled": 1,
            }
        }
        data["parentTransform"] = _handle_binding("entHardTransformBinding", "root")
        return {"Data": data}

    mesh_appearance = spec.get("meshAppearance") or "default"
    data = {
        "$type": comp_type,
        "chunkMask": "18446744073709551615",
        "meshAppearance": _cname(mesh_appearance),
        "name": _cname(name),
        "parentTransform": _handle_binding("entHardTransformBinding", bind_to),
        "skinning": _handle_binding("entSkinningBinding", bind_to),
    }

    if comp_type == "entMorphTargetSkinnedMeshComponent":
        # entMorphTargetSkinnedMeshComponent has NO `mesh` field — only
        # `morphResource`. build project_writer.py's spec carries the
        # morphtarget depot path under either "morphResource" or "graph"
        # (legacy alias); prefer morphResource.
        morph_resource = spec.get("morphResource") or spec.get("graph")
        if morph_resource:
            data["morphResource"] = _resource_path(morph_resource)
    else:
        mesh = spec.get("mesh")
        if mesh:
            data["mesh"] = _resource_path(mesh)

    return {"Data": data}


def _parse_spec_file(components_json: Path) -> tuple[str | None, list[dict[str, Any]]]:
    try:
        payload = json.loads(components_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise InjectError(f"Failed to read component spec: {e}") from e

    appearance_name = payload.get("appearance_name")
    specs = payload.get("components")
    if specs is None:
        raise InjectError("JSON missing 'components' array.")
    return appearance_name, specs


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_appearance(doc: dict[str, Any], appearance_index: int) -> dict[str, Any]:
    root = doc.get("Data", {}).get("RootChunk", {})
    if root.get("$type") != "appearanceAppearanceResource":
        raise InjectError(
            f".app RootChunk is {root.get('$type', 'null')}, expected appearanceAppearanceResource."
        )
    appearances = root.get("appearances", [])
    if appearance_index >= len(appearances):
        raise InjectError(
            f"Appearance index {appearance_index} out of range "
            f"(file has {len(appearances)} appearance(s))."
        )
    handle = appearances[appearance_index]
    data = handle.get("Data")
    if not data or data.get("$type") != "appearanceAppearanceDefinition":
        raise InjectError(
            f"Appearance at index {appearance_index} is not an appearanceAppearanceDefinition."
        )
    return data


def _inline_handle_refs(comp: dict[str, Any], resolved_twin: dict[str, Any]) -> dict[str, Any]:
    """Rewrite bare `{"HandleRefId": N}` fields as self-contained `{"Data": {...}}`.

    WolvenKit's serialized JSON carries two parallel views of each
    component: the top-level `appearances[i].Data.components[k]` (decoded,
    but with nested handle-typed fields like `parentTransform`/`skinning`/
    `controlBinding` collapsed to a bare `{"HandleRefId": N}` pointing into
    the file's global handle table) and
    `appearances[i].Data.compiledData.Data.Chunks[k]` (the SAME component,
    same index k, but with those same fields expanded inline as
    `{"HandleId": N, "Data": {...}}`).

    A component copied verbatim out of `components` (as donor-infrastructure
    components are) carries `HandleRefId`s whose targets live ONLY in the
    donor's `compiledData.Data.Chunks` — never in `components` itself. If we
    copy the bare component into a fresh appearance without also carrying
    those targets, WolvenKit's deserializer fails outright (JsonException on
    the dangling handle) rather than silently dropping it — confirmed
    empirically (Task 7 attempt 2's second failure mode, root-caused via
    exact byte-offset lookup in the failing JSON against the reference
    `.app`'s `compiledData.Data.Chunks[k]`, index-matched to `components[k]`).

    `resolved_twin` is the matching `Chunks[k]` entry (same component, same
    index, handle fields expanded). This walks `comp`'s top level and
    replaces every bare-HandleRefId field with the inline `{"Data": {...}}`
    pulled from the twin's same-named field — restoring the self-contained
    shape `build_component_json` already produces for freshly-built
    components, so donor-copied and freshly-built components round-trip
    through the same code path.

    Index alignment between `components[k]` and `compiledData.Data.Chunks[k]`
    is asserted, not assumed: WolvenKit's expanded chunk carries its own
    `HandleId` alongside `Data` (confirmed against a real serialized .app —
    e.g. `chunks[1].parentTransform == {"HandleId": "2", "Data": {...}}` for
    a component whose bare field was `{"HandleRefId": 2}`). We compare that
    `HandleId` against the `HandleRefId` being resolved and raise loudly on
    a mismatch, so a future donor file with non-index-aligned handles fails
    fast instead of silently producing a wrong-but-valid-looking .app.
    """
    out = dict(comp)
    for key, value in comp.items():
        if isinstance(value, dict) and set(value.keys()) == {"HandleRefId"}:
            ref_id = value["HandleRefId"]
            twin_value = resolved_twin.get(key)
            if isinstance(twin_value, dict) and "Data" in twin_value:
                twin_handle_id = twin_value.get("HandleId")
                if twin_handle_id is not None and str(twin_handle_id) != str(ref_id):
                    raise InjectError(
                        f"Handle-ref mismatch resolving '{key}': component expects "
                        f"HandleRefId {ref_id!r} but the index-matched compiledData "
                        f"chunk carries HandleId {twin_handle_id!r}. Donor component "
                        "and compiledData.Data.Chunks are no longer index-aligned — "
                        "refusing to inline a possibly-wrong handle."
                    )
                out[key] = {"Data": twin_value["Data"]}
    return out


def _copy_infrastructure(
    source_appearance: dict[str, Any],
    target_appearance: dict[str, Any],
    *,
    face_rig: str | None,
    facial_setup: str | None,
    face_graph: str | None,
    skip_donor_hair_dangle: bool,
) -> None:
    target_components = target_appearance.setdefault("components", [])
    source_components = source_appearance.get("components", [])
    # Parallel array, index-matched to source_components — see
    # _inline_handle_refs for why this is needed.
    source_chunks = source_appearance.get("compiledData", {}).get("Data", {}).get("Chunks", [])

    for index, comp in enumerate(source_components):
        comp_type = comp.get("$type")
        if comp_type not in INFRASTRUCTURE_TYPES:
            continue

        comp_name = comp.get("name", {}).get("$value", "")

        if skip_donor_hair_dangle and comp_name == "hair_dangle":
            continue

        comp = json.loads(json.dumps(comp))  # deep copy before mutating

        if index < len(source_chunks):
            comp = _inline_handle_refs(comp, source_chunks[index])

        if comp_type == "entAnimatedComponent" and comp_name == "face_rig":
            if face_rig is not None:
                comp["rig"] = _resource_path(face_rig)
            if facial_setup is not None:
                comp["facialSetup"] = _resource_path(facial_setup)
            if face_graph is not None:
                comp["graph"] = _resource_path(face_graph, "Obligatory")

        target_components.append(comp)


def inject_components(
    wk: Any,
    app_path: Path,
    components_json: Path,
    *,
    donor_app: Path | None = None,
    face_rig: str | None = None,
    facial_setup: str | None = None,
    face_graph: str | None = None,
    hair_dangle_graph: str | None = None,
    appearance_index: int = 0,
    scratch_dir: Path | None = None,
) -> None:
    """Inject mesh + donor-infrastructure components into a cooked .app.

    Pure-Python equivalent of npv-inject: serialize `app_path` to JSON via
    `wk`, build/append component objects, deserialize back to `app_path`.
    Modifies `app_path` in place (matches npv-inject's contract).

    `hair_dangle_graph == "skip"` mirrors npv-inject's
    `--skip-donor-hair-dangle`: the donor's own hair_dangle component is
    dropped (a custom one is supplied among `components_json`'s specs
    instead).
    """
    if not app_path.exists():
        raise InjectError(f"File not found: {app_path}")
    if not components_json.exists():
        raise InjectError(f"File not found: {components_json}")

    appearance_name, specs = _parse_spec_file(components_json)
    if not specs:
        raise InjectError("No components in spec file.")

    own_scratch = scratch_dir is None
    if scratch_dir is None:
        import tempfile

        scratch_dir = Path(tempfile.mkdtemp(prefix="npv_app_inject_"))

    try:
        serialize_dir = scratch_dir / "serialize"
        app_json_path = wk.serialize(app_path, dest=serialize_dir)
        doc = _load_json(app_json_path)

        appearance = _find_appearance(doc, appearance_index)

        if appearance_name:
            appearance["name"] = _cname(appearance_name)

        root = doc["Data"]["RootChunk"]
        appearances = root["appearances"]
        # Keep only the target appearance (mirrors Program.cs's trim loop).
        target_handle = appearances[appearance_index]
        root["appearances"] = [target_handle]

        if donor_app is not None:
            donor_json_path = wk.serialize(donor_app, dest=scratch_dir / "donor_serialize")
            donor_doc = _load_json(donor_json_path)
            donor_root = donor_doc.get("Data", {}).get("RootChunk", {})
            donor_appearances = donor_root.get("appearances", [])
            if donor_appearances:
                donor_appearance = donor_appearances[0].get("Data", {})
                skip_hair_dangle = hair_dangle_graph == "skip"
                _copy_infrastructure(
                    donor_appearance,
                    appearance,
                    face_rig=face_rig,
                    facial_setup=facial_setup,
                    face_graph=face_graph,
                    skip_donor_hair_dangle=skip_hair_dangle,
                )

        components = appearance.setdefault("components", [])
        for spec in specs:
            components.append(build_component_json(spec)["Data"])

        app_json_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        wk.deserialize(app_json_path)

        produced = app_json_path.with_suffix("")  # strip trailing .json
        if produced.exists() and produced != app_path:
            shutil.copyfile(produced, app_path)
    finally:
        if own_scratch:
            shutil.rmtree(scratch_dir, ignore_errors=True)
