"""RED tests for Task 6: wolvenkit.py + blender_module.py -> run_tool migration."""

import pytest

import npv_build.blender_module as bm
import npv_build.wolvenkit as wkmod
from npv_build.blender_module import BlenderError
from npv_build.core.errors import ToolError


def test_blender_error_is_tool_error():
    assert issubclass(BlenderError, ToolError)


def test_no_direct_subprocess_in_migrated_modules():
    import inspect

    for mod in (bm, wkmod):
        src = inspect.getsource(mod)
        assert "subprocess.run(" not in src, f"{mod.__name__} still calls subprocess.run directly"
        assert "subprocess.Popen(" not in src, (
            f"{mod.__name__} still calls subprocess.Popen directly"
        )


def test_blender_run_wraps_tool_error(monkeypatch):
    def exploding(argv, **kwargs):
        raise ToolError("blender exploded", tool="blender", exit_code=1)

    monkeypatch.setattr(bm, "run_tool", exploding)
    with pytest.raises(BlenderError):
        bm._run(["blender", "--background"], 0, "Bake failed")
