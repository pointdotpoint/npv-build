import pytest


@pytest.fixture(autouse=True)
def _isolate_user_dirs(tmp_path, monkeypatch):
    """Tests must never touch the real ~/.config/npv or ~/.cache/npv."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
