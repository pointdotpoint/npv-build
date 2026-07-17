"""Cross-platform discovery of saves and game installs (spec PLT-1/2)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

GAME_STEAM_APPID = "1091500"
_SAVE_SUFFIX = Path("Saved Games") / "CD Projekt Red" / "Cyberpunk 2077"
_VDF_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')


def steam_root_candidates() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        candidates = [Path("C:/Program Files (x86)/Steam")]
    else:
        candidates = [
            home / ".steam" / "steam",
            home / ".local" / "share" / "Steam",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        ]
    return [c for c in candidates if (c / "steamapps").is_dir()]


def steam_libraries(steam_roots: list[Path] | None = None) -> list[Path]:
    roots = steam_root_candidates() if steam_roots is None else steam_roots
    libraries: list[Path] = []
    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        for raw in _VDF_PATH_RE.findall(vdf.read_text(encoding="utf-8", errors="replace")):
            lib = Path(raw.replace("\\\\", "\\"))
            if (lib / "steamapps").is_dir() and lib not in libraries:
                libraries.append(lib)
    return libraries


def candidate_save_dirs(
    home: Path | None = None,
    steam_roots: list[Path] | None = None,
) -> list[Path]:
    home = Path.home() if home is None else home
    found: list[Path] = []
    native = home / _SAVE_SUFFIX
    if native.is_dir():
        found.append(native)
    for lib in steam_libraries(steam_roots):
        proton = (
            lib / "steamapps" / "compatdata" / GAME_STEAM_APPID / "pfx" / "drive_c"
            / "users" / "steamuser" / _SAVE_SUFFIX
        )
        if proton.is_dir() and proton not in found:
            found.append(proton)
    return found


def is_valid_game_dir(path: Path) -> bool:
    return (path / "archive" / "pc" / "content").is_dir()


def find_game_dirs(steam_roots: list[Path] | None = None) -> list[Path]:
    found: list[Path] = []
    for lib in steam_libraries(steam_roots):
        candidate = lib / "steamapps" / "common" / "Cyberpunk 2077"
        if is_valid_game_dir(candidate) and candidate not in found:
            found.append(candidate)
    return found
