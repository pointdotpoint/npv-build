import logging
import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

import npv_build.gui_theme as theme

from .config import get_cache_dir, load_config, save_config
from .core.errors import NpvError
from .core.platform import open_folder
from .gui_backend import BuildWorker, InstallerWorker, check_dependencies, preview_save
from .gui_logic.wizard import WizardModel
from .gui_views.build_view import BuildView
from .gui_views.modmanager_view import ModManagerView
from .gui_views.save_browser_view import SaveBrowserView
from .gui_views.settings_view import SettingsView
from .gui_views.wizard_view import WizardView
from .save_parser import SaveParserError

logger = logging.getLogger(__name__)


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()

        # TkinterDnD initialization for drag-and-drop support
        try:
            self.TkdndVersion = TkinterDnD._to_path(self)
        except (AttributeError, RuntimeError, tk.TclError):
            self.TkdndVersion = None

        # Window configuration
        self.title("NPV Build - Cyberpunk 2077 NPC Creator")
        self.geometry("1100x750")
        self.minsize(1050, 700)
        self.configure(fg_color=theme.BG)

        # Set default ctk theme/mode
        theme.apply_theme()

        # Load persisted configuration
        self.config = load_config()

        # Build Queue & Worker. Separate queues: BuildView (Task 3) polls its
        # own dedicated build_queue, and the auto-install banner polls its own
        # install_queue -- kept apart so "done"/"error" tuples from one worker
        # can never be misread as the other's.
        self.build_queue = queue.Queue()
        self.install_queue = queue.Queue()
        self.worker = BuildWorker(self.build_queue)
        self.installer_worker = InstallerWorker(self.install_queue)

        # Build GUI Components (tab shell + nav)
        self.create_widgets()

        # Run initial dependency checks
        self.run_checks()

        # First-run wizard: shown on top when no valid game_dir is on record.
        if WizardModel.needs_wizard(self.config):
            self.show_wizard()

    # --- Navigation helpers -------------------------------------------------
    def _output_root(self) -> Path:
        """Best-effort root directory under which built mods live, for the Mod
        Manager tab. Falls back to the current Build tab's output entry, then
        to the default `~/npv_builds` used by update_default_output().
        """
        out_str = self.entry_output.get().strip()
        if out_str:
            # The Build tab's output entry points at a single mod's own output
            # dir (e.g. ~/npv_builds/my_v_mod); the Mod Manager scans one level
            # up for all built mods.
            return Path(out_str).parent
        return Path.home() / "npv_builds"

    def _game_dir_path(self) -> Path:
        game_dir_str = self.entry_game_dir.get().strip()
        return Path(game_dir_str) if game_dir_str else Path("")

    def show_save_browser_tab(self) -> None:
        self.tabview.set("Save Browser")

    def show_build_tab(self) -> None:
        self.tabview.set("Build")

    def show_mod_manager_tab(self) -> None:
        # game_dir/output_root may have changed (wizard, settings, manual edit)
        # since the view was built, so rebuild it fresh rather than just
        # calling refresh() against stale roots.
        self._modmanager_view.destroy()
        self._modmanager_view = ModManagerView(
            self._tab_mods, output_root=self._output_root(), game_dir=self._game_dir_path()
        )
        self._modmanager_view.pack(fill="both", expand=True)
        self.tabview.set("Mod Manager")

    def show_settings_tab(self) -> None:
        self.tabview.set("Settings")

    def _on_save_selected(self, path: Path) -> None:
        """Save Browser callback: feed the chosen save into the Build tab."""
        self.entry_save.delete(0, "end")
        self.entry_save.insert(0, str(path))
        self.update_save_preview()
        self.show_build_tab()

    def _on_settings_saved(self) -> None:
        self.config = load_config()
        self.entry_game_dir.delete(0, "end")
        self.entry_game_dir.insert(0, self.config.get("game_dir", "") or "")
        self.run_checks()
        self.show_build_tab()

    def _on_settings_cancelled(self) -> None:
        self.show_build_tab()

    def show_wizard(self):
        self._wizard_overlay = ctk.CTkFrame(self, fg_color=theme.BG)
        self._wizard_overlay.grid(row=0, column=0, sticky="nsew")
        self._wizard_overlay.grid_rowconfigure(0, weight=1)
        self._wizard_overlay.grid_columnconfigure(0, weight=1)

        self._wizard_view = WizardView(
            self._wizard_overlay,
            on_complete=self._on_wizard_complete,
            start_install=self.installer_worker.start,
            install_queue=self.install_queue,
            is_installer_alive=lambda: self.installer_worker.is_alive,
        )
        self._wizard_view.grid(row=0, column=0, sticky="nsew", padx=40, pady=40)

    def _on_wizard_complete(self):
        self.config = load_config()
        self._wizard_overlay.destroy()
        self.entry_game_dir.delete(0, "end")
        self.entry_game_dir.insert(0, self.config.get("game_dir", ""))
        self.run_checks()

    def create_widgets(self):
        """Build the app shell: a CTkTabview navigating the five M4 screens.

        The "Build" tab hosts the original single-pane build form (config +
        console) essentially unchanged, preserving full GUI-1 field parity.
        The other tabs mount the thin views built in Tasks 2-3, 5, 7.
        """
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(
            self,
            fg_color=theme.BG,
            segmented_button_selected_color=theme.ACCENT,
            segmented_button_selected_hover_color=theme.ACCENT_HOVER,
            segmented_button_unselected_color=theme.SURFACE,
            text_color=theme.BG,
        )
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=theme.PAD_M, pady=theme.PAD_M)

        tab_build = self.tabview.add("Build")
        tab_saves = self.tabview.add("Save Browser")
        self._tab_mods = self.tabview.add("Mod Manager")
        tab_settings = self.tabview.add("Settings")

        self._build_build_tab(tab_build)

        self._save_browser_view = SaveBrowserView(tab_saves, on_select=self._on_save_selected)
        self._save_browser_view.pack(fill="both", expand=True)

        self._modmanager_view = ModManagerView(
            self._tab_mods, output_root=self._output_root(), game_dir=self._game_dir_path()
        )
        self._modmanager_view.pack(fill="both", expand=True)

        self._settings_view = SettingsView(
            tab_settings,
            on_saved=self._on_settings_saved,
            on_cancelled=self._on_settings_cancelled,
        )
        self._settings_view.pack(fill="both", expand=True)

    def _build_build_tab(self, parent):
        # Configure Grid Layout (1 row, 2 columns)
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=4, minsize=450)  # Config pane
        parent.grid_columnconfigure(1, weight=5, minsize=500)  # Console pane

        # ==========================================
        # LEFT COLUMN: Configurations & Setup
        # ==========================================
        self.scroll_config = ctk.CTkScrollableFrame(
            parent,
            label_text="Configuration Panel",
            label_text_color=theme.ACCENT,
            label_font=theme.title_font(),
            fg_color=theme.BG,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=8,
            scrollbar_button_color=theme.ACCENT,
        )
        self.scroll_config.grid(row=0, column=0, sticky="nsew", padx=theme.PAD_L, pady=theme.PAD_L)
        self.scroll_config.grid_columnconfigure(0, weight=1)

        # --- Section 1: System Status & Game Dir ---
        self.frame_system = ctk.CTkFrame(
            self.scroll_config,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=8,
        )
        self.frame_system.grid(row=0, column=0, sticky="ew", padx=theme.PAD_M, pady=theme.PAD_M)
        self.frame_system.grid_columnconfigure(0, weight=1)

        lbl_sys_title = ctk.CTkLabel(
            self.frame_system,
            text="System Dependencies",
            font=theme.header_font(),
            text_color=theme.ACCENT,
        )
        lbl_sys_title.grid(
            row=0, column=0, columnspan=2, sticky="w", padx=theme.PAD_L, pady=theme.PAD_M
        )

        # Game Directory Input
        lbl_game_dir = ctk.CTkLabel(
            self.frame_system,
            text="Cyberpunk 2077 Game Directory:",
            font=theme.label_font(),
            text_color=theme.TEXT,
        )
        lbl_game_dir.grid(
            row=1, column=0, columnspan=2, sticky="w", padx=theme.PAD_L, pady=theme.PAD_XS
        )

        _gd_placeholder = (
            "e.g. C:\\Steam\\steamapps\\common\\Cyberpunk 2077"
            if sys.platform == "win32"
            else "e.g. ~/.steam/steam/steamapps/common/Cyberpunk 2077"
        )
        self.entry_game_dir = ctk.CTkEntry(
            self.frame_system,
            placeholder_text=_gd_placeholder,
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_game_dir.grid(
            row=2, column=0, sticky="ew", padx=(theme.PAD_L, theme.PAD_S), pady=theme.PAD_S
        )
        if self.config.get("game_dir"):
            self.entry_game_dir.insert(0, self.config["game_dir"])
        self.entry_game_dir.bind("<KeyRelease>", lambda e: self.run_checks())

        btn_game_browse = ctk.CTkButton(
            self.frame_system,
            text="Browse",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.browse_game_dir,
        )
        btn_game_browse.grid(
            row=2, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S
        )

        # Status Lamps
        # Note: no .NET/npv-inject lamp here. Per ADR 0001 (Branch A'),
        # npv-inject is being retired (WolvenKit round-trip replaces it), so
        # the Build button must not gate on it and it is not user-relevant
        # to surface. See run_checks() below.
        self.frame_lamps = ctk.CTkFrame(self.frame_system, fg_color="transparent")
        self.frame_lamps.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=theme.PAD_L,
            pady=(theme.PAD_S, theme.PAD_S),
        )
        self.frame_lamps.grid_columnconfigure((0, 1), weight=1)

        self.lamp_wkit = ctk.CTkLabel(
            self.frame_lamps, text="● WolvenKit CLI", font=theme.label_font()
        )
        self.lamp_wkit.grid(row=0, column=0, padx=theme.PAD_XS, pady=theme.PAD_XS, sticky="w")

        self.lamp_blender = ctk.CTkLabel(
            self.frame_lamps, text="● Blender", font=theme.label_font()
        )
        self.lamp_blender.grid(row=0, column=1, padx=theme.PAD_XS, pady=theme.PAD_XS, sticky="w")

        # Auto-install Button
        self.btn_auto_install = ctk.CTkButton(
            self.frame_system,
            text="Auto-Install Missing Dependencies",
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            height=30,
            font=theme.body_font(),
            command=self.start_auto_install,
        )
        self.btn_auto_install.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=theme.PAD_L,
            pady=(theme.PAD_S, theme.PAD_L),
        )

        # --- Section 2: Character Creation Save Input ---
        self.frame_char = ctk.CTkFrame(
            self.scroll_config,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=8,
        )
        self.frame_char.grid(row=1, column=0, sticky="ew", padx=theme.PAD_M, pady=theme.PAD_M)
        self.frame_char.grid_columnconfigure(0, weight=1)

        lbl_char_title = ctk.CTkLabel(
            self.frame_char,
            text="Character & Input Data",
            font=theme.header_font(),
            text_color=theme.ACCENT,
        )
        lbl_char_title.grid(
            row=0, column=0, columnspan=2, sticky="w", padx=theme.PAD_L, pady=theme.PAD_M
        )

        # Save File
        lbl_save_file = ctk.CTkLabel(
            self.frame_char,
            text="Save File (sav.dat) - Drag & Drop here:",
            font=theme.label_font(),
            text_color=theme.TEXT,
        )
        lbl_save_file.grid(
            row=1, column=0, columnspan=2, sticky="w", padx=theme.PAD_L, pady=theme.PAD_XS
        )

        self.entry_save = ctk.CTkEntry(
            self.frame_char,
            placeholder_text="Drop save file or click Browse...",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_save.grid(
            row=2, column=0, sticky="ew", padx=(theme.PAD_L, theme.PAD_S), pady=theme.PAD_S
        )
        self.entry_save.bind("<KeyRelease>", lambda e: self.update_save_preview())

        # Enable Drag and Drop on Entry
        if self.TkdndVersion:
            self.entry_save.register_drop_target(DND_FILES)
            self.entry_save.bind("<<Drop>>", self.handle_save_drop)

        btn_save_browse = ctk.CTkButton(
            self.frame_char,
            text="Browse",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.browse_save_file,
        )
        btn_save_browse.grid(
            row=2, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S
        )

        # Preview Details Frame
        self.frame_preview = ctk.CTkFrame(
            self.frame_char,
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=6,
        )
        self.frame_preview.grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=theme.PAD_L, pady=theme.PAD_M
        )
        self.frame_preview.grid_columnconfigure((0, 1), weight=1)

        self.lbl_prev_rig = ctk.CTkLabel(
            self.frame_preview,
            text="Rig: None",
            font=theme.hint_font(),
            text_color=theme.TEXT_MUTED,
        )
        self.lbl_prev_rig.grid(row=0, column=0, padx=theme.PAD_S, pady=theme.PAD_XS, sticky="w")

        self.lbl_prev_skin = ctk.CTkLabel(
            self.frame_preview,
            text="Skin: None",
            font=theme.hint_font(),
            text_color=theme.TEXT_MUTED,
        )
        self.lbl_prev_skin.grid(row=0, column=1, padx=theme.PAD_S, pady=theme.PAD_XS, sticky="w")

        self.lbl_prev_hair = ctk.CTkLabel(
            self.frame_preview,
            text="Hair: None",
            font=theme.hint_font(),
            text_color=theme.TEXT_MUTED,
        )
        self.lbl_prev_hair.grid(row=1, column=0, padx=theme.PAD_S, pady=theme.PAD_XS, sticky="w")

        self.lbl_prev_selections = ctk.CTkLabel(
            self.frame_preview,
            text="Selections: None",
            font=theme.hint_font(),
            text_color=theme.TEXT_MUTED,
        )
        self.lbl_prev_selections.grid(
            row=1, column=1, padx=theme.PAD_S, pady=theme.PAD_XS, sticky="w"
        )

        # NPV Name
        lbl_npv_name = ctk.CTkLabel(
            self.frame_char,
            text="NPV Name (AMM spawn label):",
            font=theme.label_font(),
            text_color=theme.TEXT,
        )
        lbl_npv_name.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            padx=theme.PAD_L,
            pady=(theme.PAD_M, theme.PAD_XS),
        )

        self.entry_npv_name = ctk.CTkEntry(
            self.frame_char,
            placeholder_text="e.g. My V NPC",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_npv_name.grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=theme.PAD_L, pady=theme.PAD_S
        )
        self.entry_npv_name.bind("<KeyRelease>", lambda e: self.update_default_output())

        # Output Folder
        lbl_output = ctk.CTkLabel(
            self.frame_char,
            text="Output Directory:",
            font=theme.label_font(),
            text_color=theme.TEXT,
        )
        lbl_output.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="w",
            padx=theme.PAD_L,
            pady=(theme.PAD_M, theme.PAD_XS),
        )

        self.entry_output = ctk.CTkEntry(
            self.frame_char,
            placeholder_text="Directory where the mod will be built",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_output.grid(
            row=7, column=0, sticky="ew", padx=(theme.PAD_L, theme.PAD_S), pady=theme.PAD_S
        )

        btn_output_browse = ctk.CTkButton(
            self.frame_char,
            text="Browse",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.browse_output_dir,
        )
        btn_output_browse.grid(
            row=7, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S
        )

        # --- Section 3: Advanced Overrides (Collapsible Style) ---
        self.adv_expanded = False
        self.btn_toggle_adv = ctk.CTkButton(
            self.scroll_config,
            text="▶ Show Advanced Overrides",
            fg_color="transparent",
            hover_color=theme.SURFACE_ALT,
            text_color=theme.ACCENT,
            font=theme.label_font(),
            command=self.toggle_advanced,
        )
        self.btn_toggle_adv.grid(row=2, column=0, sticky="w", padx=theme.PAD_L, pady=theme.PAD_M)

        self.frame_adv = ctk.CTkFrame(
            self.scroll_config,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=8,
        )
        # We don't grid it initially, shown when adv_expanded = True

        self.setup_advanced_fields()

        # ==========================================
        # RIGHT COLUMN: Build Status & Console Log
        # ==========================================
        self.frame_console = ctk.CTkFrame(
            parent,
            fg_color=theme.SURFACE,
            border_color=theme.BORDER,
            border_width=1,
            corner_radius=8,
        )
        self.frame_console.grid(row=0, column=1, sticky="nsew", padx=theme.PAD_L, pady=theme.PAD_L)
        self.frame_console.grid_rowconfigure(2, weight=1)
        self.frame_console.grid_columnconfigure(0, weight=1)

        # Console Header
        lbl_console_title = ctk.CTkLabel(
            self.frame_console,
            text="Build Progress & Output",
            font=theme.title_font(),
            text_color=theme.ACCENT,
        )
        lbl_console_title.grid(row=0, column=0, sticky="w", padx=theme.PAD_L, pady=theme.PAD_L)

        # BUILD trigger button (BuildView itself only owns Cancel/Retry, not
        # the initial trigger -- that stays here since it needs the Build
        # tab's input widgets to gather + validate kwargs first).
        self.btn_build = ctk.CTkButton(
            self.frame_console,
            text="BUILD NPV MOD",
            font=theme.title_font(),
            fg_color=theme.ACCENT,
            text_color=theme.BG,
            hover_color=theme.ACCENT_HOVER,
            border_width=0,
            corner_radius=8,
            height=45,
            command=self.start_build,
        )
        self.btn_build.grid(row=1, column=0, sticky="ew", padx=theme.PAD_L, pady=(0, theme.PAD_M))

        # Stage progress, live log, Cancel + Retry-from-failed-stage (GUI-4,
        # CORE-3/4) -- delegates entirely to the Task 3 BuildView widget.
        self._build_view = BuildView(
            self.frame_console,
            start_build=self.worker.start,
            cancel_build=self.worker.cancel,
            build_queue=self.build_queue,
            is_worker_alive=lambda: self.worker.is_alive,
            on_done=self._on_build_done,
        )
        self._build_view.grid(
            row=2, column=0, sticky="nsew", padx=theme.PAD_L, pady=(0, theme.PAD_L)
        )

        # Empty-state placeholder shown over the output area until a build
        # starts (Task 2 card-framing spec). BuildView owns the actual log
        # box; this sits on top of frame_console so it's visible before any
        # build activity exists.
        self.lbl_output_placeholder = ctk.CTkLabel(
            self.frame_console,
            text="Select a save and click Build NPV Mod",
            font=theme.hint_font(),
            text_color=theme.TEXT_MUTED,
            fg_color="transparent",
        )
        self.lbl_output_placeholder.grid(row=2, column=0, sticky="n", pady=(theme.PAD_XL, 0))

        # Auto-install banner: separate from BuildView, drives InstallerWorker
        # via its own queue (see start_auto_install/install_finished below).
        self.frame_actions = ctk.CTkFrame(self.frame_console, fg_color="transparent")
        self.frame_actions.grid(
            row=3, column=0, sticky="ew", padx=theme.PAD_L, pady=(0, theme.PAD_L)
        )
        self.frame_actions.grid_columnconfigure(0, weight=1)

        # Progress Indicator (auto-install only)
        self.progress_bar = ctk.CTkProgressBar(
            self.frame_actions, fg_color=theme.SURFACE_ALT, progress_color=theme.ACCENT
        )
        # Hidden initially

        # Success/Failure Alert Banner (auto-install only; build success/failure
        # is surfaced by BuildView's own error label + the Open Output Folder
        # button appended below it via _on_build_done).
        self.lbl_banner = ctk.CTkLabel(
            self.frame_actions,
            text="",
            font=theme.label_font(),
            height=30,
            corner_radius=4,
        )
        # Hidden initially

    def setup_advanced_fields(self):
        self.frame_adv.grid_columnconfigure(0, weight=1)

        # CET CC JSON
        lbl_cc_json = ctk.CTkLabel(
            self.frame_adv,
            text="CET Appearance JSON (--cc-json):",
            font=theme.system_font(11, "bold"),
            text_color=theme.TEXT,
        )
        lbl_cc_json.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=theme.PAD_L,
            pady=(theme.PAD_M, theme.PAD_XS),
        )
        self.entry_cc_json = ctk.CTkEntry(
            self.frame_adv,
            placeholder_text="Path to cc_dump.json",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_cc_json.grid(
            row=1, column=0, sticky="ew", padx=(theme.PAD_L, theme.PAD_S), pady=theme.PAD_S
        )
        btn_cc_browse = ctk.CTkButton(
            self.frame_adv,
            text="Browse",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.browse_cc_json,
        )
        btn_cc_browse.grid(
            row=1, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S
        )

        # Hair Override
        lbl_hair_ovr = ctk.CTkLabel(
            self.frame_adv,
            text="Hair Override:",
            font=theme.system_font(11, "bold"),
            text_color=theme.TEXT,
        )
        lbl_hair_ovr.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            padx=theme.PAD_L,
            pady=(theme.PAD_S, theme.PAD_XS),
        )

        frame_hair_input = ctk.CTkFrame(self.frame_adv, fg_color="transparent")
        frame_hair_input.grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=theme.PAD_L, pady=theme.PAD_S
        )
        frame_hair_input.grid_columnconfigure(0, weight=1)

        self.entry_hair_ovr = ctk.CTkEntry(
            frame_hair_input,
            placeholder_text="e.g. zara, none, 12, or select/drop a mod file...",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_hair_ovr.grid(row=0, column=0, sticky="ew", padx=(0, theme.PAD_S))

        if self.TkdndVersion:
            self.entry_hair_ovr.register_drop_target(DND_FILES)
            self.entry_hair_ovr.bind("<<Drop>>", self.handle_hair_drop)

        btn_hair_browse = ctk.CTkButton(
            frame_hair_input,
            text="Browse",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.browse_hair_mod,
        )
        btn_hair_browse.grid(row=0, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_S))

        btn_hair_clear = ctk.CTkButton(
            frame_hair_input,
            text="Clear",
            width=60,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.TEXT_MUTED,
            border_color=theme.TEXT_MUTED,
            border_width=1,
            font=theme.body_font(),
            command=self.clear_hair_mod,
        )
        btn_hair_clear.grid(row=0, column=2, sticky="w", padx=(theme.PAD_S, 0))

        # Skin Override
        lbl_skin_ovr = ctk.CTkLabel(
            self.frame_adv,
            text="Skin Tone Override:",
            font=theme.system_font(11, "bold"),
            text_color=theme.TEXT,
        )
        lbl_skin_ovr.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            padx=theme.PAD_L,
            pady=(theme.PAD_S, theme.PAD_XS),
        )
        self.entry_skin_ovr = ctk.CTkEntry(
            self.frame_adv,
            placeholder_text="e.g. 01_ca_pale, 02_ca_limestone",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_skin_ovr.grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=theme.PAD_L, pady=theme.PAD_S
        )

        # Garment Overrides (Multiple items)
        lbl_garments = ctk.CTkLabel(
            self.frame_adv,
            text="Garment Override Depot Paths (Double click to remove):",
            font=theme.system_font(11, "bold"),
            text_color=theme.TEXT,
        )
        lbl_garments.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="w",
            padx=theme.PAD_L,
            pady=(theme.PAD_S, theme.PAD_XS),
        )

        self.garment_list = tk.Listbox(
            self.frame_adv,
            bg=theme.SURFACE_ALT,
            fg=theme.TEXT,
            selectbackground=theme.ACCENT,
            selectforeground=theme.BG,
            font=("Courier New", 10),
            borderwidth=1,
            highlightcolor=theme.ACCENT,
        )
        self.garment_list.grid(
            row=7, column=0, sticky="ew", padx=(theme.PAD_L, theme.PAD_S), pady=theme.PAD_S
        )
        self.garment_list.bind("<Double-Button-1>", self.remove_selected_garment)

        btn_add_garment = ctk.CTkButton(
            self.frame_adv,
            text="+ Add",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.add_garment_override,
        )
        btn_add_garment.grid(
            row=7, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S
        )

        # Custom Head GLB / Mesh / Heb Mesh
        lbl_custom_head = ctk.CTkLabel(
            self.frame_adv,
            text="BYO Head Options (Custom Mesh/GLB):",
            font=theme.system_font(11, "bold"),
            text_color=theme.TEXT,
        )
        lbl_custom_head.grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="w",
            padx=theme.PAD_L,
            pady=(theme.PAD_M, theme.PAD_XS),
        )

        self.entry_head_glb = ctk.CTkEntry(
            self.frame_adv,
            placeholder_text="Path to user_head.glb",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_head_glb.grid(
            row=9, column=0, sticky="ew", padx=(theme.PAD_L, theme.PAD_S), pady=theme.PAD_S
        )
        btn_glb_browse = ctk.CTkButton(
            self.frame_adv,
            text="Browse GLB",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.browse_head_glb,
        )
        btn_glb_browse.grid(
            row=9, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S
        )

        self.entry_head_mesh = ctk.CTkEntry(
            self.frame_adv,
            placeholder_text="Path to user_head.mesh",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_head_mesh.grid(
            row=10, column=0, sticky="ew", padx=(theme.PAD_L, theme.PAD_S), pady=theme.PAD_S
        )
        btn_mesh_browse = ctk.CTkButton(
            self.frame_adv,
            text="Browse Mesh",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.browse_head_mesh,
        )
        btn_mesh_browse.grid(
            row=10, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S
        )

        self.entry_heb_mesh = ctk.CTkEntry(
            self.frame_adv,
            placeholder_text="Path to user_heb.mesh (details)",
            fg_color=theme.SURFACE_ALT,
            border_color=theme.BORDER,
            text_color=theme.TEXT,
            font=theme.body_font(),
        )
        self.entry_heb_mesh.grid(
            row=11, column=0, sticky="ew", padx=(theme.PAD_L, theme.PAD_S), pady=theme.PAD_S
        )
        btn_heb_browse = ctk.CTkButton(
            self.frame_adv,
            text="Browse HEB",
            width=80,
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            border_color=theme.ACCENT,
            border_width=1,
            font=theme.body_font(),
            command=self.browse_heb_mesh,
        )
        btn_heb_browse.grid(
            row=11, column=1, sticky="w", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S
        )

        # Clear Cache / Restore Head Toggles
        self.switch_clear_cache = ctk.CTkSwitch(
            self.frame_adv,
            text="Clear cache before build",
            font=theme.body_font(),
            text_color=theme.TEXT,
            progress_color=theme.ACCENT,
        )
        self.switch_clear_cache.grid(
            row=12, column=0, columnspan=2, sticky="w", padx=theme.PAD_L, pady=theme.PAD_M
        )

        self.switch_restore_head = ctk.CTkSwitch(
            self.frame_adv,
            text="Restore head materials",
            font=theme.body_font(),
            text_color=theme.TEXT,
            progress_color=theme.ACCENT,
        )
        self.switch_restore_head.select()
        self.switch_restore_head.grid(
            row=13, column=0, columnspan=2, sticky="w", padx=theme.PAD_L, pady=(0, theme.PAD_L)
        )

    # --- Toggle Advanced Frame ---
    def toggle_advanced(self):
        if self.adv_expanded:
            self.frame_adv.grid_forget()
            self.btn_toggle_adv.configure(text="▶ Show Advanced Overrides")
            self.adv_expanded = False
        else:
            self.frame_adv.grid(row=3, column=0, sticky="ew", padx=theme.PAD_M, pady=theme.PAD_M)
            self.btn_toggle_adv.configure(text="▼ Hide Advanced Overrides")
            self.adv_expanded = True

    # --- Logs ---
    def append_log(self, text: str):
        # BuildView (Task 3) owns the build log box; route non-worker log
        # lines (validation errors, hair-mod install progress, etc.) into it
        # so they remain visible in the same place build output shows up.
        self._build_view.log(text)

    # --- Actions / Commands ---
    def run_checks(self):
        game_path_str = self.entry_game_dir.get().strip()
        game_path = Path(game_path_str) if game_path_str else None

        status = check_dependencies(game_path)

        def update_lamp(lamp, found):
            if found:
                lamp.configure(text_color=theme.SUCCESS)
            else:
                lamp.configure(text_color=theme.ERROR)

        update_lamp(self.lamp_wkit, status["wolvenkit"])
        update_lamp(self.lamp_blender, status["blender"])
        # No .NET/npv-inject lamp: ADR 0001 (Branch A') retires npv-inject, so
        # its presence/absence is no longer user-relevant or gating.

        # Game Dir validation feedback
        if game_path_str:
            if status["game_dir_valid"]:
                self.entry_game_dir.configure(border_color=theme.SUCCESS)
                # Persist valid path
                self.config["game_dir"] = str(game_path.resolve())
                save_config(self.config)
            else:
                self.entry_game_dir.configure(border_color=theme.ERROR)
        else:
            self.entry_game_dir.configure(border_color=theme.TEXT_MUTED)

        # Disable/Enable Build button based on checks. Deliberately does not
        # gate on status["npv_inject"] -- ADR 0001 (Branch A') retires
        # npv-inject, so its absence must not block the Build button.
        ready = status["wolvenkit"] and status["blender"] and status["game_dir_valid"]
        if ready:
            self.btn_build.configure(state="normal", fg_color=theme.ACCENT, text_color=theme.BG)
        else:
            self.btn_build.configure(
                state="disabled", fg_color=theme.SURFACE_ALT, text_color=theme.TEXT_MUTED
            )

    # --- Browse Helpers ---
    def browse_game_dir(self):
        path = filedialog.askdirectory(title="Select Cyberpunk 2077 Installation Root")
        if path:
            self.entry_game_dir.delete(0, "end")
            self.entry_game_dir.insert(0, path)
            self.run_checks()

    def browse_save_file(self):
        # Look for standard save folders if not specified
        from .core.platform import candidate_save_dirs

        candidates = candidate_save_dirs()
        init_dir = candidates[0] if candidates else Path.home()

        path = filedialog.askopenfilename(
            initialdir=str(init_dir),
            title="Select Cyberpunk 2077 Save File",
            filetypes=[("Save Files", "*.dat"), ("All Files", "*.*")],
        )
        if path:
            self.entry_save.delete(0, "end")
            self.entry_save.insert(0, path)
            self.update_save_preview()

    def handle_save_drop(self, event):
        path = event.data
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]
        self.entry_save.delete(0, "end")
        self.entry_save.insert(0, path)
        self.update_save_preview()

    def update_save_preview(self):
        path_str = self.entry_save.get().strip()
        if not path_str:
            self.clear_preview()
            return

        path = Path(path_str)
        if not path.exists() or not path.is_file():
            self.clear_preview()
            return

        try:
            prev = preview_save(path)
            self.lbl_prev_rig.configure(text=f"Rig: {prev['body_rig']}", text_color=theme.TEXT)
            self.lbl_prev_skin.configure(text=f"Skin: {prev['skin_tone']}", text_color=theme.TEXT)
            self.lbl_prev_hair.configure(
                text=f"Hair: {prev['hair_style']} (col: {prev['hair_color']})",
                text_color=theme.TEXT,
            )
            self.lbl_prev_selections.configure(
                text=f"Selections: {prev['selections_count']}", text_color=theme.TEXT
            )
            self.update_default_output()
        except SaveParserError as e:
            self.lbl_prev_rig.configure(text="Rig: Error", text_color=theme.ERROR)
            self.lbl_prev_skin.configure(text="Skin: Error", text_color=theme.ERROR)
            self.lbl_prev_hair.configure(text=f"Err: {str(e)[:25]}", text_color=theme.ERROR)
            self.lbl_prev_selections.configure(text="Selections: Error", text_color=theme.ERROR)
        except NpvError as e:
            self.lbl_prev_rig.configure(text="Rig: Error", text_color=theme.ERROR)
            self.lbl_prev_skin.configure(text="Skin: Error", text_color=theme.ERROR)
            self.lbl_prev_hair.configure(text=f"Err: {e.user_message[:25]}", text_color=theme.ERROR)
            self.lbl_prev_selections.configure(text="Selections: Error", text_color=theme.ERROR)

    def clear_preview(self):
        self.lbl_prev_rig.configure(text="Rig: None", text_color=theme.TEXT_MUTED)
        self.lbl_prev_skin.configure(text="Skin: None", text_color=theme.TEXT_MUTED)
        self.lbl_prev_hair.configure(text="Hair: None", text_color=theme.TEXT_MUTED)
        self.lbl_prev_selections.configure(text="Selections: None", text_color=theme.TEXT_MUTED)

    def update_default_output(self):
        name = self.entry_npv_name.get().strip()
        if not name:
            name = "my_v_mod"

        # Safe name for path
        safe_name = "".join(
            [c if c.isalnum() or c in ("-", "_") else "_" for c in name.lower()]
        ).strip("_")

        # Put in home directory / npv_builds
        default_out = Path.home() / "npv_builds" / safe_name
        self.entry_output.delete(0, "end")
        self.entry_output.insert(0, str(default_out))

    def browse_output_dir(self):
        path = filedialog.askdirectory(title="Select Output Directory")
        if path:
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, path)

    def browse_cc_json(self):
        path = filedialog.askopenfilename(
            title="Select CET CC JSON file",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if path:
            self.entry_cc_json.delete(0, "end")
            self.entry_cc_json.insert(0, path)

    def browse_hair_mod(self):
        game_dir_str = self.entry_game_dir.get().strip()
        if not game_dir_str:
            self.show_error(
                "Game Dir Required",
                "Please specify the Game Directory before selecting a hair mod.",
            )
            return

        file_path = filedialog.askopenfilename(
            title="Select Hair Mod File",
            filetypes=[
                ("Cyberpunk Hair Mod Files", "*.archive *.zip *.7z *.rar"),
                ("Raw Archive", "*.archive"),
                ("Compressed Archive", "*.zip *.7z *.rar"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            from .hair_mod_helper import install_hair_mod

            derived_name, installed_files = install_hair_mod(Path(file_path), Path(game_dir_str))

            self.entry_hair_ovr.delete(0, "end")
            self.entry_hair_ovr.insert(0, derived_name)

            self.append_log(f"Successfully processed hair mod: {Path(file_path).name}\n")
            self.append_log(f"Derived hair override token: '{derived_name}'\n")
            for f in installed_files:
                self.append_log(f"Installed to game: {f.relative_to(Path(game_dir_str))}\n")
            self.append_log("\n")

        except Exception as e:  # noqa: BLE001 - GUI event loop must survive
            logger.exception("Hair mod installation failed")
            self.show_error("Hair Mod Error", f"Failed to install hair mod:\n{str(e)}")

    def clear_hair_mod(self):
        self.entry_hair_ovr.delete(0, "end")

    def handle_hair_drop(self, event):
        path_str = event.data
        if path_str.startswith("{") and path_str.endswith("}"):
            path_str = path_str[1:-1]

        game_dir_str = self.entry_game_dir.get().strip()
        if not game_dir_str:
            self.show_error(
                "Game Dir Required", "Please specify the Game Directory before dropping a hair mod."
            )
            return

        try:
            from .hair_mod_helper import install_hair_mod

            derived_name, installed_files = install_hair_mod(Path(path_str), Path(game_dir_str))

            self.entry_hair_ovr.delete(0, "end")
            self.entry_hair_ovr.insert(0, derived_name)

            self.append_log(f"Successfully processed hair mod: {Path(path_str).name}\n")
            self.append_log(f"Derived hair override token: '{derived_name}'\n")
            for f in installed_files:
                self.append_log(f"Installed to game: {f.relative_to(Path(game_dir_str))}\n")
            self.append_log("\n")

        except Exception as e:  # noqa: BLE001 - GUI event loop must survive
            logger.exception("Hair mod installation failed")
            self.show_error("Hair Mod Error", f"Failed to install hair mod:\n{str(e)}")

    def browse_head_glb(self):
        path = filedialog.askopenfilename(
            title="Select Custom Head GLB file",
            filetypes=[("GLB Files", "*.glb"), ("All Files", "*.*")],
        )
        if path:
            self.entry_head_glb.delete(0, "end")
            self.entry_head_glb.insert(0, path)

    def browse_head_mesh(self):
        path = filedialog.askopenfilename(
            title="Select Custom Head Mesh file",
            filetypes=[("Mesh Files", "*.mesh"), ("All Files", "*.*")],
        )
        if path:
            self.entry_head_mesh.delete(0, "end")
            self.entry_head_mesh.insert(0, path)

    def browse_heb_mesh(self):
        path = filedialog.askopenfilename(
            title="Select Custom HEB Mesh file",
            filetypes=[("Mesh Files", "*.mesh"), ("All Files", "*.*")],
        )
        if path:
            self.entry_heb_mesh.delete(0, "end")
            self.entry_heb_mesh.insert(0, path)

    def add_garment_override(self):
        path = filedialog.askopenfilename(
            title="Select Garment entity (.ent) file",
            filetypes=[("Entity Files", "*.ent"), ("All Files", "*.*")],
        )
        if path:
            self.garment_list.insert("end", path)
        else:
            # Let user write it in if it's a raw depot path
            text = ctk.CTkInputDialog(text="Enter Garment Depot Path:", title="Add Garment")
            val = text.get_input()
            if val and val.strip():
                self.garment_list.insert("end", val.strip())

    def remove_selected_garment(self, event):
        selection = self.garment_list.curselection()
        if selection:
            self.garment_list.delete(selection[0])

    # --- Build Orchestration ---
    def start_build(self):
        # 1. Gather & Validate inputs
        save_path_str = self.entry_save.get().strip()
        cc_json_str = self.entry_cc_json.get().strip()
        npv_name = self.entry_npv_name.get().strip()
        output_dir_str = self.entry_output.get().strip()
        game_dir_str = self.entry_game_dir.get().strip()

        if not npv_name:
            self.show_error("Validation Error", "Please specify an NPV Name.")
            return
        if not output_dir_str:
            self.show_error("Validation Error", "Please specify an Output Directory.")
            return
        if not save_path_str and not cc_json_str:
            self.show_error(
                "Validation Error", "Either Save File or CET Appearance JSON must be provided."
            )
            return

        save_path = Path(save_path_str) if save_path_str else None
        cc_json = Path(cc_json_str) if cc_json_str else None
        output_dir = Path(output_dir_str)
        game_dir = Path(game_dir_str)

        self.lbl_banner.grid_forget()
        if hasattr(self, "btn_open_out"):
            self.btn_open_out.grid_forget()

        # Set up build kwargs (1:1 with BuildRequest fields; resume is not
        # user-facing here -- BuildView's own Retry button passes resume=True).
        kwargs = {
            "save_path": save_path,
            "npv_name": npv_name,
            "output_dir": output_dir,
            "game_dir": game_dir,
            "template_cache": get_cache_dir() / "templates",
            "clear_cache": self.switch_clear_cache.get() == 1,
            "cc_json_path": cc_json,
            "hair_override": self.entry_hair_ovr.get().strip() or None,
            "skin_override": self.entry_skin_ovr.get().strip() or None,
            "garments": list(self.garment_list.get(0, "end")),
            "user_head_glb": Path(self.entry_head_glb.get().strip())
            if self.entry_head_glb.get().strip()
            else None,
            "user_head_mesh": Path(self.entry_head_mesh.get().strip())
            if self.entry_head_mesh.get().strip()
            else None,
            "user_heb_mesh": Path(self.entry_heb_mesh.get().strip())
            if self.entry_heb_mesh.get().strip()
            else None,
            "restore_head_materials": self.switch_restore_head.get() == 1,
        }

        self.lbl_output_placeholder.grid_forget()
        self._build_view.log(f"Starting NPV Build mod generation for V '{npv_name}'...\n")
        self._build_view.start(**kwargs)

    def _on_build_done(self, output_dir: str) -> None:
        """BuildView's on_done hook: append the Open Output Folder button."""
        self.last_output_dir = Path(output_dir)
        self.btn_open_out = ctk.CTkButton(
            self.frame_console,
            text="Open Output Folder",
            fg_color=theme.SURFACE_ALT,
            hover_color=theme.BORDER,
            text_color=theme.ACCENT,
            font=theme.body_font(),
            command=self.open_output_folder,
        )
        self.btn_open_out.grid(
            row=4, column=0, sticky="ew", padx=theme.PAD_L, pady=(0, theme.PAD_M)
        )

    def start_auto_install(self):
        # Ask for confirmation before downloading
        confirm = tk.messagebox.askyesno(
            "Download Dependencies?",
            "This will download and locally install missing tools into your application cache:\n"
            "- WolvenKit.CLI (approx. 40MB)\n"
            "- Blender 4.2.0 LTS (approx. 150MB)\n\n"
            "This requires about 190MB of downloads and up to 1GB of disk space. "
            "Proceed?",
        )
        if not confirm:
            return

        self.lbl_banner.grid_forget()
        self._build_view.log("Starting dependency auto-installer...\n")

        # Update UI states
        self.btn_auto_install.configure(state="disabled", text="INSTALLING...")

        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # Spawn background thread
        self.installer_worker.start()

        # Schedule this banner's own queue poller (separate from BuildView's
        # internal polling of self.build_queue).
        self.after(50, self.poll_install_queue)

    def poll_install_queue(self):
        try:
            while True:
                msg_type, msg_val = self.install_queue.get_nowait()
                if msg_type == "log":
                    self._build_view.log(msg_val)
                elif msg_type == "progress":
                    self.progress_bar.set(msg_val)
                elif msg_type == "install_done":
                    self.install_finished(success=True)
                elif msg_type == "install_error":
                    self.install_finished(success=False, error_msg=msg_val)
                self.install_queue.task_done()
        except queue.Empty:
            pass

        if self.installer_worker.is_alive:
            self.after(50, self.poll_install_queue)

    def install_finished(self, success: bool, error_msg: str = ""):
        self.progress_bar.grid_forget()
        self.btn_auto_install.configure(state="normal", text="Auto-Install Missing Dependencies")
        self.progress_bar.configure(mode="indeterminate")

        if success:
            self._build_view.log(
                "\n[Success] All dependencies installed successfully! Ready to build.\n"
            )
            self.lbl_banner.configure(
                text="✓ Dependencies Installed Successfully!",
                fg_color=theme.SUCCESS,
                text_color=theme.BG,
            )
        else:
            self._build_view.log(f"\n[Error] Dependency installation failed: {error_msg}\n")
            self.lbl_banner.configure(
                text="✗ Installation Failed. Check logs above.",
                fg_color=theme.ERROR,
                text_color=theme.TEXT,
            )

        self.lbl_banner.grid(row=1, column=0, sticky="ew", pady=5)

        # Re-run checks to update lamps
        self.run_checks()

    def open_output_folder(self):
        # The "Open Output Folder" button is only ever created in
        # _on_build_done() (BuildView's on_done hook), right after
        # self.last_output_dir is set, so it is always present here.
        target = self.last_output_dir
        if not target.exists():
            self.show_error(
                "Folder Not Found",
                "The output folder does not exist yet. Build the mod first.",
            )
            return
        try:
            open_folder(target)
        except Exception as e:  # noqa: BLE001 - GUI event loop must survive
            logger.exception("Failed to open output folder")
            self.show_error("Open Folder Error", f"Could not open folder:\n{e}")

    def show_error(self, title: str, message: str):
        self.append_log(f"\n[{title}] {message}\n")
        # Standard ctk popups or standard tk dialogs
        tk.messagebox.showerror(title, message)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
