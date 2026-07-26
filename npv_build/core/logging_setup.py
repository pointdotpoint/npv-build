"""Logging configuration for CLI and GUI frontends (spec LOG-1..3)."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

_PACKAGE = "npv_build"
_CONSOLE_LEVELS = {0: logging.WARNING, 1: logging.INFO}
_OWNED_ATTRIBUTE = "_npv_build_owned"


def _mark_owned(handler: logging.Handler, role: str) -> logging.Handler:
    setattr(handler, _OWNED_ATTRIBUTE, role)
    return handler


class CallbackHandler(logging.Handler):
    def __init__(self, fn: Callable[[str], None]) -> None:
        super().__init__(level=logging.DEBUG)
        self._fn = fn
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._fn(self.format(record))
        except Exception:  # noqa: BLE001 - logging must never crash the pipeline
            self.handleError(record)


def configure_logging(
    verbosity: int = 0,
    log_file: Path | None = None,
    extra_handler: logging.Handler | None = None,
) -> logging.Logger:
    pkg = logging.getLogger(_PACKAGE)
    pkg.setLevel(logging.DEBUG)
    pkg.propagate = False
    for handler in list(pkg.handlers):
        if getattr(handler, _OWNED_ATTRIBUTE, None):
            pkg.removeHandler(handler)
            if handler is not extra_handler:
                handler.close()

    console = _mark_owned(logging.StreamHandler(stream=sys.stderr), "console")
    console.setLevel(_CONSOLE_LEVELS.get(verbosity, logging.DEBUG))
    console.setFormatter(logging.Formatter("%(message)s"))
    pkg.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = _mark_owned(
            logging.FileHandler(log_file, encoding="utf-8"), "file"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        pkg.addHandler(file_handler)

    if extra_handler is not None:
        _mark_owned(extra_handler, "callback")
        extra_handler.setLevel(logging.DEBUG)
        if extra_handler not in pkg.handlers:
            pkg.addHandler(extra_handler)

    return pkg
