"""Regression test for config/cache dir isolation.

Ensures the autouse fixture in tests/conftest.py actually redirects
save_config()/load_config() away from the user's real ~/.config/npv,
so running the test suite can never again pollute a developer's machine.
"""

from pathlib import Path

from npv_build.config import get_config_dir, load_config, save_config


def test_save_config_does_not_touch_real_home(tmp_path):
    real_config_path = Path.home() / ".config" / "npv" / "config.toml"
    real_existed_before = real_config_path.exists()
    real_mtime_before = real_config_path.stat().st_mtime if real_existed_before else None
    real_contents_before = real_config_path.read_bytes() if real_existed_before else None

    save_config({"game_dir": "/x"})

    # The write must have landed under the fixture's isolated tmp_path,
    # never under the real home directory.
    config_dir = get_config_dir()
    assert str(config_dir).startswith(str(tmp_path)), (
        f"get_config_dir() returned {config_dir!r}, expected it to be "
        f"rooted under the test tmp_path {tmp_path!r} (isolation fixture not applied)"
    )

    written_path = config_dir / "config.toml"
    assert written_path.exists()
    assert load_config() == {"game_dir": "/x"}

    # The real file must be untouched (same as before, or still absent).
    if real_existed_before:
        assert real_config_path.stat().st_mtime == real_mtime_before
        assert real_config_path.read_bytes() == real_contents_before
    else:
        assert not real_config_path.exists()
