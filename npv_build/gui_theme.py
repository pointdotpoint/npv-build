"""Central theme: palette, system-font resolver, spacing (UI polish spec)."""

from __future__ import annotations

import customtkinter as ctk

# --- Refined-dark palette ---
BG = "#1a1b26"
SURFACE = "#24283b"
SURFACE_ALT = "#1f2335"
BORDER = "#2f3549"
ACCENT = "#7dcfff"
ACCENT_HOVER = "#5fb8e8"
TEXT = "#c0caf5"
TEXT_MUTED = "#787c99"
SUCCESS = "#9ece6a"
WARNING = "#e0af68"
ERROR = "#f7768e"

# --- Spacing scale ---
PAD_XS = 4
PAD_S = 8
PAD_M = 12
PAD_L = 20
PAD_XL = 32

# Preferred UI families, best-first. resolve_ui_family picks the first the
# running Tk reports as available, else the Tk default.
_PREFERRED = ("Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Helvetica", "Arial")
_family_cache: str | None = None


def resolve_ui_family() -> str:
    """Best available UI font family for this OS. Requires a Tk root to exist."""
    global _family_cache
    if _family_cache is not None:
        return _family_cache
    try:
        import tkinter.font as tkfont

        available = set(tkfont.families())
        for fam in _PREFERRED:
            if fam in available:
                _family_cache = fam
                return fam
        # Tk default UI font family
        _family_cache = tkfont.nametofont("TkDefaultFont").cget("family")
    except Exception:  # noqa: BLE001 - font resolution must never crash the GUI
        _family_cache = "TkDefaultFont"
    return _family_cache


def system_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=resolve_ui_family(), size=size, weight=weight)


def title_font() -> ctk.CTkFont:
    return system_font(18, "bold")


def header_font() -> ctk.CTkFont:
    return system_font(14, "bold")


def label_font() -> ctk.CTkFont:
    return system_font(12, "bold")


def body_font() -> ctk.CTkFont:
    return system_font(12, "normal")


def hint_font() -> ctk.CTkFont:
    return system_font(11, "normal")


def apply_theme() -> None:
    """Set global appearance mode. Per-widget colors come from the palette
    constants (applied by each view) — we use dark mode as the base."""
    ctk.set_appearance_mode("dark")
