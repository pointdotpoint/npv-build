import json
import logging
import re
import struct
from collections.abc import Callable
from pathlib import Path

from .core.errors import UnsupportedPatchError
from .save_format import SaveContainer, SaveFormatError, _Reader

logger = logging.getLogger(__name__)


class SaveParserError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.module_name = "Save Parser"


class _CCReader(_Reader):
    def __init__(self, data: bytes, pos: int = 0):
        super().__init__(data, pos)

    def u64(self):
        v = struct.unpack_from("<Q", self.data, self.pos)[0]
        self.pos += 8
        return v


class Thing5:
    def __init__(self, reader):
        self.uk0 = reader.read_str_lpfxd()
        self.uk1 = reader.read_str_lpfxd()
        self.uk2 = reader.read_str_lpfxd()


class Link:
    def __init__(self, reader):
        self.uk0 = reader.read_str_lpfxd()
        self.uk1 = reader.read_str_lpfxd()
        self.uk2 = reader.u32()
        self.uk3 = reader.u32()


class Sel:
    def __init__(self, reader, v3_version):
        if v3_version == 195:
            self.cn = reader.u64()
        else:
            self.cn = reader.read_str_lpfxd()
        self.uk0 = reader.read_str_lpfxd()
        self.uk1 = reader.read_str_lpfxd()
        self.uk2 = reader.u32()
        self.uk3 = reader.u32()


class Slot:
    def __init__(self, reader, v3_version):
        self.uks = reader.read_str_lpfxd()
        v3_count = reader.u32()
        self.v3 = [Sel(reader, v3_version) for _ in range(v3_count)]
        v4_count = reader.u32()
        self.v4 = [Link(reader) for _ in range(v4_count)]


class Group:
    def __init__(self, reader, v3_version):
        count = reader.u32()
        self.slots = [Slot(reader, v3_version) for _ in range(count)]


class CCharacterCustomization:
    def __init__(self, reader, version):
        v1, v2, v3 = version
        # 4-byte node-data header precedes the CCharacterCustomization struct in
        # the persisted node (a length/id; observed value 1176). PixelRick's
        # node_reader strips it before from_node_impl runs, so the struct grammar
        # in the header file starts after it. Skip it here.
        self.node_header = reader.u32()
        self.data_exists = reader.u8()
        self.uk0 = reader.u32()
        self.ukt0 = None
        self.ukt1 = None
        self.ukt2 = None
        self.ukt5 = []
        self.uk6 = []

        if self.data_exists:
            self.uk1 = reader.u32()
            self.uk2 = reader.u8()
            self.uk3 = reader.u8()
            self.ukt0 = Group(reader, v3)
            self.ukt1 = Group(reader, v3)
            self.ukt2 = Group(reader, v3)
            ukt5_count = reader.u32()
            self.ukt5 = [Thing5(reader) for _ in range(ukt5_count)]
            if v1 > 171:
                uk6_count = reader.read_int64_packed()
                self.uk6 = [reader.read_str_lpfxd() for _ in range(uk6_count)]


def detect_patch(version: tuple) -> str:
    v1, v2, v3 = version
    versions_file = Path(__file__).parent / "data" / "save_versions.json"
    supported_builds = []
    if versions_file.exists():
        try:
            with open(versions_file) as f:
                versions = json.load(f)
            supported_builds = sorted(versions.keys())
            v2_str = str(v2)
            if v2_str in versions:
                return versions[v2_str]
        except (OSError, json.JSONDecodeError):
            pass
    # Build number not found: hard-fail with remediation
    supported_str = ", ".join(supported_builds) if supported_builds else "none configured"
    raise UnsupportedPatchError(
        f"Game build {v2} is not supported. Supported builds: {supported_str}.",
        remediation="Run `npv-build --probe-save <sav.dat>` and open an issue with the output.",
        module_name="Save Parser",
    )


def decode_selection(slot_label: str, raw: str, cn_hash: int = 0) -> dict:
    prefix = ""
    index = 0
    rig = ""
    group = ""
    variant = ""

    parts = raw.split("__")
    header = parts[0]

    match = re.match(r"^([a-zA-Z0-9]+)_([0-9]{3})(?:_([a-zA-Z0-9]+))?$", header)
    if match:
        prefix = match.group(1)
        index = int(match.group(2))
        rig = match.group(3) or ""
    else:
        if header.startswith("fhair_"):
            prefix = "fhair"
            group = header[6:]
        else:
            for p in ["h0", "he", "ht", "hb", "hx", "i1", "t0", "a0", "l0", "n0", "fhair"]:
                if header.startswith(p):
                    prefix = p
                    break

    if len(parts) > 1:
        if not group:
            group = parts[1]
    if len(parts) > 2:
        variant = parts[2]

    return {
        "slot": slot_label,
        "prefix": prefix,
        "index": index,
        "rig": rig,
        "group": group,
        "variant": variant,
        "raw": raw,
        "cname_hash": cn_hash,
    }


def _decode_cc_v195(sc: SaveContainer) -> dict:
    raw = sc.node_bytes("CharacetrCustomization_Appearances")
    if raw is None:
        raise SaveParserError("no CC node — is this a character save?")

    v1, v2, v3 = sc.version
    try:
        reader = _CCReader(raw)
        cc = CCharacterCustomization(reader, sc.version)
        if reader.pos > len(raw):
            raise SaveParserError(
                f"CC layout mismatch: read past end of data. Cursor: {reader.pos}, Length: {len(raw)}"
            )
        leftover = len(raw) - reader.pos
        if leftover > 0 and v3 != 195:
            raise SaveParserError(
                f"CC layout mismatch for save version {sc.version}; parser targets v3=195. Leftover bytes: {leftover}"
            )
    except Exception as e:
        if isinstance(e, SaveParserError):
            raise
        raise SaveParserError(
            f"CC layout mismatch for save version {sc.version}; parser targets v3=195. Original error: {e}"
        ) from e

    # The 'character_customization' slot is the authoritative CC source; the
    # TPP/FPP/photomode slots are render-time duplicates. Each Sel there pairs
    # uk0 (the appearance/resource name) with uk1 (a semantic label such as
    # skin_type_05, eyes_color, teeth, makeupEyes_31, or the hair mesh name).
    cc_entries = []  # authoritative list of {label(uk1), resource(uk0), cn}
    selections = []  # full decoded list (all slots) for diagnostics + resolver
    face_morphs = {}  # {region: morph_name} e.g. {"jaw":"h114","nose":"h042"}
    for g in [cc.ukt0, cc.ukt1, cc.ukt2]:
        if g is None:
            continue
        for slot in g.slots:
            for sel in slot.v3:
                if not sel.uk0:
                    continue
                decoded = decode_selection(slot.uks, sel.uk0, getattr(sel, "cn", 0))
                decoded["label"] = getattr(sel, "uk1", "") or ""
                selections.append(decoded)
                if slot.uks == "character_customization":
                    cc_entries.append(decoded)
            # v4 Links on the customization slot carry the face sub-shape morph
            # selections: region (uk0: eyes/nose/mouth/jaw/ear) -> morph name
            # (uk1: e.g. h114). These are morph targets in the head .morphtarget.
            if slot.uks == "character_customization":
                for link in getattr(slot, "v4", []):
                    region = (getattr(link, "uk0", "") or "").lower()
                    morph = getattr(link, "uk1", "") or ""
                    if region in ("eyes", "nose", "mouth", "jaw", "ear") and morph:
                        face_morphs[region] = morph

    def by_label(*needles):
        for e in cc_entries:
            lbl = (e.get("label") or "").lower()
            if any(n in lbl for n in needles):
                return e
        for e in selections:
            lbl = (e.get("label") or "").lower()
            if any(n in lbl for n in needles):
                return e
        return None

    def by_prefix_in_cc(prefix, exclude_substr=None):
        for e in cc_entries:
            if e["prefix"] == prefix:
                if exclude_substr and exclude_substr in e["raw"]:
                    continue
                return e
        for e in selections:
            if e["prefix"] == prefix:
                if exclude_substr and exclude_substr in e["raw"]:
                    continue
                return e
        return None

    # Head: the tone-bearing basehead variant (skin_type label), not face_rig.
    head_sel = by_label("skin_type") or by_prefix_in_cc("h0", exclude_substr="face_rig")
    eyes_sel = by_label("eyes_color")
    teeth_sel = by_label("teeth")
    # Hair label is the mesh name itself (e.g. fhair_miyavivi_twistup_soft or
    # edie_hair for CCXL hairs); uk0 there is the colour ("62_molten_marmalade").
    hair_entry = next((e for e in cc_entries if (e.get("label") or "").startswith("fhair_")), None)
    if not hair_entry:
        hair_entry = next(
            (
                e
                for e in cc_entries
                if (e.get("label") or "").endswith("_hair")
                and not (e.get("label") or "").endswith("_fpp")
                and e.get("raw", "") != "default"
            ),
            None,
        )

    body_rig = "pwa"
    for sel in selections:
        if "pma" in sel["raw"] or "_ma_" in sel["raw"]:
            body_rig = "pma"
            break
        if "pwa" in sel["raw"] or "_wa_" in sel["raw"]:
            body_rig = "pwa"
            break

    skin_tone = head_sel["variant"] if (head_sel and head_sel.get("variant")) else ""

    hair_style = ""
    hair_raw = ""
    if hair_entry:
        hair_mesh = hair_entry.get("label", "")  # fhair_miyavivi_twistup_soft or edie_hair
        hair_raw = hair_mesh
        if hair_mesh.startswith("fhair_"):
            hair_style = hair_mesh[6:]
        elif hair_mesh.endswith("_hair"):
            hair_style = hair_mesh[:-5]
        else:
            hair_style = hair_mesh

    cc_settings = {
        "patch": detect_patch(sc.version),
        "body_rig": body_rig,
        "selections": selections,
        "head": {
            "preset_id": head_sel["index"] if head_sel else 0,
            "raw": head_sel["raw"] if head_sel else "",
        },
        "eyes": {"raw": eyes_sel["raw"] if eyes_sel else ""},
        "teeth": {"raw": teeth_sel["raw"] if teeth_sel else ""},
        "skin": {"tone_id": skin_tone},
        "hair": {"style_id": hair_style, "raw": hair_raw},
        "overlays": [e["raw"] for e in cc_entries if e["prefix"] == "hx"],
        "face_morphs": face_morphs,  # {region: morph_name} for Blender bake
    }

    return cc_settings


CC_DECODERS: dict[int, Callable[[SaveContainer], dict]] = {195: _decode_cc_v195}


def _resolve_decoder(v3: int) -> Callable[[SaveContainer], dict]:
    decoder = CC_DECODERS.get(v3)
    if decoder is None:
        supported = ", ".join(str(k) for k in sorted(CC_DECODERS))
        raise UnsupportedPatchError(
            f"This save's character-customization struct version (v3={v3}) is not supported "
            f"(supported: {supported}).",
            remediation=(
                "The game patch is newer than this npv-build release. "
                "Run `npv-build --probe-save <sav.dat>` and open an issue with the output."
            ),
            module_name="Save Parser",
        )
    return decoder


def parse_save(save_path: Path) -> dict:
    if not save_path.exists():
        raise SaveParserError(f"Save file not found: {save_path}")

    try:
        data = save_path.read_bytes()
    except Exception as e:
        raise SaveParserError(f"Failed to read save file: {e}") from e

    try:
        sc = SaveContainer(data)
    except SaveFormatError as e:
        raise SaveParserError(f"Save format error: {e}") from e
    except Exception as e:
        raise SaveParserError(f"Unexpected container parse error: {e}") from e

    _v1, _v2, v3 = sc.version
    decoder = _resolve_decoder(v3)
    return decoder(sc)
