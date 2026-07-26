"""Build and cache the vanilla clothing picker catalog.

Only exact primary player-equipment meshes enumerated from the user's game
archives can be marked buildable.  Every source item is retained so unresolved
items can be shown disabled instead of silently disappearing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ..config import get_cache_dir
from ..core.bundled_tools import bundled_tool_path
from ..core.errors import NpvError
from ..core.proc import run_tool

DEFAULT_CACHE_PATH = get_cache_dir() / "clothing_catalog.json"
CATALOG_FORMAT_VERSION = 4

_ITEM_RE = re.compile(r'"Items\.([^"]+)"')
_ITEM_KEY_RE = re.compile(
    r"^(?P<family>[A-Za-z]+)_(?P<number>\d{1,3})(?:_|$)",
    re.IGNORECASE,
)
_PRIMARY_MESH_RE = re.compile(
    r"\\(?P<directory>(?P<code>[a-z]\d_\d{3})_(?P<descriptor>[^\\]+))"
    r"\\(?P=code)_(?P<rig>pwa|pma)_(?P=descriptor)\.mesh$",
    re.IGNORECASE,
)
_PREFIX_SLOTS = {
    "t1": "inner_torso",
    "t2": "outer_torso",
    "l1": "legs",
    "s1": "feet",
    "h1": "head",
    "h2": "head",
}
_FAMILY_PREFIXES = {
    "balaclava": ("h1", "h2"),
    "boots": ("s1",),
    "cap": ("h1", "h2"),
    "casualshoes": ("s1",),
    "coat": ("t2",),
    "dress": ("t1", "t2"),
    "formaljacket": ("t2",),
    "formalpants": ("l1",),
    "formalshirt": ("t1",),
    "formalshoes": ("s1",),
    "formalskirt": ("l1",),
    "glasses": ("h1", "h2"),
    "hat": ("h1", "h2"),
    "helmet": ("h1", "h2"),
    "jacket": ("t2",),
    "jumpsuit": ("t1", "t2"),
    "looseshirt": ("t1",),
    "mask": ("h1", "h2"),
    "pants": ("l1",),
    "scarf": ("h1", "h2"),
    "shirt": ("t1",),
    "shoes": ("s1",),
    "shorts": ("l1",),
    "skirt": ("l1",),
    "tightjumpsuit": ("t1", "t2"),
    "tshirt": ("t1",),
    "undershirt": ("t1",),
    "vest": ("t2",),
    "visor": ("h1", "h2"),
}
_FAMILY_DESCRIPTORS = {
    "balaclava": ("balaclava",),
    "boots": ("boot",),
    "cap": ("cap", "hat"),
    "casualshoes": ("shoe", "sneaker", "sandal"),
    "coat": ("coat",),
    "dress": ("dress",),
    "formaljacket": ("jacket",),
    "formalpants": ("pants",),
    "formalshirt": ("shirt",),
    "formalshoes": ("shoe",),
    "formalskirt": ("skirt",),
    "glasses": ("glasses", "specs"),
    "hat": ("hat",),
    "helmet": ("helmet",),
    "jacket": ("jacket",),
    "jumpsuit": ("jumpsuit", "full"),
    "looseshirt": ("shirt",),
    "mask": ("mask",),
    "pants": ("pants",),
    "scarf": ("scarf",),
    "shirt": ("shirt",),
    "shoes": ("shoe",),
    "shorts": ("shorts",),
    "skirt": ("skirt",),
    "tightjumpsuit": ("jumpsuit", "full"),
    "tshirt": ("tshirt",),
    "undershirt": ("undershirt",),
    "vest": ("vest",),
    "visor": ("visor",),
}


def _item_id(entry: dict[str, Any]) -> str:
    match = _ITEM_RE.search(str(entry.get("command", "")))
    return match.group(1) if match else ""


def _item_key(value: str) -> tuple[str, int] | None:
    match = _ITEM_KEY_RE.match(value)
    if not match:
        return None
    return match.group("family").lower(), int(match.group("number"))


def slot_for_mesh(mesh: str) -> str:
    """Return the inspector garment slot inferred from a mesh basename."""
    basename = mesh.replace("\\", "/").rsplit("/", 1)[-1].lower()
    prefix = basename.split("_", 1)[0]
    return _PREFIX_SLOTS.get(prefix, "other")


def _slot_for_item(value: str) -> str:
    key = _item_key(value)
    if not key:
        return "other"
    prefixes = _FAMILY_PREFIXES.get(key[0], ())
    slots = {_PREFIX_SLOTS.get(prefix, "other") for prefix in prefixes}
    return slots.pop() if len(slots) == 1 else "other"


def _primary_groups(mesh_paths: list[str]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for raw_path in mesh_paths:
        mesh = raw_path.strip().replace("/", "\\")
        if "\\player_equipment\\" not in mesh.lower():
            continue
        match = _PRIMARY_MESH_RE.search(mesh)
        if not match:
            continue
        code = match.group("code").lower()
        descriptor = match.group("descriptor").lower()
        rows = groups.setdefault(code, [])
        group = next((row for row in rows if row["descriptor"] == descriptor), None)
        if group is None:
            group = {"descriptor": descriptor}
            rows.append(group)
        group[match.group("rig").lower()] = mesh
    return groups


def _matching_group(value: str, groups: dict[str, list[dict[str, str]]]) -> dict[str, str] | None:
    key = _item_key(value)
    if not key:
        return None
    family, number = key
    prefixes = _FAMILY_PREFIXES.get(family, ())
    descriptors = _FAMILY_DESCRIPTORS.get(family, ())
    candidates = [
        group
        for prefix in prefixes
        for group in groups.get(f"{prefix}_{number:03d}", [])
        if any(token in group["descriptor"] for token in descriptors)
    ]
    return candidates[0] if len(candidates) == 1 else None


def build_catalog(mesh_paths: list[str], clothes: list[dict]) -> list[dict]:
    """Join display-name records to exact archive-backed garment meshes."""
    groups = _primary_groups(mesh_paths)
    entries: list[dict] = []
    for source in clothes:
        value = _item_id(source)
        group = _matching_group(value, groups)
        mesh_pwa = group.get("pwa") if group else None
        mesh_pma = group.get("pma") if group else None
        mesh = mesh_pwa or mesh_pma
        entries.append(
            {
                "item_id": value,
                "name": str(source.get("name") or "Unknown item"),
                "image": str(source.get("image") or ""),
                "slot": slot_for_mesh(mesh) if mesh else _slot_for_item(value),
                "mesh": mesh,
                # Per-rig paths let the bridge return the right sibling rather
                # than accidentally putting a PWA mesh on a PMA build.
                "mesh_pwa": mesh_pwa,
                "mesh_pma": mesh_pma,
                "buildable_pwa": mesh_pwa is not None,
                "buildable_pma": mesh_pma is not None,
            }
        )
    return entries


def _component_value(component: dict, key: str, default: str = "") -> str:
    value = component.get(key, default)
    if isinstance(value, dict):
        return str(value.get("$value", default))
    return str(value or default)


def _app_identity_for_item(
    *,
    item_record: dict,
    rig: str,
    entity_documents: dict[str, dict],
) -> tuple[str, str]:
    """Resolve an item's exact app depot and app appearance.

    TweakDB's ``appearanceName`` is encoded as
    ``<app-stem>_<entity-appearance-base>_``. Deriving the target from the
    actual entity template handles both ordinary ``basic_01`` items and EP1
    quest shapes such as ``outfit_01__q301_nusa_agent_`` without guessing from
    the inventory record ID.
    """
    appearance_key = str(item_record.get("appearance_name") or "").rstrip("_")
    entity_name = str(item_record.get("entity_name") or "")
    if not appearance_key or not entity_name:
        return "", ""
    rig_suffix = "w" if rig == "pwa" else "m"
    candidates = []
    for template in (
        (entity_documents.get(entity_name) or {})
        .get("Data", {})
        .get("RootChunk", {})
        .get("appearances", [])
    ):
        depot = template.get("appearanceResource", {}).get("DepotPath", {}).get("$value", "")
        stem = depot.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".app")
        prefix = f"{stem}_"
        if not depot or not appearance_key.casefold().startswith(prefix.casefold()):
            continue
        target = f"{appearance_key[len(prefix) :]}_{rig_suffix}"
        if _component_value(template, "appearanceName") != target:
            continue
        candidates.append((depot, target))
    candidates = list(dict.fromkeys(candidates))
    return candidates[0] if len(candidates) == 1 else ("", "")


def _components_for_item(
    *,
    item_id: str,
    item_record: dict,
    rig: str,
    entity_documents: dict[str, dict],
    app_documents: dict[str, dict],
) -> list[dict]:
    app_depot, target_appearance = _app_identity_for_item(
        item_record=item_record,
        rig=rig,
        entity_documents=entity_documents,
    )
    if not app_depot or not target_appearance:
        return []
    app = app_documents.get(app_depot) or {}
    matching = [
        entry.get("Data", {})
        for entry in app.get("Data", {}).get("RootChunk", {}).get("appearances", [])
        if _component_value(entry.get("Data", {}), "name") == target_appearance
    ]
    if len(matching) != 1:
        return []

    components = []
    for chunk in matching[0].get("compiledData", {}).get("Data", {}).get("Chunks", []):
        component_type = str(chunk.get("$type") or "")
        if component_type not in (
            "entGarmentSkinnedMeshComponent",
            "entSkinnedMeshComponent",
        ):
            continue
        mesh = chunk.get("mesh", {}).get("DepotPath", {}).get("$value", "")
        if not mesh:
            continue
        bind_to = (
            chunk.get("skinning", {}).get("Data", {}).get("bindName", {}).get("$value", "root")
        )
        components.append(
            {
                "type": component_type,
                "name": _component_value(chunk, "name")
                or mesh.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".mesh"),
                "mesh": mesh,
                "appearance": _component_value(chunk, "meshAppearance", "default"),
                "bind_to": bind_to or "root",
                "chunk_mask": str(chunk.get("chunkMask") or ""),
            }
        )
    return components


def _app_depot_for_item(
    *,
    item_id: str,
    item_record: dict,
    rig: str,
    entity_documents: dict[str, dict],
) -> str:
    del item_id  # Identity comes from TweakDB appearanceName, not ID shape.
    depot, _appearance = _app_identity_for_item(
        item_record=item_record,
        rig=rig,
        entity_documents=entity_documents,
    )
    return depot


def build_exact_catalog(
    clothes: list[dict],
    item_records: dict[str, dict],
    entity_documents: dict[str, dict],
    app_documents: dict[str, dict],
) -> list[dict]:
    """Build an item-exact catalog from the game's item appearance graph.

    Unlike :func:`build_catalog`, this follows the TweakDB item identity
    through the shared item entity and appearance resource. Distinct inventory
    records may therefore share a mesh while retaining different material
    appearances and child components.
    """
    entries = []
    for source in clothes:
        item_id = _item_id(source)
        item_record = item_records.get(item_id) or {}
        components_pwa = _components_for_item(
            item_id=item_id,
            item_record=item_record,
            rig="pwa",
            entity_documents=entity_documents,
            app_documents=app_documents,
        )
        components_pma = _components_for_item(
            item_id=item_id,
            item_record=item_record,
            rig="pma",
            entity_documents=entity_documents,
            app_documents=app_documents,
        )
        primary_pwa = components_pwa[0] if components_pwa else {}
        primary_pma = components_pma[0] if components_pma else {}
        primary = primary_pwa or primary_pma
        mesh = primary.get("mesh")
        occupied_pwa = sorted(
            {
                slot_for_mesh(component.get("mesh", ""))
                for component in components_pwa
                if slot_for_mesh(component.get("mesh", "")) != "other"
            }
        )
        occupied_pma = sorted(
            {
                slot_for_mesh(component.get("mesh", ""))
                for component in components_pma
                if slot_for_mesh(component.get("mesh", "")) != "other"
            }
        )
        entries.append(
            {
                "item_id": item_id,
                "name": str(source.get("name") or "Unknown item"),
                "image": str(source.get("image") or ""),
                "slot": slot_for_mesh(mesh) if mesh else _slot_for_item(item_id),
                "mesh": mesh,
                "mesh_pwa": primary_pwa.get("mesh"),
                "mesh_pma": primary_pma.get("mesh"),
                "appearance_pwa": primary_pwa.get("appearance"),
                "appearance_pma": primary_pma.get("appearance"),
                "components_pwa": components_pwa,
                "components_pma": components_pma,
                "occupied_slots_pwa": occupied_pwa,
                "occupied_slots_pma": occupied_pma,
                "buildable_pwa": bool(components_pwa),
                "buildable_pma": bool(components_pma),
            }
        )
    return entries


def catalog_selection(entry: dict, rig: str) -> dict | None:
    """Return the immutable request value represented by one catalog row."""
    if rig not in {"pwa", "pma"} or not entry.get(f"buildable_{rig}"):
        return None
    components = entry.get(f"components_{rig}")
    mesh = entry.get(f"mesh_{rig}")
    appearance = entry.get(f"appearance_{rig}")
    if not isinstance(components, list) or not components or not mesh or not appearance:
        return None
    return {
        "item_id": str(entry.get("item_id") or ""),
        "name": str(entry.get("name") or "Unknown item"),
        "slot": str(entry.get("slot") or ""),
        "mesh": str(mesh),
        "appearance": str(appearance),
        "components": components,
        "occupied_slots": entry.get(f"occupied_slots_{rig}") or [str(entry.get("slot") or "")],
        "source_kind": "catalog",
    }


def validate_catalog_selection(
    selection: Any,
    entries: list[dict] | None,
    rig: str,
    *,
    expected_slot: str | None = None,
) -> str | None:
    """Return a user-facing error when a selection is not an exact catalog row."""
    if isinstance(selection, str):
        return "Variant unknown — reselect this garment"
    if not isinstance(selection, dict):
        return "Garment selection must be an object"
    if selection.get("source_kind") != "catalog":
        return "Garment selection is not an exact catalog item"
    if entries is None:
        return "Clothing catalog is unavailable — rebuild it and reselect this garment"
    item_id = str(selection.get("item_id") or "")
    matches = [entry for entry in entries if entry.get("item_id") == item_id]
    if len(matches) != 1:
        return f"Catalog item '{item_id or 'unknown'}' is unavailable"
    canonical = catalog_selection(matches[0], rig)
    if canonical is None:
        return f"Catalog item '{item_id}' is not buildable for {rig.upper()}"
    slot = str(selection.get("slot") or "")
    if expected_slot and slot != expected_slot:
        return f"Garment slot '{slot}' does not match '{expected_slot}'"
    if slot_for_mesh(str(selection.get("mesh") or "")) != slot:
        return f"Garment mesh does not belong to slot '{slot}'"
    if selection != canonical:
        return f"Catalog item '{item_id}' metadata changed — reselect this garment"
    return None


def _tweakdb_helper_binary() -> Path:
    configured = os.environ.get("NPV_TWEAKDB_BINARY")
    if configured and Path(configured).expanduser().is_file():
        return Path(configured).expanduser()
    on_path = shutil.which("npv-tweakdb")
    if on_path:
        return Path(on_path)
    bundled = bundled_tool_path("npv-tweakdb")
    if bundled is not None:
        return bundled
    repo_root = Path(__file__).resolve().parents[2]
    project = repo_root / "tools" / "npv-tweakdb" / "npv-tweakdb.csproj"
    binary = (
        project.parent
        / "bin"
        / "Release"
        / "net8.0"
        / ("npv-tweakdb.exe" if os.name == "nt" else "npv-tweakdb")
    )
    if not binary.is_file():
        run_tool(
            ["dotnet", "build", str(project), "-c", "Release", "--nologo"],
            tool="Clothing metadata helper",
            timeout=600.0,
        )
    if not binary.is_file():
        raise NpvError(
            "Clothing metadata helper could not be built.",
            remediation="Install the .NET 8 SDK and rebuild the clothing catalog.",
        )
    return binary


def catalog_source_fingerprints(game_dir: Path) -> dict[str, dict[str, int]]:
    """Fingerprint the derived catalog's installed metadata inputs."""
    candidates = {
        "tweakdb": game_dir / "r6" / "cache" / "tweakdb.bin",
        "tweakdb_ep1": game_dir / "r6" / "cache" / "tweakdb_ep1.bin",
    }
    configured = os.environ.get("NPV_TWEAKDB_BINARY")
    on_path = shutil.which("npv-tweakdb")
    repo_binary = (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "npv-tweakdb"
        / "bin"
        / "Release"
        / "net8.0"
        / ("npv-tweakdb.exe" if os.name == "nt" else "npv-tweakdb")
    )
    helper = (
        Path(configured).expanduser() if configured else Path(on_path) if on_path else repo_binary
    )
    candidates["npv_tweakdb"] = helper
    fingerprints = {}
    for name, path in candidates.items():
        try:
            stat = path.stat()
        except OSError:
            continue
        fingerprints[name] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return fingerprints


def _load_item_records(game_dir: Path, clothes: list[dict]) -> dict[str, dict]:
    tweakdb_paths = [
        path
        for path in (
            game_dir / "r6" / "cache" / "tweakdb.bin",
            game_dir / "r6" / "cache" / "tweakdb_ep1.bin",
        )
        if path.is_file()
    ]
    if not tweakdb_paths:
        raise NpvError(
            "Cyberpunk TweakDB files were not found.",
            remediation="Verify the configured game directory and game installation.",
        )
    item_ids = [f"Items.{_item_id(entry)}" for entry in clothes if _item_id(entry)]
    with tempfile.TemporaryDirectory(prefix="npv-clothing-tdb-") as temp:
        item_file = Path(temp) / "items.json"
        item_file.write_text(json.dumps(item_ids), encoding="utf-8")
        command = [str(_tweakdb_helper_binary())]
        for tweakdb_path in tweakdb_paths:
            command.extend(["--tweakdb", str(tweakdb_path)])
        command.extend(["--items-json", str(item_file)])
        result = run_tool(
            command,
            tool="Clothing metadata helper",
            timeout=600.0,
        )
    try:
        rows = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise NpvError(
            "Clothing metadata helper returned invalid data.",
            remediation="Rebuild the helper and retry the clothing catalog.",
            details=str(error),
        ) from error
    records = {}
    for row in rows:
        item_id = str(row.get("item_id") or "").removeprefix("Items.")
        if item_id:
            records[item_id] = row
    return records


def _archive_roots(game_dir: Path) -> list[Path]:
    roots = [game_dir / "archive" / "pc" / "content"]
    expansion = game_dir / "archive" / "pc" / "ep1"
    if expansion.is_dir():
        roots.append(expansion)
    return [root for root in roots if root.is_dir()]


def _resource_map(wk: Any, roots: list[Path], pattern: str) -> dict[str, Path]:
    resources: dict[str, Path] = {}
    for root in roots:
        for depot in wk.list_archive(pattern, archive=root):
            if depot:
                resources[depot.replace("/", "\\")] = root
    return resources


def _uncook_documents(
    wk: Any,
    resources: dict[str, Path],
    requested: set[str],
) -> dict[str, dict]:
    documents: dict[str, dict] = {}
    by_root: dict[Path, list[str]] = {}
    for depot in sorted(requested, key=str.casefold):
        normalized = depot.replace("/", "\\")
        root = resources.get(normalized)
        if root is not None:
            by_root.setdefault(root, []).append(normalized)
    for root, depots in by_root.items():
        with tempfile.TemporaryDirectory(prefix="npv-clothing-uncook-") as temp:
            destination = Path(temp)
            basenames = [depot.replace("\\", "/").rsplit("/", 1)[-1] for depot in depots]
            pattern = "(?:" + "|".join(re.escape(name) for name in basenames) + r")$"
            wk.uncook_many(pattern, archive=root, dest=destination)
            for depot in depots:
                path = destination / (depot.replace("\\", "/") + ".json")
                if not path.is_file():
                    candidates = list(
                        destination.rglob(depot.replace("\\", "/").rsplit("/", 1)[-1] + ".json")
                    )
                    if len(candidates) != 1:
                        continue
                    path = candidates[0]
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    documents[depot] = value
    return documents


def _mesh_appearances(document: dict) -> set[str]:
    return {
        str(entry.get("Data", {}).get("name", {}).get("$value", ""))
        for entry in document.get("Data", {}).get("RootChunk", {}).get("appearances", [])
        if entry.get("Data", {}).get("name", {}).get("$value")
    }


def _validate_catalog_meshes(
    entries: list[dict],
    mesh_documents: dict[str, dict],
) -> None:
    for entry in entries:
        for rig in ("pwa", "pma"):
            components_key = f"components_{rig}"
            components = entry.get(components_key) or []
            valid = bool(components)
            for component in components:
                appearances = _mesh_appearances(mesh_documents.get(component.get("mesh", "")) or {})
                if component.get("appearance") not in appearances:
                    valid = False
                    break
            if not valid:
                entry[components_key] = []
                entry[f"mesh_{rig}"] = None
                entry[f"appearance_{rig}"] = None
                entry[f"occupied_slots_{rig}"] = []
            entry[f"buildable_{rig}"] = valid
        primary = (entry.get("components_pwa") or entry.get("components_pma") or [{}])[0]
        entry["mesh"] = primary.get("mesh")


def load_catalog(
    cache_path: Path = DEFAULT_CACHE_PATH,
    *,
    expected_fingerprints: dict[str, dict[str, int]] | None = None,
) -> list[dict] | None:
    """Load a cached catalog; missing or corrupt caches behave as unbuilt."""
    try:
        value = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("format_version") != CATALOG_FORMAT_VERSION:
        return None
    if (
        expected_fingerprints is not None
        and value.get("source_fingerprints") != expected_fingerprints
    ):
        return None
    entries = value.get("entries")
    return entries if isinstance(entries, list) else None


def save_catalog(
    cache_path: Path,
    entries: list[dict],
    *,
    source_fingerprints: dict[str, dict[str, int]] | None = None,
) -> None:
    """Atomically-enough persist the generated catalog for subsequent starts."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    envelope = {
        "format_version": CATALOG_FORMAT_VERSION,
        "source_fingerprints": source_fingerprints or {},
        "entries": entries,
    }
    temporary.write_text(
        json.dumps(envelope, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(cache_path)


def build_catalog_from_game(
    game_dir: Path,
    wk: Any,
    clothes_path: Path,
    cache_path: Path = DEFAULT_CACHE_PATH,
) -> list[dict]:
    """Build an item-exact catalog from the user's TweakDB and archives."""
    clothes = json.loads(clothes_path.read_text())
    if not isinstance(clothes, list):
        raise ValueError("clothes.json must contain a list")
    item_records = _load_item_records(game_dir, clothes)
    roots = _archive_roots(game_dir)
    entity_resources = _resource_map(
        wk,
        roots,
        r"(?:base|ep1)\\gameplay\\items\\equipment\\.*_item(?:_ep1)?\.ent$",
    )
    entity_by_name = {
        depot.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".ent"): depot
        for depot in entity_resources
    }
    requested_entities = {
        entity_by_name[record.get("entity_name", "")]
        for record in item_records.values()
        if record.get("entity_name") in entity_by_name
    }
    entity_by_depot = _uncook_documents(wk, entity_resources, requested_entities)
    entity_documents = {
        name: entity_by_depot[depot]
        for name, depot in entity_by_name.items()
        if depot in entity_by_depot
    }

    app_resources = _resource_map(
        wk,
        roots,
        r"(?:base|ep1)\\characters\\appearances\\player\\items\\.*\.app$",
    )
    requested_apps = {
        depot
        for item_id, record in item_records.items()
        for rig in ("pwa", "pma")
        if (
            depot := _app_depot_for_item(
                item_id=item_id,
                item_record=record,
                rig=rig,
                entity_documents=entity_documents,
            )
        )
        and depot.replace("/", "\\") in app_resources
    }
    app_documents = _uncook_documents(wk, app_resources, requested_apps)
    entries = build_exact_catalog(
        clothes,
        item_records,
        entity_documents,
        app_documents,
    )

    mesh_resources = _resource_map(
        wk,
        roots,
        r"(?:base|ep1)\\characters\\garment\\.*\.mesh$",
    )
    requested_meshes = {
        component["mesh"]
        for entry in entries
        for rig in ("pwa", "pma")
        for component in entry.get(f"components_{rig}", [])
        if component.get("mesh", "").replace("/", "\\") in mesh_resources
    }
    mesh_documents = _uncook_documents(wk, mesh_resources, requested_meshes)
    _validate_catalog_meshes(entries, mesh_documents)
    save_catalog(
        cache_path,
        entries,
        source_fingerprints=catalog_source_fingerprints(game_dir),
    )
    return entries
