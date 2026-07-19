
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


def test_get_state_default_output_root(monkeypatch, tmp_path):
    from pathlib import Path

    from npv_build.gui_logic.settings import Settings

    def fake_settings(output_dir):
        return lambda: Settings(
            game_dir=str(tmp_path), output_dir=output_dir, log_verbosity=1,
            patch_override=None, check_updates=True,
        )

    monkeypatch.setattr(
        "npv_build.webui_api.check_dependencies",
        lambda game_dir: {},
    )
    monkeypatch.setattr("npv_build.webui_api.load_settings", fake_settings(None))
    state = WebUiApi().get_state()
    assert state["default_output_root"] == str(Path.home() / "npv_builds")

    monkeypatch.setattr("npv_build.webui_api.load_settings", fake_settings("/custom/out"))
    state = WebUiApi().get_state()
    assert state["default_output_root"] == "/custom/out"


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
                           mtime=123.0, thumbnail=None, patch="2.31")],
    )
    saves = WebUiApi().list_saves()
    assert saves == [{"path": str(tmp_path / "sav.dat"), "name": "AutoSave-0",
                      "mtime": 123.0, "thumbnail": None, "patch": "2.31"}]


def test_add_save_path_ok(tmp_path):
    d = tmp_path / "MySave"
    d.mkdir()
    (d / "sav.dat").write_bytes(b"\x00")
    out = WebUiApi().add_save_path(str(d / "sav.dat"))
    assert out["ok"] is True
    assert out["save"]["name"] == "MySave"
    assert out["save"]["path"] == str(d / "sav.dat")
    assert "patch" in out["save"]


def test_add_save_path_accepts_save_folder(tmp_path):
    d = tmp_path / "FolderPick"
    d.mkdir()
    (d / "sav.dat").write_bytes(b"\x00")
    out = WebUiApi().add_save_path(str(d))
    assert out["ok"] is True and out["save"]["name"] == "FolderPick"


def test_add_save_path_missing_is_structured_error(tmp_path):
    out = WebUiApi().add_save_path(str(tmp_path / "nope" / "sav.dat"))
    assert out["ok"] is False
    assert out["error"] and out["remediation"]


def test_browse_for_save_without_webview_is_structured_error():
    out = WebUiApi().browse_for_save()
    assert out["ok"] is False
    assert out.get("cancelled") is not True
    assert out["error"]


def test_zip_info_reports_contents(tmp_path):
    import zipfile

    z = tmp_path / "my_v_abc.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("archive/pc/mod/my_v_abc.archive", b"A" * 100)
        zf.writestr("r6/tweaks/npv_build/my_v_abc_photomode.yaml", b"x: 1")
    out = WebUiApi().zip_info(str(tmp_path))
    assert out["ok"] is True
    assert out["zip"]["path"] == str(z)
    assert out["zip"]["size"] == z.stat().st_size
    names = [f["name"] for f in out["zip"]["files"]]
    assert "archive/pc/mod/my_v_abc.archive" in names
    assert out["zip"]["files"][0]["size"] >= 0


def test_zip_info_without_zip_is_structured(tmp_path):
    out = WebUiApi().zip_info(str(tmp_path))
    assert out["ok"] is False and out["error"]


def test_open_folder_ok(monkeypatch, tmp_path):
    opened = {}
    monkeypatch.setattr("npv_build.webui_api.platform_open_folder",
                        lambda p: opened.setdefault("path", p))
    out = WebUiApi().open_folder(str(tmp_path))
    assert out["ok"] is True
    assert str(opened["path"]) == str(tmp_path)


def test_open_folder_missing_is_structured(tmp_path):
    out = WebUiApi().open_folder(str(tmp_path / "nope"))
    assert out["ok"] is False and out["error"]


def test_cache_info_and_clear(monkeypatch, tmp_path):
    cache = tmp_path / "npv-cache"
    (cache / "index").mkdir(parents=True)
    (cache / "index" / "2.13.json").write_bytes(b"x" * 1000)
    (cache / "tools").mkdir()
    monkeypatch.setattr("npv_build.webui_api.get_cache_dir", lambda: cache)

    api = WebUiApi()
    out = api.cache_info()
    assert out["ok"] is True
    by_name = {e["name"]: e for e in out["entries"]}
    assert by_name["index"]["size"] == 1000
    assert by_name["tools"]["size"] == 0

    cleared = api.clear_cache("index")
    assert cleared["ok"] is True
    assert not (cache / "index").exists()


def test_clear_cache_rejects_unknown_names(monkeypatch, tmp_path):
    monkeypatch.setattr("npv_build.webui_api.get_cache_dir", lambda: tmp_path)
    out = WebUiApi().clear_cache("../../etc")
    assert out["ok"] is False and out["error"]


def test_get_state_includes_tool_paths(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.check_dependencies", lambda g: {})
    monkeypatch.setattr("npv_build.webui_api.resolve_tool_paths",
                        lambda: {"wolvenkit": "/t/wk", "blender": None})
    state = WebUiApi().get_state()
    assert state["tool_paths"] == {"wolvenkit": "/t/wk", "blender": None}


def test_install_tools_runs_worker_and_emits_events(monkeypatch):
    def fake_install(cb):
        cb("Downloading WolvenKit", 40)
        cb("All missing dependencies verified & installed!", 100)

    monkeypatch.setattr("npv_build.webui_api.auto_install_missing", fake_install)
    api = WebUiApi()
    assert api.install_tools() == {"ok": True}
    import time

    deadline = time.time() + 5
    events = []
    while time.time() < deadline:
        events += api.poll_tool_events()
        if any(e["kind"] == "tool_done" for e in events):
            break
        time.sleep(0.02)
    kinds = [e["kind"] for e in events]
    assert "tool_progress" in kinds and "tool_done" in kinds
    prog = next(e for e in events if e["kind"] == "tool_progress")
    assert prog["message"] and prog["value"] == 40


def test_install_tools_failure_is_structured(monkeypatch):
    def boom(cb):
        raise RuntimeError("network down")

    monkeypatch.setattr("npv_build.webui_api.auto_install_missing", boom)
    api = WebUiApi()
    assert api.install_tools() == {"ok": True}
    import time

    deadline = time.time() + 5
    events = []
    while time.time() < deadline:
        events += api.poll_tool_events()
        if any(e["kind"] == "tool_error" for e in events):
            break
        time.sleep(0.02)
    err = next(e for e in events if e["kind"] == "tool_error")
    assert "network down" in err["message"]


def test_detect_game_dirs_bridge(monkeypatch, tmp_path):
    monkeypatch.setattr("npv_build.webui_api.find_game_dirs",
                        lambda: [tmp_path / "Cyberpunk 2077"])
    out = WebUiApi().detect_game_dirs()
    assert out == {"ok": True, "dirs": [str(tmp_path / "Cyberpunk 2077")]}


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
    assert result["ok"] is True
    [mod] = result["mods"]
    assert mod["mod_id"] == "v_abc"
    assert mod["archive_path"] == str(tmp_path / "v_abc.archive")
    assert mod["installed"] is False
    assert "built_at" in mod and "npv_name" in mod and "save_path" in mod
    assert api.install_mod("v_abc") == {"ok": True}
    assert installed == ["v_abc"]


def test_list_mods_includes_build_meta(monkeypatch, tmp_path):
    import json

    from npv_build.gui_logic.modmanager import ModEntry

    mod_root = tmp_path / "out" / "my_v_abc"
    archive = mod_root / "archive" / "pc" / "mod" / "my_v_abc.archive"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"A")
    (mod_root / "build_meta.json").write_text(
        json.dumps({"npv_name": "My V", "save_path": "/saves/x/sav.dat"}))
    entry = ModEntry(mod_id="my_v_abc", archive_path=archive,
                     lua_path=mod_root / "x.lua", installed=False, built_at=42.0)
    monkeypatch.setattr("npv_build.webui_api.mm_list_mods", lambda r, g: [entry])
    api = WebUiApi()
    api._settings_for_mods = lambda: (tmp_path, tmp_path)
    [mod] = api.list_mods()["mods"]
    assert mod["built_at"] == 42.0
    assert mod["npv_name"] == "My V"
    assert mod["save_path"] == "/saves/x/sav.dat"


def test_delete_mod_bridge(monkeypatch, tmp_path):
    from npv_build.gui_logic.modmanager import ModEntry

    entry = ModEntry(mod_id="v_abc", archive_path=tmp_path / "v_abc.archive",
                     lua_path=tmp_path / "v_abc.lua", installed=False)
    deleted = []
    monkeypatch.setattr("npv_build.webui_api.mm_list_mods", lambda r, g: [entry])
    monkeypatch.setattr("npv_build.webui_api.mm_delete_mod",
                        lambda e, g: deleted.append(e.mod_id))
    api = WebUiApi()
    api._settings_for_mods = lambda: (tmp_path, tmp_path)
    assert api.delete_mod("v_abc") == {"ok": True}
    assert deleted == ["v_abc"]
    out = api.delete_mod("ghost")
    assert out["ok"] is False and out["error"]


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
    # Rebuild metadata is persisted alongside the build output
    import json

    meta = json.loads((tmp_path / "o" / "build_meta.json").read_text())
    assert meta == {"npv_name": "V", "save_path": str(tmp_path / "sav.dat")}


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


def test_appearance_data_rows_and_overrides(monkeypatch, tmp_path):
    cc = {
        "patch": "2.31", "body_rig": "pwa", "selections": [],
        "head": {}, "eyes": {"raw": "he_000_pwa__basehead__11_gradient_blue"},
        "teeth": {"raw": ""}, "skin": {"tone_id": "01_ca_pale"},
        "hair": {"style_id": "winona_2", "raw": ""}, "overlays": [],
        "face_morphs": {"eyes": "h091"},
    }
    monkeypatch.setattr("npv_build.webui_api.parse_save_for_inspector", lambda p: cc)
    monkeypatch.setattr("npv_build.webui_api.load_part_index", lambda patch: {})
    monkeypatch.setattr("npv_build.webui_api.load_overrides",
                        lambda p: {"skin_tone": "03_ca_medium"})
    out = WebUiApi().appearance_data("/s/sav.dat")
    assert out["ok"] is True
    ids = [r["slot_id"] for r in out["rows"]]
    assert "skin_tone" in ids and "face_morph_eyes" in ids
    assert out["overrides"] == {"skin_tone": "03_ca_medium"}


def test_set_overrides_validates_and_persists(monkeypatch):
    saved = {}
    monkeypatch.setattr("npv_build.webui_api.save_overrides",
                        lambda p, o: saved.update({p: o}))
    monkeypatch.setattr("npv_build.webui_api.load_part_index", lambda patch: {})
    monkeypatch.setattr("npv_build.webui_api.parse_save_for_inspector",
                        lambda p: {"patch": "2.31", "body_rig": "pwa"})
    api = WebUiApi()
    # no option list available -> value accepted (validated at build)
    assert api.set_overrides("/s/sav.dat", {"skin_tone": "x"}) == {"ok": True}
    assert saved["/s/sav.dat"] == {"skin_tone": "x"}
    # unknown slot always rejected
    out = api.set_overrides("/s/sav.dat", {"bogus": "x"})
    assert out["ok"] is False and "bogus" in out["error"]


def test_start_build_passes_stored_overrides(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    started = {}

    class FakeWorker:
        def __init__(self, q): pass
        def start(self, **kwargs): started.update(kwargs)

    monkeypatch.setattr("npv_build.webui_api.BuildWorker", FakeWorker)
    monkeypatch.setattr("npv_build.webui_api.load_overrides",
                        lambda p: {"skin_tone": "03_ca_medium"})
    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    WebUiApi().start_build({"save_path": "/s/sav.dat", "npv_name": "V",
                            "output_dir": str(tmp_path / "o")})
    assert started["cc_overrides"] == {"skin_tone": "03_ca_medium"}


def test_load_part_index_resolves_table_key(monkeypatch, tmp_path):
    from npv_build import webui_api

    calls = []

    def spy(patch):
        calls.append(patch)
        return tmp_path / f"{patch}.json"

    (tmp_path / "2.13.json").write_text('{"part_ents": {}}', encoding="utf-8")

    monkeypatch.setattr(webui_api, "get_index_path", spy)
    result = webui_api.load_part_index("2.31")
    assert result == {"part_ents": {}}
    assert calls == ["2.13"]


def test_add_hair_mod_installs_probes_and_returns_token(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.install_hair_mod",
                        lambda src, gd: ("edie", [tmp_path / "edie_hair.archive"]))
    monkeypatch.setattr(
        "npv_build.webui_api.list_mod_archive_apps",
        lambda wk, archive_path: ["base\\x\\fhair_edie.app"],
    )
    monkeypatch.setattr(
        "npv_build.webui_api.extract_hair_components",
        lambda gd, token, rig, verbosity=0, wk=None:
            ([{"name": "c"}], "edie_hair.archive", "base\\x\\fhair_edie.app", "edie"),
    )
    out = WebUiApi().add_hair_mod(str(tmp_path / "edie_hair.zip"))
    assert out["ok"] is True
    assert out["token"] == "edie"
    assert out["source"] == "edie_hair.archive"


def test_add_hair_mod_no_hair_app_is_structured_error(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    monkeypatch.setattr("npv_build.webui_api.install_hair_mod",
                        lambda src, gd: ("notahair", [tmp_path / "notahair.archive"]))
    monkeypatch.setattr(
        "npv_build.webui_api.list_mod_archive_apps",
        lambda wk, archive_path: ["base\\x\\not_a_hair_thing.app"],
    )
    monkeypatch.setattr(
        "npv_build.webui_api.extract_hair_components",
        lambda gd, token, rig, verbosity=0, wk=None: ([], None, None, None),
    )
    out = WebUiApi().add_hair_mod(str(tmp_path / "notahair.zip"))
    assert out["ok"] is False
    assert "hair" in out["error"].lower()
    assert out["remediation"]


def test_add_hair_mod_token_from_app_basename_not_filename(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    archive_path = tmp_path / "ANRUI_MiyaviHair_Fluffypony_CCXL.archive"
    monkeypatch.setattr(
        "npv_build.webui_api.install_hair_mod",
        lambda src, gd: ("anrui_miyavihair_fluffypony_ccxl", [archive_path]),
    )
    monkeypatch.setattr(
        "npv_build.webui_api.list_mod_archive_apps",
        lambda wk, archive_path_arg: [
            "anruimurasaki\\ccxl\\miyavihair_fluffytail\\appearances\\fhair_miyavi_fluffytail.app",
            "anruimurasaki\\ccxl\\miyavihair_fluffytail\\appearances\\fpp\\"
            "fhair_miyavi_fluffytail_fpp.app",
            "anruimurasaki\\ccxl\\miyavihair_fluffytail\\appearances\\mhair_miyavi_fluffytail.app",
        ],
    )
    seen_tokens = []

    def fake_extract(gd, token, rig, verbosity=0, wk=None):
        seen_tokens.append(token)
        return ([{"name": "c"}], archive_path.name, "base\\x\\fhair_miyavi_fluffytail.app", token)

    monkeypatch.setattr("npv_build.webui_api.extract_hair_components", fake_extract)
    out = WebUiApi().add_hair_mod(str(tmp_path / "ANRUI_MiyaviHair_Fluffypony_CCXL.archive"))
    assert out["ok"] is True
    assert out["token"] == "miyavi_fluffytail"
    assert seen_tokens == ["miyavi_fluffytail"]
    assert out["source"] == archive_path.name


def test_add_hair_mod_roundtrip_failure_is_structured(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    archive_path = tmp_path / "weird_hair.archive"
    monkeypatch.setattr(
        "npv_build.webui_api.install_hair_mod",
        lambda src, gd: ("weird_hair", [archive_path]),
    )
    monkeypatch.setattr(
        "npv_build.webui_api.list_mod_archive_apps",
        lambda wk, archive_path_arg: ["base\\x\\fhair_something_else.app"],
    )
    monkeypatch.setattr(
        "npv_build.webui_api.extract_hair_components",
        lambda gd, token, rig, verbosity=0, wk=None: ([], None, None, None),
    )
    out = WebUiApi().add_hair_mod(str(tmp_path / "weird_hair.archive"))
    assert out["ok"] is False
    assert "could not be resolved" in out["error"].lower()
    assert "something_else" in out["error"]
    assert out["remediation"]


def test_add_hair_mod_without_game_dir_is_structured(monkeypatch):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=None, output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )
    out = WebUiApi().add_hair_mod("/x/hair.zip")
    assert out["ok"] is False and "Game directory" in out["error"]


def test_add_hair_mod_bad_package_is_structured(monkeypatch, tmp_path):
    from npv_build.gui_logic.settings import Settings

    monkeypatch.setattr(
        "npv_build.webui_api.load_settings",
        lambda: Settings(game_dir=str(tmp_path), output_dir=None, log_verbosity=1,
                         patch_override=None, check_updates=True),
    )

    def boom(src, gd):
        raise ValueError("No .archive file found inside the mod package.")

    monkeypatch.setattr("npv_build.webui_api.install_hair_mod", boom)
    out = WebUiApi().add_hair_mod(str(tmp_path / "empty.zip"))
    assert out["ok"] is False and "No .archive" in out["error"]
