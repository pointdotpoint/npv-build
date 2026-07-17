import logging

from npv_build.core.logging_setup import CallbackHandler, configure_logging


def test_verbosity_levels(capsys):
    configure_logging(verbosity=0)
    log = logging.getLogger("npv_build.sample")
    log.info("info-msg")
    log.warning("warn-msg")
    out = capsys.readouterr()
    assert "info-msg" not in out.err + out.out
    assert "warn-msg" in out.err + out.out

    configure_logging(verbosity=1)
    log.info("info-2")
    out = capsys.readouterr()
    assert "info-2" in out.err + out.out


def test_reconfigure_does_not_duplicate(capsys):
    configure_logging(verbosity=1)
    configure_logging(verbosity=1)
    logging.getLogger("npv_build.sample").info("once")
    combined = "".join(capsys.readouterr())
    assert combined.count("once") == 1


def test_log_file_gets_debug(tmp_path):
    f = tmp_path / "build.log"
    configure_logging(verbosity=0, log_file=f)
    logging.getLogger("npv_build.sample").debug("deep-detail")
    for h in logging.getLogger("npv_build").handlers:
        h.flush()
    assert "deep-detail" in f.read_text(encoding="utf-8")


def test_callback_handler():
    seen: list[str] = []
    configure_logging(verbosity=0, extra_handler=CallbackHandler(seen.append))
    logging.getLogger("npv_build.sample").info("to-gui")
    assert any("to-gui" in s for s in seen)
