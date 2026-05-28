import os
import sys
from pathlib import Path
import tomli_w
try:
    import tomllib
except ImportError:
    import tomli as tomllib

def get_config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if not base:
            base = os.path.expanduser("~")
        return Path(base) / "npv"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        if not base:
            base = os.path.expanduser("~/.config")
        return Path(base) / "npv"

def get_cache_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = os.path.expanduser("~")
        return Path(base) / "npv"
    else:
        base = os.environ.get("XDG_CACHE_HOME")
        if not base:
            base = os.path.expanduser("~/.cache")
        return Path(base) / "npv"

def load_config() -> dict:
    config_path = get_config_dir() / "config.toml"
    if not config_path.exists():
        return {}
    with open(config_path, "rb") as f:
        return tomllib.load(f)

def save_config(config: dict):
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    with open(config_path, "wb") as f:
        tomli_w.dump(config, f)
