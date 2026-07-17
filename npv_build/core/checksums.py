"""SHA-256 verification for downloaded artifacts (spec SEC-2)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .errors import SecurityError

_CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    actual = sha256_of(path)
    if actual.lower() != expected.strip().lower():
        raise SecurityError(
            f"Checksum mismatch for {path.name}.",
            remediation="The download may be corrupt or tampered; delete it and retry.",
            details=f"expected={expected.lower()} actual={actual}",
        )


def verify_from_sums(path: Path, sums_text: str, filename: str) -> None:
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            verify_sha256(path, parts[0])
            return
    raise SecurityError(
        f"No published checksum found for {filename}.",
        remediation="Cannot verify the download; refusing to proceed.",
    )
