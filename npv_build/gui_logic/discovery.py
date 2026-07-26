"""Tk-free data for the save browser (spec GUI-3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.platform import candidate_save_dirs

_THUMB_NAMES = ("screenshot.png",)


@dataclass
class SaveEntry:
    path: Path  # the sav.dat file
    name: str
    mtime: float
    thumbnail: Path | None
    patch: str | None = None  # game patch badge, None when undetectable


def _probe_patch(sav: Path) -> str | None:
    """Best-effort patch label from the save header; None means no badge
    (the save still lists — preview_save reports the real error on pick)."""
    from ..save_format import probe_save_version
    from ..save_parser import detect_patch

    try:
        return detect_patch(probe_save_version(sav))
    except Exception:  # noqa: BLE001 - badge is cosmetic, never blocks listing
        return None


def entry_for_path(sav: Path) -> SaveEntry:
    """Build a SaveEntry for one explicitly chosen sav.dat file."""
    sav = Path(sav)
    name = sav.parent.name if sav.name == "sav.dat" else sav.stem
    thumb = next((sav.parent / n for n in _THUMB_NAMES if (sav.parent / n).is_file()), None)
    return SaveEntry(
        path=sav,
        name=name,
        mtime=sav.stat().st_mtime,
        thumbnail=thumb,
        patch=_probe_patch(sav),
    )


def list_saves(save_dirs: list[Path] | None = None) -> list[SaveEntry]:
    dirs = candidate_save_dirs() if save_dirs is None else save_dirs
    entries: list[SaveEntry] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for sub in d.iterdir():
            sav = sub / "sav.dat"
            if not sav.is_file():
                continue
            entries.append(entry_for_path(sav))
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries
