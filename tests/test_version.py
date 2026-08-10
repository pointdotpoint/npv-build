import re
import tomllib
from pathlib import Path

import npv_build


def test_package_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", npv_build.__version__), npv_build.__version__


def test_pyproject_version_matches_package():
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == npv_build.__version__
