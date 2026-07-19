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


def test_check_webview_runtime_linux_missing(monkeypatch):
    from npv_build import webui_shell

    def boom():
        raise ImportError("cannot import gi")

    monkeypatch.setattr(webui_shell, "_probe_webkitgtk", boom)
    hint = webui_shell.check_webview_runtime("linux")
    assert hint is not None
    assert "gir1.2-webkit2-4.1" in hint


def test_check_webview_runtime_linux_present(monkeypatch):
    from npv_build import webui_shell

    monkeypatch.setattr(webui_shell, "_probe_webkitgtk", lambda: None)
    assert webui_shell.check_webview_runtime("linux") is None


def test_check_webview_runtime_windows_is_none():
    from npv_build.webui_shell import check_webview_runtime

    assert check_webview_runtime("win32") is None


def test_main_reports_missing_webkitgtk(monkeypatch, capsys):
    from npv_build import webui_shell

    monkeypatch.setattr(webui_shell.sys, "platform", "linux")
    monkeypatch.setattr(webui_shell, "check_webview_runtime",
                        lambda: "WebKitGTK runtime not found.\n"
                                "sudo apt install gir1.2-webkit2-4.1")
    assert webui_shell.main() == 1
    assert "gir1.2-webkit2-4.1" in capsys.readouterr().err


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
