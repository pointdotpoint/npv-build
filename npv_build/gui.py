import os
import sys
import queue
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

from .config import load_config, save_config, get_cache_dir
from .gui_backend import check_dependencies, BuildWorker, InstallerWorker, preview_save


# Styling Constants
BG_DARK = "#0b0c10"
BG_CARD = "#1f2833"
ACCENT_CYAN = "#66fcf1"
ACCENT_PINK = "#ff007f"
STATUS_GREEN = "#2ecc71"
STATUS_RED = "#e74c3c"
TEXT_WHITE = "#ffffff"
TEXT_MUTED = "#c5c6c7"


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()

        # TkinterDnD initialization for drag-and-drop support
        try:
            self.TkdndVersion = TkinterDnD._to_path(self)
        except Exception:
            self.TkdndVersion = None

        # Window configuration
        self.title("NPV Build - Cyberpunk 2077 NPC Creator")
        self.geometry("1100x750")
        self.minsize(1050, 700)
        self.configure(fg_color=BG_DARK)

        # Set default ctk theme/mode
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Load persisted configuration
        self.config = load_config()

        # Build Queue & Worker
        self.queue = queue.Queue()
        self.worker = BuildWorker(self.queue)
        self.installer_worker = InstallerWorker(self.queue)

        # Build GUI Components
        self.create_widgets()

        # Run initial dependency checks
        self.run_checks()

    def create_widgets(self):
        # Configure Grid Layout (1 row, 2 columns)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=4, minsize=450)  # Config pane
        self.grid_columnconfigure(1, weight=5, minsize=500)  # Console pane

        # ==========================================
        # LEFT COLUMN: Configurations & Setup
        # ==========================================
        self.scroll_config = ctk.CTkScrollableFrame(
            self,
            label_text="Configuration Panel",
            label_text_color=ACCENT_CYAN,
            label_font=("Arial", 16, "bold"),
            fg_color=BG_DARK,
            scrollbar_button_color=ACCENT_CYAN,
        )
        self.scroll_config.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        self.scroll_config.grid_columnconfigure(0, weight=1)

        # --- Section 1: System Status & Game Dir ---
        self.frame_system = ctk.CTkFrame(self.scroll_config, fg_color=BG_CARD)
        self.frame_system.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.frame_system.grid_columnconfigure(0, weight=1)

        lbl_sys_title = ctk.CTkLabel(
            self.frame_system,
            text="System Dependencies",
            font=("Arial", 14, "bold"),
            text_color=ACCENT_CYAN,
        )
        lbl_sys_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=10)

        # Game Directory Input
        lbl_game_dir = ctk.CTkLabel(
            self.frame_system,
            text="Cyberpunk 2077 Game Directory:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_WHITE,
        )
        lbl_game_dir.grid(row=1, column=0, columnspan=2, sticky="w", padx=15, pady=2)

        self.entry_game_dir = ctk.CTkEntry(
            self.frame_system,
            placeholder_text="e.g. C:\\Steam\\steamapps\\common\\Cyberpunk 2077",
            fg_color="#121212",
            border_color=TEXT_MUTED,
            text_color=TEXT_WHITE,
        )
        self.entry_game_dir.grid(row=2, column=0, sticky="ew", padx=(15, 5), pady=5)
        if self.config.get("game_dir"):
            self.entry_game_dir.insert(0, self.config["game_dir"])
        self.entry_game_dir.bind("<KeyRelease>", lambda e: self.run_checks())

        btn_game_browse = ctk.CTkButton(
            self.frame_system,
            text="Browse",
            width=80,
            fg_color=BG_DARK,
            hover_color="#333",
            text_color=ACCENT_CYAN,
            border_color=ACCENT_CYAN,
            border_width=1,
            command=self.browse_game_dir,
        )
        btn_game_browse.grid(row=2, column=1, sticky="w", padx=(5, 15), pady=5)

        # Status Lamps
        self.frame_lamps = ctk.CTkFrame(self.frame_system, fg_color="transparent")
        self.frame_lamps.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 5))
        self.frame_lamps.grid_columnconfigure((0, 1, 2), weight=1)

        self.lamp_wkit = ctk.CTkLabel(
            self.frame_lamps, text="● WolvenKit CLI", font=("Arial", 11, "bold")
        )
        self.lamp_wkit.grid(row=0, column=0, padx=5, pady=2, sticky="w")

        self.lamp_blender = ctk.CTkLabel(
            self.frame_lamps, text="● Blender", font=("Arial", 11, "bold")
        )
        self.lamp_blender.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        self.lamp_dotnet = ctk.CTkLabel(
            self.frame_lamps, text="● .NET/Injector", font=("Arial", 11, "bold")
        )
        self.lamp_dotnet.grid(row=0, column=2, padx=5, pady=2, sticky="w")

        # Auto-install Button
        self.btn_auto_install = ctk.CTkButton(
            self.frame_system,
            text="Auto-Install Missing Dependencies",
            fg_color=BG_DARK,
            hover_color="#1f2833",
            text_color=ACCENT_CYAN,
            border_color=ACCENT_CYAN,
            border_width=1,
            height=30,
            command=self.start_auto_install,
        )
        self.btn_auto_install.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 15))

        # --- Section 2: Character Creation Save Input ---
        self.frame_char = ctk.CTkFrame(self.scroll_config, fg_color=BG_CARD)
        self.frame_char.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.frame_char.grid_columnconfigure(0, weight=1)

        lbl_char_title = ctk.CTkLabel(
            self.frame_char,
            text="Character & Input Data",
            font=("Arial", 14, "bold"),
            text_color=ACCENT_CYAN,
        )
        lbl_char_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=10)

        # Save File
        lbl_save_file = ctk.CTkLabel(
            self.frame_char,
            text="Save File (sav.dat) - Drag & Drop here:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_WHITE,
        )
        lbl_save_file.grid(row=1, column=0, columnspan=2, sticky="w", padx=15, pady=2)

        self.entry_save = ctk.CTkEntry(
            self.frame_char,
            placeholder_text="Drop save file or click Browse...",
            fg_color="#121212",
            border_color=TEXT_MUTED,
            text_color=TEXT_WHITE,
        )
        self.entry_save.grid(row=2, column=0, sticky="ew", padx=(15, 5), pady=5)
        self.entry_save.bind("<KeyRelease>", lambda e: self.update_save_preview())

        # Enable Drag and Drop on Entry
        if self.TkdndVersion:
            self.entry_save.register_drop_target(DND_FILES)
            self.entry_save.bind("<<Drop>>", self.handle_save_drop)

        btn_save_browse = ctk.CTkButton(
            self.frame_char,
            text="Browse",
            width=80,
            fg_color=BG_DARK,
            hover_color="#333",
            text_color=ACCENT_CYAN,
            border_color=ACCENT_CYAN,
            border_width=1,
            command=self.browse_save_file,
        )
        btn_save_browse.grid(row=2, column=1, sticky="w", padx=(5, 15), pady=5)

        # Preview Details Frame
        self.frame_preview = ctk.CTkFrame(self.frame_char, fg_color="#121212")
        self.frame_preview.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=10)
        self.frame_preview.grid_columnconfigure((0, 1), weight=1)

        self.lbl_prev_rig = ctk.CTkLabel(
            self.frame_preview, text="Rig: None", font=("Arial", 11), text_color=TEXT_MUTED
        )
        self.lbl_prev_rig.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.lbl_prev_skin = ctk.CTkLabel(
            self.frame_preview, text="Skin: None", font=("Arial", 11), text_color=TEXT_MUTED
        )
        self.lbl_prev_skin.grid(row=0, column=1, padx=10, pady=5, sticky="w")

        self.lbl_prev_hair = ctk.CTkLabel(
            self.frame_preview, text="Hair: None", font=("Arial", 11), text_color=TEXT_MUTED
        )
        self.lbl_prev_hair.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        self.lbl_prev_selections = ctk.CTkLabel(
            self.frame_preview, text="Selections: None", font=("Arial", 11), text_color=TEXT_MUTED
        )
        self.lbl_prev_selections.grid(row=1, column=1, padx=10, pady=5, sticky="w")

        # NPV Name
        lbl_npv_name = ctk.CTkLabel(
            self.frame_char,
            text="NPV Name (AMM spawn label):",
            font=("Arial", 12, "bold"),
            text_color=TEXT_WHITE,
        )
        lbl_npv_name.grid(row=4, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 2))

        self.entry_npv_name = ctk.CTkEntry(
            self.frame_char,
            placeholder_text="e.g. My V NPC",
            fg_color="#121212",
            border_color=TEXT_MUTED,
            text_color=TEXT_WHITE,
        )
        self.entry_npv_name.grid(row=5, column=0, columnspan=2, sticky="ew", padx=15, pady=5)
        self.entry_npv_name.bind("<KeyRelease>", lambda e: self.update_default_output())

        # Output Folder
        lbl_output = ctk.CTkLabel(
            self.frame_char,
            text="Output Directory:",
            font=("Arial", 12, "bold"),
            text_color=TEXT_WHITE,
        )
        lbl_output.grid(row=6, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 2))

        self.entry_output = ctk.CTkEntry(
            self.frame_char,
            placeholder_text="Directory where the mod will be built",
            fg_color="#121212",
            border_color=TEXT_MUTED,
            text_color=TEXT_WHITE,
        )
        self.entry_output.grid(row=7, column=0, sticky="ew", padx=(15, 5), pady=5)

        btn_output_browse = ctk.CTkButton(
            self.frame_char,
            text="Browse",
            width=80,
            fg_color=BG_DARK,
            hover_color="#333",
            text_color=ACCENT_CYAN,
            border_color=ACCENT_CYAN,
            border_width=1,
            command=self.browse_output_dir,
        )
        btn_output_browse.grid(row=7, column=1, sticky="w", padx=(5, 15), pady=5)

        # --- Section 3: Advanced Overrides (Collapsible Style) ---
        self.adv_expanded = False
        self.btn_toggle_adv = ctk.CTkButton(
            self.scroll_config,
            text="▶ Show Advanced Overrides",
            fg_color="transparent",
            hover_color="#161920",
            text_color=ACCENT_CYAN,
            font=("Arial", 12, "bold"),
            command=self.toggle_advanced,
        )
        self.btn_toggle_adv.grid(row=2, column=0, sticky="w", padx=15, pady=10)

        self.frame_adv = ctk.CTkFrame(self.scroll_config, fg_color=BG_CARD)
        # We don't grid it initially, shown when adv_expanded = True

        self.setup_advanced_fields()

        # ==========================================
        # RIGHT COLUMN: Build Status & Console Log
        # ==========================================
        self.frame_console = ctk.CTkFrame(self, fg_color=BG_CARD)
        self.frame_console.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.frame_console.grid_rowconfigure(1, weight=1)
        self.frame_console.grid_columnconfigure(0, weight=1)

        # Console Header
        lbl_console_title = ctk.CTkLabel(
            self.frame_console,
            text="Build Progress & Output",
            font=("Arial", 16, "bold"),
            text_color=ACCENT_CYAN,
        )
        lbl_console_title.grid(row=0, column=0, sticky="w", padx=15, pady=15)

        # Console Log Monospace Box
        self.textbox_log = ctk.CTkTextbox(
            self.frame_console,
            font=("Courier New", 12),
            fg_color="#0a0a0d",
            text_color="#c8c8c8",
            border_color="#333",
            border_width=1,
        )
        self.textbox_log.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        self.append_log("NPV Build GUI initialized. Ready.\n")

        # Action panel at the bottom right
        self.frame_actions = ctk.CTkFrame(self.frame_console, fg_color="transparent")
        self.frame_actions.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
        self.frame_actions.grid_columnconfigure(0, weight=1)

        # Progress Indicator
        self.progress_bar = ctk.CTkProgressBar(
            self.frame_actions, fg_color="#121212", progress_color=ACCENT_CYAN
        )
        # Hidden initially
        
        # Build Button
        self.btn_build = ctk.CTkButton(
            self.frame_actions,
            text="BUILD NPV MOD",
            font=("Arial", 16, "bold"),
            fg_color=BG_DARK,
            text_color=ACCENT_CYAN,
            border_color=ACCENT_CYAN,
            border_width=2,
            hover_color="#1f2833",
            height=45,
            command=self.start_build,
        )
        self.btn_build.grid(row=1, column=0, sticky="ew", pady=5)

        # Success/Failure Alert Banner
        self.lbl_banner = ctk.CTkLabel(
            self.frame_actions,
            text="",
            font=("Arial", 13, "bold"),
            height=30,
            corner_radius=4,
        )
        # Hidden initially

    def setup_advanced_fields(self):
        self.frame_adv.grid_columnconfigure(0, weight=1)

        # CET CC JSON
        lbl_cc_json = ctk.CTkLabel(
            self.frame_adv, text="CET Appearance JSON (--cc-json):", font=("Arial", 11, "bold"), text_color=TEXT_WHITE
        )
        lbl_cc_json.grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 2))
        self.entry_cc_json = ctk.CTkEntry(self.frame_adv, placeholder_text="Path to cc_dump.json", fg_color="#121212", border_color=TEXT_MUTED, text_color=TEXT_WHITE)
        self.entry_cc_json.grid(row=1, column=0, sticky="ew", padx=(15, 5), pady=5)
        btn_cc_browse = ctk.CTkButton(self.frame_adv, text="Browse", width=80, fg_color=BG_DARK, hover_color="#333", text_color=ACCENT_CYAN, border_color=ACCENT_CYAN, border_width=1, command=self.browse_cc_json)
        btn_cc_browse.grid(row=1, column=1, sticky="w", padx=(5, 15), pady=5)

        # Hair Override
        lbl_hair_ovr = ctk.CTkLabel(
            self.frame_adv, text="Hair Override:", font=("Arial", 11, "bold"), text_color=TEXT_WHITE
        )
        lbl_hair_ovr.grid(row=2, column=0, columnspan=2, sticky="w", padx=15, pady=(5, 2))
        
        frame_hair_input = ctk.CTkFrame(self.frame_adv, fg_color="transparent")
        frame_hair_input.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=5)
        frame_hair_input.grid_columnconfigure(0, weight=1)
        
        self.entry_hair_ovr = ctk.CTkEntry(
            frame_hair_input, placeholder_text="e.g. zara, none, 12, or select/drop a mod file...",
            fg_color="#121212", border_color=TEXT_MUTED, text_color=TEXT_WHITE
        )
        self.entry_hair_ovr.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        if self.TkdndVersion:
            self.entry_hair_ovr.register_drop_target(DND_FILES)
            self.entry_hair_ovr.bind("<<Drop>>", self.handle_hair_drop)
            
        btn_hair_browse = ctk.CTkButton(
            frame_hair_input, text="Browse", width=80, fg_color=BG_DARK,
            hover_color="#333", text_color=ACCENT_CYAN, border_color=ACCENT_CYAN,
            border_width=1, command=self.browse_hair_mod
        )
        btn_hair_browse.grid(row=0, column=1, sticky="w", padx=(5, 5))
        
        btn_hair_clear = ctk.CTkButton(
            frame_hair_input, text="Clear", width=60, fg_color=BG_DARK,
            hover_color="#333", text_color=TEXT_MUTED, border_color=TEXT_MUTED,
            border_width=1, command=self.clear_hair_mod
        )
        btn_hair_clear.grid(row=0, column=2, sticky="w", padx=(5, 0))

        # Skin Override
        lbl_skin_ovr = ctk.CTkLabel(
            self.frame_adv, text="Skin Tone Override:", font=("Arial", 11, "bold"), text_color=TEXT_WHITE
        )
        lbl_skin_ovr.grid(row=4, column=0, columnspan=2, sticky="w", padx=15, pady=(5, 2))
        self.entry_skin_ovr = ctk.CTkEntry(self.frame_adv, placeholder_text="e.g. 01_ca_pale, 02_ca_limestone", fg_color="#121212", border_color=TEXT_MUTED, text_color=TEXT_WHITE)
        self.entry_skin_ovr.grid(row=5, column=0, columnspan=2, sticky="ew", padx=15, pady=5)

        # Garment Overrides (Multiple items)
        lbl_garments = ctk.CTkLabel(
            self.frame_adv, text="Garment Override Depot Paths (Double click to remove):", font=("Arial", 11, "bold"), text_color=TEXT_WHITE
        )
        lbl_garments.grid(row=6, column=0, columnspan=2, sticky="w", padx=15, pady=(5, 2))
        
        self.garment_list = tk.Listbox(
            self.frame_adv,
            bg="#121212",
            fg=TEXT_WHITE,
            selectbackground=ACCENT_CYAN,
            selectforeground=BG_DARK,
            font=("Courier New", 10),
            borderwidth=1,
            highlightcolor=ACCENT_CYAN,
        )
        self.garment_list.grid(row=7, column=0, sticky="ew", padx=(15, 5), pady=5)
        self.garment_list.bind("<Double-Button-1>", self.remove_selected_garment)
        
        btn_add_garment = ctk.CTkButton(self.frame_adv, text="+ Add", width=80, fg_color=BG_DARK, hover_color="#333", text_color=ACCENT_CYAN, border_color=ACCENT_CYAN, border_width=1, command=self.add_garment_override)
        btn_add_garment.grid(row=7, column=1, sticky="w", padx=(5, 15), pady=5)

        # Custom Head GLB / Mesh / Heb Mesh
        lbl_custom_head = ctk.CTkLabel(
            self.frame_adv, text="BYO Head Options (Custom Mesh/GLB):", font=("Arial", 11, "bold"), text_color=TEXT_WHITE
        )
        lbl_custom_head.grid(row=8, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 2))
        
        self.entry_head_glb = ctk.CTkEntry(self.frame_adv, placeholder_text="Path to user_head.glb", fg_color="#121212", border_color=TEXT_MUTED, text_color=TEXT_WHITE)
        self.entry_head_glb.grid(row=9, column=0, sticky="ew", padx=(15, 5), pady=5)
        btn_glb_browse = ctk.CTkButton(self.frame_adv, text="Browse GLB", width=80, fg_color=BG_DARK, hover_color="#333", text_color=ACCENT_CYAN, border_color=ACCENT_CYAN, border_width=1, command=self.browse_head_glb)
        btn_glb_browse.grid(row=9, column=1, sticky="w", padx=(5, 15), pady=5)

        self.entry_head_mesh = ctk.CTkEntry(self.frame_adv, placeholder_text="Path to user_head.mesh", fg_color="#121212", border_color=TEXT_MUTED, text_color=TEXT_WHITE)
        self.entry_head_mesh.grid(row=10, column=0, sticky="ew", padx=(15, 5), pady=5)
        btn_mesh_browse = ctk.CTkButton(self.frame_adv, text="Browse Mesh", width=80, fg_color=BG_DARK, hover_color="#333", text_color=ACCENT_CYAN, border_color=ACCENT_CYAN, border_width=1, command=self.browse_head_mesh)
        btn_mesh_browse.grid(row=10, column=1, sticky="w", padx=(5, 15), pady=5)

        self.entry_heb_mesh = ctk.CTkEntry(self.frame_adv, placeholder_text="Path to user_heb.mesh (details)", fg_color="#121212", border_color=TEXT_MUTED, text_color=TEXT_WHITE)
        self.entry_heb_mesh.grid(row=11, column=0, sticky="ew", padx=(15, 5), pady=5)
        btn_heb_browse = ctk.CTkButton(self.frame_adv, text="Browse HEB", width=80, fg_color=BG_DARK, hover_color="#333", text_color=ACCENT_CYAN, border_color=ACCENT_CYAN, border_width=1, command=self.browse_heb_mesh)
        btn_heb_browse.grid(row=11, column=1, sticky="w", padx=(5, 15), pady=5)

        # Clear Cache / Restore Head Toggles
        self.switch_clear_cache = ctk.CTkSwitch(
            self.frame_adv, text="Clear cache before build", font=("Arial", 11), text_color=TEXT_WHITE, progress_color=ACCENT_CYAN
        )
        self.switch_clear_cache.grid(row=12, column=0, columnspan=2, sticky="w", padx=15, pady=10)

        self.switch_restore_head = ctk.CTkSwitch(
            self.frame_adv, text="Restore head materials", font=("Arial", 11), text_color=TEXT_WHITE, progress_color=ACCENT_CYAN
        )
        self.switch_restore_head.select()
        self.switch_restore_head.grid(row=13, column=0, columnspan=2, sticky="w", padx=15, pady=(0, 15))

    # --- Toggle Advanced Frame ---
    def toggle_advanced(self):
        if self.adv_expanded:
            self.frame_adv.grid_forget()
            self.btn_toggle_adv.configure(text="▶ Show Advanced Overrides")
            self.adv_expanded = False
        else:
            self.frame_adv.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
            self.btn_toggle_adv.configure(text="▼ Hide Advanced Overrides")
            self.adv_expanded = True

    # --- Logs ---
    def append_log(self, text: str):
        self.textbox_log.configure(state="normal")
        self.textbox_log.insert("end", text)
        self.textbox_log.see("end")
        self.textbox_log.configure(state="disabled")

    # --- Actions / Commands ---
    def run_checks(self):
        game_path_str = self.entry_game_dir.get().strip()
        game_path = Path(game_path_str) if game_path_str else None
        
        status = check_dependencies(game_path)

        def update_lamp(lamp, found):
            if found:
                lamp.configure(text_color=STATUS_GREEN)
            else:
                lamp.configure(text_color=STATUS_RED)

        update_lamp(self.lamp_wkit, status["wolvenkit"])
        update_lamp(self.lamp_blender, status["blender"])
        update_lamp(self.lamp_dotnet, status["npv_inject"])
        
        # Game Dir validation feedback
        if game_path_str:
            if status["game_dir_valid"]:
                self.entry_game_dir.configure(border_color=STATUS_GREEN)
                # Persist valid path
                self.config["game_dir"] = str(game_path.resolve())
                save_config(self.config)
            else:
                self.entry_game_dir.configure(border_color=STATUS_RED)
        else:
            self.entry_game_dir.configure(border_color=TEXT_MUTED)

        # Disable/Enable Build button based on checks
        ready = status["wolvenkit"] and status["blender"] and status["npv_inject"] and status["game_dir_valid"]
        if ready:
            self.btn_build.configure(state="normal", border_color=ACCENT_CYAN, text_color=ACCENT_CYAN)
        else:
            self.btn_build.configure(state="disabled", border_color="#333", text_color="#555")

    # --- Browse Helpers ---
    def browse_game_dir(self):
        path = filedialog.askdirectory(title="Select Cyberpunk 2077 Installation Root")
        if path:
            self.entry_game_dir.delete(0, "end")
            self.entry_game_dir.insert(0, path)
            self.run_checks()

    def browse_save_file(self):
        # Look for standard save folders if not specified
        init_dir = Path.home()
        if sys.platform == "win32":
            saved_games = Path.home() / "Saved Games" / "CD Projekt Red" / "Cyberpunk 2077"
            if saved_games.exists():
                init_dir = saved_games
        else:
            steam_proton = Path.home() / ".steam" / "steam" / "steamapps" / "compatdata" / "1091500" / "pfx" / "drive_c" / "users" / "steamuser" / "Saved Games" / "CD Projekt Red" / "Cyberpunk 2077"
            if steam_proton.exists():
                init_dir = steam_proton

        path = filedialog.askopenfilename(
            initialdir=str(init_dir),
            title="Select Cyberpunk 2077 Save File",
            filetypes=[("Save Files", "*.dat"), ("All Files", "*.*")]
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
            self.lbl_prev_rig.configure(text=f"Rig: {prev['body_rig']}", text_color=TEXT_WHITE)
            self.lbl_prev_skin.configure(text=f"Skin: {prev['skin_tone']}", text_color=TEXT_WHITE)
            self.lbl_prev_hair.configure(text=f"Hair: {prev['hair_style']} (col: {prev['hair_color']})", text_color=TEXT_WHITE)
            self.lbl_prev_selections.configure(text=f"Selections: {prev['selections_count']}", text_color=TEXT_WHITE)
            self.update_default_output()
        except Exception as e:
            self.lbl_prev_rig.configure(text="Rig: Error", text_color=STATUS_RED)
            self.lbl_prev_skin.configure(text="Skin: Error", text_color=STATUS_RED)
            self.lbl_prev_hair.configure(text=f"Err: {str(e)[:25]}", text_color=STATUS_RED)
            self.lbl_prev_selections.configure(text="Selections: Error", text_color=STATUS_RED)

    def clear_preview(self):
        self.lbl_prev_rig.configure(text="Rig: None", text_color=TEXT_MUTED)
        self.lbl_prev_skin.configure(text="Skin: None", text_color=TEXT_MUTED)
        self.lbl_prev_hair.configure(text="Hair: None", text_color=TEXT_MUTED)
        self.lbl_prev_selections.configure(text="Selections: None", text_color=TEXT_MUTED)

    def update_default_output(self):
        name = self.entry_npv_name.get().strip()
        if not name:
            name = "my_v_mod"
        
        # Safe name for path
        safe_name = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in name.lower()]).strip("_")
        
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
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if path:
            self.entry_cc_json.delete(0, "end")
            self.entry_cc_json.insert(0, path)

    def browse_hair_mod(self):
        game_dir_str = self.entry_game_dir.get().strip()
        if not game_dir_str:
            self.show_error("Game Dir Required", "Please specify the Game Directory before selecting a hair mod.")
            return

        file_path = filedialog.askopenfilename(
            title="Select Hair Mod File",
            filetypes=[
                ("Cyberpunk Hair Mod Files", "*.archive *.zip *.7z *.rar"),
                ("Raw Archive", "*.archive"),
                ("Compressed Archive", "*.zip *.7z *.rar"),
                ("All files", "*.*")
            ]
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

        except Exception as e:
            self.show_error("Hair Mod Error", f"Failed to install hair mod:\n{str(e)}")

    def clear_hair_mod(self):
        self.entry_hair_ovr.delete(0, "end")

    def handle_hair_drop(self, event):
        path_str = event.data
        if path_str.startswith("{") and path_str.endswith("}"):
            path_str = path_str[1:-1]

        game_dir_str = self.entry_game_dir.get().strip()
        if not game_dir_str:
            self.show_error("Game Dir Required", "Please specify the Game Directory before dropping a hair mod.")
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

        except Exception as e:
            self.show_error("Hair Mod Error", f"Failed to install hair mod:\n{str(e)}")

    def browse_head_glb(self):
        path = filedialog.askopenfilename(
            title="Select Custom Head GLB file",
            filetypes=[("GLB Files", "*.glb"), ("All Files", "*.*")]
        )
        if path:
            self.entry_head_glb.delete(0, "end")
            self.entry_head_glb.insert(0, path)

    def browse_head_mesh(self):
        path = filedialog.askopenfilename(
            title="Select Custom Head Mesh file",
            filetypes=[("Mesh Files", "*.mesh"), ("All Files", "*.*")]
        )
        if path:
            self.entry_head_mesh.delete(0, "end")
            self.entry_head_mesh.insert(0, path)

    def browse_heb_mesh(self):
        path = filedialog.askopenfilename(
            title="Select Custom HEB Mesh file",
            filetypes=[("Mesh Files", "*.mesh"), ("All Files", "*.*")]
        )
        if path:
            self.entry_heb_mesh.delete(0, "end")
            self.entry_heb_mesh.insert(0, path)

    def add_garment_override(self):
        path = filedialog.askopenfilename(
            title="Select Garment entity (.ent) file",
            filetypes=[("Entity Files", "*.ent"), ("All Files", "*.*")]
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
            self.show_error("Validation Error", "Either Save File or CET Appearance JSON must be provided.")
            return

        save_path = Path(save_path_str) if save_path_str else None
        cc_json = Path(cc_json_str) if cc_json_str else None
        output_dir = Path(output_dir_str)
        game_dir = Path(game_dir_str)

        # Clear logs and alert banner
        self.textbox_log.configure(state="normal")
        self.textbox_log.delete("1.0", "end")
        self.textbox_log.configure(state="disabled")
        self.lbl_banner.grid_forget()

        self.append_log(f"Starting NPV Build mod generation for V '{npv_name}'...\n")

        # Set up build kwargs
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
            "user_head_glb": Path(self.entry_head_glb.get().strip()) if self.entry_head_glb.get().strip() else None,
            "user_head_mesh": Path(self.entry_head_mesh.get().strip()) if self.entry_head_mesh.get().strip() else None,
            "user_heb_mesh": Path(self.entry_heb_mesh.get().strip()) if self.entry_heb_mesh.get().strip() else None,
            "restore_head_materials": self.switch_restore_head.get() == 1,
        }

        # 2. Update UI states
        self.btn_build.configure(state="disabled", text="BUILDING...")
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.progress_bar.start()

        # 3. Spawn background thread
        self.worker.start(**kwargs)

        # 4. Schedule Queue Poller
        self.after(50, self.poll_queue)

    def poll_queue(self):
        try:
            while True:
                msg_type, msg_val = self.queue.get_nowait()
                if msg_type == "log":
                    self.append_log(msg_val)
                elif msg_type == "progress":
                    self.progress_bar.set(msg_val)
                elif msg_type == "done":
                    self.build_finished(success=True, payload=msg_val)
                elif msg_type == "error":
                    self.build_finished(success=False, payload=msg_val)
                elif msg_type == "install_done":
                    self.install_finished(success=True)
                elif msg_type == "install_error":
                    self.install_finished(success=False, error_msg=msg_val)
                self.queue.task_done()
        except queue.Empty:
            pass

        if self.worker.is_alive or self.installer_worker.is_alive:
            self.after(50, self.poll_queue)

    def start_auto_install(self):
        # Ask for confirmation before downloading
        confirm = tk.messagebox.askyesno(
            "Download Dependencies?",
            "This will download and locally install missing tools into your application cache:\n"
            "- .NET 8.0 SDK (approx. 120MB)\n"
            "- WolvenKit.CLI (approx. 40MB)\n"
            "- Blender 4.2.0 LTS (approx. 150MB)\n\n"
            "This requires about 350MB of downloads and up to 1GB of disk space. "
            "Proceed?",
        )
        if not confirm:
            return

        # Clear logs and alert banner
        self.textbox_log.configure(state="normal")
        self.textbox_log.delete("1.0", "end")
        self.textbox_log.configure(state="disabled")
        self.lbl_banner.grid_forget()

        self.append_log("Starting dependency auto-installer...\n")

        # Update UI states
        self.btn_auto_install.configure(state="disabled", text="INSTALLING...")
        self.btn_build.configure(state="disabled")
        
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # Spawn background thread
        self.installer_worker.start()

        # Schedule Queue Poller
        self.after(50, self.poll_queue)

    def install_finished(self, success: bool, error_msg: str = ""):
        self.progress_bar.grid_forget()
        self.btn_auto_install.configure(state="normal", text="Auto-Install Missing Dependencies")
        self.progress_bar.configure(mode="indeterminate")

        if success:
            self.append_log("\n[Success] All dependencies installed successfully! Ready to build.\n")
            self.lbl_banner.configure(
                text="✓ Dependencies Installed Successfully!",
                fg_color=STATUS_GREEN,
                text_color=BG_DARK,
            )
        else:
            self.append_log(f"\n[Error] Dependency installation failed: {error_msg}\n")
            self.lbl_banner.configure(
                text="✗ Installation Failed. Check logs above.",
                fg_color=STATUS_RED,
                text_color=TEXT_WHITE,
            )

        self.lbl_banner.grid(row=2, column=0, sticky="ew", pady=5)
        
        # Re-run checks to update lamps
        self.run_checks()

    def build_finished(self, success: bool, payload: str):
        self.progress_bar.stop()
        self.progress_bar.grid_forget()
        self.btn_build.configure(state="normal", text="BUILD NPV MOD")

        if success:
            self.append_log(f"\n[Success] NPV Mod built successfully! Saved at: {payload}\n")
            self.lbl_banner.configure(
                text="✓ Build Successful! Mod Ready.",
                fg_color=STATUS_GREEN,
                text_color=BG_DARK,
            )
            # Add helper button to open output dir
            self.btn_open_out = ctk.CTkButton(
                self.frame_actions,
                text="Open Output Folder",
                fg_color="#333",
                hover_color="#444",
                text_color=ACCENT_CYAN,
                command=lambda: webbrowser.open(f"file://{payload}"),
            )
            self.btn_open_out.grid(row=3, column=0, sticky="ew", pady=5)
        else:
            self.append_log(f"\n[Error] Build failed: {payload}\n")
            self.lbl_banner.configure(
                text="✗ Build Failed. Check logs above.",
                fg_color=STATUS_RED,
                text_color=TEXT_WHITE,
            )
            if hasattr(self, "btn_open_out"):
                self.btn_open_out.grid_forget()

        self.lbl_banner.grid(row=2, column=0, sticky="ew", pady=5)

    def show_error(self, title: str, message: str):
        self.append_log(f"\n[{title}] {message}\n")
        # Standard ctk popups or standard tk dialogs
        tk.messagebox.showerror(title, message)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
