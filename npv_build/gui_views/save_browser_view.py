"""Save browser view: lists discovered saves with thumbnails (spec GUI-3)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import npv_build.gui_theme as theme

from ..gui_logic.discovery import SaveEntry, list_saves

logger = logging.getLogger(__name__)

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
_THUMB_SIZE = (96, 54)


def build_rows(entries: list[SaveEntry]) -> list[dict]:
    """Map SaveEntry objects to plain row dicts for display.

    Pure and Tk-free: formats each entry's own mtime (never wall-clock "now").
    """
    rows = []
    for e in entries:
        rows.append(
            {
                "name": e.name,
                "path": e.path,
                "timestamp": datetime.fromtimestamp(e.mtime).strftime(_TIMESTAMP_FORMAT),
                "has_thumb": e.thumbnail is not None,
            }
        )
    return rows


class SaveBrowserView(ctk.CTkFrame):
    """Scrollable list of discovered saves, plus a manual file-picker fallback."""

    def __init__(
        self,
        master,
        on_select: Callable[[Path], None],
        save_dirs: list[Path] | None = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._on_select = on_select
        self._save_dirs = save_dirs

        self.configure(fg_color=theme.BG)

        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=theme.BG,
            scrollbar_button_color=theme.ACCENT,
        )
        self._scroll.pack(
            fill="both", expand=True, padx=theme.PAD_S, pady=(theme.PAD_S, theme.PAD_XS)
        )

        self._browse_button = ctk.CTkButton(
            self,
            text="Browse…",
            command=self._on_browse_clicked,
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            text_color=theme.BG,
            font=theme.body_font(),
        )
        self._browse_button.pack(fill="x", padx=theme.PAD_S, pady=(0, theme.PAD_S))

        self._image_refs: list[ctk.CTkImage] = []

        self.refresh()

    def refresh(self) -> None:
        """Clear and rebuild the row list from list_saves()."""
        for child in self._scroll.winfo_children():
            child.destroy()
        self._image_refs.clear()

        entries = list_saves(self._save_dirs)
        rows = build_rows(entries)

        if not rows:
            ctk.CTkLabel(
                self._scroll,
                text="No saves found — use Browse…",
                font=theme.hint_font(),
                text_color=theme.TEXT_MUTED,
            ).pack(pady=theme.PAD_S)
            return

        for entry, row in zip(entries, rows, strict=True):
            self._build_row(entry, row)

    def _build_row(self, entry: SaveEntry, row: dict) -> None:
        row_frame = ctk.CTkFrame(
            self._scroll,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=6,
        )
        row_frame.pack(fill="x", padx=theme.PAD_XS, pady=theme.PAD_XS)

        image = self._load_thumbnail(entry.thumbnail)

        name_label = ctk.CTkLabel(
            row_frame,
            text=row["name"],
            font=theme.label_font(),
            text_color=theme.TEXT,
            anchor="w",
        )
        timestamp_label = ctk.CTkLabel(
            row_frame,
            text=row["timestamp"],
            font=theme.hint_font(),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )

        def _on_enter(_event=None, frame=row_frame):
            frame.configure(border_color=theme.ACCENT)

        def _on_leave(_event=None, frame=row_frame):
            frame.configure(border_color=theme.BORDER)

        button = ctk.CTkButton(
            row_frame,
            text="",
            image=image,
            compound="left",
            anchor="w",
            fg_color="transparent",
            hover_color=theme.SURFACE_ALT,
            command=lambda p=entry.path: self._on_select(p),
        )
        button.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=theme.PAD_XS, pady=theme.PAD_XS)
        name_label.grid(row=0, column=1, sticky="w", padx=(0, theme.PAD_S), pady=(theme.PAD_XS, 0))
        timestamp_label.grid(
            row=1, column=1, sticky="w", padx=(0, theme.PAD_S), pady=(0, theme.PAD_XS)
        )
        row_frame.grid_columnconfigure(1, weight=1)

        for widget in (row_frame, button, name_label, timestamp_label):
            widget.bind("<Enter>", _on_enter)
            widget.bind("<Leave>", _on_leave)

    def _load_thumbnail(self, thumbnail: Path | None) -> ctk.CTkImage | None:
        if thumbnail is None:
            return None
        try:
            from PIL import Image

            pil_image = Image.open(thumbnail)
            pil_image.load()  # force eager decode now, inside the guard - catches
            # truncated/corrupt pixel data that Image.open() (lazy, header-only) misses.
            # Without this, CTkImage defers decoding until CTkButton draws it, which
            # happens outside this try/except and would crash the whole save list.
            image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=_THUMB_SIZE)
            self._image_refs.append(image)
            return image
        except Exception:  # noqa: BLE001 - a bad thumbnail must never crash the save list
            logger.debug("Failed to load thumbnail %s", thumbnail, exc_info=True)
            return None

    def _on_browse_clicked(self) -> None:
        path = filedialog.askopenfilename(
            title="Select sav.dat",
            filetypes=[("Cyberpunk save", "sav.dat"), ("All files", "*.*")],
        )
        if path:
            self._on_select(Path(path))
