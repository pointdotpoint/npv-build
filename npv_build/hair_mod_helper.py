import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from .core.errors import InstallError, SecurityError
from .core.proc import run_tool
from .core.safe_extract import is_safe_member, safe_extract_7z


def derive_hair_name(archive_filename: str) -> str:
    """Extracts a search token name from the hair archive filename.
    Strips fhair_/mhair_ prefixes and common suffixes like _mod, _hair.
    """
    name = Path(archive_filename).name
    if name.lower().endswith(".archive"):
        name = name[:-8]

    name = name.lower()

    # Strip gender prefixes
    for pre in ("fhair_", "mhair_"):
        if name.startswith(pre):
            name = name[len(pre) :]
            break

    # Strip common suffixes iteratively
    while True:
        prev = name
        name = re.sub(r"(_mod|_hair|_v\d+[\d\.]*|_+)$", "", name)
        if name == prev:
            break
    return name


def install_hair_mod(source_path: Path, game_dir: Path) -> tuple[str, list[Path]]:
    """Installs the hair mod (.archive and optional .xl files) from source_path
    into game_dir/archive/pc/mod.

    Supports:
      - .archive (direct file copy, plus same-named .xl sidecar if present)
      - .zip (recursive extraction of .archive and .xl files)
      - .7z (using py7zr to recursively extract .archive and .xl files)
      - .rar (using unrar command to recursively extract .archive and .xl files)

    Returns:
      (derived_hair_name, list_of_installed_paths)
    """
    if not game_dir:
        raise ValueError("Game directory is not specified.")

    mod_dir = game_dir / "archive" / "pc" / "mod"
    mod_dir.mkdir(parents=True, exist_ok=True)

    source_path = Path(source_path)
    suffix = source_path.suffix.lower()

    installed_files = []
    first_archive_name = None

    if suffix == ".archive":
        # Direct archive
        dest_archive = mod_dir / source_path.name
        if not dest_archive.exists():
            shutil.copy2(source_path, dest_archive)
            installed_files.append(dest_archive)
        else:
            installed_files.append(dest_archive)

        first_archive_name = source_path.name

        # Check for matching .xl sidecar
        xl_sidecar = source_path.with_suffix(".xl")
        if xl_sidecar.exists():
            dest_xl = mod_dir / xl_sidecar.name
            if not dest_xl.exists():
                shutil.copy2(xl_sidecar, dest_xl)
                installed_files.append(dest_xl)
            else:
                installed_files.append(dest_xl)

    elif suffix == ".zip":
        with zipfile.ZipFile(source_path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                filename = member.filename
                basename = Path(filename).name
                lower_name = basename.lower()

                if lower_name.endswith(".archive") or lower_name.endswith(".xl"):
                    dest_path = mod_dir / basename
                    if lower_name.endswith(".archive") and not first_archive_name:
                        first_archive_name = basename
                    if not dest_path.exists():
                        with zf.open(member) as source, open(dest_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        installed_files.append(dest_path)
                    else:
                        installed_files.append(dest_path)

    elif suffix == ".7z":
        import py7zr

        with py7zr.SevenZipFile(source_path, mode="r") as sz:
            targets = []
            for info in sz.list():
                if info.is_directory:
                    continue
                fname = info.filename
                basename = Path(fname).name
                lower_name = basename.lower()
                if lower_name.endswith(".archive") or lower_name.endswith(".xl"):
                    targets.append(fname)
                    if lower_name.endswith(".archive") and not first_archive_name:
                        first_archive_name = basename

            if targets:
                with tempfile.TemporaryDirectory() as td:
                    safe_extract_7z(source_path, Path(td), targets=targets)
                    for fname in targets:
                        src_extracted = Path(td) / fname
                        if src_extracted.exists():
                            basename = src_extracted.name
                            dest_path = mod_dir / basename
                            if not dest_path.exists():
                                shutil.copy2(src_extracted, dest_path)
                                installed_files.append(dest_path)
                            else:
                                installed_files.append(dest_path)

    elif suffix == ".rar":
        if not shutil.which("unrar"):
            raise InstallError(
                "The 'unrar' utility is not installed on the system.",
                remediation="Install 'unrar' via your system package manager to extract .rar mods.",
            )

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)

            # Validate every member BEFORE extracting. rglob(td_path) after
            # extraction can only see files that landed *inside* td_path, so it
            # is structurally blind to the actual CVE-2022-30333 threat: unrar
            # writing a member like "../../evil" to a path *outside* td_path.
            # Listing the archive first (unrar lb = bare list, one member path
            # per line, no headers/sizes) lets us catch traversal in the names
            # themselves before anything is written to disk.
            listing = run_tool(["unrar", "lb", str(source_path)], tool="unrar", timeout=300)
            members = [line for line in listing.stdout.splitlines() if line.strip()]
            for member in members:
                if not is_safe_member(member, td_path):
                    raise SecurityError(
                        f"Archive member escapes the extraction directory: {member!r}",
                        remediation="The archive may be malicious or corrupt; do not extract it.",
                        details=f"dest={td_path}",
                    ) from None

            run_tool(["unrar", "x", "-y", str(source_path), td], tool="unrar", timeout=300)

            # Defensive post-extract check too (cheap, catches anything the
            # listing didn't reveal, e.g. symlinks resolved on disk by unrar).
            for p in td_path.rglob("*"):
                rel = str(p.relative_to(td_path))
                if not is_safe_member(rel, td_path):
                    shutil.rmtree(td_path, ignore_errors=True)
                    raise SecurityError(
                        f"Archive member escapes the extraction directory: {p.name!r}",
                        remediation="The archive may be malicious or corrupt; do not extract it.",
                        details=f"dest={td_path}",
                    ) from None

            for p in td_path.rglob("*"):
                if p.is_file():
                    lower_name = p.name.lower()
                    if lower_name.endswith(".archive") or lower_name.endswith(".xl"):
                        if lower_name.endswith(".archive") and not first_archive_name:
                            first_archive_name = p.name
                        dest_path = mod_dir / p.name
                        if not dest_path.exists():
                            shutil.copy2(p, dest_path)
                            installed_files.append(dest_path)
                        else:
                            installed_files.append(dest_path)

    else:
        raise ValueError(
            f"Unsupported mod file format: {suffix}. Please select a .archive, .zip, .7z, or .rar file."
        )

    if not first_archive_name:
        raise ValueError("No .archive file found inside the mod package.")

    derived_name = derive_hair_name(first_archive_name)
    return derived_name, installed_files
