from pathlib import Path

import npv_build.gui_backend as gui_backend


def test_check_dependencies(monkeypatch):
    # Mock shutil.which
    def mock_which(cmd):
        if "WolvenKit.CLI" in cmd:
            return "/path/to/WolvenKit.CLI"
        if "blender" in cmd:
            return "/path/to/blender"
        if "npv-inject" in cmd:
            return "/path/to/npv-inject"
        return None

    monkeypatch.setattr(gui_backend.shutil, "which", mock_which)

    # Mock _resolve_inject_binary
    monkeypatch.setattr("npv_build.wolvenkit._resolve_inject_binary", lambda: "/path/to/npv-inject")

    # Test with game_dir=None
    res = gui_backend.check_dependencies(None)
    assert res["wolvenkit"] is True
    assert res["blender"] is True
    assert res["npv_inject"] is True
    assert res["game_dir_valid"] is False

    # Test with valid mock game_dir
    class MockPath:
        def __init__(self, path):
            self.path = Path(path)

        def __truediv__(self, other):
            return MockPath(self.path / other)

        def exists(self):
            # simulate basegame_4_appearance.archive exists
            return "basegame_4_appearance.archive" in str(self.path)

    res = gui_backend.check_dependencies(MockPath("/fake/game/dir"))
    assert res["game_dir_valid"] is True


def test_preview_save(monkeypatch):
    # Mock parse_save
    def mock_parse_save(save_path):
        return {
            "body_rig": "pwa",
            "skin_tone": "01_ca_pale",
            "hair": {"style": "hh_001", "color": "black"},
            "selections": [1, 2, 3],
        }

    monkeypatch.setattr(gui_backend, "parse_save", mock_parse_save)

    res = gui_backend.preview_save(Path("dummy.sav.dat"))
    assert res["body_rig"] == "pwa"
    assert res["skin_tone"] == "01_ca_pale"
    assert res["hair_style"] == "hh_001"
    assert res["hair_color"] == "black"
    assert res["selections_count"] == 3
