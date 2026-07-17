"""Logging configuration for CLI and GUI frontends (spec LOG-1..3)."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

_PACKAGE = "npv_build"
_CONSOLE_LEVELS = {0: logging.WARNING, 1: logging.INFO}


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
        pkg.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(_CONSOLE_LEVELS.get(verbosity, logging.DEBUG))
    console.setFormatter(logging.Formatter("%(message)s"))
    pkg.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        pkg.addHandler(file_handler)

    if extra_handler is not None:
        extra_handler.setLevel(logging.DEBUG)
        pkg.addHandler(extra_handler)

    return pkg
