import json
import logging
import shutil
import tempfile
from pathlib import Path

from .config import get_cache_dir
from .core.errors import NpvError, ToolError
from .core.proc import run_tool

logger = logging.getLogger(__name__)


class ResolverError(NpvError):
    def __init__(self, user_message: str, **kwargs) -> None:
        kwargs.setdefault("module_name", "Part Resolver")
        super().__init__(user_message, **kwargs)


def get_index_path(patch: str) -> Path:
    return get_cache_dir() / "index" / f"{patch}.json"


def get_mock_index() -> dict:
    return {
        "part_ents": {
            "h0_000_pwa__basehead": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pwa__basehead.ent",
            "h0_000_pma__basehead": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\h0_000_pma__basehead.ent",
            "he_000_pwa__basehead": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\he_000_pwa__basehead.ent",
            "he_000_pma__basehead": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\he_000_pma__basehead.ent",
            "ht_000_pwa__basehead": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\ht_000_pwa__basehead.ent",
            "ht_000_pma__basehead": "base\\characters\\head\\player_base_heads\\appearances\\entity\\head\\ht_000_pma__basehead.ent",
            "heb_000_pwa__basehead": "base\\characters\\head\\player_base_heads\\appearances\\entity\\face_decals\\heb_000_pwa__basehead.ent",
            "heb_000_pma__basehead": "base\\characters\\head\\player_base_heads\\appearances\\entity\\face_decals\\heb_000_pma__basehead.ent",
            "hx_000_pwa__scars_01": "base\\characters\\head\\player_base_heads\\appearances\\entity\\scars\\hx_000_pwa__scars_01.ent",
            "hx_000_pma__scars_01": "base\\characters\\head\\player_base_heads\\appearances\\entity\\scars\\hx_000_pma__scars_01.ent",
        },
        "head_apps": {
            "h0_000__basehead": "base\\characters\\head\\player_base_heads\\appearances\\head\\h0_000__basehead.app",
            "he_000__basehead": "base\\characters\\head\\player_base_heads\\appearances\\head\\he_000__basehead.app",
        },
        "app_appearances": {
            "base\\characters\\head\\player_base_heads\\appearances\\head\\h0_000__basehead.app": [
                "h0_000_pwa__basehead__01_ca_pale",
                "h0_000_pma__basehead__01_ca_pale",
            ]
        },
    }


def generate_index(game_dir: Path, index_path: Path, verbosity: int = 0, wk=None) -> dict:
    if not game_dir:
        raise ResolverError("No game directory configured, cannot index archives.")

    archive_path = game_dir / "archive" / "pc" / "content" / "basegame_4_appearance.archive"
    if not archive_path.exists():
        raise ResolverError(f"basegame_4_appearance.archive not found in {archive_path.parent}")

    logger.info(f"[Indexer] Scanning basegame_4_appearance.archive at {archive_path}...")

    if wk:
        raw_lines = wk.list_archive(r".*\.(ent|app)", archive=archive_path)
    else:
        cli_binary = shutil.which("WolvenKit.CLI") or "WolvenKit.CLI"
        cmd = [cli_binary, "archive", str(archive_path), "-l", "--regex", r".*\.(ent|app)"]
        try:
            res = run_tool(cmd, tool="WolvenKit.CLI", timeout=600.0, logger=logger)
        except ToolError as e:
            raise ResolverError(f"WolvenKit archive list failed: {e.user_message}") from e
        raw_lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]

    depot_paths = [
        line
        for line in raw_lines
        if (line.endswith(".ent") or line.endswith(".app")) and line.startswith("base\\")
    ]

    part_ents = {}
    head_apps = {}

    def depot_stem(path):
        base = path.replace("\\", "/").rsplit("/", 1)[-1]
        return base.rsplit(".", 1)[0]

    for p in depot_paths:
        if p.endswith(".ent") and "player_base_heads" in p:
            part_ents[depot_stem(p)] = p
        elif p.endswith(".app") and "player_base_heads" in p and "appearances\\head" in p:
            head_apps[depot_stem(p)] = p

    head_app_paths = [
        p
        for p in depot_paths
        if p.endswith(".app") and "player_base_heads" in p and "appearances\\head" in p
    ]

    app_appearances = {}
    appearance_to_app = {}

    uncook_regex = r"base\\characters\\head\\player_base_heads\\appearances\\head\\.*\.app$"

    if wk:
        temp_dir_path = wk.uncook_many(uncook_regex)
    else:
        cli_binary = shutil.which("WolvenKit.CLI") or "WolvenKit.CLI"
        temp_dir_path = Path(tempfile.mkdtemp(prefix="wk_index_"))
        try:
            run_tool(
                [
                    cli_binary,
                    "uncook",
                    "-p",
                    str(archive_path),
                    "-r",
                    uncook_regex,
                    "-o",
                    str(temp_dir_path),
                    "-s",
                ],
                tool="WolvenKit.CLI",
                timeout=600.0,
                logger=logger,
            )
        except BaseException:
            shutil.rmtree(temp_dir_path, ignore_errors=True)
            raise

    try:
        logger.info(f"[Indexer] Uncooking {len(head_app_paths)} head appearance .app files...")

        for p in head_app_paths:
            json_file = temp_dir_path / (p.replace("\\", "/") + ".json")
            if not json_file.exists():
                continue
            try:
                with open(json_file) as f:
                    app_data = json.load(f)
                appearances = app_data.get("Data", {}).get("RootChunk", {}).get("appearances", [])
                names = []
                for app in appearances:
                    name_val = app.get("Data", {}).get("name", {}).get("$value")
                    if name_val:
                        names.append(name_val)
                        appearance_to_app.setdefault(name_val, [])
                        if p not in appearance_to_app[name_val]:
                            appearance_to_app[name_val].append(p)
                app_appearances[p] = names
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"[Indexer] failed to parse uncooked head app {p}: {e}")
    finally:
        shutil.rmtree(temp_dir_path, ignore_errors=True)

    index_data = {
        "part_ents": part_ents,
        "head_apps": head_apps,
        "app_appearances": app_appearances,
        "appearance_to_app": appearance_to_app,
    }

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2)

    return index_data


def resolve_appearance_to_app(index: dict, selection: str, slot_label: str = "") -> str:
    """Pick the .app that actually contains V's selection's shape variant.

    The same appearance NAME (e.g. "01_black" makeup, or "female__03_ginger_copper"
    eyebrow colour) lives in many `.app`s — one per shape/style. The selection
    string and/or its uk1 label encode which shape V picked:
      hx_000_pwa__basehead_makeup_eyes__01_black     -> shape "01" -> ..._01.app
      hx_000_pwa__basehead__makeup_lips_01__01_black -> shape "01" -> ..._01.app
      female__03_ginger_copper (label: eyebrows_color5) -> shape "05" -> ..._05.app

    Returns the best-matching .app depot path, or "".
    """
    import re as _re

    a2a = index.get("appearance_to_app", {})
    raw = a2a.get(selection)
    # Backwards-compat: old index stored a single string. Normalize to list.
    if isinstance(raw, str):
        return raw
    candidates = list(raw or [])
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]

    # 1. Extract the shape number from the selection itself, if encoded.
    #    The shape is the NN that appears *immediately before* the __<color>
    #    suffix and is part of the FEATURE token, e.g.
    #      ...makeup_eyes__01_black   -> shape 01 (eyes_01.app)
    #      ...makeup_lips_01__01_black -> shape 01 (lips_01.app; the inner _01)
    #      ...pimples_01__black_02     -> shape 01
    #    For selections without a feature-side shape (e.g. tattoo "w__01_ca_pale"
    #    where 01_ca_pale is purely a colour), we leave sel_shape None and rely
    #    on slot_label.
    sel_shape = None
    # feature_NN__ pattern: an NN that sits between a non-color feature token
    # and a __ separator.
    m = _re.search(
        r"(?:eyes|lips|cheeks|freckles|pimples|cyberware|tattoo|scars)_(\d{2})__", selection
    )
    if m:
        sel_shape = m.group(1)

    # 2. Slot label encodes the option index for many features (e.g.
    #    "eyebrows_color5", "facial_tattoo_08", "makeupCheeks_04"). When the
    #    label and selection disagree, prefer label for feature shape.
    label_shape = None
    if slot_label:
        m = _re.search(r"(\d+)$", slot_label)
        if m:
            label_shape = m.group(1).zfill(2)

    def app_shape(app_path):
        # Last numeric token in the app filename, e.g. ..._makeup_eyes_06.app -> "06"
        stem = app_path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        nums = _re.findall(r"_(\d+)", stem)
        return nums[-1].zfill(2) if nums else None

    # Label shape (V's actual CC option index, e.g. makeupLips_08, eyebrows_color5,
    # facial_tattoo_08) is the authoritative shape selector. Many appearance
    # names are duplicated across all shape .apps (e.g. "01_black" lives in
    # every lips_NN.app), so the appearance name alone is insufficient.
    # sel_shape is a weaker secondary signal used only when label has no number.
    for shape in (label_shape, sel_shape):
        if not shape:
            continue
        for c in candidates:
            if app_shape(c) == shape:
                return c
    return sorted(candidates, key=lambda c: app_shape(c) or "99")[0]


def _depot_to_fs(temp_dir: Path, depot_path: str) -> Path:
    rel = depot_path.replace("\\", "/")
    return temp_dir / (rel + ".json")


def extract_recipe(game_dir: Path, feature_apps: dict, verbosity: int = 0, wk=None) -> dict:
    """Pull the exact partsValues + partsOverrides for V's chosen appearances.

    A facial feature's material/variant (skin tone, eye colour, makeup colour,
    brow colour) lives in `partsOverrides[].componentsOverrides[].meshAppearance`
    inside the feature's own `.app`. We copy those appearance bodies verbatim and
    merge their parts + overrides into one NPV appearance, so the NPV reproduces
    V's face with correct materials rather than engine defaults.

    feature_apps: { app_depot_path: appearance_name_to_extract }
    Returns { "parts": [partsValues...], "overrides": [partsOverrides...] }.
    """
    if not game_dir:
        return {"parts": [], "overrides": []}

    archive_path = game_dir / "archive" / "pc" / "content" / "basegame_4_appearance.archive"
    if not archive_path.exists():
        return {"parts": [], "overrides": []}

    cli_binary = shutil.which("WolvenKit.CLI") or "WolvenKit.CLI"
    merged_parts = []
    merged_overrides = []
    seen_part_paths = set()

    import re as _re

    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        if not feature_apps:
            return {"parts": [], "overrides": []}
        # Match each feature .app by its full depot path basename (they live in
        # varied subdirs: makeup_eyes\, eyebrows\, etc.), so anchor on the
        # filename. Escape regex-special chars in stems.
        basenames = sorted({app.replace("\\", "/").rsplit("/", 1)[-1] for app in feature_apps})
        alt = "|".join(_re.escape(b) for b in basenames)
        regex = r"appearances\\head\\.*(" + alt + r")$"
        if wk:
            try:
                wk.uncook_many(regex, archive=archive_path, dest=temp_dir)
            except ToolError as e:
                raise ResolverError(
                    f"Failed to uncook required base-game archive {archive_path.name}: {e}"
                ) from e
        else:
            cmd = [
                cli_binary,
                "uncook",
                "-p",
                str(archive_path),
                "-r",
                regex,
                "-o",
                str(temp_dir),
                "-s",
            ]
            try:
                run_tool(cmd, tool="WolvenKit.CLI", timeout=600.0, logger=logger)
            except ToolError as e:
                raise ResolverError(
                    f"Failed to uncook required base-game archive {archive_path.name}: {e}"
                ) from e

        for app_depot, want_name in feature_apps.items():
            jf = _depot_to_fs(temp_dir, app_depot)
            if not jf.exists():
                logger.info(f"[Recipe] missing uncooked {app_depot}")
                continue
            try:
                data = json.load(open(jf))
            except (OSError, json.JSONDecodeError):
                continue
            apps = data.get("Data", {}).get("RootChunk", {}).get("appearances", [])
            target = None
            for a in apps:
                if a.get("Data", {}).get("name", {}).get("$value") == want_name:
                    target = a["Data"]
                    break
            if target is None:
                logger.info(f"[Recipe] appearance '{want_name}' not in {app_depot}")
                continue
            for pv in target.get("partsValues", []):
                path = pv.get("resource", {}).get("DepotPath", {}).get("$value", "")
                if path and path not in seen_part_paths:
                    seen_part_paths.add(path)
                    merged_parts.append(pv)
            for ov in target.get("partsOverrides", []):
                merged_overrides.append(ov)
            logger.info(
                f"[Recipe]   {want_name}: +{len(target.get('partsValues', []))} parts, "
                f"+{len(target.get('partsOverrides', []))} overrides"
            )

    # Remap each override's componentName values to the part's REAL component
    # names. The recipe's overrides were copied from cooked head .apps where
    # the componentName referred to a sibling component in the head's own
    # cooked compiledData (e.g. "MorphTargetSkinnedMesh7243"). When the part is
    # standalone, its own component has a different name. Without remap, the
    # override applies to a nonexistent component and the material variant
    # (skin tone, makeup colour, freckle colour) is silently dropped.
    _remap_override_component_names(game_dir, merged_overrides, verbosity, wk=wk)

    return {"parts": merged_parts, "overrides": merged_overrides}


def _remap_override_component_names(game_dir: Path, overrides, verbosity: int = 0, wk=None):
    if not game_dir or not overrides:
        return
    cli_binary = shutil.which("WolvenKit.CLI") or "WolvenKit.CLI"
    archive = game_dir / "archive" / "pc" / "content" / "basegame_4_appearance.archive"
    if not archive.exists():
        return
    # Collect referenced part .ent depot paths.
    part_paths = []
    for ov in overrides:
        pr = ov.get("partResource", {}).get("DepotPath", {}).get("$value", "")
        if pr and pr.endswith(".ent") and pr not in part_paths:
            part_paths.append(pr)
    if not part_paths:
        return
    import re as _re

    basenames = sorted({p.replace("\\", "/").rsplit("/", 1)[-1] for p in part_paths})
    alt = "|".join(_re.escape(b) for b in basenames)
    regex = r"(" + alt + r")$"

    component_names = {}  # part_depot -> [mesh component names]
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        if wk:
            try:
                wk.uncook_many(regex, archive=archive, dest=temp_dir)
            except ToolError as e:
                raise ResolverError(
                    f"Failed to uncook required base-game archive {archive.name}: {e}"
                ) from e
        else:
            try:
                run_tool(
                    [
                        cli_binary,
                        "uncook",
                        "-p",
                        str(archive),
                        "-r",
                        regex,
                        "-o",
                        str(temp_dir),
                        "-s",
                    ],
                    tool="WolvenKit.CLI",
                    timeout=600.0,
                    logger=logger,
                )
            except ToolError as e:
                raise ResolverError(
                    f"Failed to uncook required base-game archive {archive.name}: {e}"
                ) from e
        for p in part_paths:
            jf = temp_dir / (p.replace("\\", "/") + ".json")
            if not jf.exists():
                cands = list(temp_dir.rglob(p.replace("\\", "/").rsplit("/", 1)[-1] + ".json"))
                if cands:
                    jf = cands[0]
                else:
                    continue
            try:
                d = json.load(open(jf))
            except (OSError, json.JSONDecodeError):
                continue
            names = []
            chunks = (
                d.get("Data", {})
                .get("RootChunk", {})
                .get("compiledData", {})
                .get("Data", {})
                .get("Chunks", [])
            )
            if not chunks:
                chunks = d.get("Data", {}).get("RootChunk", {}).get("components", [])
            for c in chunks:
                t = c.get("$type", "")
                if "Mesh" in t:
                    nm = c.get("name", {}).get("$value") if isinstance(c.get("name"), dict) else ""
                    if not nm:
                        nm = c.get("name", "")
                    if nm:
                        names.append(nm)
            if names:
                component_names[p] = names

    fixed = 0
    for ov in overrides:
        pr = ov.get("partResource", {}).get("DepotPath", {}).get("$value", "")
        real = component_names.get(pr)
        if not real:
            continue
        real_set = set(real)
        for co in ov.get("componentsOverrides", []):
            cn = co.get("componentName", {})
            cn_v = cn.get("$value", "") if isinstance(cn, dict) else ""
            if cn_v and cn_v not in real_set:
                # Pick the first real component name as the rebind target.
                cn["$value"] = real[0]
                fixed += 1
    if fixed:
        logger.info(f"[Recipe] remapped {fixed} override componentName(s) to real part components")


def extract_hair_components(
    game_dir: Path, hair_mesh_name: str, body_rig: str = "pwa", verbosity: int = 0, wk=None
):
    """Find a (modded) hair .app across all mod archives whose appearance carries
    the given hair name, and return its entSkinnedMeshComponent chunks so we can
    author a hair part .ent. Returns ([components], source_archive_name) or ([], None).

    hair_mesh_name e.g. 'fhair_miyavivi_twistup_soft' (from save uk1). The mod's
    .app is often named slightly differently (fhair_miyavi_twistup_soft), so we
    match by the meaningful tokens.
    """
    if not game_dir:
        return [], None, None, None
    mod_dir = game_dir / "archive" / "pc" / "mod"
    if not mod_dir.exists():
        return [], None, None, None

    cli_binary = shutil.which("WolvenKit.CLI") or "WolvenKit.CLI"

    # Normalise: strip fhair_/mhair_ prefix, split into tokens for fuzzy match.
    base = hair_mesh_name
    for pre in ("fhair_", "mhair_"):
        if base.startswith(pre):
            base = base[len(pre) :]
            break
    tokens = [t for t in base.split("_") if t and t not in ("soft", "fpp")]
    gender_pref = "fhair_" if body_rig == "pwa" else "mhair_"

    # Pre-filter archives by FILENAME or XL sidecar content.
    all_arch = sorted(mod_dir.glob("*.archive"))

    def name_matches(arch):
        low = arch.name.lower()
        hits = sum(1 for t in tokens if t in low)
        return hits >= max(1, len(tokens) - 1)

    candidates = [a for a in all_arch if name_matches(a)]

    # Also search .xl sidecar files for the hair name (CCXL hairs register there)
    if not candidates:
        hair_search = "_".join(tokens)
        for xl in mod_dir.glob("*.xl"):
            try:
                text = xl.read_text(errors="ignore").lower()
                if hair_search in text or base in text:
                    arch = xl.with_suffix(".archive")
                    if arch.exists() and arch not in candidates:
                        candidates.append(arch)
            except OSError:
                pass

    if not candidates:
        candidates = [a for a in all_arch if "hair" in a.name.lower()]
    logger.info(f"[Hair] scanning {len(candidates)} candidate archive(s) of {len(all_arch)}")

    # Find candidate archives whose listing contains a matching hair .app.
    best = None  # (archive_path, app_depot)
    for arch in candidates:
        try:
            if wk:
                lines = wk.list_archive(r".*\.app$", archive=arch)
            else:
                res = run_tool(
                    [cli_binary, "archive", str(arch), "-l", "--regex", r".*\.app$"],
                    tool="WolvenKit.CLI",
                    timeout=600.0,
                    logger=logger,
                )
                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except ToolError as e:
            logger.warning("Skipping mod archive %s: %s", arch.name, e.user_message)
            continue
        for p in lines:
            if not p.endswith(".app") or "\\fpp\\" in p:
                continue
            low = p.lower()
            if all(t in low for t in tokens) and "hair" in low:
                # prefer the gender-correct, non-cyb/shaved, soft if requested
                score = 0
                bn = p.replace("\\", "/").rsplit("/", 1)[-1].lower()
                if bn.startswith(gender_pref):
                    score += 4
                if "soft" in hair_mesh_name and "soft" in bn:
                    score += 2
                if "cyb" not in bn and "shaved" not in bn:
                    score += 1
                if best is None or score > best[2]:
                    best = (arch, p, score)
    if not best:
        logger.info(f"[Hair] no mod .app matched tokens {tokens}")
        return [], None, None, None

    arch, app_depot, _ = best
    logger.info(f"[Hair] matched {app_depot} in {arch.name}")

    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        bn = app_depot.replace("\\", "/").rsplit("/", 1)[-1]
        import re as _re

        rgx = _re.escape(bn) + r"$"
        try:
            if wk:
                wk.uncook_many(rgx, archive=arch, dest=Path(td))
            else:
                run_tool(
                    [cli_binary, "uncook", "-p", str(arch), "-r", rgx, "-o", str(temp_dir), "-s"],
                    tool="WolvenKit.CLI",
                    timeout=600.0,
                    logger=logger,
                )
        except ToolError as e:
            logger.warning("Skipping mod archive %s: %s", arch.name, e.user_message)
            return [], None, None, None
        jf = temp_dir / (app_depot.replace("\\", "/") + ".json")
        if not jf.exists():
            # fall back: search any uncooked json
            cands = list(temp_dir.rglob(bn + ".json"))
            if not cands:
                return [], None, None, None
            jf = cands[0]
        try:
            data = json.load(open(jf))
        except (OSError, json.JSONDecodeError):
            return [], None, None, None
        apps = data.get("Data", {}).get("RootChunk", {}).get("appearances", [])
        if not apps:
            return [], None, None, None
        a0 = apps[0].get("Data", {})
        chunks = a0.get("compiledData", {}).get("Data", {}).get("Chunks", [])
        mesh_chunks = [
            c
            for c in chunks
            if c.get("$type") in ("entSkinnedMeshComponent", "entAnimatedComponent")
        ]
        logger.info(f"[Hair] extracted {len(mesh_chunks)} hair components")
        # Also return the source .app depot path + appearance name so the
        # caller can choose to attach via app-reference instead of copying
        # components (which loses parentTransform/rig bindings).
        return mesh_chunks, arch.name, app_depot, a0.get("name", {}).get("$value", "")


def get_or_create_index(
    patch: str, game_dir: Path = None, reindex: bool = False, verbosity: int = 0, wk=None
) -> dict:
    index_path = get_index_path(patch)

    if not reindex and index_path.exists():
        try:
            with open(index_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    try:
        return generate_index(game_dir, index_path, verbosity, wk=wk)
    except ResolverError as e:
        logger.info(f"[Indexer] Scan failed: {e}. Falling back to mock/embedded index.")
        return get_mock_index()
