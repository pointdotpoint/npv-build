from npv_build.gui_logic.wizard import WizardModel


def _valid_game(tmp_path):
    (tmp_path / "archive" / "pc" / "content").mkdir(parents=True)
    return tmp_path


def test_needs_wizard_when_no_game_dir():
    assert WizardModel.needs_wizard({}) is True
    assert WizardModel.needs_wizard({"game_dir": "/x"}) is False


def test_set_game_dir_validates(tmp_path):
    m = WizardModel()
    assert m.set_game_dir(tmp_path) is False  # not a game dir
    g = _valid_game(tmp_path / "game")
    assert m.set_game_dir(g) is True
    assert m.game_dir == g


def test_finish_writes_config(tmp_path, monkeypatch):
    written = {}
    import npv_build.gui_logic.wizard as wz

    monkeypatch.setattr(wz, "save_config", lambda c: written.update(c))
    m = WizardModel()
    g = _valid_game(tmp_path / "game")
    m.set_game_dir(g)
    m.finish()
    assert written["game_dir"] == str(g)
