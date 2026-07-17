import os
import queue

import pytest

from npv_build.gui_views.build_view import BuildViewModel

_HAS_DISPLAY = bool(os.environ.get("DISPLAY"))


def test_lifecycle_running_then_done():
    vm = BuildViewModel()
    assert not vm.can_cancel and not vm.can_retry
    vm.on_start()
    assert vm.can_cancel and not vm.can_retry
    vm.on_event("done", "/out")
    assert not vm.can_cancel and not vm.can_retry
    assert vm.state == "done"


def test_failure_enables_retry():
    vm = BuildViewModel()
    vm.on_start()
    vm.on_event("error", "Bake failed")
    assert vm.state == "failed"
    assert vm.can_retry and not vm.can_cancel
    assert vm.last_error == "Bake failed"


def test_cancel_transitions_to_cancelling():
    vm = BuildViewModel()
    vm.on_start()
    vm.on_cancel_requested()
    assert vm.state == "cancelling" and not vm.can_cancel
    vm.on_event("error", "Build cancelled.")
    assert vm.state == "failed"  # cancelled surfaces as a terminal error tuple
    assert vm.can_retry


def test_retry_resets_to_running():
    vm = BuildViewModel()
    vm.on_start()
    vm.on_event("error", "x")
    vm.on_start(resume=True)
    assert vm.state == "running" and vm.resume_requested


@pytest.mark.skipif(not _HAS_DISPLAY, reason="requires a display (headless environment)")
def test_build_view_instantiates():
    import customtkinter as ctk

    from npv_build.gui_views.build_view import BuildView

    root = ctk.CTk()
    try:
        view = BuildView(
            root,
            start_build=lambda **kw: None,
            cancel_build=lambda: None,
            build_queue=queue.Queue(),
            is_worker_alive=lambda: False,
        )
        root.update()
        assert view is not None
        assert view.vm.state == "idle"
    finally:
        root.destroy()


@pytest.mark.skipif(not _HAS_DISPLAY, reason="requires a display (headless environment)")
def test_build_view_shows_full_error_and_retry_button():
    """Regression: error display must show the FULL val string (user_message +
    remediation), not truncate to 25 chars, and Retry must appear only on failure.
    """
    import customtkinter as ctk

    from npv_build.gui_views.build_view import BuildView

    root = ctk.CTk()
    try:
        view = BuildView(
            root,
            start_build=lambda **kw: None,
            cancel_build=lambda: None,
            build_queue=queue.Queue(),
            is_worker_alive=lambda: False,
        )
        long_msg = "Bake failed: " + ("x" * 100) + "\nRemediation: reinstall Blender"
        view.vm.on_start()
        view.vm.on_event("error", long_msg)
        view._sync_widgets()
        root.update()
        assert view._error_label.cget("text") == long_msg
        assert view._retry_button.grid_info()  # gridded (visible) once vm.can_retry
    finally:
        root.destroy()
