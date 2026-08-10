import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def test_release_workflow_builds_all_requested_formats():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "npv-build-*-windows-x86_64-setup.exe" in workflow
    assert "npv-build-*-windows-x86_64.zip" in workflow
    assert "npv-build-*-x86_64.AppImage" in workflow
    assert "npv-build_*_amd64.deb" in workflow
    assert "draft: false" in workflow


def test_release_workflow_bundles_helpers_on_both_platforms():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("astral-sh/setup-uv@v9.0.0") == 2
    assert workflow.count("submodules: recursive") == 2
    assert "--rid linux-x64 --output packaging/helpers" in workflow
    assert "--rid win-x64 --output packaging/helpers" in workflow
    assert workflow.count("npv-inject") >= 2
    assert workflow.count("npv-photomode") >= 2
    assert workflow.count("npv-tweakdb") >= 2
    assert "Start-Process -FilePath $helper -Wait -PassThru" in workflow
    assert "Start-Process -FilePath $installer -ArgumentList" in workflow


def test_release_bundle_includes_blender_runtime_scripts():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    spec = (ROOT / "packaging" / "npv-build.spec").read_text(encoding="utf-8")

    for script in ("bake_head.py", "render_npv.py"):
        assert script in spec
        bundled_path = f"npv_build/data/blender/{script}"
        assert workflow.count(bundled_path) == 2


def test_packagers_reference_versioned_outputs():
    appimage = (ROOT / "packaging" / "build_appimage.sh").read_text(encoding="utf-8")
    deb = (ROOT / "packaging" / "build_deb.sh").read_text(encoding="utf-8")
    spec = (ROOT / "packaging" / "npv-build.spec").read_text(encoding="utf-8")
    installer = (ROOT / "packaging" / "windows" / "npv-build.iss").read_text(encoding="utf-8")

    assert "npv-build-${VERSION}-x86_64.AppImage" in appimage
    assert "npv-build_${VERSION}_amd64.deb" in deb
    assert "npv-build-{#MyAppVersion}-windows-x86_64-setup" in installer
    assert "npv-build.ico" in spec
    assert r"SetupIconFile=..\npv-build.ico" in installer


def test_brand_icon_has_svg_and_windows_variants():
    svg = (ROOT / "packaging" / "npv-build.svg").read_text(encoding="utf-8")
    ico = (ROOT / "packaging" / "npv-build.ico").read_bytes()

    assert svg.count("<path") == 3
    assert 'fill="#77a7ff"' in svg
    assert 'fill="#9bc0ff"' in svg
    assert 'fill="#ff5d79"' in svg
    assert ico.startswith(b"\x00\x00\x01\x00")


def test_linux_release_uses_bundled_qt_instead_of_host_webkitgtk():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    gui_dependencies = pyproject["project"]["optional-dependencies"]["gui"]
    workflow = WORKFLOW.read_text(encoding="utf-8")
    spec = (ROOT / "packaging" / "npv-build.spec").read_text(encoding="utf-8")

    assert any("pywebview[qt]" in dependency for dependency in gui_dependencies)
    assert all("pygobject" not in dependency.lower() for dependency in gui_dependencies)
    assert "gir1.2-webkit2" not in workflow
    assert workflow.count("xvfb-run -a timeout 10s") == 2
    assert 'excludes=["gi"]' in spec
    for xcb_dependency in ("libxcb-icccm4", "libxcb-keysyms1", "libxcb-shape0"):
        assert xcb_dependency in workflow
