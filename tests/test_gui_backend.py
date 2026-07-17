import queue as queue_mod
from pathlib import Path

import pytest

import npv_build.gui_backend as gui_backend
from npv_build.core.errors import NpvError, UnsupportedPatchError
from npv_build.core.pipeline import PipelineEvent


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


def test_preview_save_unsupported_patch_error(monkeypatch):
    # Regression test: UnsupportedPatchError should propagate from preview_save
    # and be handleable by the GUI without crashing the callback
    def mock_parse_save(save_path):
        raise UnsupportedPatchError(
            user_message="Game build 3000 is not supported (supports 1.6 only)",
            remediation="Update your game to patch 1.6",
        )

    monkeypatch.setattr(gui_backend, "parse_save", mock_parse_save)

    with pytest.raises(UnsupportedPatchError) as exc_info:
        gui_backend.preview_save(Path("dummy.sav.dat"))

    assert exc_info.value.user_message == "Game build 3000 is not supported (supports 1.6 only)"
    assert exc_info.value.remediation == "Update your game to patch 1.6"


def _drain(q):
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue_mod.Empty:
            return items


def test_build_worker_success_posts_done(monkeypatch, tmp_path):
    class FakeService:
        def build(self, req, on_event=None, cancel=None):
            on_event(
                PipelineEvent(kind="stage_started", stage="parse_save", message="Parsing save")
            )
            on_event(PipelineEvent(kind="stage_completed", stage="parse_save", message="ok"))

            class R:
                output_dir = str(tmp_path)

            return R()

    monkeypatch.setattr(gui_backend, "PipelineService", FakeService)
    q = queue_mod.Queue()
    w = gui_backend.BuildWorker(q)
    save = tmp_path / "s.dat"
    save.write_bytes(b"x")
    w.start(
        save_path=save,
        npv_name="V",
        output_dir=tmp_path,
        game_dir=tmp_path,
        template_cache=tmp_path,
        clear_cache=False,
    )
    w._thread.join(timeout=10)
    items = _drain(q)
    assert ("done", str(tmp_path)) in items
    assert any(
        kind == "log" and "parse_save" in str(val) or "Parsing" in str(val) for kind, val in items
    )


def test_build_worker_error_posts_error(monkeypatch, tmp_path):
    class FakeService:
        def build(self, req, on_event=None, cancel=None):
            raise NpvError("bad save", remediation="pick another")

    monkeypatch.setattr(gui_backend, "PipelineService", FakeService)
    q = queue_mod.Queue()
    w = gui_backend.BuildWorker(q)
    save = tmp_path / "s.dat"
    save.write_bytes(b"x")
    w.start(
        save_path=save,
        npv_name="V",
        output_dir=tmp_path,
        game_dir=tmp_path,
        template_cache=tmp_path,
        clear_cache=False,
    )
    w._thread.join(timeout=10)
    items = _drain(q)
    errs = [val for kind, val in items if kind == "error"]
    assert errs and "bad save" in errs[0] and "pick another" in errs[0]


def test_build_worker_cancel_sets_token(monkeypatch, tmp_path):
    q = queue_mod.Queue()
    w = gui_backend.BuildWorker(q)
    w.cancel()  # before start: must not raise
    assert w._make_token().cancelled is False  # fresh token per start
