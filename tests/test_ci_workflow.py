import re
from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


def _job(name: str) -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    marker = f"  {name}:\n"
    start = workflow.index(marker) + len(marker)
    next_job = re.search(r"^  [A-Za-z0-9_-]+:\s*$", workflow[start:], re.MULTILINE)
    return workflow[start:] if next_job is None else workflow[start : start + next_job.start()]


def test_unit_matrix_does_not_install_native_gui_or_run_browser_smoke():
    job = _job("test")

    assert "uv sync --locked --extra gui" not in job
    assert "uv sync --locked" in job
    assert "uv run pytest -q --ignore=tests/webui_smoke" in job
    assert "playwright install" not in job


def test_browser_smoke_job_owns_browser_setup_and_tests():
    job = _job("gui-smoke")

    assert "uv sync --locked --extra gui" not in job
    assert "uv sync --locked" in job
    install = job.index("uv run playwright install chromium --with-deps")
    tests = job.index("uv run pytest tests/webui_smoke/ -q")
    assert install < tests
