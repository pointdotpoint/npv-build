import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import make_preset as preset_script  # noqa: E402
from make_preset import make_preset  # noqa: E402


def test_make_preset_roundtrips_parser_output(synth_save_2310):
    preset = make_preset(synth_save_2310, "pwa")
    assert preset["body_rig"] == "pwa"
    assert preset["selections"]
    json.dumps(preset)


def test_make_preset_rejects_rig_mismatch(synth_save_2310):
    with pytest.raises(SystemExit):
        make_preset(synth_save_2310, "pma")


def test_cli_writes_named_vendorable_preset(
    synth_save_2310,
    monkeypatch,
    tmp_path,
):
    preset_dir = tmp_path / "presets"
    monkeypatch.setattr(preset_script, "PRESET_DIR", preset_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["make_preset.py", str(synth_save_2310), "pwa"],
    )

    preset_script.main()

    output = preset_dir / "default_v_pwa.json"
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["body_rig"] == "pwa"
