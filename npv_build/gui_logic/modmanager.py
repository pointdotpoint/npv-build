"""Mod manager: list/install/uninstall built NPV mods (spec GUI-5).

A "built mod" is one npv-build output directory, identified by its
archive stem (the mod_id): ``<output_root>/<mod_id>/archive/pc/mod/<mod_id>.archive``,
with a matching AMM lua file under
``<output_root>/<mod_id>/bin/x64/plugins/cyber_engine_tweaks/mods/AppearanceMenuMod/Collabs/Custom Entities/<mod_id>.lua``.

Installing copies the archive + lua (+ any sibling ``.xl`` file, for
forward-compat with an ArchiveXL-based pipeline) into the game's own
mod directories. Uninstalling removes them. Both are idempotent.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import InstallError

_LUA_SUBPATH = Path(
    "bin/x64/plugins/cyber_engine_tweaks/mods/AppearanceMenuMod/Collabs/Custom Entities"
)


@dataclass
class ModEntry:
    mod_id: str
    archive_path: Path
    lua_path: Path
    installed: bool


def game_mod_dir(game_dir: Path) -> Path:
    return Path(game_dir) / "archive" / "pc" / "mod"


def _game_lua_dir(game_dir: Path) -> Path:
    return Path(game_dir) / _LUA_SUBPATH


def _xl_path(archive_path: Path) -> Path:
    return archive_path.with_suffix(".xl")


def list_mods(output_root: Path, game_dir: Path) -> list[ModEntry]:
    """Enumerate built mods under output_root, marking installed status."""
    output_root = Path(output_root)
    mod_dir = game_mod_dir(game_dir)
    entries: list[ModEntry] = []
    for archive_path in sorted(output_root.glob("*/archive/pc/mod/*.archive")):
        mod_id = archive_path.stem
        # glob pattern is "<mod_root>/archive/pc/mod/<file>.archive" -- 3 parents
        # up from the .archive file lands back on <mod_root> (mod/ -> pc/ -> archive/).
        mod_root = archive_path.parents[3]
        lua_path = mod_root / _LUA_SUBPATH / f"{mod_id}.lua"
        installed = (mod_dir / archive_path.name).is_file()
        entries.append(
            ModEntry(
                mod_id=mod_id,
                archive_path=archive_path,
                lua_path=lua_path,
                installed=installed,
            )
        )
    return entries


def install_mod(entry: ModEntry, game_dir: Path) -> None:
    """Copy the mod's archive + lua (+ .xl if present) into game_dir. Idempotent."""
    if not entry.archive_path.is_file():
        raise InstallError(
            f"Cannot install '{entry.mod_id}': archive not found.",
            remediation=f"Expected archive at {entry.archive_path}. Rebuild the mod.",
        )
    if not entry.lua_path.is_file():
        raise InstallError(
            f"Cannot install '{entry.mod_id}': AMM lua file not found.",
            remediation=f"Expected lua at {entry.lua_path}. Rebuild the mod.",
        )

    mod_dir = game_mod_dir(game_dir)
    lua_dir = _game_lua_dir(game_dir)
    mod_dir.mkdir(parents=True, exist_ok=True)
    lua_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(entry.archive_path, mod_dir / entry.archive_path.name)
    shutil.copy2(entry.lua_path, lua_dir / entry.lua_path.name)

    xl_src = _xl_path(entry.archive_path)
    if xl_src.is_file():
        shutil.copy2(xl_src, mod_dir / xl_src.name)


def uninstall_mod(entry: ModEntry, game_dir: Path) -> None:
    """Remove the mod's archive + lua (+ .xl if present) from game_dir. Idempotent."""
    mod_dir = game_mod_dir(game_dir)
    lua_dir = _game_lua_dir(game_dir)

    (mod_dir / entry.archive_path.name).unlink(missing_ok=True)
    (lua_dir / entry.lua_path.name).unlink(missing_ok=True)
    (mod_dir / _xl_path(entry.archive_path).name).unlink(missing_ok=True)
