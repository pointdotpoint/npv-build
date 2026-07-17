"""Tests for post-import morphtarget verification (spec PC-6, guards WK#849).

Payload shape confirmed against a REAL WolvenKit 8.19.0 serialize() of a
freshly-baked morphtarget (wk819_gate_e879aac4_morphs.morphtarget, 105
shapekeys): the authoritative target count lives at
Data.RootChunk.targets (a list) -- there is no numTargets scalar field.
verify_morphtarget reads len(Data.RootChunk.targets).
"""

import json

import pytest

from npv_build.core.errors import BakeVerificationError
from npv_build.head_bake import verify_morphtarget


class FakeWk:
    def __init__(self, payload):
        self._payload = payload

    def serialize(self, cr2w_file, *, dest):
        out = dest / (cr2w_file.name + ".json")
        out.write_text(json.dumps(self._payload), encoding="utf-8")
        return out


def _payload(n_targets):
    # Real shape from WolvenKit 8.19.0: Data.RootChunk.targets is a list of
    # MorphTargetMeshEntry objects; the count is len(targets).
    return {
        "Data": {
            "RootChunk": {
                "$type": "MorphTargetMesh",
                "targets": [{"$type": "MorphTargetMeshEntry"} for _ in range(n_targets)],
            }
        }
    }


def test_verify_passes_with_targets(tmp_path):
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    assert verify_morphtarget(FakeWk(_payload(35)), mt) == 35


def test_verify_raises_on_zero_targets(tmp_path):
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    with pytest.raises(BakeVerificationError) as ei:
        verify_morphtarget(FakeWk(_payload(0)), mt)
    assert "849" in ei.value.remediation


def test_verify_raises_below_expected_min(tmp_path):
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    with pytest.raises(BakeVerificationError) as ei:
        verify_morphtarget(FakeWk(_payload(3)), mt, expected_min_targets=5)
    assert "849" in ei.value.remediation
    assert "3" in str(ei.value)
    assert "5" in str(ei.value)


def test_verify_error_names_file(tmp_path):
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    with pytest.raises(BakeVerificationError) as ei:
        verify_morphtarget(FakeWk(_payload(0)), mt)
    assert "x_morphs.morphtarget" in str(ei.value)
