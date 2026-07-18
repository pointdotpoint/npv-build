from pathlib import Path

_GUI = Path(__file__).resolve().parents[2] / "npv_build"
_FILES = [_GUI / "gui.py"] + sorted((_GUI / "gui_views").glob("*.py"))


def test_no_hardcoded_arial_font():
    offenders = []
    for f in _FILES:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if '"Arial"' in line or "'Arial'" in line:
                offenders.append(f"{f.name}:{i}")
    assert not offenders, f"hardcoded Arial font (use gui_theme): {offenders}"
