from pathlib import Path

import pytest

import npv_build.installer as installer
from npv_build.core.errors import InstallError, SecurityError, ToolError


def test_auto_install_missing_all_missing(monkeypatch):
    calls = []

    def mock_check_dependencies(game_dir):
        # Return that everything is missing
        return {"wolvenkit": False, "blender": False, "npv_inject": False, "game_dir_valid": False}

    def mock_install_dotnet(tools_dir, progress_cb):
        calls.append("dotnet")

    def mock_install_wolvenkit(tools_dir, progress_cb):
        calls.append("wolvenkit")

    def mock_build_npv_inject(tools_dir, progress_cb):
        calls.append("npv-inject")

    def mock_install_blender(tools_dir, progress_cb):
        calls.append("blender")

    monkeypatch.setattr("npv_build.gui_backend.check_dependencies", mock_check_dependencies)
    monkeypatch.setattr(installer, "install_dotnet_windows", mock_install_dotnet)
    monkeypatch.setattr(installer, "install_dotnet_linux", mock_install_dotnet)
    monkeypatch.setattr(installer, "install_wolvenkit", mock_install_wolvenkit)
    monkeypatch.setattr(installer, "build_npv_inject", mock_build_npv_inject)
    monkeypatch.setattr(installer, "install_blender", mock_install_blender)

    # Mock get_cache_dir
    monkeypatch.setattr(installer, "get_cache_dir", lambda: Path("/tmp/mock_cache"))

    # Mock shutil.which to say dotnet is not installed (so it downloads it)
    monkeypatch.setattr(installer.shutil, "which", lambda cmd: None)

    # Run auto install
    installer.auto_install_missing(lambda msg, pct: None)

    assert "dotnet" in calls
    assert "wolvenkit" in calls
    assert "npv-inject" in calls
    assert "blender" in calls


def test_auto_install_missing_some_present(monkeypatch):
    calls = []

    def mock_check_dependencies(game_dir):
        # Return that WolvenKit is present, but Blender and npv-inject are missing
        return {"wolvenkit": True, "blender": False, "npv_inject": False, "game_dir_valid": False}

    def mock_install_dotnet(tools_dir, progress_cb):
        calls.append("dotnet")

    def mock_install_wolvenkit(tools_dir, progress_cb):
        calls.append("wolvenkit")

    def mock_build_npv_inject(tools_dir, progress_cb):
        calls.append("npv-inject")

    def mock_install_blender(tools_dir, progress_cb):
        calls.append("blender")

    monkeypatch.setattr("npv_build.gui_backend.check_dependencies", mock_check_dependencies)
    monkeypatch.setattr(installer, "install_dotnet_windows", mock_install_dotnet)
    monkeypatch.setattr(installer, "install_dotnet_linux", mock_install_dotnet)
    monkeypatch.setattr(installer, "install_wolvenkit", mock_install_wolvenkit)
    monkeypatch.setattr(installer, "build_npv_inject", mock_build_npv_inject)
    monkeypatch.setattr(installer, "install_blender", mock_install_blender)

    # Mock get_cache_dir
    monkeypatch.setattr(installer, "get_cache_dir", lambda: Path("/tmp/mock_cache"))

    # Mock shutil.which to say dotnet is available globally
    monkeypatch.setattr(
        installer.shutil, "which", lambda cmd: "/usr/bin/dotnet" if cmd == "dotnet" else None
    )

    # Run auto install
    installer.auto_install_missing(lambda msg, pct: None)

    # Should not download dotnet since it's available globally,
    # and should skip wolvenkit since it's present.
    # But should build npv-inject and install Blender.
    assert "dotnet" not in calls
    assert "wolvenkit" not in calls
    assert "npv-inject" in calls
    assert "blender" in calls


def test_install_dotnet_linux_failure_raises_install_error(monkeypatch, tmp_path):
    def exploding(argv, **kwargs):
        raise ToolError("script failed", tool="dotnet-install", exit_code=1)

    monkeypatch.setattr(installer, "run_tool", exploding)
    monkeypatch.setattr(installer, "download_file", lambda url, dest, cb=None: dest.write_text(""))

    with pytest.raises(InstallError):
        installer.install_dotnet_linux(tmp_path, lambda msg, pct: None)


def test_install_dotnet_windows_failure_raises_install_error(monkeypatch, tmp_path):
    def exploding(argv, **kwargs):
        raise ToolError("script failed", tool="dotnet-install", exit_code=1)

    monkeypatch.setattr(installer, "run_tool", exploding)
    monkeypatch.setattr(installer, "download_file", lambda url, dest, cb=None: dest.write_text(""))

    with pytest.raises(InstallError):
        installer.install_dotnet_windows(tmp_path, lambda msg, pct: None)


def test_install_wolvenkit_failure_raises_install_error(monkeypatch, tmp_path):
    def exploding(argv, **kwargs):
        raise ToolError("nuget failed", tool="dotnet", exit_code=1, details="network unreachable")

    monkeypatch.setattr(installer, "run_tool", exploding)
    monkeypatch.setattr(installer.shutil, "which", lambda cmd: "/usr/bin/dotnet")

    with pytest.raises(InstallError):
        installer.install_wolvenkit(tmp_path, lambda msg, pct: None)


def test_install_wolvenkit_already_installed_is_not_an_error(monkeypatch, tmp_path):
    calls = []

    def exploding(argv, **kwargs):
        raise ToolError(
            "dotnet tool install failed",
            tool="dotnet",
            exit_code=1,
            details="Tool 'wolvenkit.cli' is already installed.",
        )

    def progress(msg, pct):
        calls.append((msg, pct))

    monkeypatch.setattr(installer, "run_tool", exploding)
    monkeypatch.setattr(installer.shutil, "which", lambda cmd: "/usr/bin/dotnet")

    installer.install_wolvenkit(tmp_path, progress)

    assert any("already installed" in msg for msg, _pct in calls)


def test_build_npv_inject_failure_raises_install_error(monkeypatch, tmp_path):
    def exploding(argv, **kwargs):
        raise ToolError("build failed", tool="dotnet", exit_code=1)

    monkeypatch.setattr(installer, "run_tool", exploding)
    monkeypatch.setattr(installer.shutil, "which", lambda cmd: "/usr/bin/dotnet")

    with pytest.raises(InstallError):
        installer.build_npv_inject(tmp_path, lambda msg, pct: None)


def test_blender_extract_uses_safe_extract(tmp_path):
    """A zip-slip Blender archive must raise SecurityError, not extract."""
    import zipfile

    arc = tmp_path / "blender.zip"
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("../escape.txt", "x")
    with pytest.raises(SecurityError):
        installer._extract_blender_archive(arc, tmp_path / "dest")


def test_blender_extract_tar_uses_safe_extract(tmp_path):
    """A zip-slip Blender tarball must raise SecurityError, not extract."""
    import io
    import tarfile

    arc = tmp_path / "blender.tar.xz"
    with tarfile.open(arc, "w:xz") as t:
        data = b"x"
        info = tarfile.TarInfo(name="../escape.txt")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    with pytest.raises(SecurityError):
        installer._extract_blender_archive(arc, tmp_path / "dest")


def test_install_blender_verifies_checksum_before_extract(monkeypatch, tmp_path):
    """install_blender must fetch and verify the published checksum before extracting."""
    calls = []

    def fake_download_file(url, dest, cb=None):
        calls.append(url)
        if url.endswith(".sha256"):
            # Correct sha256 of b"archive-bytes"
            import hashlib

            digest = hashlib.sha256(b"archive-bytes").hexdigest()
            dest.write_text(f"{digest}  {Path(url).stem}\n")
        else:
            dest.write_bytes(b"archive-bytes")

    def fake_extract(archive, dest):
        calls.append(("extract", archive, dest))
        dest.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(installer, "download_file", fake_download_file)
    monkeypatch.setattr(installer, "_extract_blender_archive", fake_extract)
    monkeypatch.setattr(installer, "get_cache_dir", lambda: tmp_path / "cache")

    installer.install_blender(tmp_path, lambda msg, pct: None)

    assert any(str(c).endswith(".sha256") for c in calls if isinstance(c, str))
    assert any(isinstance(c, tuple) and c[0] == "extract" for c in calls)


def test_install_blender_missing_checksum_raises_security_error(monkeypatch, tmp_path):
    """If blender.org's checksum URL 404s, install_blender must hard-fail, never skip."""

    def fake_download_file(url, dest, cb=None):
        if url.endswith(".sha256"):
            raise InstallError("404 not found")
        dest.write_bytes(b"archive-bytes")

    extract_calls = []

    def fake_extract(archive, dest):
        extract_calls.append(archive)

    monkeypatch.setattr(installer, "download_file", fake_download_file)
    monkeypatch.setattr(installer, "_extract_blender_archive", fake_extract)

    with pytest.raises(SecurityError):
        installer.install_blender(tmp_path, lambda msg, pct: None)

    assert not extract_calls
