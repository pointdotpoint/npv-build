import hashlib

import pytest

from npv_build.core.checksums import sha256_of, verify_from_sums, verify_sha256
from npv_build.core.errors import SecurityError


def _write(tmp_path, data=b"hello"):
    p = tmp_path / "f.bin"
    p.write_bytes(data)
    return p, hashlib.sha256(data).hexdigest()


def test_sha256_of(tmp_path):
    p, h = _write(tmp_path)
    assert sha256_of(p) == h


def test_verify_ok(tmp_path):
    p, h = _write(tmp_path)
    verify_sha256(p, h)  # no raise
    verify_sha256(p, h.upper())  # case-insensitive


def test_verify_mismatch_raises(tmp_path):
    p, _ = _write(tmp_path)
    with pytest.raises(SecurityError) as ei:
        verify_sha256(p, "0" * 64)
    assert "checksum" in str(ei.value).lower()


def test_verify_from_sums_ok(tmp_path):
    p, h = _write(tmp_path)
    sums = f"{h}  f.bin\n{'a' * 64}  other.bin\n"
    verify_from_sums(p, sums, "f.bin")


def test_verify_from_sums_missing_filename_raises(tmp_path):
    p, h = _write(tmp_path)
    with pytest.raises(SecurityError):
        verify_from_sums(p, f"{h}  other.bin\n", "f.bin")
