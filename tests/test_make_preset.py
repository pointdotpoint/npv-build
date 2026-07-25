import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from make_preset import make_preset  # noqa: E402


def test_make_preset_roundtrips_parser_output(synth_save_2310):
    preset = make_preset(synth_save_2310, "pwa")
    assert preset["body_rig"] == "pwa"
    assert preset["selections"]
    json.dumps(preset)


def test_make_preset_rejects_rig_mismatch(synth_save_2310):
    with pytest.raises(SystemExit):
        make_preset(synth_save_2310, "pma")
