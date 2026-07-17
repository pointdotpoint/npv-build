"""Settings model and persistence (spec GUI-7).

Provides a Settings dataclass for the GUI configuration screen, with
load/save round-trip semantics that preserve unknown/future config keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import load_config as config_load_config
from ..config import save_config as config_save_config
from ..core.platform import is_valid_game_dir

# Re-export for monkeypatch in tests
load_config = config_load_config
save_config = config_save_config


@dataclass
class Settings:
    """Settings bound to the GUI form.

    Fields:
      - game_dir: Path to Cyberpunk 2077 install, or None if not set.
      - output_dir: Path where to save built mods, or None to use default.
      - log_verbosity: Verbosity level (0=quiet, 1=normal, 2=verbose).
      - patch_override: Force a specific patch version, or None to auto-detect.
      - check_updates: Whether to check for npv-build updates on startup.
    """

    game_dir: str | None
    output_dir: str | None
    log_verbosity: int
    patch_override: str | None
    check_updates: bool


def load_settings() -> Settings:
    """Load settings from config, filling in defaults.

    Returns:
        Settings with values loaded from config, defaulting to:
          game_dir=None, output_dir=None, log_verbosity=0, patch_override=None,
          check_updates=True.
    """
    config = load_config()
    return Settings(
        game_dir=config.get("game_dir"),
        output_dir=config.get("output_dir"),
        log_verbosity=config.get("log_verbosity", 0),
        patch_override=config.get("patch_override"),
        check_updates=config.get("check_updates", True),
    )


def save_settings(s: Settings) -> None:
    """Save settings to config, preserving unknown keys.

    Loads the full config dict, updates only the known Settings fields,
    and saves back. This ensures unknown/future keys are not clobbered.

    Args:
        s: Settings instance to save.
    """
    config = load_config()
    config["game_dir"] = s.game_dir
    config["output_dir"] = s.output_dir
    config["log_verbosity"] = s.log_verbosity
    config["patch_override"] = s.patch_override
    config["check_updates"] = s.check_updates
    save_config(config)


def validate(s: Settings) -> list[str]:
    """Validate settings, returning human-readable problems.

    Checks:
      - log_verbosity must be in {0, 1, 2}
      - game_dir, if set, must be a valid Cyberpunk 2077 install

    Args:
        s: Settings instance to validate.

    Returns:
        List of problem strings (empty if valid).
    """
    problems = []

    if s.log_verbosity not in (0, 1, 2):
        problems.append(f"Log verbosity must be 0, 1, or 2 (got {s.log_verbosity})")

    if s.game_dir is not None:
        if not is_valid_game_dir(Path(s.game_dir)):
            problems.append(f"Game directory is not valid: {s.game_dir}")

    return problems
