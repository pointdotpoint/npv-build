"""GUI-1 feature-parity gate (Task 8, Step 3).

Enumerates `BuildRequest`'s fields and asserts each is settable through some
view's public surface -- concretely, that the Build tab's `start_build()`
gathers a value for every field (other than `resume`, which is not a
Build-tab input: BuildView's own Retry-from-failed-stage button drives it
internally via `resume=True`, per Task 3) and hands it to `BuildView.start()`
with the field's own name as the kwarg key (BuildRequest field names and the
GUI's kwarg names are required to match 1:1 -- see
`gui_backend._request_kwargs`'s docstring).

This is a scripted, non-interactive assertion (no button clicks / no widget
introspection beyond attribute presence), but it does need a live App
instance to observe what start_build() actually gathers, so it is
DISPLAY-gated like the rest of the Tk-touching test suite.
"""

from __future__ import annotations

import os
from dataclasses import fields

import pytest

from npv_build.core.pipeline import BuildRequest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"), reason="requires a display (headless environment)"
)

# resume is driven by BuildView's Retry-from-failed-stage button
# (resume=True), not a Build-tab input field -- see BuildView._on_retry_clicked.
_NOT_BUILD_TAB_FIELDS = {"resume"}


def test_every_build_request_field_is_settable_via_build_tab():
    from npv_build.gui import App

    app = App()
    try:
        app.update()
        app.entry_npv_name.insert(0, "Parity Test V")
        app.entry_output.insert(0, "/tmp/npv_parity_test/out")
        app.entry_game_dir.insert(0, "/tmp/npv_parity_test/game")
        app.entry_save.insert(0, "/tmp/npv_parity_test/sav.dat")

        captured = {}

        def fake_start(**kwargs):
            captured.update(kwargs)

        app._build_view.start = fake_start
        app.start_build()

        expected_fields = {f.name for f in fields(BuildRequest)} - _NOT_BUILD_TAB_FIELDS
        missing = expected_fields - captured.keys()
        assert not missing, f"BuildRequest fields not gathered by start_build(): {missing}"
    finally:
        app.destroy()


def test_every_build_request_field_has_a_dedicated_widget():
    """Belt-and-suspenders: each field (other than `resume`) also has its own
    named widget attribute on App, not just a value baked into start_build().
    """
    from npv_build.gui import App

    # BuildRequest field name -> App widget attribute name.
    field_to_widget = {
        "save_path": "entry_save",
        "npv_name": "entry_npv_name",
        "output_dir": "entry_output",
        "game_dir": "entry_game_dir",
        # template_cache is derived from get_cache_dir(), not user-entered.
        "clear_cache": "switch_clear_cache",
        "cc_json_path": "entry_cc_json",
        "hair_override": "entry_hair_ovr",
        "skin_override": "entry_skin_ovr",
        "garments": "garment_list",
        "user_head_glb": "entry_head_glb",
        "user_head_mesh": "entry_head_mesh",
        "user_heb_mesh": "entry_heb_mesh",
        "restore_head_materials": "switch_restore_head",
    }
    expected_fields = (
        {f.name for f in fields(BuildRequest)} - _NOT_BUILD_TAB_FIELDS - {"template_cache"}
    )
    assert expected_fields <= field_to_widget.keys(), (
        "test's own mapping is missing a BuildRequest field -- update field_to_widget"
    )

    app = App()
    try:
        app.update()
        for field_name, widget_attr in field_to_widget.items():
            assert hasattr(app, widget_attr), (
                f"BuildRequest field '{field_name}' has no corresponding App.{widget_attr} widget"
            )
    finally:
        app.destroy()
