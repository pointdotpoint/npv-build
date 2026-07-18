
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


def test_list_saves_serializes(monkeypatch, tmp_path):
    from npv_build.gui_logic.discovery import SaveEntry

    monkeypatch.setattr(
        "npv_build.webui_api.discover_saves",
        lambda: [SaveEntry(path=tmp_path / "sav.dat", name="AutoSave-0",
                           mtime=123.0, thumbnail=None)],
    )
    saves = WebUiApi().list_saves()
    assert saves == [{"path": str(tmp_path / "sav.dat"), "name": "AutoSave-0",
                      "mtime": 123.0, "thumbnail": None}]


def test_preview_save_ok(monkeypatch):
    monkeypatch.setattr(
        "npv_build.webui_api.preview_save_file",
        lambda p: {"body_rig": "pwa", "skin_tone": "03", "hair_style": "bob",
                   "hair_color": "copper", "selections_count": 152},
    )
    out = WebUiApi().preview_save("/s/sav.dat")
    assert out["ok"] is True and out["body_rig"] == "pwa"


def test_preview_save_error_is_structured(monkeypatch):
    from npv_build.core.errors import NpvError

    def boom(p):
        raise NpvError("Unsupported patch", remediation="Update mappings")

    monkeypatch.setattr("npv_build.webui_api.preview_save_file", boom)
    out = WebUiApi().preview_save("/s/sav.dat")
    assert out == {"ok": False, "error": "Unsupported patch",
                   "remediation": "Update mappings"}


def test_preview_save_real_parser_error_is_structured(tmp_path):
    bad = tmp_path / "sav.dat"
    bad.write_bytes(b"not a save file")
    out = WebUiApi().preview_save(str(bad))
    assert out["ok"] is False
    assert isinstance(out["error"], str) and out["error"]
    assert "remediation" in out


def test_mod_roundtrip(monkeypatch, tmp_path):
    from npv_build.gui_logic.modmanager import ModEntry

    entry = ModEntry(mod_id="v_abc", archive_path=tmp_path / "v_abc.archive",
                     lua_path=tmp_path / "v_abc.lua", installed=False)
    installed = []
    monkeypatch.setattr("npv_build.webui_api.mm_list_mods",
                        lambda root, gd: [entry])
    monkeypatch.setattr("npv_build.webui_api.mm_install_mod",
                        lambda e, gd: installed.append(e.mod_id))
    api = WebUiApi()
    api._settings_for_mods = lambda: (tmp_path, tmp_path)  # test seam
    result = api.list_mods()
    assert result == {"ok": True, "mods": [{"mod_id": "v_abc",
                     "archive_path": str(tmp_path / "v_abc.archive"),
                     "installed": False}]}
    assert api.install_mod("v_abc") == {"ok": True}
    assert installed == ["v_abc"]


def test_list_mods_without_game_dir_is_structured_error(monkeypatch):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    out = WebUiApi().list_mods()
    assert out["ok"] is False
    assert "Game directory" in out["error"]


def test_poll_events_translates_queue(monkeypatch, tmp_path):
    api = WebUiApi()
    api._queue.put(("log", "[assemble] baking\n"))
    api._queue.put(("progress", 0.6))
    api._queue.put(("stage", {"stage": "assemble", "status": "started",
                              "message": "Assembling"}))
    api._queue.put(("done", "/out"))
    events = api.poll_events()
    assert events == [
        {"kind": "log", "text": "[assemble] baking\n"},
        {"kind": "progress", "value": 0.6},
        {"kind": "stage", "stage": "assemble", "status": "started",
         "message": "Assembling"},
        {"kind": "done", "output_dir": "/out"},
    ]
    assert api.poll_events() == []


def test_start_build_fills_context_and_starts_worker(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    started = {}

    class FakeWorker:
        def __init__(self, q):
            started["queue"] = q

        def start(self, **kwargs):
            started["kwargs"] = kwargs

        @property
        def is_alive(self):
            return False

    monkeypatch.setattr("npv_build.webui_api.BuildWorker", FakeWorker)
    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None,
                         log_verbosity=1, patch_override=None, check_updates=True),
    )
    api = WebUiApi()
    out = api.start_build({"save_path": str(tmp_path / "sav.dat"),
                           "npv_name": "V", "output_dir": str(tmp_path / "o"),
                           "clear_cache": False, "resume": False})
    assert out == {"ok": True}
    kw = started["kwargs"]
    assert kw["game_dir"] == tmp_path
    assert kw["npv_name"] == "V"
    assert str(kw["template_cache"]).endswith("templates")


def test_start_build_without_game_dir_errors(monkeypatch):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    out = WebUiApi().start_build({"save_path": "/s", "npv_name": "V",
                                  "output_dir": "/o"})
    assert out["ok"] is False and "Game directory" in out["error"]
