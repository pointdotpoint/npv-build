import shutil
import zipfile
from pathlib import Path

import py7zr
import pytest

from npv_build.core.errors import InstallError, SecurityError, ToolError
from npv_build.hair_mod_helper import derive_hair_name, install_hair_mod


def test_derive_hair_name():
    assert derive_hair_name("fhair_zara.archive") == "zara"
    assert derive_hair_name("mhair_buzz.archive") == "buzz"
    assert derive_hair_name("fhair_miyavi_twistup_soft_mod.archive") == "miyavi_twistup_soft"
    assert derive_hair_name("cool_hair.archive") == "cool"
    assert derive_hair_name("fhair_edie_hair_v1.0.archive") == "edie"
    assert derive_hair_name("fhair_long_wavy_hair_mod_v2.archive") == "long_wavy"


def test_install_hair_mod_archive(tmp_path):
    # Set up source directories
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    archive_file = src_dir / "fhair_zara.archive"
    archive_file.write_text("dummy archive content")

    xl_file = src_dir / "fhair_zara.xl"
    xl_file.write_text("dummy xl content")

    # Run installer
    hair_name, installed = install_hair_mod(archive_file, game_dir)

    assert hair_name == "zara"
    dest_mod_dir = game_dir / "archive" / "pc" / "mod"
    assert (dest_mod_dir / "fhair_zara.archive").exists()
    assert (dest_mod_dir / "fhair_zara.xl").exists()
    assert dest_mod_dir / "fhair_zara.archive" in installed
    assert dest_mod_dir / "fhair_zara.xl" in installed


def test_install_hair_mod_zip(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    zip_path = src_dir / "hair_mod.zip"

    # Create a real zip file with nested structure
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("archive/pc/mod/fhair_zara.archive", "dummy zip archive content")
        zf.writestr("archive/pc/mod/fhair_zara.xl", "dummy zip xl content")
        zf.writestr("README.txt", "should not extract")

    hair_name, installed = install_hair_mod(zip_path, game_dir)

    assert hair_name == "zara"
    dest_mod_dir = game_dir / "archive" / "pc" / "mod"
    assert (dest_mod_dir / "fhair_zara.archive").exists()
    assert (dest_mod_dir / "fhair_zara.xl").exists()
    assert not (dest_mod_dir / "README.txt").exists()
    assert len(installed) == 2


def test_install_hair_mod_7z(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    sevenz_path = src_dir / "hair_mod.7z"

    # Create a real 7z file
    with py7zr.SevenZipFile(sevenz_path, "w") as sz:
        sz.writestr("dummy 7z archive content", "archive/pc/mod/fhair_zara.archive")
        sz.writestr("dummy 7z xl content", "archive/pc/mod/fhair_zara.xl")
        sz.writestr("should not extract", "README.txt")

    hair_name, installed = install_hair_mod(sevenz_path, game_dir)

    assert hair_name == "zara"
    dest_mod_dir = game_dir / "archive" / "pc" / "mod"
    assert (dest_mod_dir / "fhair_zara.archive").exists()
    assert (dest_mod_dir / "fhair_zara.xl").exists()
    assert not (dest_mod_dir / "README.txt").exists()
    assert len(installed) == 2


def test_install_hair_mod_rar(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    rar_path = src_dir / "hair_mod.rar"
    rar_path.write_text("fake rar data")

    # Mock shutil.which to ensure 'unrar' is found
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/unrar" if cmd == "unrar" else None)

    # Mock run_tool to simulate unrar's listing, then extraction to the temp dir
    def mock_run_tool(argv, **kwargs):
        from npv_build.core.proc import ToolResult

        if argv[1] == "lb":
            listing = (
                "archive/pc/mod/fhair_zara.archive\narchive/pc/mod/fhair_zara.xl\nreadme.txt\n"
            )
            return ToolResult(argv=list(argv), returncode=0, stdout=listing, stderr="")

        # The last argument is the extraction path
        extract_path = Path(argv[-1])
        # Create mock extracted structure
        arch_dir = extract_path / "archive" / "pc" / "mod"
        arch_dir.mkdir(parents=True, exist_ok=True)
        (arch_dir / "fhair_zara.archive").write_text("mock rar archive")
        (arch_dir / "fhair_zara.xl").write_text("mock rar xl")
        (extract_path / "readme.txt").write_text("should be ignored")

        return ToolResult(argv=list(argv), returncode=0, stdout="success", stderr="")

    import npv_build.hair_mod_helper as hair_mod_helper

    monkeypatch.setattr(hair_mod_helper, "run_tool", mock_run_tool)

    hair_name, installed = install_hair_mod(rar_path, game_dir)

    assert hair_name == "zara"
    dest_mod_dir = game_dir / "archive" / "pc" / "mod"
    assert (dest_mod_dir / "fhair_zara.archive").exists()
    assert (dest_mod_dir / "fhair_zara.xl").exists()
    assert not (dest_mod_dir / "readme.txt").exists()
    assert len(installed) == 2


def test_install_hair_mod_unsupported(tmp_path):
    game_dir = tmp_path / "game"
    bad_file = tmp_path / "cool_hair.txt"
    bad_file.write_text("test")

    with pytest.raises(ValueError, match="Unsupported mod file format"):
        install_hair_mod(bad_file, game_dir)


def test_install_hair_no_archive_in_zip(tmp_path):
    game_dir = tmp_path / "game"
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("README.txt", "no archives here")

    with pytest.raises(ValueError, match="No .archive file found inside the mod package"):
        install_hair_mod(zip_path, game_dir)


def test_install_hair_mod_rar_missing_unrar_raises_install_error(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    rar_path = src_dir / "hair_mod.rar"
    rar_path.write_text("fake rar data")

    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    with pytest.raises(InstallError):
        install_hair_mod(rar_path, game_dir)


def test_install_hair_mod_7z_zip_slip_raises_security_error(tmp_path, monkeypatch):
    """A 7z archive with a path-traversal member must raise SecurityError, not extract.

    py7zr's own writer API refuses to author a traversal path (check_archive_path),
    so a legitimately-built .7z can't smuggle one in via writestr(). We instead
    patch SevenZipFile.getnames() to report a malicious member name, exercising
    the same is_safe_member() gate that a hand-crafted malicious archive would hit.
    """
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    sevenz_path = src_dir / "evil.7z"
    with py7zr.SevenZipFile(sevenz_path, "w") as sz:
        sz.writestr("dummy archive content", "archive/pc/mod/fhair_zara.archive")

    monkeypatch.setattr(py7zr.SevenZipFile, "getnames", lambda self: ["../../escape.archive"])

    with pytest.raises(SecurityError):
        install_hair_mod(sevenz_path, game_dir)


def test_install_hair_mod_rar_zip_slip_raises_security_error(tmp_path, monkeypatch):
    """If unrar extracts a member outside the temp dir, must raise SecurityError + clean up."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    rar_path = src_dir / "evil.rar"
    rar_path.write_text("fake rar data")

    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/unrar" if cmd == "unrar" else None)

    escape_target = tmp_path / "escaped.archive"

    def mock_run_tool(argv, **kwargs):
        from npv_build.core.proc import ToolResult

        if argv[1] == "lb":
            # The listing itself looks innocuous; the escape only manifests
            # once unrar resolves a symlink during actual extraction.
            return ToolResult(
                argv=list(argv), returncode=0, stdout="escape_link.archive\n", stderr=""
            )

        # Simulate unrar writing a file that escapes the extraction dir
        # (e.g. via a symlink or absolute path trick already resolved on disk).
        extract_path = Path(argv[-1])
        extract_path.mkdir(parents=True, exist_ok=True)
        escape_target.write_text("escaped content")
        # Symlink inside the temp dir pointing outside it.
        link = extract_path / "escape_link.archive"
        link.symlink_to(escape_target)

        return ToolResult(argv=list(argv), returncode=0, stdout="success", stderr="")

    import npv_build.hair_mod_helper as hair_mod_helper

    monkeypatch.setattr(hair_mod_helper, "run_tool", mock_run_tool)

    with pytest.raises(SecurityError):
        install_hair_mod(rar_path, game_dir)


def test_install_hair_mod_rar_listing_traversal_blocks_before_extract(tmp_path, monkeypatch):
    """CVE-2022-30333 class: a malicious rar's *listing* names a member outside
    the temp dir (e.g. "../../evil.archive"). The old post-extract rglob(td_path)
    check could never see this, because unrar would write the file outside
    td_path entirely -- rglob only walks files physically inside td_path, so the
    escape would go undetected, uncleaned, and unreported.

    The fix validates every member name from `unrar lb` (the listing) before
    calling `unrar x` (the extract) at all. This test asserts SecurityError is
    raised and that extraction never runs -- i.e. nothing is ever written to
    disk for the malicious member.
    """
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    rar_path = src_dir / "evil.rar"
    rar_path.write_text("fake rar data")

    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/unrar" if cmd == "unrar" else None)

    extract_calls = []

    def mock_run_tool(argv, **kwargs):
        from npv_build.core.proc import ToolResult

        if argv[1] == "lb":
            # Malicious listing: a member that resolves outside the temp dir.
            return ToolResult(
                argv=list(argv),
                returncode=0,
                stdout="archive/pc/mod/fhair_zara.archive\n../../evil.archive\n",
                stderr="",
            )

        # Any non-listing call is treated as the extract invocation.
        extract_calls.append(argv)
        return ToolResult(argv=list(argv), returncode=0, stdout="success", stderr="")

    import npv_build.hair_mod_helper as hair_mod_helper

    monkeypatch.setattr(hair_mod_helper, "run_tool", mock_run_tool)

    with pytest.raises(SecurityError, match=r"\.\./\.\./evil\.archive"):
        install_hair_mod(rar_path, game_dir)

    # The critical assertion: extraction must never be invoked once a bad
    # member is found in the listing. This is the out-of-temp-dir write case
    # the old rglob-based post-extract check structurally could not catch.
    assert extract_calls == []


def test_install_hair_mod_rar_extraction_failure_propagates_tool_error(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    game_dir = tmp_path / "game"

    rar_path = src_dir / "hair_mod.rar"
    rar_path.write_text("fake rar data")

    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/unrar" if cmd == "unrar" else None)

    def exploding(argv, **kwargs):
        raise ToolError("unrar failed", tool="unrar", exit_code=1)

    import npv_build.hair_mod_helper as hair_mod_helper

    monkeypatch.setattr(hair_mod_helper, "run_tool", exploding)

    with pytest.raises(ToolError):
        install_hair_mod(rar_path, game_dir)
