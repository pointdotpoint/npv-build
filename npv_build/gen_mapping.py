"""Mapping drift report: diff a vendored CC mapping against the live game index.

Semi-automation for authoring `data/mappings/2.3x.json` on a new game patch
(spec PC-4). Two failure modes matter:

  missing_assets      -- depot paths the mapping references that are no
                          longer present in the current game's archive index.
                          These are stale after a game update and must be
                          removed/replaced.
  unmapped_candidates  -- head-related .ent depot paths present in the game
                          index that the mapping does not reference at all.
                          These are new CC options a mapping author should
                          consider adding.

Path comparison is backslash-literal (depot convention) -- no normalization.
"""

from __future__ import annotations

import json
from pathlib import Path

from .part_resolver import get_or_create_index


def _load_mapping(patch: str) -> dict:
    mapping_file = Path(__file__).parent / "data" / "mappings" / f"{patch}.json"
    with open(mapping_file) as f:
        return json.load(f)


def _load_index(game_dir: Path, patch: str, wk=None) -> dict:
    return get_or_create_index(patch, game_dir=game_dir, wk=wk)


def extract_mapping_paths(mapping: dict) -> set[str]:
    """Flatten every depot path string from `head_preset_parts` across all
    body rigs in a mapping.json.

    Scoped to `head_preset_parts` only (not `body_part`/`arms_part`/
    `hair_part`): those live under `player_base_bodies` and modded-hair
    archives respectively, which part_resolver's index does not scan --
    comparing them against the head-only index would produce permanent
    false-positive `missing_assets` noise. `head_preset_parts` is exactly
    the set of entries part_resolver's `part_ents` table covers (both are
    head/face/scar/decal .ent files under `player_base_heads`), so it's the
    only section where a diff against the index is meaningful.
    """
    paths: set[str] = set()
    for rig_map in mapping.values():
        if not isinstance(rig_map, dict):
            continue  # skip "_comment" and similar non-rig top-level keys
        for preset_paths in rig_map.get("head_preset_parts", {}).values():
            for p in preset_paths:
                if p:
                    paths.add(p)
    return paths


def extract_index_head_paths(index: dict) -> set[str]:
    """Head-related .ent depot paths from part_resolver's index -- the
    `part_ents` table (stem -> depot path) is exactly the set of candidate
    head/face/scar/decal part entities the mapping is expected to cover.
    """
    return set(index.get("part_ents", {}).values())


def diff_mapping(mapping_paths: set[str], index_paths: set[str]) -> tuple[set[str], set[str]]:
    """Pure set diff. No normalization -- depot paths are backslash-literal.

    Returns (missing_assets, unmapped_candidates):
      missing_assets      = mapping_paths - index_paths
      unmapped_candidates = index_paths - mapping_paths
    """
    missing_assets = mapping_paths - index_paths
    unmapped_candidates = index_paths - mapping_paths
    return missing_assets, unmapped_candidates


def mapping_report(game_dir: Path, mapping_patch: str = "2.13", wk=None) -> dict:
    """Compose extract -> diff using the real mapping/index loaders."""
    mapping = _load_mapping(mapping_patch)
    index = _load_index(game_dir, mapping_patch, wk)

    mapping_paths = extract_mapping_paths(mapping)
    index_paths = extract_index_head_paths(index)

    missing_assets, unmapped_candidates = diff_mapping(mapping_paths, index_paths)

    return {
        "missing_assets": sorted(missing_assets),
        "unmapped_candidates": sorted(unmapped_candidates),
        "checked": len(mapping_paths),
    }


def format_report(report: dict) -> str:
    lines = [
        f"mapping entries checked: {report['checked']}",
        f"missing assets (in mapping, absent from game index): {len(report['missing_assets'])}",
    ]
    for p in report["missing_assets"]:
        lines.append(f"  - {p}")
    lines.append(
        f"unmapped candidates (in game index, absent from mapping): "
        f"{len(report['unmapped_candidates'])}"
    )
    for p in report["unmapped_candidates"]:
        lines.append(f"  + {p}")
    return "\n".join(lines)
