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
