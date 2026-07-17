import tarfile
import zipfile

import pytest

from npv_build.core.errors import SecurityError
from npv_build.core.safe_extract import (
    is_safe_member,
    safe_extract_tar,
    safe_extract_zip,
)


def test_is_safe_member_accepts_normal(tmp_path):
    assert is_safe_member("a/b/c.txt", tmp_path) is True


def test_is_safe_member_rejects_traversal(tmp_path):
    assert is_safe_member("../../etc/passwd", tmp_path) is False
    assert is_safe_member("/abs/path", tmp_path) is False


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
