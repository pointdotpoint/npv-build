import json
from pathlib import Path

import pytest

from npv_build.save_parser import parse_save

_FIX = Path(__file__).resolve().parents[1] / "fixtures"
_SAVE = _FIX / "sample_2.31.sav.dat"
_GOLDEN = _FIX / "sample_2.31.cc.json"

pytestmark = pytest.mark.skipif(
    not (_SAVE.exists() and _GOLDEN.exists()),
    reason=(
        "real 2.31 save fixture not committed (privacy: full sav.dat carries quest/"
        "inventory/world state, not just CC data) - place sample_2.31.sav.dat and "
        "sample_2.31.cc.json under tests/fixtures/ to run this test locally"
    ),
)


def test_golden_2_31_save_parses():
    d = parse_save(_SAVE)
    golden = json.loads(_GOLDEN.read_text())
    for k, v in golden.items():
        assert d[k] == v
    assert d["patch"] == "2.31"
    assert "selections" in d and len(d["selections"]) > 0
