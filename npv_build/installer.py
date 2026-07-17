import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .config import get_cache_dir
from .core.checksums import verify_from_sums
from .core.errors import InstallError, SecurityError, ToolError
from .core.proc import run_tool
from .core.safe_extract import safe_extract_tar, safe_extract_zip


def download_file(url: str, dest_path: Path, progress_callback=None):
    """Download a file with progress updates."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req) as response:
        total_size = int(response.info().get("Content-Length", 0))
        downloaded = 0
        block_size = 16384
        with open(dest_path, "wb") as f:
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                f.write(buffer)
                downloaded += len(buffer)
                if total_size > 0 and progress_callback:
                    percent = int(downloaded * 100 / total_size)
                    progress_callback(percent)


def install_dotnet_windows(tools_dir: Path, progress_callback):
    """Download and run dotnet-install.ps1 on Windows."""
    script_url = "https://dot.net/v1/dotnet-install.ps1"
    script_path = tools_dir / "dotnet-install.ps1"
    tools_dir.mkdir(parents=True, exist_ok=True)

    progress_callback("Downloading .NET SDK installation script...", 0)
    download_file(script_url, script_path)

    progress_callback("Running .NET 8.0 SDK installer (this can take a minute)...", 10)

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Channel",
        "8.0",
        "-InstallDir",
        str(tools_dir / "dotnet"),
    ]
    try:
        run_tool(cmd, tool="dotnet-install", timeout=900)
    except ToolError as e:
        raise InstallError(
            f".NET installation failed: {e.user_message}",
            details=e.details,
            remediation="Check your network connection and re-run the installer.",
        ) from e

    if script_path.exists():
        script_path.unlink()

    progress_callback(".NET SDK installed locally.", 100)


def install_dotnet_linux(tools_dir: Path, progress_callback):
    """Download and run dotnet-install.sh on Linux."""
    script_url = "https://dot.net/v1/dotnet-install.sh"
    script_path = tools_dir / "dotnet-install.sh"
    tools_dir.mkdir(parents=True, exist_ok=True)

    progress_callback("Downloading .NET SDK installation script...", 0)
    download_file(script_url, script_path)

    script_path.chmod(0o755)

    progress_callback("Running .NET 8.0 SDK installer (this can take a minute)...", 10)

    cmd = ["bash", str(script_path), "--channel", "8.0", "--install-dir", str(tools_dir / "dotnet")]
    try:
        run_tool(cmd, tool="dotnet-install", timeout=900)
    except ToolError as e:
        raise InstallError(
            f".NET installation failed: {e.user_message}",
            details=e.details,
            remediation="Check your network connection and re-run the installer.",
        ) from e

    if script_path.exists():
        script_path.unlink()

    progress_callback(".NET SDK installed locally.", 100)


def install_wolvenkit(tools_dir: Path, progress_callback):
    """Install WolvenKit.CLI using dotnet tool install."""
    progress_callback("Preparing WolvenKit.CLI installation...", 0)

    dotnet_bin = tools_dir / "dotnet" / ("dotnet.exe" if sys.platform == "win32" else "dotnet")
    if not dotnet_bin.exists():
        system_dotnet = shutil.which("dotnet")
        if system_dotnet:
            dotnet_bin = Path(system_dotnet)
        else:
            raise FileNotFoundError(".NET SDK binary not found. Please install .NET first.")

    cmd = [
        str(dotnet_bin),
        "tool",
        "install",
        "--tool-path",
        str(tools_dir / "wolvenkit"),
        "WolvenKit.CLI",
        "--version",
        "8.19.0",
    ]

    progress_callback("Downloading WolvenKit.CLI 8.19.0 via NuGet...", 30)
    try:
        run_tool(cmd, tool="dotnet", timeout=900)
    except ToolError as e:
        if "already installed" in e.details:
            progress_callback("WolvenKit.CLI is already installed.", 100)
            return
        raise InstallError(
            f"WolvenKit.CLI installation failed: {e.user_message}",
            details=e.details,
            remediation="Check your network connection and re-run the installer.",
        ) from e

    progress_callback("WolvenKit.CLI installed successfully.", 100)


def build_npv_inject(tools_dir: Path, progress_callback):
    """Compile tools/npv-inject using local or system dotnet."""
    progress_callback("Starting compilation of npv-inject...", 0)

    dotnet_bin = tools_dir / "dotnet" / ("dotnet.exe" if sys.platform == "win32" else "dotnet")
    if not dotnet_bin.exists():
        system_dotnet = shutil.which("dotnet")
        if system_dotnet:
            dotnet_bin = Path(system_dotnet)
        else:
            raise FileNotFoundError(".NET SDK binary not found. Please install .NET first.")

    project_dir = Path(__file__).parent.parent / "tools" / "npv-inject"
    cmd = [str(dotnet_bin), "build", str(project_dir), "-c", "Release"]

    progress_callback("Compiling C# component injector...", 40)
    try:
        run_tool(cmd, tool="dotnet", timeout=900)
    except ToolError as e:
        raise InstallError(
            f"npv-inject compilation failed: {e.user_message}",
            details=e.details,
            remediation="Ensure the .NET 8.0 SDK is installed and re-run the installer.",
        ) from e

    progress_callback("npv-inject compiled successfully.", 100)


def _extract_blender_archive(archive: Path, dest: Path) -> None:
    """Safely extract a Blender release archive (.zip or .tar.xz) to dest.

    Dispatches by suffix to the path-traversal-safe helpers (spec SEC-1).
    Raises SecurityError if any member would escape dest.
    """
    suffix = archive.suffix.lower()
    if suffix == ".zip":
        safe_extract_zip(archive, dest)
    else:
        # .tar.xz / .txz and friends
        safe_extract_tar(archive, dest)


def _verify_blender_download(url: str, temp_archive: Path, archive_name: str) -> None:
    """Fetch blender.org's published checksum for this release and verify it.

    blender.org publishes a `<file>.sha256` alongside each download. If that
    checksum can't be fetched (e.g. 404 for the pinned version), this is a
    hard failure -- we never skip verification.
    """
    sums_url = url + ".sha256"
    with tempfile.TemporaryDirectory() as td:
        sums_path = Path(td) / f"{archive_name}.sha256"
        try:
            download_file(sums_url, sums_path)
        except (urllib.error.URLError, InstallError, OSError) as e:
            raise SecurityError(
                f"Could not fetch Blender checksum from {sums_url}.",
                remediation=(
                    "The pinned Blender release may have been removed from blender.org. "
                    "Refusing to install an unverified download."
                ),
                details=str(e),
            ) from e

        sums_text = sums_path.read_text()
        verify_from_sums(temp_archive, sums_text, archive_name)


def install_blender(tools_dir: Path, progress_callback):
    """Download and extract Blender 4.2.0 LTS (portable zip/tarball)."""
    progress_callback("Starting Blender 4.2.0 LTS download...", 0)

    blender_dir = tools_dir / "blender"
    if blender_dir.exists():
        shutil.rmtree(blender_dir)
    blender_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        url = "https://download.blender.org/release/Blender4.2/blender-4.2.0-windows-x64.zip"
        archive_name = "blender-4.2.0-windows-x64.zip"
    else:
        url = "https://download.blender.org/release/Blender4.2/blender-4.2.0-linux-x64.tar.xz"
        archive_name = "blender-4.2.0-linux-x64.tar.xz"

    temp_archive = tools_dir / archive_name

    def download_progress(pct):
        progress_callback(f"Downloading Blender 4.2.0 LTS ({pct}%)...", int(pct * 0.7))

    download_file(url, temp_archive, download_progress)

    progress_callback("Verifying Blender download checksum...", 75)
    _verify_blender_download(url, temp_archive, archive_name)

    progress_callback("Extracting Blender package (this may take a few seconds)...", 85)

    _extract_blender_archive(temp_archive, blender_dir)

    if temp_archive.exists():
        temp_archive.unlink()

    progress_callback("Blender installed successfully.", 100)


def auto_install_missing(progress_callback):
    """Orchestrate download & installation of all missing tools."""
    from .gui_backend import check_dependencies

    tools_dir = get_cache_dir() / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    # Query current status (game_dir is None since we only check system tools)
    status = check_dependencies(None)

    # 1. Evaluate .NET SDK requirement
    # We need dotnet SDK if npv-inject or WolvenKit is missing and we don't have it on PATH
    needs_dotnet = not status["npv_inject"] or not status["wolvenkit"]
    dotnet_bin = tools_dir / "dotnet" / ("dotnet.exe" if sys.platform == "win32" else "dotnet")

    # Check if we can avoid downloading dotnet
    needs_dotnet_download = needs_dotnet and not dotnet_bin.exists() and not shutil.which("dotnet")

    if needs_dotnet_download:
        if sys.platform == "win32":
            install_dotnet_windows(tools_dir, progress_callback)
        else:
            install_dotnet_linux(tools_dir, progress_callback)

    # 2. Install WolvenKit CLI if missing
    if not status["wolvenkit"]:
        install_wolvenkit(tools_dir, progress_callback)

    # 3. Build npv-inject if missing
    if not status["npv_inject"]:
        build_npv_inject(tools_dir, progress_callback)

    # 4. Install Blender if missing
    if not status["blender"]:
        install_blender(tools_dir, progress_callback)

    progress_callback("All missing dependencies verified & installed!", 100)
