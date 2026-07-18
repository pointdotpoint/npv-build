# PyInstaller one-dir build of npv-build (GUI + CLI in one executable).
# The GUI is pywebview (webkit2gtk on Linux / WebView2 on Windows) + a static
# HTML/CSS/JS frontend under npv_build/webui/ -- no customtkinter/tkinter here.
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = collect_data_files("npv_build")  # npv_build/data/** (includes npv_build/webui/**)
binaries = []
hiddenimports = []
d, b, h = collect_all("webview")
datas += d
binaries += b
hiddenimports += h

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
