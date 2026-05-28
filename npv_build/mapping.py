import json
from pathlib import Path


class MappingError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.module_name = "Mapping"


def resolve_assets(cc_settings: dict, game_dir: Path = None, hair_override: str = None, garments: list = None, wk=None) -> dict:
    """Resolve CC settings to the list of part-entity (.ent) depot paths that
    compose the NPV's appearance via partsValues.

    CP2077 appearances are built by referencing per-part .ent files (head base,
    eyes, teeth, brows, body, hair) — not by editing cooked meshes. We collect
    those paths here; the generator authors an uncooked .app whose appearance's
    partsValues point at them, which WolvenKit then cooks.
    """
    patch = cc_settings.get("patch")
    if not patch:
        raise MappingError("No patch version found in CC settings.")

    mapping_file = Path(__file__).parent / "data" / "mappings" / f"{patch}.json"
    if not mapping_file.exists():
        raise MappingError(f"MappingNotFoundError: no mapping vendored for patch {patch}.")

    with open(mapping_file, "r") as f:
        mapping = json.load(f)

    body_rig = cc_settings.get("body_rig")
    if body_rig not in mapping:
        raise MappingError(f"Body rig {body_rig} not found in mapping for patch {patch}.")

    rig_map = mapping[body_rig]

    # Load Tier 1 index via part_resolver
    from .part_resolver import get_or_create_index

    index = get_or_create_index(patch, game_dir=game_dir, verbosity=1, wk=wk)

    asset_paths = {
        "patch": patch,
        "body_rig": body_rig,
        "head_app": "",
        "head_appearance_name": "",
        "part_entities": [],
        "external_dependencies": [],
        "unresolved": [],
    }

    part_entities = []
    selections = cc_settings.get("selections", [])

    # 1. Resolve head preset part .ent (Form A: head .app + tone appearance name).
    # Use the parser's authoritative head roll-up (the tone-bearing
    # "..__NN_ca_*" variant), NOT the first raw h0 selection (which is face_rig).
    head_info = cc_settings.get("head", {})
    head_raw = head_info.get("raw", "")  # e.g. h0_000_pwa__basehead__01_ca_pale
    head_index = head_info.get("preset_id", 0)
    if not head_raw:
        for s in selections:
            if s.get("slot") == "head" or s.get("prefix") == "h0":
                head_raw = s.get("raw", "")
                head_index = s.get("index", 0)
                break
    if head_raw:
        head_key = f"h0_{str(head_index).zfill(3)}_{body_rig}__basehead"
        if head_key in index.get("part_ents", {}):
            part_entities.append(index["part_ents"][head_key])
            app_key = f"h0_{str(head_index).zfill(3)}__basehead"
            if app_key in index.get("head_apps", {}):
                asset_paths["head_app"] = index["head_apps"][app_key]
                asset_paths["head_appearance_name"] = head_raw
        else:
            fallback_head = rig_map.get("head_preset_parts", {}).get("00", [])
            for p in fallback_head:
                if "h0_000" in p:
                    part_entities.append(p)
                    asset_paths["head_app"] = "base\\characters\\head\\player_base_heads\\appearances\\head\\h0_000__basehead.app"
                    asset_paths["head_appearance_name"] = head_raw or f"h0_000_{body_rig}__basehead__01_ca_pale"
            asset_paths["unresolved"].append(head_raw)

    # 1b. Modded hair from the parser roll-up -> external dependency.
    hair_info = cc_settings.get("hair", {})
    hair_raw = hair_info.get("raw", "")
    hair_style = hair_info.get("style_id", "")
    if hair_raw.startswith("fhair_") or (hair_raw.endswith("_hair") and hair_style):
        asset_paths["external_dependencies"].append({
            "selection": hair_raw,
            "reason": "modded hair not in base game",
        })

    # 2. Resolve body + arms parts (Tier 2 curated)
    body_part = rig_map.get("body_part")
    if body_part:
        part_entities.append(body_part)
    arms_part = rig_map.get("arms_part")
    if arms_part:
        part_entities.append(arms_part)

    # 3. Walk through all other selections: eyes, teeth, eyebrows, overlays, hair
    for sel in selections:
        prefix = sel.get("prefix")
        if prefix == "h0":
            continue

        raw = sel.get("raw")

        if prefix == "fhair":
            asset_paths["external_dependencies"].append({
                "selection": raw,
                "reason": "modded hair not in base game",
            })
            continue

        key = f"{prefix}_{str(sel.get('index', 0)).zfill(3)}_{body_rig}__{sel.get('group', '')}"

        resolved_path = ""
        if key in index.get("part_ents", {}):
            resolved_path = index["part_ents"][key]
        else:
            key_pa = f"{prefix}_{str(sel.get('index', 0)).zfill(3)}_pa__{sel.get('group', '')}"
            if key_pa in index.get("part_ents", {}):
                resolved_path = index["part_ents"][key_pa]
            else:
                for k, p in index.get("part_ents", {}).items():
                    if k.endswith(f"__{sel.get('group', '')}") and k.startswith(f"{prefix}_"):
                        resolved_path = p
                        break

        if resolved_path:
            if resolved_path not in part_entities:
                part_entities.append(resolved_path)
        else:
            fallback_resolved = False
            fallback_parts = rig_map.get("head_preset_parts", {}).get("00", [])
            for fp in fallback_parts:
                fp_stem = Path(fp).stem
                if fp_stem.startswith(f"{prefix}_"):
                    if fp not in part_entities:
                        part_entities.append(fp)
                    fallback_resolved = True
                    break

            if not fallback_resolved:
                asset_paths["unresolved"].append(raw)

    # If the selections array was empty or mock settings are loaded, check compatibility fallbacks
    if not part_entities:
        fallback_head = rig_map.get("head_preset_parts", {}).get("00", [])
        part_entities.extend(fallback_head)
        if body_part:
            part_entities.append(body_part)

    part_entities = list(sorted(set(part_entities)))
    asset_paths["part_entities"] = part_entities

    if not asset_paths["part_entities"]:
        raise MappingError("No part entities resolved; cannot build an appearance.")

    # Recipe: pull the EXACT partsValues+partsOverrides from each facial
    # feature's .app for V's chosen appearance names. The partsOverrides carry
    # meshAppearance (skin tone / eye colour) — without them features render
    # with default materials (the "random face" symptom). Feature .app stem is
    # the selection minus rig+variant: he_000_pwa__basehead__14_gradient_grey
    # -> he_000__basehead.app, appearance name = the raw selection.
    from .part_resolver import extract_recipe

    # Build feature_apps {app_depot_path: appearance_name} for EVERY facial
    # selection V made, by reverse-looking-up each appearance name in the index's
    # appearance_to_app map. This covers head/eyes/teeth/eyebrows/makeup/freckles/
    # pimples/scars uniformly — each carries its own material override.
    appearance_to_app = index.get("appearance_to_app", {})

    # Collect candidate appearance names from the authoritative cc selections.
    candidate_names = []
    for s in selections:
        if s.get("slot") != "character_customization":
            continue
        raw = s.get("raw", "")
        # skip rigs/colour-only/non-asset rows and modded hair
        if not raw or raw in ("default",) or raw.startswith("fhair_"):
            continue
        if raw.endswith("__face_rig") or "face_rig" in raw:
            continue
        candidate_names.append(raw)
    # de-dup, preserve order
    seen_names = set()
    candidate_names = [n for n in candidate_names if not (n in seen_names or seen_names.add(n))]

    # Build {appearance_name: slot_label} from V's CC for disambiguation.
    name_to_label = {}
    for s in selections:
        if s.get("slot") == "character_customization":
            name_to_label.setdefault(s.get("raw", ""), s.get("label", ""))

    from .part_resolver import resolve_appearance_to_app

    feature_apps = {}
    for name in candidate_names:
        app_path = resolve_appearance_to_app(index, name, name_to_label.get(name, ""))
        if app_path:
            feature_apps[app_path] = name

    recipe = {"parts": [], "overrides": []}
    if feature_apps and game_dir:
        try:
            recipe = extract_recipe(game_dir, feature_apps, verbosity=1, wk=wk)
        except Exception as e:
            print(f"Warning: recipe extraction failed ({e}); falling back to plain part list.")

    asset_paths["recipe_parts"] = recipe.get("parts", [])
    asset_paths["recipe_overrides"] = recipe.get("overrides", [])

    # Face shape morphs (jaw/nose/mouth/eyes/ear) for the Blender bake step.
    asset_paths["face_morphs"] = cc_settings.get("face_morphs", {})
    asset_paths["_game_dir"] = str(game_dir) if game_dir else None

    # Hair colour: V's save stores the colour as e.g. "62_molten_marmalade"
    # (CC option index + meshAppearance name). Strip the numeric prefix.
    import re as _re
    hair_color_raw = ""
    for s in selections:
        if s.get("slot") == "character_customization":
            lbl = (s.get("label") or "").lower()
            if lbl.startswith("fhair_") or lbl.startswith("mhair_"):
                hair_color_raw = s.get("raw", "")
                break
    if not hair_color_raw:
        for s in selections:
            if s.get("slot") in ("character_customization", "hairs"):
                lbl = (s.get("label") or "").lower()
                if "hair" in lbl and "fpp" not in lbl and s.get("raw", "") != "default":
                    hair_color_raw = s.get("raw", "")
                    break
    hair_color = _re.sub(r"^\d+_", "", hair_color_raw)
    asset_paths["hair_color"] = hair_color

    # Hair resolution.
    asset_paths["hair_components"] = []

    if hair_override is not None:
        # Override forms:
        #   "none"/"bald" -> no hair
        #   integer (e.g. "1") -> vanilla hh_NNN_<rig>__... part .ent
        #   any other string -> modded hair name; extract mesh components from a
        #   mod archive whose filename matches.
        ov = hair_override.strip().lower()
        # Drop any in-save modded-hair dep note; override wins.
        asset_paths["external_dependencies"] = [
            d for d in asset_paths["external_dependencies"]
            if not d["selection"].startswith("fhair_")
        ]
        if ov in ("none", "bald", "0", ""):
            print("[Mapping] Hair override: none (NPV will be bald).")
        elif ov.isdigit():
            hair_num = ov.zfill(3)
            hair_ent = _find_vanilla_hair_ent(index, body_rig, hair_num)
            if hair_ent:
                asset_paths["part_entities"].append(hair_ent)
                asset_paths["part_entities"] = list(sorted(set(asset_paths["part_entities"])))
                print(f"[Mapping] Hair override: vanilla hh_{hair_num} -> {hair_ent.split(chr(92))[-1]}")
            else:
                asset_paths["unresolved"].append(f"hair_override:hh_{hair_num}")
                print(f"[Mapping] Hair override hh_{hair_num} not found in index.")
        elif game_dir:
            # Modded-hair name. Probe `extract_hair_components` with this token.
            from .part_resolver import extract_hair_components
            try:
                comps, src, app_depot, app_name = extract_hair_components(game_dir, ov, body_rig, verbosity=1, wk=wk)
                if app_depot:
                    # Prefer attaching the mod's cooked .app by appearance ref
                    # (rig graph stays intact). Fall back to component copy on
                    # failure to cook the wrapper.
                    asset_paths["hair_app"] = app_depot
                    asset_paths["hair_appearance_name"] = app_name
                    asset_paths["hair_components"] = comps  # kept for fallback
                    asset_paths["external_dependencies"].append({
                        "selection": ov,
                        "reason": f"modded hair from {src} (must stay installed)" if src else "modded hair (mod must stay installed)",
                    })
                    print(f"[Mapping] Hair override: modded '{ov}' -> {app_depot} '{app_name}'")
                else:
                    print(f"[Mapping] Hair override '{ov}': no matching mod archive found.")
                    asset_paths["unresolved"].append(f"hair_override:{ov}")
            except Exception as e:
                print(f"Warning: hair override extraction failed ({e}); NPV will be bald.")
    elif (hair_raw.startswith("fhair_") or (hair_raw.endswith("_hair") and hair_style)) and game_dir:
        # Modded hair: attach via the mod's cooked .app appearance reference.
        # For CCXL hairs (label like "edie_hair"), use the style_id as the search token.
        hair_search_token = hair_raw if hair_raw.startswith("fhair_") else hair_style
        from .part_resolver import extract_hair_components
        try:
            comps, src, app_depot, app_name = extract_hair_components(game_dir, hair_search_token, body_rig, verbosity=1, wk=wk)
            if app_depot:
                asset_paths["hair_app"] = app_depot
                asset_paths["hair_appearance_name"] = app_name
                asset_paths["hair_components"] = comps
                for dep in asset_paths["external_dependencies"]:
                    if dep["selection"] == hair_raw and src:
                        dep["reason"] = f"modded hair from {src} (must stay installed)"
        except Exception as e:
            print(f"Warning: hair extraction failed ({e}); NPV will be bald.")

    # Garment overrides: add explicit garment .ent depot paths as parts.
    for g in (garments or []):
        g = g.strip()
        if g and g not in asset_paths["part_entities"]:
            asset_paths["part_entities"].append(g)
            print(f"[Mapping] Garment added: {g.split(chr(92))[-1]}")

    return asset_paths


def _find_vanilla_hair_ent(index: dict, body_rig: str, hair_num: str) -> str:
    """Find a vanilla hair part .ent: hh_<num>_<rig>__hairs_*.ent (non-fpp,
    non-cyberware preferred)."""
    prefix = f"hh_{hair_num}_{body_rig}__"
    matches = [
        p for stem, p in index.get("part_ents", {}).items()
        if stem.startswith(prefix) and "fpp" not in p.lower()
    ]
    if not matches:
        return ""
    # Prefer the plain variant (no _cyberware suffix).
    plain = [m for m in matches if "cyberware" not in m.lower()]
    return (plain or matches)[0]
