import struct
from pathlib import Path

import lz4.block
import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def fixture_path(name: str) -> Path:
    """Resolve a path under tests/fixtures/ by filename."""
    return FIXTURES_DIR / name


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


def _wrap_cc_node_in_container(
    cc_bytes: bytes, build: int = 2310, v1: int = 269, v3: int = 195
) -> bytes:
    """Wrap arbitrary CC node bytes (synthetic or real, extracted via
    SaveContainer.node_bytes) into a valid on-disk CSAV container that
    round-trips through SaveContainer / parse_save, containing the CC node
    plus one filler node.
    """
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

    # NodeDesc.data_offset is an absolute index into the *decompressed blob*,
    # which SaveContainer._parse() sizes/addresses starting at chunk_offset
    # (the file offset of the first XLZ4 chunk) rather than 0 - confirmed
    # against a real save's node descriptors (e.g. GameSessionDesc at offset
    # ~6177, matching its chunk's file offset, not 0). Node offsets must be
    # chunk_offset-relative to round-trip correctly.
    out.extend(_lpfxd_str("CharacetrCustomization_Appearances"))
    out.extend(struct.pack("<i", -1))
    out.extend(struct.pack("<i", -1))
    out.extend(struct.pack("<I", chunk_offset))
    out.extend(struct.pack("<I", len(cc_bytes)))

    out.extend(_lpfxd_str("otherNode"))
    out.extend(struct.pack("<i", -1))
    out.extend(struct.pack("<i", -1))
    out.extend(struct.pack("<I", chunk_offset + len(cc_bytes)))
    out.extend(struct.pack("<I", len(other_bytes)))

    out.extend(b"FZLC")  # searched for literally in SaveContainer._parse
    out.extend(struct.pack("<I", 1))
    out.extend(struct.pack("<I", chunk_offset))
    out.extend(struct.pack("<I", size_field))
    out.extend(struct.pack("<I", dsize))

    out.extend(struct.pack("<I", nodedescs_start))
    out.extend(_on_disk("DONE"))
    return bytes(out)


def _build_synth_save_bytes(build: int = 2310, v1: int = 269, v3: int = 195) -> bytes:
    """Build a valid minimal CSAV container as real bytes (round-trips through
    SaveContainer), containing a synthetic CC node plus one filler node.
    """
    return _wrap_cc_node_in_container(_build_cc_node(), build=build, v1=v1, v3=v3)


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


def synth_save_from_cc_node(cc_node_bytes: bytes, build: int = 2310, v1: int = 269, v3: int = 195):
    """Wrap arbitrary (e.g. real, extracted-from-a-user-save) CC node bytes into
    valid on-disk CSAV container bytes. Callers write the result to a tmp_path
    and pass it to parse_save(). Not a pytest fixture itself (needs a bytes
    argument), just a helper importable from tests via `from conftest import
    synth_save_from_cc_node` / package-relative import.
    """
    return _wrap_cc_node_in_container(cc_node_bytes, build=build, v1=v1, v3=v3)
