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

import npv_build.gui_theme as theme

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

        self.configure(fg_color=theme.BG)

        # Load current settings
        self.settings = load_settings()

        # Build the form
        self._build_form()

    def _label(self, parent, text: str, **kwargs) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=text, font=theme.label_font(), text_color=theme.TEXT, **kwargs
        )

    def _entry(self, parent) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            parent,
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )

    def _build_form(self) -> None:
        """Construct the form widgets."""
        self.grid_columnconfigure(0, weight=1)

        # Card grouping all settings fields.
        card = ctk.CTkFrame(
            self,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=8,
        )
        card.grid(row=0, column=0, sticky="new", padx=theme.PAD_L, pady=theme.PAD_L)
        card.grid_columnconfigure(1, weight=1)

        # Game dir row
        self._label(card, "Game Directory:").grid(
            row=0, column=0, sticky="w", padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M
        )
        self._game_dir_entry = self._entry(card)
        self._game_dir_entry.insert(0, self.settings.game_dir or "")
        self._game_dir_entry.grid(
            row=0, column=1, sticky="ew", padx=(0, theme.PAD_XS), pady=theme.PAD_M
        )
        ctk.CTkButton(
            card,
            text="Browse",
            width=80,
            command=self._browse_game_dir,
            fg_color=theme.SURFACE,
            hover_color=theme.BORDER,
            border_color=theme.BORDER,
            border_width=1,
            text_color=theme.TEXT,
            font=theme.body_font(),
        ).grid(row=0, column=2, sticky="ew", padx=(theme.PAD_XS, theme.PAD_M), pady=theme.PAD_M)

        # Output dir row
        self._label(card, "Output Directory:").grid(
            row=1, column=0, sticky="w", padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M
        )
        self._output_dir_entry = self._entry(card)
        self._output_dir_entry.insert(0, self.settings.output_dir or "")
        self._output_dir_entry.grid(
            row=1, column=1, sticky="ew", padx=(0, theme.PAD_XS), pady=theme.PAD_M
        )
        ctk.CTkButton(
            card,
            text="Browse",
            width=80,
            command=self._browse_output_dir,
            fg_color=theme.SURFACE,
            hover_color=theme.BORDER,
            border_color=theme.BORDER,
            border_width=1,
            text_color=theme.TEXT,
            font=theme.body_font(),
        ).grid(row=1, column=2, sticky="ew", padx=(theme.PAD_XS, theme.PAD_M), pady=theme.PAD_M)

        # Log verbosity row
        self._label(card, "Log Verbosity:").grid(
            row=2, column=0, sticky="w", padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M
        )
        self._verbosity_var = ctk.StringVar(value=str(self.settings.log_verbosity))
        verbosity_menu = ctk.CTkComboBox(
            card,
            values=["0", "1", "2"],
            variable=self._verbosity_var,
            state="readonly",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            button_color=theme.ACCENT,
            button_hover_color=theme.ACCENT_HOVER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        verbosity_menu.grid(row=2, column=1, sticky="ew", padx=(0, theme.PAD_XS), pady=theme.PAD_M)
        ctk.CTkLabel(
            card,
            text="(0=quiet, 1=normal, 2=verbose)",
            font=theme.hint_font(),
            text_color=theme.TEXT_MUTED,
        ).grid(row=2, column=2, sticky="w", padx=(theme.PAD_XS, theme.PAD_M), pady=theme.PAD_M)

        # Patch override row
        self._label(card, "Patch Override:").grid(
            row=3, column=0, sticky="w", padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M
        )
        self._patch_override_entry = self._entry(card)
        self._patch_override_entry.insert(0, self.settings.patch_override or "")
        self._patch_override_entry.grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(0, theme.PAD_M), pady=theme.PAD_M
        )

        # Check updates row
        self._check_updates_var = ctk.BooleanVar(value=self.settings.check_updates)
        ctk.CTkCheckBox(
            card,
            text="Check for updates on startup",
            variable=self._check_updates_var,
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            checkmark_color=theme.BG,
            text_color=theme.TEXT,
            font=theme.body_font(),
        ).grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="w",
            padx=theme.PAD_M,
            pady=(theme.PAD_XS, theme.PAD_M),
        )

        # Error label
        self._error_label = ctk.CTkLabel(
            self, text="", text_color=theme.ERROR, font=theme.body_font(), wraplength=400
        )
        self._error_label.grid(
            row=1, column=0, sticky="w", padx=theme.PAD_L, pady=(0, theme.PAD_XS)
        )

        # Buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=2, column=0, sticky="ew", padx=theme.PAD_L, pady=(0, theme.PAD_L))
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            button_frame,
            text="Save",
            command=self._on_save_clicked,
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            text_color=theme.BG,
            font=theme.body_font(),
        ).grid(row=0, column=0, sticky="ew", padx=(0, theme.PAD_XS))

        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self._on_cancel_clicked,
            fg_color=theme.SURFACE,
            hover_color=theme.BORDER,
            border_color=theme.BORDER,
            border_width=1,
            text_color=theme.TEXT,
            font=theme.body_font(),
        ).grid(row=0, column=1, sticky="ew", padx=(theme.PAD_XS, 0))

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
