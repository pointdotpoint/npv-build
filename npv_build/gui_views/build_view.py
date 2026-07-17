"""Build view: stage progress, live log, cancel + retry-from-failed-stage (spec GUI-4, CORE-3/4)."""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable

import customtkinter as ctk

logger = logging.getLogger(__name__)


class BuildViewModel:
    """Pure state machine driving the build view.

    States: idle -> running -> (done | failed); running -> cancelling -> failed.
    A cancelled build surfaces as a terminal ("error", "Build cancelled.") tuple
    from the worker queue, same as any other failure, so `cancelling` always
    resolves to `failed` (never a distinct "cancelled" state) — this is what
    lets Retry-from-failed-stage handle both cases identically.
    """

    def __init__(self) -> None:
        self.state = "idle"
        self.last_error: str | None = None
        self.stage_progress: float = 0.0
        self.resume_requested = False

    @property
    def can_cancel(self) -> bool:
        return self.state == "running"

    @property
    def can_retry(self) -> bool:
        return self.state == "failed"

    def on_start(self, resume: bool = False) -> None:
        self.state = "running"
        self.resume_requested = resume
        self.last_error = None
        self.stage_progress = 0.0

    def on_cancel_requested(self) -> None:
        if self.state == "running":
            self.state = "cancelling"

    def on_event(self, kind: str, val) -> None:
        if kind == "progress":
            self.stage_progress = val
        elif kind == "done":
            self.state = "done"
        elif kind == "error":
            self.state = "failed"
            self.last_error = val


class BuildView(ctk.CTkFrame):
    """Thin widget: renders BuildViewModel, drives BuildWorker via queue polling."""

    def __init__(
        self,
        master,
        start_build: Callable[..., None],
        cancel_build: Callable[[], None],
        build_queue: queue.Queue,
        is_worker_alive: Callable[[], bool],
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._start_build = start_build
        self._cancel_build = cancel_build
        self._queue = build_queue
        self._is_worker_alive = is_worker_alive
        self.vm = BuildViewModel()

        self._progress_bar = ctk.CTkProgressBar(self)
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))

        self._log_box = ctk.CTkTextbox(self, state="disabled")
        self._log_box.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=4)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._error_label = ctk.CTkLabel(self, text="", text_color="#e74c3c", wraplength=400)

        self._cancel_button = ctk.CTkButton(
            self, text="Cancel", command=self._on_cancel_clicked, state="disabled"
        )
        self._cancel_button.grid(row=3, column=0, sticky="ew", padx=(8, 4), pady=8)

        self._retry_button = ctk.CTkButton(
            self, text="Retry from failed stage", command=self._on_retry_clicked
        )
        # Gridded only when vm.can_retry (see _sync_widgets).

        self._sync_widgets()

    def start(self, **kwargs) -> None:
        """Start (or restart) the build; kicks off queue polling."""
        self.vm.on_start(resume=kwargs.pop("resume", False))
        self._sync_widgets()
        self._start_build(**kwargs)
        self.after(50, self._poll_queue)

    def _on_cancel_clicked(self) -> None:
        if not self.vm.can_cancel:
            return
        self.vm.on_cancel_requested()
        self._cancel_build()
        self._sync_widgets()

    def _on_retry_clicked(self) -> None:
        if not self.vm.can_retry:
            return
        self.start(resume=True)

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, val = self._queue.get_nowait()
                if kind == "log":
                    self._append_log(val)
                else:
                    self.vm.on_event(kind, val)
                    if kind == "progress":
                        self._progress_bar.set(val)
                    elif kind in ("done", "error"):
                        self._append_log(f"\n{val}\n")
                self._queue.task_done()
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001 - GUI event loop must survive
            logger.exception("Unexpected error while polling build queue")

        self._sync_widgets()
        if self._is_worker_alive():
            self.after(50, self._poll_queue)

    def _append_log(self, text: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _sync_widgets(self) -> None:
        self._cancel_button.configure(state="normal" if self.vm.can_cancel else "disabled")

        if self.vm.can_retry:
            self._retry_button.grid(row=3, column=1, sticky="ew", padx=(4, 8), pady=8)
        else:
            self._retry_button.grid_forget()

        if self.vm.state == "failed" and self.vm.last_error:
            self._error_label.configure(text=self.vm.last_error)
            self._error_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 4))
        else:
            self._error_label.grid_forget()
