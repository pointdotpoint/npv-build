"""Resolve clothing for an NPV: fallback outfit + user garment overrides."""

import json
from pathlib import Path


def resolve_clothing(
    body_rig: str,
    garment_overrides: list[str] | None = None,
    equipped: list[dict] | None = None,
    verbosity: int = 0,
) -> list[dict]:
    """Return component specs for the NPV's clothing.

    If `equipped` (from the CET dump) is non-empty, the base outfit is V's
    equipped garments; otherwise it loads data/fallback_outfit.json. User
    `--garment` overrides apply on top, by slot (inferred from prefix), and
    win over both. Layered torso (t1_ + t2_) is preserved.
    """
    PREFIX_SLOTS = [
        ("t2_", "outer_torso"),
        ("t1_", "inner_torso"),
        ("l1_", "legs"),
        ("s1_", "feet"),
        ("h1_", "head"),
    ]

    def slot_for(basename: str) -> str:
        for prefix, slot in PREFIX_SLOTS:
            if basename.startswith(prefix):
                return slot
        return ""

    # base specs come from equipped clothing if present, else the fallback file.
    base_specs: list[dict] = []
    if equipped:
        for item in equipped:
            mesh = item.get("mesh", "")
            name = item.get("name", "")
            if not mesh or not name:
                continue
            base_specs.append(
                {
                    "comp_type": "entGarmentSkinnedMeshComponent",
                    "name": name,
                    "mesh": mesh,
                    "appearance": item.get("appearance") or "default",
                    "source": f"clothing:{item.get('slot') or 'equipped'} (equipped)",
                }
            )
            if verbosity > 0:
                print(f"[Clothing] equipped {item.get('slot') or '?'}: {name}")
    else:
        fallback_file = Path(__file__).parent / "data" / "fallback_outfit.json"
        fallback = json.loads(fallback_file.read_text()).get(body_rig, {})
        for slot_name, slot_data in fallback.items():
            base_specs.append(
                {
                    "comp_type": "entGarmentSkinnedMeshComponent",
                    "name": slot_data["name"],
                    "mesh": slot_data["mesh"],
                    "appearance": slot_data["appearance"],
                    "source": f"clothing:{slot_name}",
                }
            )

    # apply --garment overrides by slot: an override replaces any base spec in the
    # same slot (custom_ slot for unknown prefixes so it is purely additive).
    override_specs: list[dict] = []
    overridden_slots: set[str] = set()
    for i, g in enumerate(garment_overrides or []):
        g = g.strip()
        if not g:
            continue
        basename = g.replace("\\", "/").rsplit("/", 1)[-1].lower()
        slot = slot_for(basename) or f"custom_{i}"
        overridden_slots.add(slot)
        name = basename.rsplit(".", 1)[0]
        override_specs.append(
            {
                "comp_type": "entGarmentSkinnedMeshComponent",
                "name": name,
                "mesh": g,
                "appearance": "default",
                "source": f"clothing:{slot}",
            }
        )
        if verbosity > 0:
            print(f"[Clothing] override {slot}: {name}")

    def base_slot(spec: dict) -> str:
        # source is "clothing:<slot>" or "clothing:<slot> (equipped)" -> "<slot>"
        return spec["source"].split(":", 1)[1].split(" ", 1)[0]

    specs = [s for s in base_specs if base_slot(s) not in overridden_slots]
    specs.extend(override_specs)
    return specs
