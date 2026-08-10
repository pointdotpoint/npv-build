import sys

import pytest

from npv_build.core.bundled_tools import bundled_tool_path


def test_source_checkout_has_no_bundled_tool(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert bundled_tool_path("npv-photomode") is None


@pytest.mark.parametrize(
    ("platform", "filename"),
    [("linux", "npv-tweakdb"), ("win32", "npv-tweakdb.exe")],
)
def test_frozen_bundle_resolves_platform_helper(monkeypatch, tmp_path, platform, filename):
    helper = tmp_path / "npv_helpers" / "npv-tweakdb" / filename
    helper.parent.mkdir(parents=True)
    helper.touch()
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(sys, "platform", platform)

    assert bundled_tool_path("npv-tweakdb") == helper


def test_frozen_bundle_falls_back_to_legacy_flat_layout(monkeypatch, tmp_path):
    helper = tmp_path / "npv_helpers" / "npv-inject"
    helper.parent.mkdir(parents=True)
    helper.touch()
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    assert bundled_tool_path("npv-inject") == helper


def test_unknown_helper_is_rejected():
    with pytest.raises(ValueError, match="Unknown bundled helper"):
        bundled_tool_path("not-an-npv-tool")
