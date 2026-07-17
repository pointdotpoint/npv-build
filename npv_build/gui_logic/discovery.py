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
            thumb = next((sub / n for n in _THUMB_NAMES if (sub / n).is_file()), None)
            entries.append(
                SaveEntry(path=sav, name=sub.name, mtime=sav.stat().st_mtime, thumbnail=thumb)
            )
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries
