import os
import sys
import shutil
import urllib.request
import zipfile
import tarfile
import subprocess
from pathlib import Path

from .config import get_cache_dir


def download_file(url: str, dest_path: Path, progress_callback=None):
    """Download a file with progress updates."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req) as response:
        total_size = int(response.info().get('Content-Length', 0))
        downloaded = 0
        block_size = 16384
        with open(dest_path, 'wb') as f:
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
        "-ExecutionPolicy", "Bypass",
        "-File", str(script_path),
        "-Channel", "8.0",
        "-InstallDir", str(tools_dir / "dotnet")
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f".NET installation failed: {res.stderr}\n{res.stdout}")
    
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
    
    cmd = [
        "bash",
        str(script_path),
        "--channel", "8.0",
        "--install-dir", str(tools_dir / "dotnet")
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f".NET installation failed: {res.stderr}\n{res.stdout}")
        
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
        "tool", "install",
        "--tool-path", str(tools_dir / "wolvenkit"),
        "WolvenKit.CLI",
        "--version", "8.18.1"
    ]
    
    progress_callback("Downloading WolvenKit.CLI 8.18.1 via NuGet...", 30)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        if "already installed" in res.stderr or "already installed" in res.stdout:
            progress_callback("WolvenKit.CLI is already installed.", 100)
            return
        raise RuntimeError(f"WolvenKit.CLI installation failed: {res.stderr}\n{res.stdout}")
        
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
    cmd = [
        str(dotnet_bin),
        "build",
        str(project_dir),
        "-c", "Release"
    ]
    
    progress_callback("Compiling C# component injector...", 40)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"npv-inject compilation failed: {res.stderr}\n{res.stdout}")
        
    progress_callback("npv-inject compiled successfully.", 100)


def install_blender(tools_dir: Path, progress_callback):
    """Download and extract Blender 4.2.0 LTS (portable zip/tarball)."""
    progress_callback("Starting Blender 4.2.0 LTS download...", 0)
    
    blender_dir = tools_dir / "blender"
    if blender_dir.exists():
        shutil.rmtree(blender_dir)
    blender_dir.mkdir(parents=True, exist_ok=True)
    
    if sys.platform == "win32":
        url = "https://download.blender.org/release/Blender4.2/blender-4.2.0-windows-x64.zip"
        archive_name = "blender.zip"
    else:
        url = "https://download.blender.org/release/Blender4.2/blender-4.2.0-linux-x64.tar.xz"
        archive_name = "blender.tar.xz"
        
    temp_archive = tools_dir / archive_name
    
    def download_progress(pct):
        progress_callback(f"Downloading Blender 4.2.0 LTS ({pct}%)...", int(pct * 0.8))
        
    download_file(url, temp_archive, download_progress)
    
    progress_callback("Extracting Blender package (this may take a few seconds)...", 85)
    
    if sys.platform == "win32":
        with zipfile.ZipFile(temp_archive, 'r') as zip_ref:
            zip_ref.extractall(blender_dir)
    else:
        with tarfile.open(temp_archive, 'r:xz') as tar_ref:
            tar_ref.extractall(blender_dir)
            
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
