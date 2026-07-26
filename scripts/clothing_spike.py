"""Measure clothes.json -> player-equipment mesh join coverage per rig.

Usage:
    uv run python scripts/clothing_spike.py "<game_dir>"

The script deliberately keeps the join independent from TweakDB.  Vanilla item
record IDs use a garment family and number (for example ``TShirt_024``), while
the corresponding player meshes use a slot prefix and the same padded number
(``t1_024``).  Only primary meshes whose filename mirrors their containing
directory are accepted; decorative child meshes are never offered as garments.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

GAME = Path(sys.argv[1]) if len(sys.argv) > 1 else Path()
WK = Path.home() / ".cache" / "npv" / "tools" / "wolvenkit" / "cp77tools"
CLOTHES_PATH = Path.home() / "cyberpunk_mod_list" / "data" / "clothes.json"

FAMILY_PREFIXES = {
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
    "tech": ("t1", "t2", "l1", "s1", "h1", "h2"),
    "tightjumpsuit": ("t1", "t2"),
    "tshirt": ("t1",),
    "undershirt": ("t1",),
    "vest": ("t2",),
    "visor": ("h1", "h2"),
}

FAMILY_DESCRIPTORS = {
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

ITEM_RE = re.compile(r'"Items\.([^"]+)"')
PRIMARY_RE = re.compile(
    r"\\(?P<directory>(?P<code>[a-z]\d_\d{3})_(?P<desc>[^\\]+))"
    r"\\(?P=code)_(?P<rig>pwa|pma)_(?P=desc)\.mesh$",
    re.IGNORECASE,
)


def item_id(entry: dict) -> str:
    match = ITEM_RE.search(entry.get("command", ""))
    return match.group(1) if match else ""


def item_key(value: str) -> tuple[str, int] | None:
    match = re.match(r"^(?P<family>[A-Za-z]+)_(?P<number>\d{1,3})(?:_|$)", value)
    if not match:
        return None
    return match.group("family").lower(), int(match.group("number"))


def enumerate_meshes() -> list[str]:
    meshes: set[str] = set()
    archives = sorted((GAME / "archive" / "pc" / "content").glob("basegame_*.archive"))
    for archive in archives:
        result = subprocess.run(
            [
                str(WK),
                "archive",
                str(archive),
                "-l",
                "--regex",
                r"base\\characters\\garment\\.*\.mesh$",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        meshes.update(
            re.findall(
                r"base\\characters\\garment\\[^\r\n]+?\.mesh",
                result.stdout,
                re.IGNORECASE,
            )
        )
    return sorted(meshes)


def primary_mesh_groups(meshes: list[str]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for mesh in meshes:
        if "\\player_equipment\\" not in mesh.lower():
            continue
        match = PRIMARY_RE.search(mesh)
        if not match:
            continue
        code = match.group("code").lower()
        descriptor = match.group("desc").lower()
        existing = next(
            (row for row in groups.setdefault(code, []) if row["descriptor"] == descriptor),
            None,
        )
        if existing is None:
            existing = {"descriptor": descriptor}
            groups[code].append(existing)
        existing[match.group("rig").lower()] = mesh
    return groups


def join_item(value: str, groups: dict[str, list[dict[str, str]]]) -> dict[str, str] | None:
    key = item_key(value)
    if not key:
        return None
    family, number = key
    prefixes = FAMILY_PREFIXES.get(family, ())
    descriptors = FAMILY_DESCRIPTORS.get(family, ())
    candidates = [
        group
        for prefix in prefixes
        for group in groups.get(f"{prefix}_{number:03d}", [])
        if any(token in group["descriptor"] for token in descriptors)
    ]
    if len(candidates) != 1:
        return None
    return {rig: candidates[0][rig] for rig in ("pwa", "pma") if rig in candidates[0]}


def main() -> int:
    if not GAME.is_dir():
        print("usage: clothing_spike.py <Cyberpunk 2077 game directory>", file=sys.stderr)
        return 2
    clothes = json.loads(CLOTHES_PATH.read_text())
    meshes = enumerate_meshes()
    groups = primary_mesh_groups(meshes)

    joined = []
    per_slot_total: Counter[str] = Counter()
    per_slot_joined: Counter[str] = Counter()
    rig_counts: Counter[str] = Counter()
    prefix_slot = {
        "t1": "inner_torso",
        "t2": "outer_torso",
        "l1": "legs",
        "s1": "feet",
        "h1": "head",
        "h2": "head",
    }

    for entry in clothes:
        value = item_id(entry)
        key = item_key(value)
        expected = "other"
        if key:
            prefixes = FAMILY_PREFIXES.get(key[0], ())
            if prefixes:
                expected = prefix_slot[prefixes[0]]
        per_slot_total[expected] += 1
        rigs = join_item(value, groups)
        if not rigs:
            continue
        mesh = rigs.get("pwa") or rigs.get("pma")
        code = PRIMARY_RE.search(mesh).group("code").lower()  # type: ignore[union-attr]
        slot = prefix_slot.get(code.split("_", 1)[0], "other")
        per_slot_joined[slot] += 1
        for rig in ("pwa", "pma"):
            if rig in rigs:
                rig_counts[rig] += 1
        joined.append(
            {
                "item_id": value,
                "name": entry.get("name", ""),
                "slot": slot,
                "pwa": rigs.get("pwa"),
                "pma": rigs.get("pma"),
            }
        )

    print(f"{len(meshes)} garment meshes found")
    print(f"{len(groups)} exact primary player-equipment mesh groups")
    print(f"joined {len(joined)}/{len(clothes)} = {len(joined) / len(clothes):.1%}")
    for slot in sorted(per_slot_total):
        hit = per_slot_joined[slot]
        total = per_slot_total[slot]
        print(f"{slot}: {hit}/{total} = {hit / total:.1%}")
    for rig in ("pwa", "pma"):
        print(f"{rig}-buildable: {rig_counts[rig]}/{len(clothes)}")

    print("\n20 deterministic samples:")
    for row in random.Random(20260725).sample(joined, min(20, len(joined))):
        mesh = row["pwa"] or row["pma"]
        print(f"{row['item_id']} | {row['name']} -> {Path(mesh).name}")

    output = Path("/tmp/clothing_spike_join.json")
    output.write_text(json.dumps(joined, indent=2) + "\n")
    print(f"\nwrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
