import sys
import threading
import time

import pytest

from npv_build.core.cancel import CancelToken
from npv_build.core.errors import PipelineCancelled, ToolError, ToolTimeoutError
from npv_build.core.proc import run_tool


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_success_captures_output():
    res = run_tool(
        _py("import sys; print('out'); sys.stderr.write('err')"), tool="python", timeout=30
    )
    assert res.returncode == 0
    assert "out" in res.stdout
    assert "err" in res.stderr


def test_nonzero_exit_raises_tool_error_with_tail():
    with pytest.raises(ToolError) as ei:
        run_tool(_py("import sys; print('breadcrumb'); sys.exit(3)"), tool="python", timeout=30)
    assert ei.value.exit_code == 3
    assert ei.value.tool == "python"
    assert "breadcrumb" in str(ei.value)


def test_allow_exit_codes():
    res = run_tool(_py("import sys; sys.exit(2)"), tool="python", timeout=30, allow_exit_codes=(2,))
    assert res.returncode == 2


def test_missing_binary_raises_tool_error():
    with pytest.raises(ToolError) as ei:
        run_tool(["npv-definitely-not-a-real-binary"], tool="ghost", timeout=5)
    assert ei.value.tool == "ghost"
    assert ei.value.remediation != ""


def test_timeout_kills_process():
    start = time.monotonic()
    with pytest.raises(ToolTimeoutError):
        run_tool(_py("import time; time.sleep(60)"), tool="python", timeout=1)
    assert time.monotonic() - start < 30


def test_cancel_terminates_process():
    token = CancelToken()
    timer = threading.Timer(0.5, token.cancel)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(PipelineCancelled):
            run_tool(_py("import time; time.sleep(60)"), tool="python", timeout=120, cancel=token)
    finally:
        timer.cancel()
    assert time.monotonic() - start < 30


def test_token_raise_if_cancelled():
    token = CancelToken()
    token.raise_if_cancelled()  # no-op
    token.cancel()
    assert token.cancelled
    with pytest.raises(PipelineCancelled):
        token.raise_if_cancelled()
