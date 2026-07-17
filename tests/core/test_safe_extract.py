import tarfile
import zipfile

import py7zr
import pytest

from npv_build.core.errors import SecurityError
from npv_build.core.safe_extract import (
    is_safe_member,
    safe_extract_7z,
    safe_extract_tar,
    safe_extract_zip,
)


def test_is_safe_member_accepts_normal(tmp_path):
    assert is_safe_member("a/b/c.txt", tmp_path) is True


def test_is_safe_member_rejects_traversal(tmp_path):
    assert is_safe_member("../../etc/passwd", tmp_path) is False
    assert is_safe_member("/abs/path", tmp_path) is False


def test_is_safe_member_rejects_backslash_traversal(tmp_path):
    assert is_safe_member("..\\..\\escape", tmp_path) is False


def test_safe_extract_zip_rejects_backslash_traversal(tmp_path):
    arc = tmp_path / "evil_backslash.zip"
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("..\\escape.txt", "pwned")
    dest = tmp_path / "out"
    with pytest.raises(SecurityError):
        safe_extract_zip(arc, dest)
    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_zip_normal(tmp_path):
    arc = tmp_path / "ok.zip"
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("dir/file.txt", "hi")
    dest = tmp_path / "out"
    safe_extract_zip(arc, dest)
    assert (dest / "dir" / "file.txt").read_text() == "hi"


def test_safe_extract_zip_rejects_zipslip(tmp_path):
    arc = tmp_path / "evil.zip"
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("../escape.txt", "pwned")
    dest = tmp_path / "out"
    with pytest.raises(SecurityError) as ei:
        safe_extract_zip(arc, dest)
    assert "escape.txt" in str(ei.value)
    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_tar_rejects_traversal(tmp_path):
    payload = tmp_path / "p.txt"
    payload.write_text("x")
    arc = tmp_path / "evil.tar"
    with tarfile.open(arc, "w") as t:
        t.add(payload, arcname="../escape.txt")
    dest = tmp_path / "out"
    with pytest.raises(SecurityError):
        safe_extract_tar(arc, dest)


def test_safe_extract_tar_link_error_names_the_linkname(tmp_path):
    """The reject error must name the dangerous linkname, not the link's own filename."""
    payload = tmp_path / "p.txt"
    payload.write_text("x")
    arc = tmp_path / "evil_link.tar"
    with tarfile.open(arc, "w") as t:
        info = t.gettarinfo(payload, arcname="innocuous_link_name.txt")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../escape_target.txt"
        t.addfile(info)
    dest = tmp_path / "out"
    with pytest.raises(SecurityError) as ei:
        safe_extract_tar(arc, dest)
    assert "escape_target.txt" in str(ei.value)
    assert "innocuous_link_name.txt" not in str(ei.value)


def test_safe_extract_7z_normal(tmp_path):
    payload = tmp_path / "p.txt"
    payload.write_text("hi")
    arc = tmp_path / "ok.7z"
    with py7zr.SevenZipFile(arc, "w") as z:
        z.write(payload, arcname="dir/file.txt")
    dest = tmp_path / "out"
    safe_extract_7z(arc, dest)
    assert (dest / "dir" / "file.txt").read_text() == "hi"


def test_safe_extract_7z_rejects_traversal(tmp_path):
    # py7zr allows writing a ".." arcname directly, so we can craft a genuinely
    # malicious archive without monkeypatching getnames().
    payload = tmp_path / "p.txt"
    payload.write_text("pwned")
    arc = tmp_path / "evil.7z"
    with py7zr.SevenZipFile(arc, "w") as z:
        z.write(payload, arcname="../escape.txt")
    dest = tmp_path / "out"
    with pytest.raises(SecurityError):
        safe_extract_7z(arc, dest)
    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_7z_targets_selective(tmp_path):
    payload_a = tmp_path / "a.txt"
    payload_a.write_text("aaa")
    payload_b = tmp_path / "b.txt"
    payload_b.write_text("bbb")
    arc = tmp_path / "multi.7z"
    with py7zr.SevenZipFile(arc, "w") as z:
        z.write(payload_a, arcname="a.txt")
        z.write(payload_b, arcname="b.txt")
    dest = tmp_path / "out"
    safe_extract_7z(arc, dest, targets=["a.txt"])
    assert (dest / "a.txt").read_text() == "aaa"
    assert not (dest / "b.txt").exists()
