import struct

import lz4.block
import pytest


@pytest.fixture(autouse=True)
def _isolate_user_dirs(tmp_path, monkeypatch):
    """Tests must never touch the real ~/.config/npv or ~/.cache/npv."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


def _on_disk(tag: str) -> bytes:
    return tag.encode("ascii")[::-1]


def _lpfxd_str(s: str) -> bytes:
    if not s:
        return bytes([0])
    n = len(s)
    assert n < 0x40
    return bytes([n | 0x80]) + s.encode("latin-1")


def _packed_int(n: int) -> bytes:
    assert 0 <= n < 0x40
    return bytes([n])


def _build_cc_node() -> bytes:
    """A valid minimal CC binary node for v3=195 (see tests/test_save_parser.py)."""
    cc_node = bytearray()
    cc_node.extend(struct.pack("<I", 1176))  # node_header
    cc_node.append(1)  # data_exists
    cc_node.extend(struct.pack("<I", 0))  # uk0
    cc_node.extend(struct.pack("<I", 0))  # uk1
    cc_node.append(0)  # uk2
    cc_node.append(0)  # uk3
    cc_node.extend(struct.pack("<I", 1))  # ukt0 (head Group): 1 slot
    cc_node.extend(_lpfxd_str("head"))  # label
    cc_node.extend(struct.pack("<I", 1))  # v3_count = 1 selection
    cc_node.extend(struct.pack("<Q", 987654321))  # cn hash
    cc_node.extend(_lpfxd_str("h0_000_pwa__basehead__01_ca_pale"))  # uk0 appearance
    cc_node.extend(_lpfxd_str(""))  # uk1 secondary
    cc_node.extend(struct.pack("<I", 0))  # uk2
    cc_node.extend(struct.pack("<I", 0))  # uk3
    cc_node.extend(struct.pack("<I", 0))  # v4_count = 0
    cc_node.extend(struct.pack("<I", 0))  # ukt1 (body Group): 0 slots
    cc_node.extend(struct.pack("<I", 0))  # ukt2 (arms Group): 0 slots
    cc_node.extend(struct.pack("<I", 0))  # ukt5_count
    cc_node.append(0)  # uk6_count (v1 > 171), packed_int 0
    return bytes(cc_node)


def _build_synth_save_bytes(build: int = 2310, v1: int = 269, v3: int = 195) -> bytes:
    """Build a valid minimal CSAV container as real bytes (round-trips through
    SaveContainer), containing a CC node plus one filler node.
    """
    cc_bytes = _build_cc_node()
    other_bytes = b"hello world node data"
    nodedata = cc_bytes + other_bytes

    comp = lz4.block.compress(nodedata, mode="default", store_size=False)
    dsize = len(nodedata)
    size_field = 8 + len(comp)  # XLZ4 tag(4) + u32(4) + compressed bytes

    out = bytearray()
    out.extend(_on_disk("CSAV"))
    out.extend(struct.pack("<I", v1))
    out.extend(struct.pack("<I", build))
    out.extend(_lpfxd_str("suk"))
    out.extend(struct.pack("<I", 0))  # uk0
    out.extend(struct.pack("<I", 0))  # uk1
    if v1 >= 83:
        out.extend(struct.pack("<I", v3))

    chunk_offset = len(out)
    out.extend(_on_disk("XLZ4"))
    out.extend(struct.pack("<I", dsize))
    out.extend(comp)

    nodedescs_start = len(out)
    out.extend(_on_disk("NODE"))
    out.extend(_packed_int(2))

    out.extend(_lpfxd_str("CharacetrCustomization_Appearances"))
    out.extend(struct.pack("<i", -1))
    out.extend(struct.pack("<i", -1))
    out.extend(struct.pack("<I", 0))
    out.extend(struct.pack("<I", len(cc_bytes)))

    out.extend(_lpfxd_str("otherNode"))
    out.extend(struct.pack("<i", -1))
    out.extend(struct.pack("<i", -1))
    out.extend(struct.pack("<I", len(cc_bytes)))
    out.extend(struct.pack("<I", len(other_bytes)))

    out.extend(b"FZLC")  # searched for literally in SaveContainer._parse
    out.extend(struct.pack("<I", 1))
    out.extend(struct.pack("<I", chunk_offset))
    out.extend(struct.pack("<I", size_field))
    out.extend(struct.pack("<I", dsize))

    out.extend(struct.pack("<I", nodedescs_start))
    out.extend(_on_disk("DONE"))
    return bytes(out)


@pytest.fixture
def synth_save_2310(tmp_path):
    """Path to a synthesized, on-disk build-2310 (patch 2.13) save file."""
    path = tmp_path / "sav.dat"
    path.write_bytes(_build_synth_save_bytes(build=2310))
    return path


@pytest.fixture
def make_synth_save(tmp_path):
    """Factory fixture: make_synth_save(build=9999) -> Path, for non-2310 builds."""

    def _make(build: int = 2310, v1: int = 269, v3: int = 195):
        path = tmp_path / f"sav-{build}.dat"
        path.write_bytes(_build_synth_save_bytes(build=build, v1=v1, v3=v3))
        return path

    return _make
