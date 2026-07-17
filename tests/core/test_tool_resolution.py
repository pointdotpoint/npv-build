"""Tests for core.toolpaths.resolve_tool (spec SEC-3)."""

import pytest

from npv_build.core.errors import ToolError
from npv_build.core.toolpaths import resolve_tool


def test_resolve_tool_returns_absolute_existing(tmp_path):
    fake = tmp_path / "mytool"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    resolved = resolve_tool("mytool", [fake])
    assert resolved.is_absolute() and resolved.exists()


def test_resolve_tool_missing_raises(tmp_path):
    with pytest.raises(ToolError) as ei:
        resolve_tool("ghost", [tmp_path / "nope"])
    assert "ghost" in str(ei.value)
