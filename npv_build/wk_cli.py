"""WolvenKit CLI adapter.

Centralises all WolvenKit CLI subprocess calls behind one module.
Every other module that needs WolvenKit receives a WolvenKit instance
rather than calling subprocess.run directly.
"""
from __future__ import annotations

import json
import re as _re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WolvenKitError(Exception):
    def __init__(self, message: str, *, operation: str = "", exit_code: int = -1):
        super().__init__(message)
        self.module_name = "WolvenKit Automation"
        self.operation = operation
        self.exit_code = exit_code


SUPPORTED_VERSION_PREFIX = "8.18."


@dataclass(frozen=True)
class WolvenKitConfig:
    game_dir: Path | None = None
    cli_binary: str = "WolvenKit.CLI"
    verbosity: int = 0

    @property
    def appearance_archive(self) -> Path:
        if not self.game_dir:
            raise WolvenKitError("game_dir required", operation="config")
        return (
            self.game_dir / "archive" / "pc" / "content"
            / "basegame_4_appearance.archive"
        )


class WolvenKit:
    def __init__(self, config: WolvenKitConfig):
        self._cfg = config

    @property
    def config(self) -> WolvenKitConfig:
        return self._cfg

    # -- hero: uncook one file, get parsed JSON back -----------------------

    def uncook_json(
        self,
        filename: str,
        *,
        archive: Path | None = None,
    ) -> dict[str, Any]:
        """Uncook a single file by basename, return parsed JSON.

        Manages its own tempdir. Caller passes a plain filename
        (e.g. "h0_000_pwa__basehead.ent"); regex escaping is handled
        internally.
        """
        archive = archive or self._cfg.appearance_archive
        regex = _re.escape(filename) + r"$"

        with tempfile.TemporaryDirectory() as td:
            self._run(
                ["uncook", "-p", str(archive), "-r", regex, "-o", td, "-s"],
                operation="uncook",
            )
            matches = list(Path(td).rglob(filename + ".json"))
            if not matches:
                raise FileNotFoundError(
                    f"Uncook produced no JSON for '{filename}' in {archive.name}"
                )
            return json.loads(matches[0].read_text())

    # -- second most common: list archive contents -------------------------

    def list_archive(
        self,
        pattern: str,
        *,
        archive: Path | None = None,
    ) -> list[str]:
        """List depot paths matching a regex. Returns filtered lines."""
        archive = archive or self._cfg.appearance_archive
        # Always capture stdout regardless of verbosity — the output IS the data.
        cmd = [self._cfg.cli_binary, "archive", str(archive), "-l", "--regex", pattern]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            raise WolvenKitError(
                f"{self._cfg.cli_binary} not found in PATH.",
                operation="archive list",
            )
        if result.returncode != 0:
            tail = ((result.stderr or "") + (result.stdout or ""))[-1500:]
            raise WolvenKitError(
                f"archive list failed (exit {result.returncode}).\n{tail}",
                operation="archive list",
                exit_code=result.returncode,
            )
        return [
            line.strip()
            for line in (result.stdout or "").splitlines()
            if line.strip()
        ]

    # -- batch uncook (caller owns the output dir) -------------------------

    def uncook_many(
        self,
        regex: str,
        *,
        archive: Path | None = None,
        dest: Path | None = None,
    ) -> Path:
        """Uncook all files matching regex. Returns the output directory.

        If dest is None, creates a tempdir the CALLER must clean up.
        """
        archive = archive or self._cfg.appearance_archive
        if dest is None:
            dest = Path(tempfile.mkdtemp(prefix="wk_uncook_"))
        dest.mkdir(parents=True, exist_ok=True)
        self._run(
            ["uncook", "-p", str(archive), "-r", regex, "-o", str(dest), "-s"],
            operation="uncook",
        )
        return dest

    # -- convert: serialize / deserialize ----------------------------------

    def serialize(self, cr2w_file: Path, *, dest: Path) -> Path:
        """CR2W binary -> JSON. Returns path to the produced .json."""
        dest.mkdir(parents=True, exist_ok=True)
        self._run(
            ["convert", "serialize", str(cr2w_file), "-o", str(dest)],
            operation="serialize",
        )
        jsons = list(dest.rglob("*.json"))
        if not jsons:
            raise WolvenKitError(
                f"Serialize produced no JSON for {cr2w_file}",
                operation="serialize",
            )
        return jsons[0]

    def deserialize(self, target: Path) -> None:
        """JSON -> CR2W binary. Accepts a file or directory."""
        self._run(
            ["convert", "deserialize", str(target)],
            operation="deserialize",
        )

    # -- extract (raw CR2W, not JSON) --------------------------------------

    def extract(
        self,
        regex: str,
        *,
        archive: Path | None = None,
        dest: Path,
    ) -> Path:
        """Extract raw files from an archive. Returns dest."""
        archive = archive or self._cfg.appearance_archive
        dest.mkdir(parents=True, exist_ok=True)
        self._run(
            ["extract", str(archive), "-o", str(dest), "-r", regex],
            operation="extract",
        )
        return dest

    # -- unbundle ----------------------------------------------------------

    def unbundle(
        self,
        regex: str,
        *,
        archive: Path | None = None,
        dest: Path,
    ) -> Path:
        """Unbundle raw files preserving depot structure. Returns dest."""
        archive = archive or self._cfg.appearance_archive
        dest.mkdir(parents=True, exist_ok=True)
        self._run(
            ["unbundle", str(archive), "-o", str(dest), "-r", regex],
            operation="unbundle",
        )
        return dest

    # -- mesh export / import ----------------------------------------------

    def export(self, cr2w_file: Path, *, dest: Path) -> Path:
        """Export .morphtarget/.mesh to .glb. Returns path to produced .glb."""
        if not self._cfg.game_dir:
            raise WolvenKitError("game_dir required for export", operation="export")
        dest.mkdir(parents=True, exist_ok=True)
        self._run(
            ["export", str(cr2w_file), "-o", str(dest),
             "-gp", str(self._cfg.game_dir)],
            operation="export",
        )
        glbs = list(dest.glob("*.glb"))
        if not glbs:
            raise WolvenKitError(
                f"Export produced no .glb for {cr2w_file}",
                operation="export",
            )
        return glbs[0]

    def import_mesh(
        self,
        source_dir: Path,
        *,
        dest: Path,
        allow_exit_codes: tuple[int, ...] = (),
    ) -> None:
        """Import .glb back to .mesh (--keep mode, reuses CR2W skeleton).

        allow_exit_codes: WolvenKit import sometimes exits 3 on success.
        Pass (3,) to tolerate that.
        """
        if not self._cfg.game_dir:
            raise WolvenKitError("game_dir required for import", operation="import")
        dest.mkdir(parents=True, exist_ok=True)
        self._run(
            ["import", str(source_dir), "-o", str(dest),
             "--keep", "-gp", str(self._cfg.game_dir)],
            operation="import",
            allow_exit_codes=allow_exit_codes,
        )

    # -- pack --------------------------------------------------------------

    def pack(self, source_dir: Path, *, dest: Path) -> Path:
        """Pack directory into .archive. Returns path to the .archive."""
        dest.mkdir(parents=True, exist_ok=True)
        self._run(
            ["pack", str(source_dir), "-o", str(dest)],
            operation="pack",
        )
        archives = list(dest.glob("*.archive"))
        if not archives:
            raise WolvenKitError(
                f"Pack produced no .archive in {dest}",
                operation="pack",
            )
        return archives[0]

    # -- version check -----------------------------------------------------

    def check_version(self) -> str:
        """Check CLI version. Warns on mismatch, raises only if binary missing."""
        try:
            result = subprocess.run(
                [self._cfg.cli_binary, "--version"],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise WolvenKitError(
                f"{self._cfg.cli_binary} not found in PATH. "
                "Install WolvenKit CLI and ensure it is on PATH.",
                operation="version",
            )
        version = (result.stdout or "").strip()
        if not version.startswith(SUPPORTED_VERSION_PREFIX):
            print(
                f"[WolvenKit] Warning: detected version '{version}', "
                f"tool was developed against {SUPPORTED_VERSION_PREFIX}x. "
                "Proceeding anyway.",
                file=sys.stderr,
            )
        return version

    # -- internal: single subprocess runner --------------------------------

    def _run(
        self,
        args: list[str],
        *,
        operation: str = "",
        allow_exit_codes: tuple[int, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        cmd = [self._cfg.cli_binary, *args]
        stream = self._cfg.verbosity >= 2

        if stream:
            print(f"[WolvenKit] $ {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                stdout=None if stream else subprocess.PIPE,
                stderr=None if stream else subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError:
            raise WolvenKitError(
                f"{self._cfg.cli_binary} not found in PATH. "
                "Install WolvenKit CLI and ensure it is on PATH.",
                operation=operation,
            )

        ok_codes = {0} | set(allow_exit_codes)
        if result.returncode not in ok_codes:
            tail = ""
            if not stream:
                raw = (result.stderr or "") + (result.stdout or "")
                tail = raw[-1500:]
            raise WolvenKitError(
                f"{operation}: {self._cfg.cli_binary} {args[0]} "
                f"exited with code {result.returncode}."
                + (f"\n{tail}" if tail else ""),
                operation=operation,
                exit_code=result.returncode,
            )

        return result
