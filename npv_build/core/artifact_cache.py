"""Small content-addressed cache for deterministic intermediate artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

_SAFE_NAMESPACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class ArchiveFingerprint:
    resolved_path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class ToolFingerprint:
    resolved_path: str
    size: int
    mtime_ns: int


def _json_value(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported artifact-cache key value: {type(value).__name__}")


class ArtifactCache:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()

    @staticmethod
    def _validate_parts(namespace: str, suffix: str) -> None:
        if not _SAFE_NAMESPACE.fullmatch(namespace):
            raise ValueError(f"Unsafe cache namespace: {namespace!r}")
        if not _SAFE_SUFFIX.fullmatch(suffix):
            raise ValueError(f"Unsafe cache suffix: {suffix!r}")

    def path_for(self, namespace: str, key: object, suffix: str) -> Path:
        self._validate_parts(namespace, suffix)
        canonical = json.dumps(
            _json_value(key),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        path = self.root / namespace / digest[:2] / f"{digest}{suffix}"
        resolved_parent = path.parent.resolve()
        if self.root != resolved_parent and self.root not in resolved_parent.parents:
            raise ValueError("Derived cache path escaped its root")
        return path

    def load_json(self, namespace: str, key: object) -> dict | None:
        path = self.path_for(namespace, key, ".json")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            return None
        if not isinstance(value, dict):
            path.unlink(missing_ok=True)
            return None
        return value

    def save_json(self, namespace: str, key: object, value: dict) -> None:
        if not isinstance(value, dict):
            raise TypeError("ArtifactCache.save_json only accepts dictionaries")
        path = self.path_for(namespace, key, ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=".tmp-",
                suffix=".json",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(value, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
