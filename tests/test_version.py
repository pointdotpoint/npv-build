import tomllib
from pathlib import Path

import npv_build


def test_package_version_is_current_release():
    assert npv_build.__version__ == "2.0.2"


def test_pyproject_version_matches_package():
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == npv_build.__version__
