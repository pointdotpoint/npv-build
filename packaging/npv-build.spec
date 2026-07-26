# PyInstaller one-dir build of npv-build (GUI + CLI in one executable).
# The GUI is pywebview (bundled Qt WebEngine on Linux / WebView2 on Windows) + a static
# HTML/CSS/JS frontend under npv_build/webui/ -- no customtkinter/tkinter here.
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = collect_data_files("npv_build")  # npv_build/data/** (includes npv_build/webui/**)
binaries = []
hiddenimports = []
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
    executable = helper_root / (f"{helper}.exe" if sys.platform == "win32" else helper)
    if not executable.is_file():
        raise SystemExit(
            f"Missing release helper executable: {executable}. "
            "Run scripts/build_release_helpers.py before PyInstaller."
        )
datas.append((str(helper_root), "npv_helpers"))

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
    console=True,  # keep a console so CLI output is visible; GUI still opens its own window
)
coll = COLLECT(exe, a.binaries, a.datas, name="npv-build")
