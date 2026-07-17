import pytest

import npv_build.save_parser as sp
from npv_build.core.errors import UnsupportedPatchError


def test_registry_has_195():
    assert 195 in sp.CC_DECODERS
    assert callable(sp.CC_DECODERS[195])


def test_unknown_v3_raises_unsupported_patch(synth_save_2310, monkeypatch):
    # Force the container to report an unknown struct version.
    real_init = sp.SaveContainer.__init__

    def fake_init(self, data):
        real_init(self, data)
        self.version = (self.version[0], self.version[1], 999)

    monkeypatch.setattr(sp.SaveContainer, "__init__", fake_init)
    with pytest.raises(UnsupportedPatchError) as ei:
        sp.parse_save(synth_save_2310)
    msg = str(ei.value)
    assert "999" in msg
    assert "195" in msg  # supported list named
    assert "--probe-save" in ei.value.remediation


def test_v195_still_parses(synth_save_2310):
    result = sp.parse_save(synth_save_2310)
    assert isinstance(result, dict)


def test_detect_patch_known():
    assert sp.detect_patch((269, 2310, 195)) == "2.13"


def test_detect_patch_unknown_build_raises():
    with pytest.raises(UnsupportedPatchError) as ei:
        sp.detect_patch((269, 9999, 195))
    assert "9999" in str(ei.value)
    assert "2310" in str(ei.value)
    assert ei.value.remediation
