"""Pure cc_settings <-> inspector-row transforms (GUI redesign plan 2).

No I/O, no webview imports: everything here is unit-tested headless.
Row contract (consumed by webui/js/appearance.js and webui_api.appearance_data):
  {"category", "slot_id", "label", "value_label", "value_raw", "editable", "options"}
"""

from __future__ import annotations

import copy

EDITABLE_SLOTS = ("skin_tone", "hair_style", "hair_color", "eye_color")

_CATEGORIES = {
    "skin_tone": "Skin", "hair_style": "Hair", "hair_color": "Hair",
    "eye_color": "Eyes", "body_rig": "Body", "teeth": "Face",
}


def _hair_color_selection(cc: dict) -> dict | None:
    for s in cc.get("selections", []):
        lbl = (s.get("label") or "").lower()
        if (s.get("slot") in ("character_customization", "hairs")
                and "hair" in lbl and "fpp" not in lbl
                and s.get("raw", "") != "default"):
            return s
    return None


def _eye_variant(cc: dict) -> str:
    raw = (cc.get("eyes") or {}).get("raw", "")
    # "he_000_pwa__basehead__11_gradient_blue" -> "11_gradient_blue"
    return raw.split("__")[-1] if "__" in raw else raw


def _current_values(cc: dict) -> dict:
    hair_sel = _hair_color_selection(cc)
    return {
        "skin_tone": (cc.get("skin") or {}).get("tone_id", ""),
        "hair_style": (cc.get("hair") or {}).get("style_id", ""),
        "hair_color": hair_sel.get("raw", "") if hair_sel else "",
        "eye_color": _eye_variant(cc),
    }


def inspector_rows(cc_settings: dict, options: dict, display_names: dict) -> list[dict]:
    rows: list[dict] = []
    current = _current_values(cc_settings)

    def label_for(slot_id: str) -> str:
        return display_names.get(slot_id, slot_id)

    for slot_id in EDITABLE_SLOTS:
        opts = list(options.get(slot_id) or [])
        rows.append({
            "category": _CATEGORIES.get(slot_id, "Other"),
            "slot_id": slot_id,
            "label": label_for(slot_id),
            "value_label": current[slot_id],
            "value_raw": current[slot_id],
            "editable": bool(opts),
            "options": opts,
        })

    def readonly(slot_id: str, category: str, value: str) -> dict:
        return {"category": category, "slot_id": slot_id,
                "label": label_for(slot_id), "value_label": value,
                "value_raw": value, "editable": False, "options": []}

    rows.append(readonly("body_rig", "Body", cc_settings.get("body_rig", "")))
    rows.append(readonly("teeth", "Face", (cc_settings.get("teeth") or {}).get("raw", "")))
    for region, preset in sorted((cc_settings.get("face_morphs") or {}).items()):
        rows.append(readonly(f"face_morph_{region}", "Face morphs", preset))
    return rows


def apply_overrides(cc_settings: dict, overrides: dict) -> dict:
    """Return a deep copy of cc_settings with overrides applied.

    Raises ValueError on unknown slot ids — the pipeline hard-fails rather
    than silently building without a requested change.
    """
    out = copy.deepcopy(cc_settings)
    for slot_id, value in overrides.items():
        if slot_id == "skin_tone":
            out.setdefault("skin", {})["tone_id"] = value
        elif slot_id == "hair_style":
            out.setdefault("hair", {})["style_id"] = value
        elif slot_id == "hair_color":
            sel = _hair_color_selection(out)
            if sel is not None:
                sel["raw"] = value
        elif slot_id == "eye_color":
            rig = out.get("body_rig", "pwa")
            raw = f"he_000_{rig}__basehead__{value}"
            out.setdefault("eyes", {})["raw"] = raw
            for s in out.get("selections", []):
                if s.get("label") == "eyes_color":
                    s["raw"] = raw
                    s["variant"] = value
        elif slot_id == "hair_mod":
            pass  # applied last, below — must win over hair_style
        else:
            raise ValueError(f"Unknown override slot: {slot_id}")
    if "hair_mod" in overrides:
        # Emulate a save that used this CCXL hair: mapping.resolve_assets'
        # CCXL branch (hair.raw endswith '_hair' + style_id token) then finds
        # the installed mod via extract_hair_components. Applied after the
        # loop so it wins over a simultaneous hair_style regardless of order.
        token = overrides["hair_mod"]
        out["hair"] = {"style_id": token, "raw": f"{token}_hair"}
    return out


def validate_overrides(overrides: dict, options: dict) -> list[str]:
    """Fast, offline check of override values against known option lists.
    Stands in for the spec's 'dry-run resolve' (full resolve takes minutes)."""
    problems = []
    for slot_id, value in overrides.items():
        if slot_id == "hair_mod":
            # Token from install_hair_mod; no option list. The real
            # existence check happened at add time (add_hair_mod probe).
            if not value:
                problems.append("hair_mod: empty hair mod token")
            continue
        opts = options.get(slot_id)
        if slot_id not in EDITABLE_SLOTS:
            problems.append(f"Unknown override slot: {slot_id}")
        elif opts and value not in opts:
            problems.append(f"{slot_id}: '{value}' is not a known option")
    return problems
