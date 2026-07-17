import struct

import npv_build.save_parser as save_parser


def test_parse_save_binary(monkeypatch):
    # Construct a valid minimal CC binary node for v3=195, v1=269, v2=2310
    def lpfxd(s):
        if not s:
            return b"\x00"
        length = len(s)
        # negative length indicator for ASCII/Latin-1
        b_len = struct.pack("B", length | 0x80)
        return b_len + s.encode("ascii")

    cc_node = bytearray()
    cc_node.extend(struct.pack("<I", 1176))  # node_header
    cc_node.append(1)  # data_exists
    cc_node.extend(struct.pack("<I", 0))  # uk0
    cc_node.extend(struct.pack("<I", 0))  # uk1
    cc_node.append(0)  # uk2
    cc_node.append(0)  # uk3

    # ukt0 (head Group)
    cc_node.extend(struct.pack("<I", 1))  # 1 slot
    # Slot 1
    cc_node.extend(lpfxd("head"))  # label
    cc_node.extend(struct.pack("<I", 1))  # v3_count = 1 selection
    # Sel 1
    cc_node.extend(struct.pack("<Q", 987654321))  # cn hash
    cc_node.extend(lpfxd("h0_000_pwa__basehead__01_ca_pale"))  # uk0 appearance
    cc_node.extend(lpfxd(""))  # uk1 secondary
    cc_node.extend(struct.pack("<I", 0))  # uk2
    cc_node.extend(struct.pack("<I", 0))  # uk3
    cc_node.extend(struct.pack("<I", 0))  # v4_count = 0

    # ukt1 (body Group)
    cc_node.extend(struct.pack("<I", 0))  # 0 slots

    # ukt2 (arms Group)
    cc_node.extend(struct.pack("<I", 0))  # 0 slots

    # ukt5_count
    cc_node.extend(struct.pack("<I", 0))

    # uk6_count (v1 > 171)
    cc_node.append(0)  # packed_int 0

    # Mock SaveContainer
    class MockSaveContainer:
        def __init__(self, data):
            self.version = (269, 2310, 195)

        def node_bytes(self, name):
            if name == "CharacetrCustomization_Appearances":
                return bytes(cc_node)
            return None

    monkeypatch.setattr(save_parser, "SaveContainer", MockSaveContainer)

    # Mock Path
    class MockPath:
        def __init__(self, name):
            self.name = name

        def exists(self):
            return True

        def read_bytes(self):
            return b"dummy_save_bytes"

    res = save_parser.parse_save(MockPath("dummy.sav.dat"))

    assert res["patch"] == "2.13"
    assert res["body_rig"] == "pwa"
    assert res["head"]["preset_id"] == 0
    assert res["head"]["raw"] == "h0_000_pwa__basehead__01_ca_pale"
    assert res["skin"]["tone_id"] == "01_ca_pale"
