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

    assert workflow.count("submodules: recursive") == 2
    assert "--rid linux-x64 --output packaging/helpers" in workflow
    assert "--rid win-x64 --output packaging/helpers" in workflow
    assert workflow.count("npv-inject") >= 2
    assert workflow.count("npv-photomode") >= 2
    assert workflow.count("npv-tweakdb") >= 2


def test_packagers_reference_versioned_outputs():
    appimage = (ROOT / "packaging" / "build_appimage.sh").read_text(encoding="utf-8")
    deb = (ROOT / "packaging" / "build_deb.sh").read_text(encoding="utf-8")
    installer = (ROOT / "packaging" / "windows" / "npv-build.iss").read_text(encoding="utf-8")

    assert "npv-build-${VERSION}-x86_64.AppImage" in appimage
    assert "npv-build_${VERSION}_amd64.deb" in deb
    assert "npv-build-{#MyAppVersion}-windows-x86_64-setup" in installer
