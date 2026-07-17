import json
from pathlib import Path

import pytest
from conftest import synth_save_from_cc_node

from npv_build.save_parser import parse_save

_FIX = Path(__file__).resolve().parents[1] / "fixtures"
_CC_NODE = _FIX / "sample_2.31_cc_node.bin"
_GOLDEN = _FIX / "sample_2.31.cc.json"

pytestmark = pytest.mark.skipif(
    not (_CC_NODE.exists() and _GOLDEN.exists()),
    reason=(
        "real 2.31 CC-node fixture not present - place sample_2.31_cc_node.bin "
        "and sample_2.31.cc.json under tests/fixtures/ to run this test"
    ),
)


def test_golden_2_31_save_parses(tmp_path):
    cc_node_bytes = _CC_NODE.read_bytes()
    save_bytes = synth_save_from_cc_node(cc_node_bytes, build=2310, v1=269, v3=195)
    save_path = tmp_path / "sav.dat"
    save_path.write_bytes(save_bytes)

    d = parse_save(save_path)
    golden = json.loads(_GOLDEN.read_text())
    for k, v in golden.items():
        assert d[k] == v
    assert d["patch"] == "2.31"
    assert "body_rig" in d
    assert "selections" in d and len(d["selections"]) > 0
