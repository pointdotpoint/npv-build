import pytest

from npv_build.core.errors import (
    InstallError,
    NpvError,
    PipelineCancelled,
    SaveFormatError,
    SecurityError,
    ToolError,
    ToolTimeoutError,
    UnsupportedPatchError,
)


def test_npv_error_fields_and_str():
    e = NpvError(
        "Save file unreadable",
        remediation="Re-copy the save",
        details="bad header",
        module_name="Save Parser",
    )
    assert e.user_message == "Save file unreadable"
    assert e.remediation == "Re-copy the save"
    assert e.module_name == "Save Parser"
    assert str(e) == "Save file unreadable\nbad header"


def test_str_without_details():
    assert str(NpvError("boom")) == "boom"


def test_tool_error_fields():
    e = ToolError(
        "WolvenKit failed", tool="WolvenKit.CLI", argv=["WolvenKit.CLI", "pack"], exit_code=3
    )
    assert e.tool == "WolvenKit.CLI"
    assert e.argv == ["WolvenKit.CLI", "pack"]
    assert e.exit_code == 3
    assert isinstance(e, NpvError)


def test_hierarchy():
    assert issubclass(ToolTimeoutError, ToolError)
    for cls in (
        SaveFormatError,
        UnsupportedPatchError,
        InstallError,
        SecurityError,
        PipelineCancelled,
    ):
        assert issubclass(cls, NpvError)


def test_catchable_as_exception():
    with pytest.raises(NpvError):
        raise UnsupportedPatchError("build 3000 unsupported")
