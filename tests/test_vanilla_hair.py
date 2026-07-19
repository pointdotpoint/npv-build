"""Vanilla hairstyle support: parse the CC style number from the save's
hairs-slot label and resolve it to a vanilla hh_ part .ent via the vendored
style table (data/mappings/vanilla_hair.json)."""

import struct

import npv_build.part_resolver as part_resolver
import npv_build.save_parser as save_parser
from npv_build.mapping import resolve_assets

# ---------------------------------------------------------------- parser ----


def test_vanilla_hair_style_cyberware_label():
    # Default female V: hairs slot pairs the colour (uk0) with the style-bearing
    # label hair_color_cyberware_01 -> CC hairstyle 01.
    sels = [
        {"slot": "hairs", "label": "hair_color_cyberware_01", "raw": "15_pink_magenta"},
        {"slot": "FPP_hairs", "label": "hair_color_fpp_01", "raw": "default"},
    ]
    assert save_parser.vanilla_hair_style_from_selections(sels) == 1


def test_vanilla_hair_style_plain_label():
    # Styles without a cyberware variant use hair_colorN (no zero padding).
    sels = [{"slot": "hairs", "label": "hair_color3", "raw": "06_black_carbon"}]
    assert save_parser.vanilla_hair_style_from_selections(sels) == 3


def test_vanilla_hair_style_ignores_fpp_and_modded():
    sels = [
        {"slot": "FPP_hairs", "label": "hair_color_fpp_01", "raw": "default"},
        {"slot": "hairs", "label": "fhair_miyavivi_twistup_soft", "raw": "62_molten_marmalade"},
    ]
    assert save_parser.vanilla_hair_style_from_selections(sels) == 0


def test_parse_save_vanilla_hair(monkeypatch):
    """End-to-end through _decode_cc_v195: a hairs slot with a vanilla label
    must surface hair.vanilla_style in cc_settings."""

    def lpfxd(s):
        if not s:
            return b"\x00"
        return struct.pack("B", len(s) | 0x80) + s.encode("ascii")

    cc_node = bytearray()
    cc_node.extend(struct.pack("<I", 1176))  # node_header
    cc_node.append(1)  # data_exists
    cc_node.extend(struct.pack("<I", 0))  # uk0
    cc_node.extend(struct.pack("<I", 0))  # uk1
    cc_node.append(0)  # uk2
    cc_node.append(0)  # uk3

    # ukt0: head slot + hairs slot
    cc_node.extend(struct.pack("<I", 2))
    cc_node.extend(lpfxd("head"))
    cc_node.extend(struct.pack("<I", 1))
    cc_node.extend(struct.pack("<Q", 987654321))
    cc_node.extend(lpfxd("h0_000_pwa__basehead__03_ca_senna"))
    cc_node.extend(lpfxd(""))
    cc_node.extend(struct.pack("<I", 0))
    cc_node.extend(struct.pack("<I", 0))
    cc_node.extend(struct.pack("<I", 0))  # v4_count

    cc_node.extend(lpfxd("hairs"))
    cc_node.extend(struct.pack("<I", 1))
    cc_node.extend(struct.pack("<Q", 6178364890966597469))
    cc_node.extend(lpfxd("15_pink_magenta"))  # uk0 = colour
    cc_node.extend(lpfxd("hair_color_cyberware_01"))  # uk1 = style label
    cc_node.extend(struct.pack("<I", 0))
    cc_node.extend(struct.pack("<I", 0))
    cc_node.extend(struct.pack("<I", 0))  # v4_count

    cc_node.extend(struct.pack("<I", 0))  # ukt1
    cc_node.extend(struct.pack("<I", 0))  # ukt2
    cc_node.extend(struct.pack("<I", 0))  # ukt5_count
    cc_node.append(0)  # uk6_count

    class MockSaveContainer:
        def __init__(self, data):
            self.version = (269, 2310, 195)

        def node_bytes(self, name):
            if name == "CharacetrCustomization_Appearances":
                return bytes(cc_node)
            return None

    monkeypatch.setattr(save_parser, "SaveContainer", MockSaveContainer)

    class MockPath:
        name = "dummy.sav.dat"

        def exists(self):
            return True

        def read_bytes(self):
            return b"dummy"

    res = save_parser.parse_save(MockPath())

    assert res["hair"]["style_id"] == ""  # not modded hair
    assert res["hair"]["vanilla_style"] == 1


# --------------------------------------------------------------- mapping ----


_FAKE_INDEX = {
    "part_ents": {
        "hh_001_pwa__hairs_033": (
            "base\\characters\\head\\player_base_heads\\appearances"
            "\\entity\\hairs\\hh_001_pwa__hairs_033.ent"
        ),
    },
    "head_apps": {},
    "app_appearances": {},
    "appearance_to_app": {},
}


def _vanilla_cc(vanilla_style=1):
    return {
        "patch": "2.13",
        "body_rig": "pwa",
        "hair": {"style_id": "", "raw": "", "vanilla_style": vanilla_style},
        "selections": [
            {
                "slot": "hairs",
                "prefix": "",
                "index": 0,
                "rig": "",
                "group": "",
                "variant": "",
                "raw": "15_pink_magenta",
                "cname_hash": 0,
                "label": "hair_color_cyberware_01",
            },
        ],
    }


def test_resolve_assets_vanilla_hair(monkeypatch):
    monkeypatch.setattr(part_resolver, "get_or_create_index", lambda *a, **k: _FAKE_INDEX)

    assets = resolve_assets(_vanilla_cc())

    assert assets["vanilla_hair_ent"].endswith("hh_001_pwa__hairs_033.ent")
    assert assets["hair_color"] == "pink_magenta"
    # Vanilla hair must NOT be routed through part_entities (the hair section
    # of the assembler owns colour + dangle binding).
    assert not any("hh_001" in p for p in assets["part_entities"])


def test_resolve_assets_vanilla_hair_override_none_wins(monkeypatch):
    monkeypatch.setattr(part_resolver, "get_or_create_index", lambda *a, **k: _FAKE_INDEX)

    assets = resolve_assets(_vanilla_cc(), hair_override="none")

    assert not assets.get("vanilla_hair_ent")


# ------------------------------------------------------------- assembler ----


def test_load_vanilla_hair_components_returns_raw_chunks():
    """The vanilla hair .ent's raw chunks must flow into the same
    hair-components pipeline the modded flow uses (colour + dangle binding)."""
    from npv_build.wolvenkit import _load_vanilla_hair_components

    ent_json = {
        "Data": {
            "RootChunk": {
                "compiledData": {
                    "Data": {
                        "Chunks": [
                            {"$type": "entEntity"},
                            {
                                "$type": "entAnimatedComponent",
                                "name": {"$value": "hair_dangle"},
                                "graph": {"DepotPath": {"$value": "base\\x_dangle.animgraph"}},
                                "rig": {"DepotPath": {"$value": "base\\x_dangle.rig"}},
                            },
                            {
                                "$type": "entSkinnedMeshComponent",
                                "name": {"$value": "hh_033_wa__player"},
                                "meshAppearance": {"$value": "pink_rose"},
                                "mesh": {"DepotPath": {"$value": "base\\hh_033_wa__player.mesh"}},
                            },
                        ]
                    }
                }
            }
        }
    }

    class FakeWk:
        def uncook_json(self, basename):
            assert basename == "hh_001_pwa__hairs_033.ent"
            return ent_json

    chunks = _load_vanilla_hair_components(
        FakeWk(),
        "base\\characters\\head\\player_base_heads\\appearances"
        "\\entity\\hairs\\hh_001_pwa__hairs_033.ent",
    )

    types = [c.get("$type") for c in chunks]
    assert "entAnimatedComponent" in types
    assert "entSkinnedMeshComponent" in types


def test_resolve_assets_vanilla_hair_unknown_style(monkeypatch):
    monkeypatch.setattr(part_resolver, "get_or_create_index", lambda *a, **k: _FAKE_INDEX)

    assets = resolve_assets(_vanilla_cc(vanilla_style=2))  # style 2 ent not in fake index

    assert not assets.get("vanilla_hair_ent")
    assert any("vanilla_hair" in u for u in assets["unresolved"])
