"""WolvenKit CLI adapter.

Centralises all WolvenKit CLI subprocess calls behind one module.
Every other module that needs WolvenKit receives a WolvenKit instance
rather than calling subprocess.run directly.
"""

from __future__ import annotations

import json
import logging
import re as _re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.cancel import CancelToken
from .core.errors import ToolError
from .core.proc import run_tool

logger = logging.getLogger(__name__)


class WolvenKitError(ToolError):
    def __init__(
        self,
        message: str,
        *,
        operation: str = "",
        exit_code: int = -1,
        remediation: str = "",
    ):
        super().__init__(
            message,
            exit_code=exit_code,
            module_name="WolvenKit Automation",
            remediation=remediation,
        )
        self.operation = operation


MIN_WK_VERSION = (8, 19, 0)
TESTED_WK_PREFIX = "8.19."


@dataclass(frozen=True)
class WolvenKitConfig:
    game_dir: Path | None = None
    cli_binary: str = "WolvenKit.CLI"
    verbosity: int = 0
    timeout_s: float = 600.0
    cancel: CancelToken | None = None

    @property
    def appearance_archive(self) -> Path:
        if not self.game_dir:
            raise WolvenKitError("game_dir required", operation="config")
        return self.game_dir / "archive" / "pc" / "content" / "basegame_4_appearance.archive"


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
        result = self._run(
            ["archive", str(archive), "-l", "--regex", pattern],
            operation="archive list",
        )
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]

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
            ["export", str(cr2w_file), "-o", str(dest), "-gp", str(self._cfg.game_dir)],
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
            ["import", str(source_dir), "-o", str(dest), "--keep", "-gp", str(self._cfg.game_dir)],
            operation="import",
            allow_exit_codes=allow_exit_codes,
        )

    # -- pack --------------------------------------------------------------

    def pack(self, source_dir: Path, *, dest: Path) -> Path:
        """Pack directory into .archive. Returns path to the freshly-packed .archive.

        Packs into an isolated temp dir first so the result is unambiguous — `dest`
        often holds stale .archive files from prior builds, and globbing it would
        pick an arbitrary one. The single produced archive is then moved into dest.
        """
        dest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="wk_pack_") as td:
            td_path = Path(td)
            self._run(
                ["pack", str(source_dir), "-o", str(td_path)],
                operation="pack",
            )
            archives = list(td_path.glob("*.archive"))
            if not archives:
                raise WolvenKitError(
                    f"Pack produced no .archive in {td_path}",
                    operation="pack",
                )
            final = dest / archives[0].name
            if final.exists():
                final.unlink()
            shutil.move(str(archives[0]), str(final))
            return final

    # -- version check -----------------------------------------------------

    def check_version(self) -> str:
        """Check CLI version.

        Raises WolvenKitError if the reported version is below MIN_WK_VERSION.
        Logs a warning if it's newer than the tested TESTED_WK_PREFIX line.
        Unparseable version strings are logged and returned as-is (does not
        brick the pipeline on exotic version output).
        """
        result = self._run(["--version"], operation="version")
        version = (result.stdout or "").strip()

        match = _re.match(r"(\d+)\.(\d+)\.(\d+)", version)
        if not match:
            logger.warning(
                f"[WolvenKit] could not parse version string '{version}'; proceeding anyway."
            )
            return version

        parsed = tuple(int(x) for x in match.groups())
        if parsed < MIN_WK_VERSION:
            min_str = ".".join(str(x) for x in MIN_WK_VERSION)
            raise WolvenKitError(
                f"[WolvenKit] detected version '{version}', which is below the "
                f"minimum required version {min_str}.",
                operation="version",
                remediation=(
                    f"Install WolvenKit.CLI >= {min_str} "
                    "(e.g. `dotnet tool install --global WolvenKit.CLI "
                    f"--version {min_str}`) and re-run."
                ),
            )
        if not version.startswith(TESTED_WK_PREFIX):
            logger.warning(
                f"[WolvenKit] detected version '{version}', "
                f"tool was tested against {TESTED_WK_PREFIX}x. "
                "Proceeding anyway."
            )
        return version

    def _run(
        self,
        args: list[str],
        *,
        operation: str = "",
        allow_exit_codes: tuple[int, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        binary = self._cfg.cli_binary
        if not shutil.which(binary):
            from .config import get_cache_dir

            ext = ".exe" if sys.platform == "win32" else ""
            cache_tools_dir = get_cache_dir() / "tools" / "wolvenkit"
            # Check candidate names in order: WolvenKit.CLI (explicit install), cp77tools (dotnet tool install shim)
            for candidate_name in [f"WolvenKit.CLI{ext}", f"cp77tools{ext}"]:
                local_path = cache_tools_dir / candidate_name
                if local_path.exists():
                    binary = str(local_path)
                    break
        cmd = [binary, *args]
        stream = self._cfg.verbosity >= 2

        if stream:
            logger.debug(f"[WolvenKit] $ {' '.join(cmd)}")

        try:
            result = run_tool(
                cmd,
                tool=self._cfg.cli_binary,
                timeout=self._cfg.timeout_s,
                cancel=self._cfg.cancel,
                allow_exit_codes=tuple(allow_exit_codes),
                logger=logger,
            )
        except WolvenKitError:
            raise
        except ToolError as e:
            raise WolvenKitError(
                f"{operation}: {self._cfg.cli_binary} {args[0]} failed: {e.user_message}"
                + (f"\n{e.details}" if e.details else ""),
                operation=operation,
                exit_code=e.exit_code if e.exit_code is not None else -1,
            ) from e

        if stream:
            if result.stdout:
                logger.debug(result.stdout)
            if result.stderr:
                logger.debug(result.stderr)

        return subprocess.CompletedProcess(cmd, result.returncode, result.stdout, result.stderr)
