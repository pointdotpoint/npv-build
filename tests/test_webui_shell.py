def test_webui_dir_exists_and_has_index():
    from npv_build.webui_shell import webui_dir

    d = webui_dir()
    assert (d / "index.html").is_file()
    assert (d / "app.css").is_file()
    assert (d / "js" / "main.js").is_file()


def test_main_reports_missing_webview(monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def no_webview(name, *a, **kw):
        if name == "webview":
            raise ImportError("No module named 'webview'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_webview)
    from npv_build.webui_shell import main

    assert main() == 1
    out = capsys.readouterr().err
    assert "pywebview" in out
