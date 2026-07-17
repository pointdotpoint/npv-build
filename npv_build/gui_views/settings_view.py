"""Settings view: form for game dir, output dir, verbosity, patch override, check updates (spec GUI-7).

A thin widget that displays a form bound to Settings, with:
  - Game dir text entry + browse button
  - Output dir text entry + browse button
  - Log verbosity dropdown (0/1/2)
  - Patch override text entry
  - Check updates checkbox
  - Save and Cancel buttons
"""

from __future__ import annotations

from tkinter import filedialog

import customtkinter as ctk

from ..gui_logic.settings import Settings, load_settings, save_settings, validate


class SettingsView(ctk.CTkFrame):
    """Settings form view: display and edit Settings."""

    def __init__(
        self,
        master,
        on_saved: callable | None = None,
        on_cancelled: callable | None = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._on_saved = on_saved
        self._on_cancelled = on_cancelled

        # Load current settings
        self.settings = load_settings()

        # Build the form
        self._build_form()

    def _build_form(self) -> None:
        """Construct the form widgets."""
        self.grid_columnconfigure(1, weight=1)

        # Game dir row
        ctk.CTkLabel(self, text="Game Directory:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self._game_dir_entry = ctk.CTkEntry(self)
        self._game_dir_entry.insert(0, self.settings.game_dir or "")
        self._game_dir_entry.grid(row=0, column=1, sticky="ew", padx=(0, 4), pady=8)
        ctk.CTkButton(
            self,
            text="Browse",
            width=80,
            command=self._browse_game_dir,
        ).grid(row=0, column=2, sticky="ew", padx=(4, 8), pady=8)

        # Output dir row
        ctk.CTkLabel(self, text="Output Directory:").grid(
            row=1, column=0, sticky="w", padx=8, pady=8
        )
        self._output_dir_entry = ctk.CTkEntry(self)
        self._output_dir_entry.insert(0, self.settings.output_dir or "")
        self._output_dir_entry.grid(row=1, column=1, sticky="ew", padx=(0, 4), pady=8)
        ctk.CTkButton(
            self,
            text="Browse",
            width=80,
            command=self._browse_output_dir,
        ).grid(row=1, column=2, sticky="ew", padx=(4, 8), pady=8)

        # Log verbosity row
        ctk.CTkLabel(self, text="Log Verbosity:").grid(row=2, column=0, sticky="w", padx=8, pady=8)
        self._verbosity_var = ctk.StringVar(value=str(self.settings.log_verbosity))
        verbosity_menu = ctk.CTkComboBox(
            self,
            values=["0", "1", "2"],
            variable=self._verbosity_var,
            state="readonly",
        )
        verbosity_menu.grid(row=2, column=1, sticky="ew", padx=(0, 4), pady=8)
        ctk.CTkLabel(self, text="(0=quiet, 1=normal, 2=verbose)", text_color="gray").grid(
            row=2, column=2, sticky="w", padx=(4, 8), pady=8
        )

        # Patch override row
        ctk.CTkLabel(self, text="Patch Override:").grid(row=3, column=0, sticky="w", padx=8, pady=8)
        self._patch_override_entry = ctk.CTkEntry(self)
        self._patch_override_entry.insert(0, self.settings.patch_override or "")
        self._patch_override_entry.grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=8
        )

        # Check updates row
        self._check_updates_var = ctk.BooleanVar(value=self.settings.check_updates)
        ctk.CTkCheckBox(
            self,
            text="Check for updates on startup",
            variable=self._check_updates_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=8)

        # Error label
        self._error_label = ctk.CTkLabel(self, text="", text_color="#e74c3c", wraplength=400)
        self._error_label.grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=4)

        # Buttons
        button_frame = ctk.CTkFrame(self)
        button_frame.grid(row=6, column=0, columnspan=3, sticky="ew", padx=8, pady=(8, 8))
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            button_frame,
            text="Save",
            command=self._on_save_clicked,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self._on_cancel_clicked,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _browse_game_dir(self) -> None:
        """Open file dialog to select game directory."""
        path = filedialog.askdirectory(title="Select Cyberpunk 2077 installation directory")
        if path:
            self._game_dir_entry.delete(0, "end")
            self._game_dir_entry.insert(0, path)

    def _browse_output_dir(self) -> None:
        """Open file dialog to select output directory."""
        path = filedialog.askdirectory(title="Select output directory for mods")
        if path:
            self._output_dir_entry.delete(0, "end")
            self._output_dir_entry.insert(0, path)

    def _on_save_clicked(self) -> None:
        """Validate and save settings."""
        # Collect form values
        game_dir = self._game_dir_entry.get().strip() or None
        output_dir = self._output_dir_entry.get().strip() or None
        log_verbosity = int(self._verbosity_var.get())
        patch_override = self._patch_override_entry.get().strip() or None
        check_updates = self._check_updates_var.get()

        # Build settings object
        settings = Settings(
            game_dir=game_dir,
            output_dir=output_dir,
            log_verbosity=log_verbosity,
            patch_override=patch_override,
            check_updates=check_updates,
        )

        # Validate
        problems = validate(settings)
        if problems:
            self._error_label.configure(text="\n".join(problems))
            return

        # Save
        self._error_label.configure(text="")
        save_settings(settings)
        if self._on_saved:
            self._on_saved()

    def _on_cancel_clicked(self) -> None:
        """Cancel and discard changes."""
        if self._on_cancelled:
            self._on_cancelled()
