import re
from pathlib import Path

PIPELINE_MODULES = [
    "orchestrator.py",
    "save_parser.py",
    "mapping.py",
    "clothing.py",
    "head_bake.py",
    "part_resolver.py",
    "wolvenkit.py",
    "blender_module.py",
    "wk_cli.py",
]
_PRINT_RE = re.compile(r"(?<![\w.])print\(")


def test_pipeline_modules_do_not_print():
    pkg = Path(__file__).resolve().parents[2] / "npv_build"
    offenders = []
    for name in PIPELINE_MODULES:
        for i, line in enumerate((pkg / name).read_text(encoding="utf-8").splitlines(), 1):
            if _PRINT_RE.search(line) and "# print-ok" not in line:
                offenders.append(f"{name}:{i}")
    assert not offenders, f"print() in pipeline modules (use logging): {offenders}"
