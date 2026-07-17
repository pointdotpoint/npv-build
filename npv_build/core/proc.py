"""Single subprocess entry point for all external tools (spec ADP-1/2).

Every external invocation goes through run_tool(): enforced timeout,
cooperative cancellation, structured ToolError on failure.
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .cancel import CancelToken
from .errors import ToolError, ToolTimeoutError

_POLL_INTERVAL_S = 0.25
_TERMINATE_GRACE_S = 5.0
_OUTPUT_TAIL_CHARS = 1500


@dataclass(frozen=True)
class ToolResult:
    argv: list[str] = field(default_factory=list)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _stop_process(proc: subprocess.Popen[str]) -> tuple[str, str]:
    proc.terminate()
    try:
        return proc.communicate(timeout=_TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.communicate()


def run_tool(
    argv: Sequence[str],
    *,
    tool: str,
    timeout: float,
    cancel: CancelToken | None = None,
    cwd: Path | None = None,
    allow_exit_codes: tuple[int, ...] = (),
    logger: logging.Logger | None = None,
) -> ToolResult:
    log = logger or logging.getLogger(__name__)
    argv = [str(a) for a in argv]
    log.debug("run_tool start: %s (timeout=%ss)", " ".join(argv), timeout)

    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError as e:
        raise ToolError(
            f"{tool}: executable not found: {argv[0]}",
            tool=tool,
            argv=argv,
            remediation=f"Install {tool} or add it to PATH.",
        ) from e

    deadline = time.monotonic() + timeout
    while True:
        if cancel is not None and cancel.cancelled:
            _stop_process(proc)
            cancel.raise_if_cancelled()
        try:
            stdout, stderr = proc.communicate(timeout=_POLL_INTERVAL_S)
            break
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                out, err = _stop_process(proc)
                raise ToolTimeoutError(
                    f"{tool} timed out after {timeout:.0f}s: {' '.join(argv)}",
                    tool=tool,
                    argv=argv,
                    details=((out or "") + (err or ""))[-_OUTPUT_TAIL_CHARS:],
                    remediation="Re-run; if it persists, raise the timeout in settings.",
                ) from None

    duration = time.monotonic() - (deadline - timeout)
    log.debug("run_tool done: %s exit=%d in %.1fs", tool, proc.returncode, duration)

    ok_codes = {0} | set(allow_exit_codes)
    if proc.returncode not in ok_codes:
        tail = ((stderr or "") + (stdout or ""))[-_OUTPUT_TAIL_CHARS:]
        raise ToolError(
            f"{tool} exited with code {proc.returncode}.",
            tool=tool,
            argv=argv,
            exit_code=proc.returncode,
            details=tail,
        )

    return ToolResult(
        argv=argv, returncode=proc.returncode, stdout=stdout or "", stderr=stderr or ""
    )
