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
        verify_morphtarget(FakeWk(_payload(3)), mt, expected_targets=5)
    assert "849" in ei.value.remediation
    assert "3" in str(ei.value)
    assert "5" in str(ei.value)


def test_verify_error_names_file(tmp_path):
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    with pytest.raises(BakeVerificationError) as ei:
        verify_morphtarget(FakeWk(_payload(0)), mt)
    assert "x_morphs.morphtarget" in str(ei.value)


def test_verify_raises_on_partial_loss_matching_wk849_pattern(tmp_path):
    """WK#849 typically drops SOME channels (e.g. 105 -> 40), not all — a bare
    non-zero floor would pass this. expected_targets must catch it."""
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    with pytest.raises(BakeVerificationError) as ei:
        verify_morphtarget(FakeWk(_payload(40)), mt, expected_targets=105)
    assert "849" in ei.value.remediation
    assert "40" in str(ei.value)
    assert "105" in str(ei.value)


def test_verify_passes_when_cooked_matches_source_count(tmp_path):
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    assert verify_morphtarget(FakeWk(_payload(105)), mt, expected_targets=105) == 105


def test_verify_falls_back_to_min_one_when_expected_unknown(tmp_path):
    """When the source count can't be determined, don't crash — fall back to a
    bare 'at least one target' floor."""
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    assert verify_morphtarget(FakeWk(_payload(2)), mt, expected_targets=None) == 2

    with pytest.raises(BakeVerificationError):
        verify_morphtarget(FakeWk(_payload(0)), mt, expected_targets=None)


def test_verify_raises_distinct_error_when_targets_key_absent(tmp_path):
    """An absent 'targets' key means an unexpected WolvenKit JSON schema, not
    the known WK#849 partial-loss pattern — the message must say so distinctly."""
    mt = tmp_path / "x_morphs.morphtarget"
    mt.write_bytes(b"\x00")
    payload_missing_key = {
        "Data": {
            "RootChunk": {
                "$type": "MorphTargetMesh",
                # no "targets" key at all
            }
        }
    }
    with pytest.raises(BakeVerificationError) as ei:
        verify_morphtarget(FakeWk(payload_missing_key), mt, expected_targets=105)
    assert "849" not in ei.value.remediation
    assert "schema" in ei.value.remediation.lower()
