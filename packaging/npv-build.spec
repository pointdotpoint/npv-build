# PyInstaller one-dir build of npv-build (GUI + CLI in one executable).
import glob
import sysconfig

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

datas = collect_data_files("npv_build")  # npv_build/data/**
binaries = []
# PIL.ImageTk (used by customtkinter for images) lazily imports PIL._tkinter_finder
# to locate the Tk photo-image C API; PyInstaller's static analysis doesn't see
# that import, so it must be listed explicitly or ImageTk blows up at runtime.
hiddenimports = ["PIL._tkinter_finder"]
for pkg in ("customtkinter", "tkinterdnd2"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# PyInstaller's built-in tkinter hook bundles the tcl9/_tcl_data/_tk_data script
# libraries but, on this Python build (Tcl/Tk 9.0, libtcl9.0.so / libtcl9tk9.0.so),
# it misses the actual shared objects tkinter dlopen()s at runtime. Without them
# the frozen GUI dies with "ImportError: libtcl9.0.so: cannot open shared object
# file". collect_dynamic_libs("tkinter") pulls in whatever the running
# interpreter's tkinter extension is actually linked against.
binaries += collect_dynamic_libs("tkinter")

# Belt-and-suspenders: explicitly locate libtcl9*.so / libtk9*.so next to the
# Python installation in case collect_dynamic_libs misses them (e.g. they're
# dlopen'd by _tkinter rather than being direct link dependencies).
_libdir = sysconfig.get_config_var("LIBDIR") or ""
_found = set()
for _pattern in ("libtcl9*.so*", "libtk9*.so*"):
    for _base in (_libdir, sysconfig.get_config_var("prefix") + "/lib" if sysconfig.get_config_var("prefix") else ""):
        if not _base:
            continue
        for _path in glob.glob(f"{_base}/{_pattern}"):
            _found.add(_path)
for _path in sorted(_found):
    binaries.append((_path, "."))

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
