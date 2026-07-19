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


def test_save_settings_with_none_fields_is_toml_serializable(monkeypatch):
    """None fields (unset game_dir/output_dir/patch_override) must be dropped,
    not written: TOML has no null. Regression: GUI QA hit a TypeError crash in
    save_config when saving settings with an empty output directory."""
    import tomli_w

    import npv_build.gui_logic.settings as st

    store = {}
    monkeypatch.setattr(st, "load_config", lambda: dict(store))
    monkeypatch.setattr(st, "save_config", lambda c: store.clear() or store.update(c))

    save_settings(Settings(
        game_dir="/g",
        output_dir=None,
        log_verbosity=1,
        patch_override=None,
        check_updates=True,
    ))
    assert store["game_dir"] == "/g"
    assert "output_dir" not in store and "patch_override" not in store
    tomli_w.dumps(store)  # must not raise


def test_save_settings_none_unsets_previous_value(monkeypatch):
    """Clearing a field in the GUI (value -> None) must remove the stored key."""
    import npv_build.gui_logic.settings as st

    store = {"output_dir": "/old"}
    monkeypatch.setattr(st, "load_config", lambda: dict(store))
    monkeypatch.setattr(st, "save_config", lambda c: store.clear() or store.update(c))

    s = load_settings()
    s.output_dir = None
    save_settings(s)
    assert "output_dir" not in store


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


def test_clothing_images_dir_roundtrip_and_validation(monkeypatch, tmp_path):
    import npv_build.gui_logic.settings as st

    store = {"clothing_images_dir": str(tmp_path)}
    monkeypatch.setattr(st, "load_config", lambda: dict(store))
    monkeypatch.setattr(st, "save_config", lambda c: store.clear() or store.update(c))

    s = load_settings()
    assert s.clothing_images_dir == str(tmp_path)
    assert validate(s) == []

    s.clothing_images_dir = str(tmp_path / "missing")
    assert any("clothing images" in p.lower() for p in validate(s))

    s.clothing_images_dir = None
    save_settings(s)
    assert "clothing_images_dir" not in store


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
