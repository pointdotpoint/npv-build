"""Mod manager view: list built NPVs with install/uninstall/open-folder (spec GUI-5)."""

from __future__ import annotations

import logging
from pathlib import Path

import customtkinter as ctk

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

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        self._error_label = ctk.CTkLabel(self, text="", text_color="#e74c3c", wraplength=400)

        self.refresh()

    def refresh(self) -> None:
        """Clear and rebuild the mod list from list_mods()."""
        for child in self._scroll.winfo_children():
            child.destroy()

        mods = list_mods(self._output_root, self._game_dir)

        if not mods:
            ctk.CTkLabel(self._scroll, text="No built mods found.").pack(pady=8)
            return

        for entry in mods:
            self._build_row(entry)

    def _build_row(self, entry: ModEntry) -> None:
        row_frame = ctk.CTkFrame(self._scroll)
        row_frame.pack(fill="x", padx=4, pady=2)

        status = "Installed" if entry.installed else "Not installed"
        label = ctk.CTkLabel(row_frame, text=f"{entry.mod_id}  [{status}]", anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=4, pady=4)

        if entry.installed:
            action_button = ctk.CTkButton(
                row_frame,
                text="Uninstall",
                command=lambda e=entry: self._on_uninstall_clicked(e),
            )
        else:
            action_button = ctk.CTkButton(
                row_frame,
                text="Install",
                command=lambda e=entry: self._on_install_clicked(e),
            )
        action_button.pack(side="right", padx=4, pady=4)

        open_button = ctk.CTkButton(
            row_frame,
            text="Open Folder",
            command=lambda e=entry: self._on_open_folder_clicked(e),
        )
        open_button.pack(side="right", padx=4, pady=4)

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
            open_folder(entry.archive_path.parents[3])
        except Exception as e:  # noqa: BLE001 - GUI event loop must survive
            logger.exception("Failed to open mod folder")
            self._show_error(f"Could not open folder:\n{e}")

    def _show_error(self, message: str) -> None:
        self._error_label.configure(text=message)
        self._error_label.pack(fill="x", padx=8, pady=(0, 8))

    def _clear_error(self) -> None:
        self._error_label.pack_forget()
