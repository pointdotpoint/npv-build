"""Mod manager view: list built NPVs with install/uninstall/open-folder (spec GUI-5)."""

from __future__ import annotations

import logging
from pathlib import Path

import customtkinter as ctk

import npv_build.gui_theme as theme

from ..core.errors import InstallError
from ..core.platform import open_folder
from ..gui_logic.modmanager import ModEntry, install_mod, list_mods, uninstall_mod

logger = logging.getLogger(__name__)


class ModManagerView(ctk.CTkFrame):
    """Scrollable list of built mods, each with install/uninstall/open-folder actions."""

    def __init__(
        self,
        master,
        output_root: Path,
        game_dir: Path,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._output_root = output_root
        self._game_dir = game_dir

        self.configure(fg_color=theme.BG)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG)
        self._scroll.pack(
            fill="both", expand=True, padx=theme.PAD_S, pady=(theme.PAD_S, theme.PAD_XS)
        )

        self._error_label = ctk.CTkLabel(
            self, text="", text_color=theme.ERROR, font=theme.body_font(), wraplength=400
        )

        self.refresh()

    def refresh(self) -> None:
        """Clear and rebuild the mod list from list_mods()."""
        for child in self._scroll.winfo_children():
            child.destroy()

        mods = list_mods(self._output_root, self._game_dir)

        if not mods:
            ctk.CTkLabel(
                self._scroll,
                text="No built mods found.",
                font=theme.hint_font(),
                text_color=theme.TEXT_MUTED,
            ).pack(pady=theme.PAD_S)
            return

        for entry in mods:
            self._build_row(entry)

    def _build_row(self, entry: ModEntry) -> None:
        row_frame = ctk.CTkFrame(
            self._scroll,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=6,
        )
        row_frame.pack(fill="x", padx=theme.PAD_XS, pady=theme.PAD_XS)

        status = "Installed" if entry.installed else "Not installed"
        mod_id_label = ctk.CTkLabel(
            row_frame,
            text=entry.mod_id,
            font=theme.label_font(),
            text_color=theme.TEXT,
            anchor="w",
        )
        status_label = ctk.CTkLabel(
            row_frame,
            text=status,
            font=theme.hint_font(),
            text_color=theme.SUCCESS if entry.installed else theme.TEXT_MUTED,
            anchor="w",
        )
        mod_id_label.grid(row=0, column=0, sticky="w", padx=theme.PAD_M, pady=(theme.PAD_S, 0))
        status_label.grid(row=1, column=0, sticky="w", padx=theme.PAD_M, pady=(0, theme.PAD_S))
        row_frame.grid_columnconfigure(0, weight=1)

        if entry.installed:
            action_button = ctk.CTkButton(
                row_frame,
                text="Uninstall",
                command=lambda e=entry: self._on_uninstall_clicked(e),
                fg_color=theme.SURFACE,
                hover_color=theme.BORDER,
                border_color=theme.BORDER,
                border_width=1,
                text_color=theme.TEXT,
                font=theme.body_font(),
            )
        else:
            action_button = ctk.CTkButton(
                row_frame,
                text="Install",
                command=lambda e=entry: self._on_install_clicked(e),
                fg_color=theme.ACCENT,
                hover_color=theme.ACCENT_HOVER,
                text_color=theme.BG,
                font=theme.body_font(),
            )
        action_button.grid(row=0, column=1, rowspan=2, padx=theme.PAD_XS, pady=theme.PAD_S)

        open_button = ctk.CTkButton(
            row_frame,
            text="Open Folder",
            command=lambda e=entry: self._on_open_folder_clicked(e),
            fg_color=theme.SURFACE,
            hover_color=theme.BORDER,
            border_color=theme.BORDER,
            border_width=1,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        open_button.grid(row=0, column=2, rowspan=2, padx=(0, theme.PAD_M), pady=theme.PAD_S)

    def _on_install_clicked(self, entry: ModEntry) -> None:
        self._clear_error()
        try:
            install_mod(entry, self._game_dir)
        except InstallError as e:
            self._show_error(str(e))
            return
        self.refresh()

    def _on_uninstall_clicked(self, entry: ModEntry) -> None:
        self._clear_error()
        try:
            uninstall_mod(entry, self._game_dir)
        except InstallError as e:
            self._show_error(str(e))
            return
        self.refresh()

    def _on_open_folder_clicked(self, entry: ModEntry) -> None:
        self._clear_error()
        try:
            # archive_path is "<mod_root>/archive/pc/mod/<file>.archive"; 3 parents
            # up lands back on <mod_root> (mod/ -> pc/ -> archive/). Matches
            # gui_logic.modmanager.list_mods's mod_root derivation.
            open_folder(entry.archive_path.parents[3])
        except Exception as e:  # noqa: BLE001 - GUI event loop must survive
            logger.exception("Failed to open mod folder")
            self._show_error(f"Could not open folder:\n{e}")

    def _show_error(self, message: str) -> None:
        self._error_label.configure(text=message)
        self._error_label.pack(fill="x", padx=theme.PAD_S, pady=(0, theme.PAD_S))

    def _clear_error(self) -> None:
        self._error_label.pack_forget()
