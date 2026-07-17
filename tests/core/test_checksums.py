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


def test_verify_from_sums_strips_single_binary_marker_only(tmp_path):
    """sha256sum's binary-mode marker is a single leading '*'; only that one
    should be stripped, not every leading asterisk (over-stripping could let
    a filename with genuine leading asterisks collide with an unrelated entry).
    """
    p, h = _write(tmp_path)
    # Standard binary-mode marker: single leading '*'.
    verify_from_sums(p, f"{h} *f.bin\n", "f.bin")

    # A filename with two literal leading asterisks must NOT match "f.bin";
    # only a single marker asterisk should ever be stripped.
    p2, h2 = _write(tmp_path, data=b"other")
    with pytest.raises(SecurityError):
        verify_from_sums(p2, f"{h2} **f.bin\n", "f.bin")
