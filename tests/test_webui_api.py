
from npv_build.webui_api import WebUiApi


def test_get_state_shape(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(
            game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
            patch_override=None, check_updates=True,
        ),
    )
    monkeypatch.setattr(
        "npv_build.webui_api.check_dependencies",
        lambda game_dir: {"wolvenkit": True, "blender": False,
                          "npv_inject": True, "game_dir_valid": True},
    )
    state = WebUiApi().get_state()
    assert state["settings"]["game_dir"] == str(tmp_path)
    assert state["deps"]["blender"] is False
    assert isinstance(state["needs_onboarding"], bool)
    assert isinstance(state["version"], str)


def test_save_config_roundtrip(monkeypatch):
    saved = {}
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.save_settings",
                        lambda s: saved.update(vars(s)))
    monkeypatch.setattr("npv_build.webui_api.validate", lambda s: [])
    result = WebUiApi().save_config({"game_dir": "/g", "log_verbosity": 2})
    assert result == {"ok": True, "errors": []}
    assert saved["game_dir"] == "/g" and saved["log_verbosity"] == 2


def test_save_config_returns_validation_errors(monkeypatch):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.validate",
                        lambda s: ["game_dir does not exist"])
    result = WebUiApi().save_config({"game_dir": "/nope"})
    assert result == {"ok": False, "errors": ["game_dir does not exist"]}
