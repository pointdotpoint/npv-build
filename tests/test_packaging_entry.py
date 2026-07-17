# packaging/ is not a package; load entry.py directly
import importlib.util
import sys
from pathlib import Path

_ENTRY = Path(__file__).resolve().parents[1] / "packaging" / "entry.py"
_spec = importlib.util.spec_from_file_location("npv_entry", _ENTRY)
entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry)


def test_dispatches_to_cli_when_args(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["npv-build", "--help"])
    monkeypatch.setattr("npv_build.cli.main", lambda: called.setdefault("cli", True) or 0)
    monkeypatch.setattr("npv_build.gui.main", lambda: called.setdefault("gui", True))
    try:
        entry.run()
    except SystemExit:
        pass
    assert called == {"cli": True}


def test_dispatches_to_gui_when_no_args(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["npv-build"])
    monkeypatch.setattr("npv_build.cli.main", lambda: called.setdefault("cli", True) or 0)
    monkeypatch.setattr("npv_build.gui.main", lambda: called.setdefault("gui", True))
    entry.run()
    assert called == {"gui": True}
