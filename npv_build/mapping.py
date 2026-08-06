import json
import logging
import re
from pathlib import Path

from .core.errors import MappingResolutionError, NpvError
from .save_parser import hair_color_from_selections

logger = logging.getLogger(__name__)


class MappingError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.module_name = "Mapping"


# Skin-tone segment inside tone-keyed appearance names, e.g. the
# "__01_ca_pale" in "w__01_ca_pale". Same shape as
# gui_logic.appearance._appearance_matches_rig_and_tone.
_TONE_SEGMENT_RE = re.compile(r"__\d{2}_(?:ca|bl)_[a-z]+")

# Marketing patches that share one vendored asset-table set. CDPR kept the save
# format (build 2310 / CC struct v3=195) AND the head/appearance assets stable
# across 2.13 -> 2.31, so all of them resolve to the "2.13" tables. When a future
# patch changes the assets, vendor a new table file and drop that patch's alias.
_TABLE_ALIASES = {
    "2.31": "2.13",
    "2.3": "2.13",
    "2.21": "2.13",
    "2.2": "2.13",
}


def resolve_table_key(patch: str) -> str:
    """Map a patch label to the vendored table key whose files exist on disk.

    A patch with its own tables resolves to itself; aliased patches (which share
    assets with an earlier patch) resolve to the shared key.
    """
    return _TABLE_ALIASES.get(patch, patch)


def resolve_assets(
    cc_settings: dict,
    game_dir: Path = None,
    hair_override: str = None,
    garments: list = None,
    wk=None,
) -> dict:
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

    table_key = resolve_table_key(patch)
    mapping_file = Path(__file__).parent / "data" / "mappings" / f"{table_key}.json"
    if not mapping_file.exists():
        raise MappingError(f"MappingNotFoundError: no mapping vendored for patch {patch}.")

    with open(mapping_file) as f:
        mapping = json.load(f)

    body_rig = cc_settings.get("body_rig")
    if body_rig not in mapping:
        raise MappingError(f"Body rig {body_rig} not found in mapping for patch {patch}.")

    rig_map = mapping[body_rig]

    # Load Tier 1 index via part_resolver (keyed by the shared table key so the
    # cache is reused across aliased patches).
    from .part_resolver import get_or_create_index

    index = get_or_create_index(table_key, game_dir=game_dir, verbosity=1, wk=wk)

    asset_paths = {
        # Deliberately the RAW patch label (e.g. "2.31"), not table_key — the
        # manifest/output must report the real patch, while file lookups above
        # use the aliased table_key. Do not "simplify" this to table_key.
        "patch": patch,
        "body_rig": body_rig,
        "head_app": "",
        "head_appearance_name": "",
        "part_entities": [],
        "external_dependencies": [],
        "unresolved": [],
        "vanilla_hair_ent": "",
        "equipped_clothing": cc_settings.get("clothing", []),
        "body_tattoo": None,
        "nail_color": _nail_appearance(cc_settings),
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
            app_key = f"h0_{str(head_index).zfill(3)}__basehead"
            if app_key in index.get("head_apps", {}):
                asset_paths["head_app"] = index["head_apps"][app_key]
                asset_paths["head_appearance_name"] = head_raw
        else:
            asset_paths["head_app"] = (
                "base\\characters\\head\\player_base_heads\\appearances\\head\\h0_000__basehead.app"
            )
            asset_paths["head_appearance_name"] = (
                head_raw or f"h0_000_{body_rig}__basehead__01_ca_pale"
            )
            asset_paths["unresolved"].append(head_raw)

        # Always add the full set of head preset parts (head, eyes, teeth, eyebrows)
        preset_key = str(head_index).zfill(2)
        preset_parts = rig_map.get("head_preset_parts", {}).get(
            preset_key, rig_map.get("head_preset_parts", {}).get("00", [])
        )
        for p in preset_parts:
            # If the index has a customized head part entity for this preset, use it
            p_basename = p.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if p_basename in index.get("part_ents", {}):
                part_entities.append(index["part_ents"][p_basename])
            else:
                part_entities.append(p)

    # 1b. Modded hair from the parser roll-up -> external dependency.
    hair_info = cc_settings.get("hair", {})
    hair_raw = hair_info.get("raw", "")
    hair_style = hair_info.get("style_id", "")
    hair_kind = hair_info.get("kind")
    if not hair_kind:
        if hair_raw.startswith(("fhair_", "mhair_")) or (hair_raw.endswith("_hair") and hair_style):
            hair_kind = "modded"
        elif hair_info.get("vanilla_style"):
            hair_kind = "vanilla"
        else:
            hair_kind = "none"
    hair_selection_label = hair_info.get("selection_label") or hair_raw or hair_style
    if hair_kind == "modded":
        asset_paths["external_dependencies"].append(
            {
                "selection": hair_selection_label,
                "reason": "modded hair not in base game",
            }
        )

    # 2. Resolve body + arms parts (Tier 2 curated)
    body_part = rig_map.get("body_part")
    if body_part:
        part_entities.append(body_part)
    arms_part = rig_map.get("arms_part")
    if arms_part:
        part_entities.append(arms_part)

    # 3. Resolve canonical character-customization parts. Saves repeat the same
    # appearance across runtime slots (TPP, FPP, photomode, holstered arms,
    # proxies, and so on); those rows describe game state, not additional NPV
    # assets. The character_customization slot is the authoritative visual
    # selection set used by the recipe pass below.
    from .part_resolver import resolve_appearance_to_app

    for sel in selections:
        prefix = sel.get("prefix")
        if prefix == "h0":
            continue

        raw = sel.get("raw")
        if (
            hair_kind == "modded"
            and sel.get("label") == hair_selection_label
            and sel.get("slot") in ("hairs", "character_customization")
        ):
            continue

        if prefix == "fhair":
            asset_paths["external_dependencies"].append(
                {
                    "selection": raw,
                    "reason": "modded hair not in base game",
                }
            )
            continue

        if sel.get("slot") != "character_customization":
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

            # Some visual choices (piercings, teeth, colours, makeup) are
            # authored in .app recipes rather than as standalone part .ents.
            # Their presence in appearance_to_app is a valid resolution path.
            appearance_resolved = bool(resolve_appearance_to_app(index, raw, sel.get("label", "")))

            # Hair colour is applied by the dedicated hair path below. Arm
            # colours/nails decorate the curated arms entity added in step 2;
            # neither row names a separate part entity.
            handled_by_curated_part = prefix == "a0" or sel.get("label", "").startswith(
                "hair_color"
            )

            if (
                not fallback_resolved
                and not appearance_resolved
                and not handled_by_curated_part
                and raw != "default"
            ):
                asset_paths["unresolved"].append(raw)

    # 1c. Body tattoo: label body_tattoo_NN (slots TPP_Body/character_creation,
    # the fpp_ variant is deliberately excluded). The raw value is the
    # skin-tone-keyed tattoo appearance (e.g. w__01_ca_pale); shape NN picks
    # the tx_ overlay part .ent. The assembler applies the appearance
    # (_apply_body_tattoo).
    for sel in selections:
        m = re.match(r"^body_tattoo_(\d+)$", sel.get("label", "") or "")
        if m and sel.get("raw"):
            shape = m.group(1).zfill(2)
            appearance = sel["raw"]
            tone_id = (cc_settings.get("skin") or {}).get("tone_id") or ""
            if tone_id:
                rekeyed = _TONE_SEGMENT_RE.sub(f"__{tone_id}", appearance)
                if rekeyed != appearance:
                    logger.info(
                        f"[Mapping] Body tattoo re-keyed to effective skin tone: "
                        f"{appearance} -> {rekeyed}"
                    )
                appearance = rekeyed
            asset_paths["body_tattoo"] = {"shape": shape, "appearance": appearance}
            tx_ent = (
                "base\\characters\\common\\player_base_bodies\\appearances\\entity\\"
                f"tx_000_{body_rig}_base__full_tattoo_{shape}.ent"
            )
            part_entities.append(tx_ent)
            logger.info(f"[Mapping] Body tattoo {shape} -> {appearance}")
            break

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

    # Collect candidate appearance names from the authoritative cc selections.
    candidate_names = []
    for s in selections:
        if s.get("slot") != "character_customization":
            continue
        if hair_kind == "modded" and s.get("label") == hair_selection_label:
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

    feature_apps = {}
    for name in candidate_names:
        app_path = resolve_appearance_to_app(index, name, name_to_label.get(name, ""))
        if app_path:
            feature_apps[app_path] = name

    recipe = {"parts": [], "overrides": []}
    if feature_apps and game_dir:
        recipe = extract_recipe(game_dir, feature_apps, verbosity=1, wk=wk)

    asset_paths["recipe_parts"] = recipe.get("parts", [])
    asset_paths["recipe_overrides"] = recipe.get("overrides", [])

    # Face shape morphs (jaw/nose/mouth/eyes/ear) for the Blender bake step.
    asset_paths["face_morphs"] = cc_settings.get("face_morphs", {})
    asset_paths["_game_dir"] = str(game_dir) if game_dir else None

    hair_color = hair_info.get("mesh_appearance") or hair_color_from_selections(selections)
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
            d
            for d in asset_paths["external_dependencies"]
            if not d["selection"].startswith("fhair_")
        ]
        if ov in ("none", "bald", "0", ""):
            logger.info("[Mapping] Hair override: none (NPV will be bald).")
        elif ov.isdigit():
            hair_num = ov.zfill(3)
            hair_ent = _find_vanilla_hair_ent(index, body_rig, hair_num)
            if hair_ent:
                asset_paths["part_entities"].append(hair_ent)
                asset_paths["part_entities"] = list(sorted(set(asset_paths["part_entities"])))
                logger.info(
                    f"[Mapping] Hair override: vanilla hh_{hair_num} -> {hair_ent.split(chr(92))[-1]}"
                )
            else:
                asset_paths["unresolved"].append(f"hair_override:hh_{hair_num}")
                logger.info(f"[Mapping] Hair override hh_{hair_num} not found in index.")
        elif game_dir:
            # Modded-hair name. Probe `extract_hair_components` with this token.
            from .part_resolver import extract_hair_components

            try:
                comps, src, app_depot, app_name = extract_hair_components(
                    game_dir, ov, body_rig, verbosity=1, wk=wk
                )
            except (NpvError, OSError, TypeError) as e:
                raise MappingResolutionError(
                    f"Could not load selected hair '{ov}'.",
                    remediation=(
                        "Reinstall or load the hair mod, then confirm its files are under "
                        f"{game_dir / 'archive' / 'pc' / 'mod'}."
                    ),
                    details=str(e),
                    module_name="Mapping",
                ) from e
            if not app_depot:
                raise MappingResolutionError(
                    f"Could not find the installed .app for selected hair '{ov}'.",
                    remediation=(
                        "Reinstall or load the hair mod, then confirm its files are under "
                        f"{game_dir / 'archive' / 'pc' / 'mod'}."
                    ),
                    module_name="Mapping",
                )
            # Prefer attaching the mod's cooked .app by appearance ref
            # (rig graph stays intact). Fall back to component copy on
            # failure to cook the wrapper.
            asset_paths["hair_app"] = app_depot
            asset_paths["hair_appearance_name"] = app_name
            asset_paths["hair_components"] = comps  # kept for fallback
            asset_paths["external_dependencies"].append(
                {
                    "selection": ov,
                    "reason": f"modded hair from {src} (must stay installed)"
                    if src
                    else "modded hair (mod must stay installed)",
                }
            )
            logger.info(f"[Mapping] Hair override: modded '{ov}' -> {app_depot} '{app_name}'")
    elif hair_kind == "modded" and game_dir:
        # Modded hair: attach via the mod's cooked .app appearance reference.
        hair_search_token = hair_selection_label
        from .part_resolver import extract_hair_components

        try:
            comps, src, app_depot, app_name = extract_hair_components(
                game_dir, hair_search_token, body_rig, verbosity=1, wk=wk
            )
        except (NpvError, OSError, TypeError) as e:
            raise MappingResolutionError(
                f"Could not load selected hair '{hair_selection_label}'.",
                remediation=(
                    "Reinstall or load the hair mod, then confirm its files are under "
                    f"{game_dir / 'archive' / 'pc' / 'mod'}."
                ),
                details=str(e),
                module_name="Mapping",
            ) from e
        if not app_depot:
            raise MappingResolutionError(
                f"Could not find the installed .app for selected hair '{hair_selection_label}'.",
                remediation=(
                    "Reinstall or load the hair mod, then confirm its files are under "
                    f"{game_dir / 'archive' / 'pc' / 'mod'}."
                ),
                module_name="Mapping",
            )
        asset_paths["hair_app"] = app_depot
        asset_paths["hair_appearance_name"] = app_name
        asset_paths["hair_components"] = comps
        for dep in asset_paths["external_dependencies"]:
            if dep["selection"] == hair_selection_label and src:
                dep["reason"] = f"modded hair from {src} (must stay installed)"
    elif hair_kind == "unknown":
        raise MappingResolutionError(
            (f"Could not interpret selected hair record '{hair_selection_label or 'unknown'}'."),
            remediation=(
                "Return to Appearance and reselect the hairstyle, or explicitly "
                "choose the bald/no-hair option."
            ),
            module_name="Mapping",
        )
    elif hair_kind in ("vanilla", "none"):
        # Vanilla hairstyle from the save (no override, no modded hair). The
        # ent goes into vanilla_hair_ent — NOT part_entities — so the
        # assembler's hair section owns colour + dangle binding.
        vanilla_style = int(hair_info.get("vanilla_style") or 0)
        if vanilla_style:
            hair_ent = _vanilla_hair_ent_for_style(index, body_rig, vanilla_style)
            if hair_ent:
                asset_paths["vanilla_hair_ent"] = hair_ent
                logger.info(
                    f"[Mapping] Vanilla hair: style {vanilla_style:02d} -> "
                    f"{hair_ent.split(chr(92))[-1]}"
                )
            else:
                asset_paths["unresolved"].append(f"vanilla_hair:style_{vanilla_style:02d}")
                logger.info(
                    f"[Mapping] Vanilla hair style {vanilla_style:02d} not in index; "
                    "NPV will be bald."
                )

    # Legacy CLI garment .ent paths are resolved as part entities. Structured
    # catalog selections (and legacy raw .mesh values) are authored later by
    # clothing.resolve_clothing and must not be uncooked as entities.
    for g in garments or []:
        if not isinstance(g, str):
            continue
        g = g.strip()
        if g.lower().endswith(".ent") and g not in asset_paths["part_entities"]:
            asset_paths["part_entities"].append(g)
            logger.info(f"[Mapping] Garment added: {g.split(chr(92))[-1]}")

    return asset_paths


def _vanilla_hair_ent_for_style(index: dict, body_rig: str, style_num: int) -> str:
    """CC hairstyle number (1-51) -> depot path of the vanilla hair part .ent,
    via the vendored style table. Only index-verified paths are returned
    (hard-fail policy): "" when the style or its ent is unknown."""
    table_file = Path(__file__).parent / "data" / "mappings" / "vanilla_hair.json"
    if not table_file.exists():
        return ""
    with open(table_file) as f:
        table = json.load(f)
    stem = table.get(body_rig, {}).get(str(style_num), "")
    return index.get("part_ents", {}).get(stem, "") if stem else ""


def _find_vanilla_hair_ent(index: dict, body_rig: str, hair_num: str) -> str:
    """Find a vanilla hair part .ent: hh_<num>_<rig>__hairs_*.ent (non-fpp,
    non-cyberware preferred)."""
    prefix = f"hh_{hair_num}_{body_rig}__"
    matches = [
        p
        for stem, p in index.get("part_ents", {}).items()
        if stem.startswith(prefix) and "fpp" not in p.lower()
    ]
    if not matches:
        return ""
    # Prefer the plain variant (no _cyberware suffix).
    plain = [m for m in matches if "cyberware" not in m.lower()]
    return (plain or matches)[0]


def _nail_appearance(cc_settings: dict) -> str:
    configured = (cc_settings.get("nails") or {}).get("appearance", "")
    if configured:
        return configured
    for selection in cc_settings.get("selections", []):
        if selection.get("slot") == "character_customization" and "nails_color" in (
            selection.get("label") or ""
        ):
            parts = selection.get("raw", "").split("__")
            if len(parts) < 2:
                return ""
            appearance = parts[1].removeprefix("nails_")
            if len(parts) > 2 and parts[2]:
                appearance += f"__{parts[2]}"
            return appearance
    return ""
