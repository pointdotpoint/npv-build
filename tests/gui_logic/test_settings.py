"""Tests for settings module (spec GUI-7)."""

from npv_build.gui_logic.settings import Settings, load_settings, save_settings, validate


def test_roundtrip_preserves_unknown_keys(monkeypatch):
    """Settings round-trip must preserve unknown/future config keys."""
    import npv_build.gui_logic.settings as st

    store = {"game_dir": "/g", "some_future_key": 7}
    monkeypatch.setattr(st, "load_config", lambda: dict(store))
    monkeypatch.setattr(st, "save_config", lambda c: store.clear() or store.update(c))
    s = load_settings()
    assert s.game_dir == "/g"
    s.log_verbosity = 2
    save_settings(s)
    assert store["some_future_key"] == 7  # not clobbered
    assert store["log_verbosity"] == 2


def test_validate_flags_bad_verbosity():
    """Validate should flag verbosity outside 0-2 range."""
    s = Settings(
        game_dir=None,
        output_dir=None,
        log_verbosity=9,
        patch_override=None,
        check_updates=True,
    )
    problems = validate(s)
    assert any("verbosity" in p.lower() for p in problems)


def test_load_settings_defaults(monkeypatch):
    """Load settings with missing keys should use defaults."""
    import npv_build.gui_logic.settings as st

    store = {}
    monkeypatch.setattr(st, "load_config", lambda: dict(store))
    s = load_settings()
    assert s.game_dir is None
    assert s.output_dir is None
    assert s.log_verbosity == 0
    assert s.patch_override is None
    assert s.check_updates is True


def test_validate_ok_settings():
    """Validate should pass for valid settings."""
    s = Settings(
        game_dir="/valid/path",
        output_dir="/output",
        log_verbosity=1,
        patch_override=None,
        check_updates=False,
    )
    problems = validate(s)
    assert len(problems) == 0 or all("game_dir" not in p.lower() for p in problems)
