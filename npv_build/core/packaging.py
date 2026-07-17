"""Zips a successfully-built NPV mod into a mod-manager-ready archive.

Only the game-relative install tree (archive/, bin/) is included; build
byproducts (source/, root JSONs, logs/, the manifest) are excluded so the
zip can be dropped straight into a Cyberpunk 2077 install or a mod manager.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .errors import PackagingError

#: Top-level directories inside output_dir that make up the installable tree.
_INSTALL_DIRS = ("archive", "bin")


def package_mod(output_dir: Path, mod_id: str, zip_path: Path | None = None) -> Path:
    archive_glob = list((output_dir / "archive" / "pc" / "mod").glob("*.archive"))
    if not archive_glob:
        raise PackagingError(
            f"No built archive found for '{mod_id}'.",
            remediation="Run a build before packaging.",
            module_name="Packaging",
        )

    if zip_path is None:
        zip_path = output_dir / f"{mod_id}.zip"

    files: list[Path] = []
    for install_dir in _INSTALL_DIRS:
        base = output_dir / install_dir
        if base.exists():
            files.extend(p for p in base.rglob("*") if p.is_file())

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files, key=lambda p: p.relative_to(output_dir).as_posix()):
            arcname = path.relative_to(output_dir).as_posix()
            zf.write(path, arcname)

    return zip_path
