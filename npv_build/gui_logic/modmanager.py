"""Mod manager: list/install/uninstall built NPV mods (spec GUI-5).

A "built mod" is one npv-build output directory, identified by its
archive stem (the mod_id): ``<output_root>/<mod_id>/archive/pc/mod/<mod_id>.archive``,
with a matching AMM lua file under
``<output_root>/<mod_id>/bin/x64/plugins/cyber_engine_tweaks/mods/AppearanceMenuMod/Collabs/Custom Entities/<mod_id>.lua``.

The mod root's ``archive/``, ``bin/`` and ``r6/`` trees mirror the game
directory layout and together form the install payload (main .archive, AMM
lua, photomode .archive.xl, TweakXL yaml, ...). Installing copies every
payload file into the same relative path under the game directory;
uninstalling removes them. Both are idempotent.
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
    built_at: float = 0.0  # archive mtime; 0.0 when unknown


def game_mod_dir(game_dir: Path) -> Path:
    return Path(game_dir) / "archive" / "pc" / "mod"


_PAYLOAD_TREES = ("archive", "bin", "r6")


def _payload_files(entry: ModEntry) -> list[Path]:
    """Every payload file as a path relative to the mod root (= game dir layout)."""
    mod_root = entry.archive_path.parents[3]
    files = []
    for tree in _PAYLOAD_TREES:
        root = mod_root / tree
        if root.is_dir():
            files.extend(p.relative_to(mod_root) for p in sorted(root.rglob("*")) if p.is_file())
    return files


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
                built_at=archive_path.stat().st_mtime,
            )
        )
    return entries


def install_mod(entry: ModEntry, game_dir: Path) -> None:
    """Copy every payload file into the same relative path under game_dir. Idempotent."""
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

    mod_root = entry.archive_path.parents[3]
    game_dir = Path(game_dir)
    try:
        for rel in _payload_files(entry):
            dest = game_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mod_root / rel, dest)
    except OSError as e:
        raise InstallError(
            f"Could not write to the game directory: {game_dir}",
            remediation="Check permissions on the game/mod directory, or that the game isn't running.",
            details=str(e),
        ) from e


def delete_mod(entry: ModEntry, game_dir: Path) -> None:
    """Uninstall from the game (if installed), then remove the whole build
    output directory for this mod. Idempotent."""
    uninstall_mod(entry, game_dir)
    mod_root = entry.archive_path.parents[3]
    try:
        if mod_root.is_dir():
            shutil.rmtree(mod_root)
    except OSError as e:
        raise InstallError(
            f"Could not delete the build output: {mod_root}",
            remediation="Check permissions, or remove the folder manually.",
            details=str(e),
        ) from e


def uninstall_mod(entry: ModEntry, game_dir: Path) -> None:
    """Remove every payload file from game_dir. Idempotent."""
    game_dir = Path(game_dir)

    try:
        for rel in _payload_files(entry):
            (game_dir / rel).unlink(missing_ok=True)
    except OSError as e:
        raise InstallError(
            f"Could not remove files from the game directory: {game_dir}",
            remediation="Check permissions on the game/mod directory, or that the game isn't running.",
            details=str(e),
        ) from e
