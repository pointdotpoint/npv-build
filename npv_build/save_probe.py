"""Read-only save inspector: header version, build->patch, CC node facts.

The reverse-engineering entry point for new game patches (spec PC-1..3, M2/T7).
Never decodes the CC struct - works on any save regardless of v3.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .core.errors import SaveFormatError
from .save_format import SaveContainer

_CC_NODE = "CharacetrCustomization_Appearances"  # game's own typo


def _load_save_versions() -> dict[str, str]:
    with resources.files("npv_build").joinpath("data/save_versions.json").open("rb") as f:
        return json.load(f)


def probe_save(save_path: Path) -> dict:
    save_path = Path(save_path)
    try:
        container = SaveContainer(save_path.read_bytes())
    except Exception as e:  # noqa: BLE001 - any container failure means "not a readable save"
        raise SaveFormatError(
            f"Could not read save container: {save_path}",
            details=str(e),
            remediation="Point --probe-save at a Cyberpunk 2077 sav.dat file.",
        ) from e
    v1, v2, v3 = container.version
    versions = _load_save_versions()
    patch = versions.get(str(v2))
    nodes = container.node_names()
    cc_present = _CC_NODE in nodes
    cc_bytes = container.node_bytes(_CC_NODE) if cc_present else None
    cc_size = len(cc_bytes) if cc_bytes is not None else None
    return {
        "version": [v1, v2, v3],
        "build": v2,
        "patch": patch,
        "supported": patch is not None,
        "nodes": nodes,
        "cc_node_present": cc_present,
        "cc_node_size": cc_size,
    }


def format_probe(info: dict) -> str:
    v1, v2, v3 = info["version"]
    lines = [
        f"header:  v1={v1} build(v2)={v2} v3={v3}",
        f"patch:   {info['patch'] or 'UNKNOWN (build not in save_versions.json)'}",
        f"cc node: {'present' if info['cc_node_present'] else 'MISSING'}"
        + (f" ({info['cc_node_size']} bytes)" if info["cc_node_size"] else ""),
        f"nodes:   {len(info['nodes'])} total",
    ]
    return "\n".join(lines)
