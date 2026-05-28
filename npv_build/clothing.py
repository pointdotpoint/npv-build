"""Resolve clothing for an NPV: fallback outfit + user garment overrides."""

import json
from pathlib import Path


def resolve_clothing(
    body_rig: str,
    garment_overrides: list[str] | None = None,
    verbosity: int = 0,
) -> list[dict]:
    """Return component specs for the NPV's clothing.

    Loads a fallback outfit from data/fallback_outfit.json, then applies
    any user-supplied --garment overrides by slot (inferred from prefix).
    """
    fallback_file = Path(__file__).parent / "data" / "fallback_outfit.json"
    fallback = json.loads(fallback_file.read_text()).get(body_rig, {})

    slots: dict[str, dict] = {}
    for slot_name, slot_data in fallback.items():
        slots[slot_name] = dict(slot_data)

    for g in (garment_overrides or []):
        g = g.strip()
        if not g:
            continue
        basename = g.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if basename.startswith("t2_"):
            slot = "outer_torso"
        elif basename.startswith("t1_"):
            slot = "inner_torso"
        elif basename.startswith("l1_"):
            slot = "legs"
        elif basename.startswith("s1_"):
            slot = "feet"
        elif basename.startswith("h1_"):
            slot = "head"
        else:
            slot = f"custom_{len(slots)}"
        name = basename.rsplit(".", 1)[0]
        slots[slot] = {"name": name, "mesh": g, "appearance": "default"}
        if verbosity > 0:
            print(f"[Clothing] Override {slot}: {name}")

    specs = []
    for slot_name, slot_data in slots.items():
        specs.append({
            "comp_type": "entGarmentSkinnedMeshComponent",
            "name": slot_data["name"],
            "mesh": slot_data["mesh"],
            "appearance": slot_data["appearance"],
            "source": f"clothing:{slot_name}",
        })
        if verbosity > 0:
            print(f"[Clothing] {slot_name}: {slot_data['name']}")
    return specs
