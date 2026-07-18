import re

import customtkinter as ctk

from npv_build import gui_theme

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_palette_constants_are_hex():
    for name in (
        "BG",
        "SURFACE",
        "SURFACE_ALT",
        "BORDER",
        "ACCENT",
        "ACCENT_HOVER",
        "TEXT",
        "TEXT_MUTED",
        "SUCCESS",
        "WARNING",
        "ERROR",
    ):
        val = getattr(gui_theme, name)
        assert _HEX.match(val), f"{name}={val!r} not a hex color"


def test_spacing_constants_are_ints():
    for name in ("PAD_XS", "PAD_S", "PAD_M", "PAD_L", "PAD_XL"):
        assert isinstance(getattr(gui_theme, name), int)


def test_resolve_ui_family_returns_nonempty(gui_root):
    fam = gui_theme.resolve_ui_family()
    assert isinstance(fam, str) and fam.strip()


def test_system_font_returns_ctkfont_with_size_weight(gui_root):
    f = gui_theme.system_font(14, "bold")
    assert isinstance(f, ctk.CTkFont)
    assert f.cget("size") == 14
    assert f.cget("weight") == "bold"


def test_named_font_helpers(gui_root):
    for helper in (
        gui_theme.title_font,
        gui_theme.header_font,
        gui_theme.label_font,
        gui_theme.body_font,
        gui_theme.hint_font,
    ):
        assert isinstance(helper(), ctk.CTkFont)
