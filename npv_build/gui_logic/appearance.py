"""Pure cc_settings <-> inspector-row transforms (GUI redesign plan 2).

No I/O, no webview imports: everything here is unit-tested headless.
Row contract (consumed by webui/js/appearance.js and webui_api.appearance_data):
  {"category", "slot_id", "label", "value_label", "value_raw", "editable", "options"}
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from ..part_resolver import resolve_appearance_to_app
from ..save_parser import decode_selection, hair_from_selections

EDITABLE_SLOTS = (
    "skin_tone",
    "hair_style",
    "hair_color",
    "eye_color",
    "nail_color",
)
GARMENT_SLOTS = (
    "garment_inner_torso",
    "garment_outer_torso",
    "garment_legs",
    "garment_feet",
    "garment_head",
)

_CATEGORIES = {
    "skin_tone": "Skin",
    "hair_style": "Hair",
    "hair_color": "Hair",
    "eye_color": "Eyes",
    "nail_color": "Body",
    "body_rig": "Body",
    "teeth": "Face",
}

_PRIMARY_SELECTION_LABELS = (
    "skin_type",
    "eyes_color",
    "hair_color",
    "face_rig",
)


def _encoded_selection(label: str, raw: str) -> str:
    return json.dumps({"label": label, "raw": raw}, sort_keys=True, separators=(",", ":"))


def _selection_choice_label(label: str, raw: str) -> str:
    value = raw
    if raw != "default" and "__" in raw:
        parts = raw.split("__")
        value = " · ".join(part for part in parts[1:] if part)
    return f"{label.replace('_', ' ')} · {value.replace('_', ' ')}"


def _cc_row_label(label: str) -> str:
    lower = label.lower()
    if lower.startswith("cyberware"):
        return "Cyberware"
    if lower.startswith("piercings"):
        return "Piercings"
    if lower.startswith("eyebrows"):
        return "Eyebrows"
    if lower.startswith("eyelash"):
        return "Eyelashes"
    if lower == "teeth":
        return "Teeth"
    if "pimples" in lower:
        return "Blemishes"
    if "cheeks" in lower:
        return "Cheek makeup"
    return label.replace("_", " ").strip().title()


def _cc_row_category(label: str) -> str:
    lower = label.lower()
    if lower.startswith(("cyberware", "piercings")):
        return "Face accessories"
    if lower.startswith(("eyebrows", "eyelash")):
        return "Brows & lashes"
    if "makeup" in lower or "pimples" in lower:
        return "Makeup & skin details"
    return "Face"


def _selection_label_for_choice(original_label: str, raw: str, app_path: str) -> str:
    cyberware = re.search(r"__cyberware_(\d{2})__", raw)
    if cyberware and original_label.lower().startswith("cyberware"):
        return re.sub(r"\d+$", cyberware.group(1), original_label)

    stem = app_path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    shape = re.search(r"_(\d{2})$", stem)
    current_shape = re.search(r"(\d+)$", original_label)
    if shape and current_shape:
        replacement = shape.group(1)
        if len(current_shape.group(1)) == 1:
            replacement = str(int(replacement))
        return original_label[: current_shape.start(1)] + replacement
    return original_label


def _appearance_matches_rig_and_tone(raw: str, body_rig: str, skin_tone: str) -> bool:
    if raw == "default":
        return True
    other_rig = "pma" if body_rig == "pwa" else "pwa"
    if f"_{other_rig}_" in raw:
        return False
    gender = "female" if body_rig == "pwa" else "male"
    other_gender = "male" if gender == "female" else "female"
    if raw.startswith(f"{other_gender}_"):
        return False
    tone_match = re.search(r"__(\d{2}_(?:ca|bl)_[a-z]+)", raw)
    return not (tone_match and skin_tone and tone_match.group(1) != skin_tone)


def _related_style_apps(current_app: str, appearances: dict) -> list[str]:
    normalized = current_app.replace("\\", "/")
    directory, filename = normalized.rsplit("/", 1)
    stem = filename.rsplit(".", 1)[0]
    match = re.match(r"^(.*)_(\d{2})$", stem)
    if not match:
        return [current_app]
    family = match.group(1)
    related = []
    for app_path in appearances:
        candidate = app_path.replace("\\", "/")
        candidate_dir, candidate_name = candidate.rsplit("/", 1)
        candidate_stem = candidate_name.rsplit(".", 1)[0]
        if candidate_dir == directory and re.fullmatch(
            rf"{re.escape(family)}_\d{{2}}", candidate_stem
        ):
            related.append(app_path)
    return sorted(related) or [current_app]


def _character_customization_options(
    index: dict, body_rig: str, cc_settings: dict
) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    appearances = index.get("app_appearances", {})
    skin_tone = (cc_settings.get("skin") or {}).get("tone_id", "")

    for selection in cc_settings.get("selections", []):
        if selection.get("slot") != "character_customization":
            continue
        label = selection.get("label", "")
        raw = selection.get("raw", "")
        if not label or any(token in label.lower() for token in _PRIMARY_SELECTION_LABELS):
            continue
        app_path = resolve_appearance_to_app(index, raw, label)
        if not app_path:
            continue

        choices = []
        seen = set()
        for candidate_app in _related_style_apps(app_path, appearances):
            for candidate_raw in appearances.get(candidate_app, []):
                if not _appearance_matches_rig_and_tone(candidate_raw, body_rig, skin_tone):
                    continue
                candidate_label = _selection_label_for_choice(label, candidate_raw, candidate_app)
                value = _encoded_selection(candidate_label, candidate_raw)
                if value in seen:
                    continue
                seen.add(value)
                choices.append(
                    {
                        "value": value,
                        "label": _selection_choice_label(candidate_label, candidate_raw),
                    }
                )
        current = _encoded_selection(label, raw)
        if current not in seen:
            choices.append(
                {
                    "value": current,
                    "label": _selection_choice_label(label, raw),
                }
            )
        if choices:
            out[f"cc:{label}"] = choices
    return out


def _hair_color_selection(cc: dict) -> dict | None:
    selection_label = str((cc.get("hair") or {}).get("selection_label") or "")
    if selection_label:
        for slot in ("hairs", "character_customization"):
            for selection in cc.get("selections", []):
                if (
                    selection.get("slot") == slot
                    and selection.get("label") == selection_label
                    and selection.get("raw", "") != "default"
                ):
                    return selection
    for s in cc.get("selections", []):
        lbl = (s.get("label") or "").lower()
        if (
            s.get("slot") in ("character_customization", "hairs")
            and "hair" in lbl
            and "fpp" not in lbl
            and s.get("raw", "") != "default"
        ):
            return s
    return None


def _eye_variant(cc: dict) -> str:
    raw = (cc.get("eyes") or {}).get("raw", "")
    # "he_000_pwa__basehead__11_gradient_blue" -> "11_gradient_blue"
    return raw.split("__")[-1] if "__" in raw else raw


def _nail_appearance(cc: dict) -> str:
    configured = (cc.get("nails") or {}).get("appearance", "")
    if configured:
        return configured
    for selection in cc.get("selections", []):
        if selection.get("slot") == "character_customization" and "nails_color" in (
            selection.get("label") or ""
        ):
            raw = selection.get("raw", "")
            parts = raw.split("__")
            if len(parts) < 2:
                return ""
            appearance = parts[1].removeprefix("nails_")
            if len(parts) > 2 and parts[2]:
                appearance += f"__{parts[2]}"
            return appearance
    return ""


def _current_values(cc: dict) -> dict:
    hair_sel = _hair_color_selection(cc)
    hair = cc.get("hair") or {}
    hair_style = hair.get("style_id", "")
    if not hair_style and hair.get("vanilla_style"):
        hair_style = str(hair["vanilla_style"])
    return {
        "skin_tone": (cc.get("skin") or {}).get("tone_id", ""),
        "hair_style": hair_style,
        "hair_color": hair_sel.get("raw", "") if hair_sel else "",
        "eye_color": _eye_variant(cc),
        "nail_color": _nail_appearance(cc),
    }


def _body_tattoo_summary(cc_settings: dict) -> str:
    """Human-readable body tattoo from the save, or "" when there is none.

    Mirrors mapping.resolve_assets' body_tattoo_NN detection (the fpp_ variant
    is deliberately excluded there too).
    """
    for selection in cc_settings.get("selections", []):
        match = re.match(r"^body_tattoo_(\d+)$", selection.get("label", "") or "")
        if match and selection.get("raw"):
            return f"Pattern {match.group(1).zfill(2)} ({selection['raw']})"
    return ""


def inspector_rows(cc_settings: dict, options: dict, display_names: dict) -> list[dict]:
    rows: list[dict] = []
    current = _current_values(cc_settings)

    def label_for(slot_id: str) -> str:
        return display_names.get(slot_id, slot_id)

    for slot_id in EDITABLE_SLOTS:
        opts = list(options.get(slot_id) or [])
        value_raw = current[slot_id]
        # hair_color has no selection to write an override into when the save
        # has no non-default hair colour (e.g. bald/default-hair saves) — see
        # apply_overrides' matching hard-fail. Locking the row here keeps the
        # UI from offering an edit that would raise at apply time.
        editable = bool(opts) and not (slot_id == "hair_color" and value_raw == "")
        rows.append(
            {
                "category": _CATEGORIES.get(slot_id, "Other"),
                "slot_id": slot_id,
                "label": label_for(slot_id),
                "value_label": value_raw,
                "value_raw": value_raw,
                "editable": editable,
                "options": opts,
            }
        )

    def readonly(slot_id: str, category: str, value: str) -> dict:
        return {
            "category": category,
            "slot_id": slot_id,
            "label": label_for(slot_id),
            "value_label": value,
            "value_raw": value,
            "editable": False,
            "options": [],
        }

    rows.append(readonly("body_rig", "Body", cc_settings.get("body_rig", "")))
    # Tattoos are carried straight from the save and cannot be edited here, but
    # showing the detected one lets the user tell "the build missed my tattoo"
    # apart from "the build has it" without opening the game.
    tattoo = _body_tattoo_summary(cc_settings)
    if tattoo:
        rows.append(readonly("body_tattoo", "Body", tattoo))
    if "cc:teeth" not in options:
        rows.append(
            readonly(
                "teeth",
                "Face",
                (cc_settings.get("teeth") or {}).get("raw", ""),
            )
        )
    for region, preset in sorted((cc_settings.get("face_morphs") or {}).items()):
        rows.append(readonly(f"face_morph_{region}", "Face morphs", preset))

    canonical = {
        selection.get("label"): selection
        for selection in cc_settings.get("selections", [])
        if selection.get("slot") == "character_customization"
    }
    for slot_id, opts in options.items():
        if not slot_id.startswith("cc:"):
            continue
        original_label = slot_id[3:]
        selection = canonical.get(original_label)
        if not selection:
            continue
        raw = selection.get("raw", "")
        rows.append(
            {
                "category": _cc_row_category(original_label),
                "slot_id": slot_id,
                "label": _cc_row_label(original_label),
                "value_label": _selection_choice_label(original_label, raw),
                "value_raw": _encoded_selection(original_label, raw),
                "editable": bool(opts),
                "options": list(opts),
            }
        )
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
            if str(value).isdigit():
                out["hair"] = {
                    "style_id": "",
                    "raw": "",
                    "vanilla_style": int(value),
                }
            else:
                out.setdefault("hair", {})["style_id"] = value
        elif slot_id == "hair_color":
            sel = _hair_color_selection(out)
            if sel is None:
                raise ValueError("hair_color override has no hair-color selection to apply to")
            sel["raw"] = value
            out.setdefault("hair", {})["mesh_appearance"] = re.sub(r"^\d+_", "", str(value))
        elif slot_id == "eye_color":
            rig = out.get("body_rig", "pwa")
            raw = f"he_000_{rig}__basehead__{value}"
            out.setdefault("eyes", {})["raw"] = raw
            for s in out.get("selections", []):
                if s.get("label") == "eyes_color":
                    s["raw"] = raw
                    s["variant"] = value
        elif slot_id == "nail_color":
            out["nails"] = {"appearance": value}
        elif slot_id == "hair_mod":
            pass  # applied last, below — must win over hair_style
        elif slot_id in GARMENT_SLOTS:
            # Garments are BuildRequest inputs, not character-customization
            # selections. The bridge splits them out before this transform in
            # normal builds; accepting them here keeps the transform robust.
            pass
        elif slot_id.startswith("cc:"):
            original_label = slot_id[3:]
            try:
                choice = json.loads(value)
                new_label = choice["label"]
                new_raw = choice["raw"]
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid character-customization override for {original_label}"
                ) from error
            selection = next(
                (
                    item
                    for item in out.get("selections", [])
                    if item.get("slot") == "character_customization"
                    and item.get("label") == original_label
                ),
                None,
            )
            if selection is None:
                raise ValueError(f"Character-customization selection not found: {original_label}")
            old_raw = selection.get("raw", "")
            replacement = decode_selection(
                "character_customization",
                new_raw,
                selection.get("cname_hash", 0),
            )
            replacement["label"] = new_label
            selection.clear()
            selection.update(replacement)

            if original_label == "teeth":
                out.setdefault("teeth", {})["raw"] = new_raw
            overlays = out.get("overlays") or []
            if old_raw in overlays:
                out["overlays"] = [
                    new_raw if item == old_raw and new_raw != "default" else item
                    for item in overlays
                    if not (item == old_raw and new_raw == "default")
                ]
        else:
            raise ValueError(f"Unknown override slot: {slot_id}")
    if "hair_mod" in overrides:
        # Loaded mods and save-selected CCXL hair share one explicit contract.
        # Applied last so it wins over hair_style regardless of dict order.
        token = overrides["hair_mod"]
        selected = hair_from_selections(out.get("selections", []))
        out["hair"] = {
            "kind": "modded",
            "selection_label": token,
            "mesh_appearance": selected.get("mesh_appearance", ""),
            "style_id": token,
            "raw": token,
            "vanilla_style": 0,
        }
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
        if slot_id in GARMENT_SLOTS:
            if isinstance(value, str):
                if not value.strip():
                    problems.append(f"{slot_id}: empty garment mesh")
            elif not isinstance(value, dict):
                problems.append(f"{slot_id}: invalid garment selection")
            continue
        opts = options.get(slot_id)
        option_values = [
            option.get("value") if isinstance(option, dict) else option for option in (opts or [])
        ]
        if slot_id.startswith("cc:") and not opts:
            problems.append(f"{slot_id}: customization option is unavailable")
        elif slot_id not in EDITABLE_SLOTS and not slot_id.startswith("cc:"):
            problems.append(f"Unknown override slot: {slot_id}")
        elif opts and value not in option_values:
            problems.append(f"{slot_id}: '{value}' is not a known option")
    return problems


def option_lists(
    index: dict | None, body_rig: str, cc_settings: dict | None = None
) -> dict[str, list]:
    """Derive per-slot option lists from the part-resolver index.
    Returns {} when the index is unavailable (rows then render read-only)."""
    if not index:
        return {}
    part_ents = index.get("part_ents", {})
    app_appearances = index.get("app_appearances", {})

    hair_re = re.compile(rf"^hh_\d+_{body_rig}__")
    indexed_hair_stems = sorted(n for n in part_ents if hair_re.match(n) and not n.endswith("_fpp"))
    hair_style = _verified_vanilla_hair_styles(part_ents, body_rig) or indexed_hair_stems

    def app_suffixes(app_prefix: str) -> list[str]:
        """Find app matching (with or without rig) and return suffixes for this rig."""
        # Try direct match first (test case: he_000_pwa__basehead.app)
        for app_path, names in app_appearances.items():
            base = app_path.replace("\\", "/").rsplit("/", 1)[-1]
            if base.startswith(app_prefix):
                return sorted({n.split("__")[-1] for n in names if "__" in n})
        # Fallback: match without rig suffix (real index: he_000__basehead.app)
        # and filter names by rig. Prefer exact app.app over variants like _face_rig.app
        app_prefix_no_rig = app_prefix.replace(f"_{body_rig}", "")
        exact_match = f"{app_prefix_no_rig}.app"
        for app_path, names in app_appearances.items():
            base = app_path.replace("\\", "/").rsplit("/", 1)[-1]
            if base == exact_match:
                # Filter to appearances that include this rig
                rig_names = [n for n in names if f"_{body_rig}__" in n]
                return sorted({n.split("__")[-1] for n in rig_names if "__" in n})
        return []

    hair_color: set[str] = set()
    hair_app_re = re.compile(rf"^hh_\d+_{body_rig}\b")
    for app_path, names in app_appearances.items():
        base = app_path.replace("\\", "/").rsplit("/", 1)[-1]
        if hair_app_re.match(base):
            hair_color.update(n for n in names if "__" not in n)

    hair_color_list = sorted(hair_color)
    if not hair_color_list:
        hair_color_list = _vendored_hair_colors()

    out = {
        "hair_style": hair_style,
        "eye_color": app_suffixes(f"he_000_{body_rig}__basehead"),
        "skin_tone": app_suffixes(f"h0_000_{body_rig}__basehead"),
        "hair_color": hair_color_list,
    }
    if cc_settings and _nail_appearance(cc_settings):
        out["nail_color"] = _vendored_nail_colors()
    if cc_settings:
        out.update(_character_customization_options(index, body_rig, cc_settings))
    return {k: v for k, v in out.items() if v}


def _vendored_hair_colors() -> list[str]:
    """Global vanilla hair-colour constants, vendored from the game's
    hair-profile stems (custom_* NPC-specific profiles excluded).

    Fallback for the index-derived hair_color list: the real part index
    contains no hh_* apps, so that derivation always yields [] against a
    real (non-empty) index. See amended plan note, Task 2 review finding
    2026-07-19."""
    path = Path(__file__).parents[1] / "data" / "hair_colors.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return []


def _vendored_nail_colors() -> list[str]:
    path = Path(__file__).parents[1] / "data" / "nail_colors.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _verified_vanilla_hair_styles(part_ents: dict, body_rig: str) -> list[str]:
    path = Path(__file__).parents[1] / "data" / "mappings" / "vanilla_hair.json"
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [
        str(style)
        for style, stem in sorted(table.get(body_rig, {}).items(), key=lambda item: int(item[0]))
        if stem in part_ents
    ]
