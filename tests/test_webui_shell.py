def test_webui_dir_exists_and_has_index():
    from npv_build.webui_shell import webui_dir

    d = webui_dir()
    assert (d / "index.html").is_file()
    assert (d / "app.css").is_file()
    assert (d / "js" / "main.js").is_file()


def test_linux_env_defaults_set(monkeypatch):
    from npv_build.webui_shell import _linux_env_defaults

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("PYWEBVIEW_GUI", raising=False)
    monkeypatch.delenv("WEBKIT_DISABLE_DMABUF_RENDERER", raising=False)
    _linux_env_defaults()
    import os

    assert os.environ["PYWEBVIEW_GUI"] == "gtk"
    assert os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] == "1"


def test_linux_env_defaults_respect_overrides(monkeypatch):
    from npv_build.webui_shell import _linux_env_defaults

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("PYWEBVIEW_GUI", "qt")
    monkeypatch.setenv("WEBKIT_DISABLE_DMABUF_RENDERER", "0")
    _linux_env_defaults()
    import os

    assert os.environ["PYWEBVIEW_GUI"] == "qt"
    assert os.environ["WEBKIT_DISABLE_DMABUF_RENDERER"] == "0"


def test_linux_env_defaults_noop_elsewhere(monkeypatch):
    from npv_build.webui_shell import _linux_env_defaults

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.delenv("PYWEBVIEW_GUI", raising=False)
    _linux_env_defaults()
    import os

    assert "PYWEBVIEW_GUI" not in os.environ


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
