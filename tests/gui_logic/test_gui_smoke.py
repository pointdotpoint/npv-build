import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"), reason="requires a display (headless environment)"
)


def test_save_browser_view_instantiates():
    import customtkinter as ctk

    from npv_build.gui_views.save_browser_view import SaveBrowserView

    root = ctk.CTk()
    try:
        view = SaveBrowserView(root, lambda p: None, save_dirs=[])
        root.update()
        assert view is not None
    finally:
        root.destroy()


def test_full_app_navigates_all_tabs_no_exception(monkeypatch, tmp_path):
    """Milestone gate (Task 8): instantiate App, update(), navigate every
    view via its public nav method, destroy() -- no exception anywhere.

    Uses a config with a valid-looking game_dir on record so the wizard does
    not intercept navigation (the wizard's own display is covered by
    test_wizard_shows_on_first_run below).
    """
    from npv_build.gui import App

    fake_config = {"game_dir": str(tmp_path)}
    monkeypatch.setattr("npv_build.gui.load_config", lambda: fake_config)
    monkeypatch.setattr("npv_build.gui.save_config", lambda cfg: None)

    app = App()
    try:
        app.update()

        app.show_save_browser_tab()
        app.update()

        app.show_mod_manager_tab()
        app.update()

        app.show_settings_tab()
        app.update()

        app.show_build_tab()
        app.update()
    finally:
        app.destroy()


def test_wizard_shows_on_first_run(monkeypatch):
    """WizardModel.needs_wizard gates the first-run wizard overlay."""
    from npv_build.gui import App

    monkeypatch.setattr("npv_build.gui.load_config", lambda: {})

    app = App()
    try:
        app.update()
        assert hasattr(app, "_wizard_overlay")
    finally:
        app.destroy()
