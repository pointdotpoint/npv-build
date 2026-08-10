# PyInstaller one-dir build of npv-build (GUI + CLI in one executable).
# The GUI is pywebview (bundled Qt WebEngine on Linux / WebView2 on Windows) + a static
# HTML/CSS/JS frontend under npv_build/webui/ -- no customtkinter/tkinter here.
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = collect_data_files("npv_build")  # npv_build/data/** (includes npv_build/webui/**)
binaries = []
hiddenimports = []

# collect_data_files excludes Python source by default. These scripts are data
# consumed by external Blender processes, not importable application modules,
# so PyInstaller will not discover them through normal module analysis.
repo_root = Path(SPECPATH).parent
for blender_script in ("bake_head.py", "render_npv.py"):
    source = repo_root / "npv_build" / "data" / "blender" / blender_script
    if not source.is_file():
        raise SystemExit(f"Missing Blender runtime script: {source}")
    datas.append((str(source), "npv_build/data/blender"))

d, b, h = collect_all("webview")
datas += d
binaries += b
hiddenimports += h
if sys.platform.startswith("linux"):
    hiddenimports = [
        module for module in hiddenimports if not module.startswith("webview.platforms.gtk")
    ]

helper_root = Path(SPECPATH) / "helpers"
if not helper_root.is_dir():
    raise SystemExit(
        f"Missing release helper directory: {helper_root}. "
        "Run scripts/build_release_helpers.py before PyInstaller."
    )
for helper in ("npv-inject", "npv-photomode", "npv-tweakdb"):
    helper_dir = helper_root / helper
    executable = helper_dir / (f"{helper}.exe" if sys.platform == "win32" else helper)
    if not executable.is_file():
        raise SystemExit(
            f"Missing release helper executable: {executable}. "
            "Run scripts/build_release_helpers.py before PyInstaller "
            "(helpers must live in per-tool subdirs)."
        )
    # One datas entry per helper so each keeps its own managed DLLs.
    datas.append((str(helper_dir), f"npv_helpers/{helper}"))

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["gi"] if sys.platform.startswith("linux") else [],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="npv-build",
    icon=str(Path(SPECPATH) / "npv-build.ico") if sys.platform == "win32" else None,
    console=True,  # keep a console so CLI output is visible; GUI still opens its own window
)
coll = COLLECT(exe, a.binaries, a.datas, name="npv-build")
