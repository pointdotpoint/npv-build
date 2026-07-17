"""Save browser view: lists discovered saves with thumbnails (spec GUI-3)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

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

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        self._browse_button = ctk.CTkButton(self, text="Browse…", command=self._on_browse_clicked)
        self._browse_button.pack(fill="x", padx=8, pady=(0, 8))

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
            ctk.CTkLabel(self._scroll, text="No saves found.").pack(pady=8)
            return

        for entry, row in zip(entries, rows, strict=True):
            self._build_row(entry, row)

    def _build_row(self, entry: SaveEntry, row: dict) -> None:
        row_frame = ctk.CTkFrame(self._scroll)
        row_frame.pack(fill="x", padx=4, pady=2)

        image = self._load_thumbnail(entry.thumbnail)

        button = ctk.CTkButton(
            row_frame,
            text=f"{row['name']}\n{row['timestamp']}",
            image=image,
            compound="left",
            anchor="w",
            command=lambda p=entry.path: self._on_select(p),
        )
        button.pack(fill="x", padx=4, pady=4)

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
