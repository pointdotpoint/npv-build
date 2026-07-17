"""First-run wizard: game dir + dependency setup (spec GUI-2)."""

from __future__ import annotations

from pathlib import Path

from ..config import load_config, save_config
from ..core.platform import find_game_dirs, is_valid_game_dir
from ..gui_backend import check_dependencies

# .NET/npv-inject is being retired (ADR 0001 / M3 ArchiveXL spike, Branch A').
# The wizard only cares about the tools that survive that retirement.
REQUIRED_DEPS = ("wolvenkit", "blender")


class WizardModel:
    """Pure state for the first-run wizard. No Tk imports here."""

    steps = ("game_dir", "dependencies", "done")

    def __init__(self) -> None:
        self.step_index = 0
        self.game_dir: Path | None = None

    @property
    def step(self) -> str:
        return self.steps[self.step_index]

    @staticmethod
    def needs_wizard(config: dict) -> bool:
        """True when the config has no game_dir recorded yet.

        Deliberately does not re-validate the path on disk here: this is a
        cheap "have we ever completed setup" check, not a health check. A
        game dir that later moves/vanishes is caught by check_dependencies,
        not by the wizard gate.
        """
        return not config.get("game_dir")

    def detect_game_dirs(self) -> list[Path]:
        return find_game_dirs()

    def set_game_dir(self, path: Path) -> bool:
        """Validate and accept a candidate game dir. Returns whether accepted."""
        path = Path(path)
        if not is_valid_game_dir(path):
            return False
        self.game_dir = path
        return True

    def dependency_status(self) -> dict:
        return check_dependencies(self.game_dir)

    def deps_satisfied(self) -> bool:
        """True once every non-retired required dependency is present.

        Deliberately ignores dependency_status()["npv_inject"] — .NET/
        npv-inject is being retired (ADR 0001 / Branch A') and must not
        gate or be offered for install by the wizard.
        """
        status = self.dependency_status()
        return all(status.get(dep) for dep in REQUIRED_DEPS)

    def advance(self) -> None:
        if self.step_index < len(self.steps) - 1:
            self.step_index += 1

    def finish(self) -> None:
        config = load_config()
        config["game_dir"] = str(self.game_dir)
        save_config(config)
