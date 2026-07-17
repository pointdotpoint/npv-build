"""First-run wizard view: game dir -> dependencies -> done (spec GUI-2).

Three panes driven by WizardModel:
  - game_dir: auto-detected candidates list + manual browse button.
  - dependencies: status lamps for WolvenKit + Blender (NOT .NET/npv-inject,
    which is being retired per ADR 0001 / Branch A') plus an "Install
    missing" button that drives the shared InstallerWorker queue.
  - done: confirmation pane, calls WizardModel.finish() then on_complete().
"""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ..gui_logic.wizard import WizardModel

logger = logging.getLogger(__name__)

_DEP_LABELS = {
    "wolvenkit": "WolvenKit CLI",
    "blender": "Blender",
}


class WizardView(ctk.CTkFrame):
    """Thin widget: renders WizardModel, drives InstallerWorker via queue polling."""

    def __init__(
        self,
        master,
        on_complete: Callable[[], None],
        start_install: Callable[[], None],
        install_queue: queue.Queue,
        is_installer_alive: Callable[[], bool],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._on_complete = on_complete
        self._start_install = start_install
        self._queue = install_queue
        self._is_installer_alive = is_installer_alive
        self.vm = WizardModel()

        self.grid_columnconfigure(0, weight=1)

        self._title = ctk.CTkLabel(self, text="", font=("Arial", 16, "bold"))
        self._title.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        # --- game_dir pane ---
        self._game_dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._game_dir_frame.grid_columnconfigure(0, weight=1)

        self._detected_list = ctk.CTkScrollableFrame(
            self._game_dir_frame, label_text="Detected installs"
        )
        self._detected_list.grid(row=0, column=0, sticky="nsew", padx=8, pady=4)

        self._browse_button = ctk.CTkButton(
            self._game_dir_frame, text="Browse…", command=self._on_browse_clicked
        )
        self._browse_button.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        self._game_dir_status = ctk.CTkLabel(self._game_dir_frame, text="", wraplength=400)
        self._game_dir_status.grid(row=2, column=0, sticky="w", padx=8, pady=4)

        self._next_button = ctk.CTkButton(
            self._game_dir_frame, text="Next", command=self._on_next_clicked, state="disabled"
        )
        self._next_button.grid(row=3, column=0, sticky="ew", padx=8, pady=(8, 4))

        # --- dependencies pane ---
        self._deps_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._deps_frame.grid_columnconfigure(0, weight=1)

        self._dep_lamps: dict[str, ctk.CTkLabel] = {}
        for i, (key, label) in enumerate(_DEP_LABELS.items()):
            lamp = ctk.CTkLabel(self._deps_frame, text=f"● {label}", font=("Arial", 12, "bold"))
            lamp.grid(row=i, column=0, sticky="w", padx=8, pady=2)
            self._dep_lamps[key] = lamp

        self._install_button = ctk.CTkButton(
            self._deps_frame, text="Install missing", command=self._on_install_clicked
        )
        self._install_button.grid(row=len(_DEP_LABELS), column=0, sticky="ew", padx=8, pady=8)

        self._deps_next_button = ctk.CTkButton(
            self._deps_frame, text="Next", command=self._on_next_clicked
        )
        self._deps_next_button.grid(row=len(_DEP_LABELS) + 1, column=0, sticky="ew", padx=8, pady=4)

        # --- done pane ---
        self._done_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._done_frame.grid_columnconfigure(0, weight=1)

        self._done_label = ctk.CTkLabel(self._done_frame, text="Setup complete.")
        self._done_label.grid(row=0, column=0, sticky="w", padx=8, pady=8)

        self._finish_button = ctk.CTkButton(
            self._done_frame, text="Finish", command=self._on_finish_clicked
        )
        self._finish_button.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        self._refresh_detected()
        self._sync_widgets()

    # --- game_dir pane ---

    def _refresh_detected(self) -> None:
        for child in self._detected_list.winfo_children():
            child.destroy()
        candidates = self.vm.detect_game_dirs()
        if not candidates:
            ctk.CTkLabel(self._detected_list, text="No installs auto-detected.").pack(pady=4)
            return
        for path in candidates:
            ctk.CTkButton(
                self._detected_list,
                text=str(path),
                command=lambda p=path: self._choose_game_dir(p),
            ).pack(fill="x", padx=4, pady=2)

    def _on_browse_clicked(self) -> None:
        path = filedialog.askdirectory(title="Select Cyberpunk 2077 Installation Root")
        if path:
            self._choose_game_dir(Path(path))

    def _choose_game_dir(self, path: Path) -> None:
        accepted = self.vm.set_game_dir(path)
        if accepted:
            self._game_dir_status.configure(text=f"Selected: {path}", text_color="#2ecc71")
        else:
            self._game_dir_status.configure(
                text=f"Not a valid Cyberpunk 2077 install: {path}", text_color="#e74c3c"
            )
        self._sync_widgets()

    # --- dependencies pane ---

    def _refresh_dep_lamps(self) -> None:
        status = self.vm.dependency_status()
        for key, lamp in self._dep_lamps.items():
            found = bool(status.get(key))
            lamp.configure(text_color="#2ecc71" if found else "#e74c3c")

    def _on_install_clicked(self) -> None:
        self._install_button.configure(state="disabled", text="Installing…")
        self._start_install()
        self.after(50, self._poll_queue)

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, _val = self._queue.get_nowait()
                if kind in ("install_done", "install_error"):
                    self._install_button.configure(state="normal", text="Install missing")
                    self._refresh_dep_lamps()
                self._queue.task_done()
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001 - GUI event loop must survive
            logger.exception("Unexpected error while polling installer queue")

        if self._is_installer_alive():
            self.after(50, self._poll_queue)

    # --- navigation ---

    def _on_next_clicked(self) -> None:
        if self.vm.step == "game_dir" and self.vm.game_dir is None:
            return
        self.vm.advance()
        self._sync_widgets()

    def _on_finish_clicked(self) -> None:
        self.vm.finish()
        self._on_complete()

    def _sync_widgets(self) -> None:
        self._next_button.configure(state="normal" if self.vm.game_dir is not None else "disabled")

        step = self.vm.step
        self._title.configure(text=f"First-run setup — step {self.vm.step_index + 1} of 3")

        self._game_dir_frame.grid_forget()
        self._deps_frame.grid_forget()
        self._done_frame.grid_forget()

        if step == "game_dir":
            self._game_dir_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        elif step == "dependencies":
            self._refresh_dep_lamps()
            self._deps_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        elif step == "done":
            self._done_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
