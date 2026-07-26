"""Resolve clothing for an NPV: fallback outfit + user garment overrides."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def resolve_clothing(
    body_rig: str,
    garment_overrides: list[str | dict[str, Any]] | None = None,
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
            logger.info(f"[Clothing] equipped {item.get('slot') or '?'}: {name}")
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
    for i, garment in enumerate(garment_overrides or []):
        if isinstance(garment, dict):
            mesh = str(garment.get("mesh") or "").strip()
            appearance = str(garment.get("appearance") or "").strip()
            slot = str(garment.get("slot") or "").strip()
            item_id = str(garment.get("item_id") or "").strip()
            display_name = str(garment.get("name") or "").strip()
            if (
                garment.get("source_kind") != "catalog"
                or not mesh
                or not appearance
                or not slot
                or not item_id
            ):
                raise ValueError("Invalid catalog garment selection")
            components = garment.get("components")
            if not isinstance(components, list) or not components:
                raise ValueError(f"Catalog garment '{item_id}' has no validated components")
            occupied_slots = garment.get("occupied_slots") or [slot]
            if (
                not isinstance(occupied_slots, list)
                or slot not in occupied_slots
                or not all(isinstance(value, str) and value for value in occupied_slots)
            ):
                raise ValueError(f"Catalog garment '{item_id}' has invalid occupied slots")
            overridden_slots.update(occupied_slots)
            for component in components:
                component_mesh = str(component.get("mesh") or "").strip()
                component_appearance = str(component.get("appearance") or "").strip()
                if not component_mesh or not component_appearance:
                    raise ValueError(f"Catalog garment '{item_id}' has an invalid component")
                basename = component_mesh.replace("\\", "/").rsplit("/", 1)[-1].lower()
                override_specs.append(
                    {
                        "comp_type": component.get("type") or "entGarmentSkinnedMeshComponent",
                        "name": component.get("name") or basename.rsplit(".", 1)[0],
                        "mesh": component_mesh,
                        "appearance": component_appearance,
                        "bind_to": component.get("bind_to") or "root",
                        "chunk_mask": str(component.get("chunk_mask") or ""),
                        "source": (
                            f"clothing:{slot} catalog:{item_id}"
                            + (f" ({display_name})" if display_name else "")
                        ),
                    }
                )
            logger.info(
                "[Clothing] exact override %s: %s (%s)",
                slot,
                display_name or item_id,
                appearance,
            )
            continue

        g = str(garment).strip()
        if not g:
            continue
        basename = g.replace("\\", "/").rsplit("/", 1)[-1].lower()
        slot = slot_for(basename) or f"custom_{i}"
        overridden_slots.add(slot)
        if g.casefold().endswith(".ent"):
            # Legacy CLI part entities are resolved through mapping.py. They
            # still replace the fallback garment in this slot, but an .ent is
            # never authored as an entGarmentSkinnedMeshComponent mesh.
            logger.info("[Clothing] legacy part override %s: %s", slot, basename)
            continue
        if not g.casefold().endswith(".mesh"):
            raise ValueError("Legacy garment override must be a .mesh or .ent path")
        name = basename.rsplit(".", 1)[0]
        override_specs.append(
            {
                "comp_type": "entGarmentSkinnedMeshComponent",
                "name": name,
                "mesh": g,
                "appearance": "default",
                "source": f"clothing:{slot}",
                "source_kind": "legacy_mesh",
            }
        )
        logger.info(f"[Clothing] override {slot}: {name}")

    def base_slot(spec: dict) -> str:
        # source is "clothing:<slot>" or "clothing:<slot> (equipped)" -> "<slot>"
        return spec["source"].split(":", 1)[1].split(" ", 1)[0]

    specs = [s for s in base_specs if base_slot(s) not in overridden_slots]
    specs.extend(override_specs)
    return specs
