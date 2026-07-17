"""Path-traversal-safe archive extraction (spec SEC-1)."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from .errors import SecurityError


def is_safe_member(name: str, dest: Path) -> bool:
    name = name.replace("\\", "/")
    dest_resolved = dest.resolve()
    target = (dest_resolved / name).resolve()
    try:
        target.relative_to(dest_resolved)
    except ValueError:
        return False
    return True


def _reject(name: str, dest: Path) -> None:
    raise SecurityError(
        f"Archive member escapes the extraction directory: {name!r}",
        remediation="The archive may be malicious or corrupt; do not extract it.",
        details=f"dest={dest}",
    )


def safe_extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not is_safe_member(name, dest):
                _reject(name, dest)
        z.extractall(dest)


def safe_extract_tar(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as t:
        for member in t.getmembers():
            if not is_safe_member(member.name, dest):
                _reject(member.name, dest)
            if member.islnk() or member.issym():
                # link targets can escape too
                if not is_safe_member(member.linkname, dest):
                    _reject(member.linkname, dest)
        t.extractall(dest)


def safe_extract_7z(archive: Path, dest: Path, targets: list[str] | None = None) -> None:
    import py7zr

    dest.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(archive, "r") as z:
        for name in z.getnames():
            if not is_safe_member(name, dest):
                _reject(name, dest)
        if targets is not None:
            z.extract(path=dest, targets=targets)
        else:
            z.extractall(path=dest)
