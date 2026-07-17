"""Cooperative cancellation token shared by frontends and the pipeline."""

from __future__ import annotations

import threading

from .errors import PipelineCancelled


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise PipelineCancelled("Build cancelled")
