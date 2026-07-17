"""Resolve external tools to absolute, existing paths (spec SEC-3).

Every external tool invocation must be handed an absolute, validated path
rather than a bare name resolved implicitly via PATH lookup inside
subprocess.Popen/execvp. Callers build an ordered candidate list (explicit
config path, cache locations, ...) and resolve_tool() falls back to a PATH
search by `name` only as a last resort, still returning an absolute path.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from .errors import ToolError


def resolve_tool(name: str, candidates: Iterable[Path]) -> Path:
    """Return an absolute, existing path for `name`.

    Checks `candidates` in order (skipping falsy/missing entries), then
    falls back to a PATH search for `name`. Raises ToolError if nothing
    resolves to an existing file.
    """
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c).resolve()
    which = shutil.which(name)
    if which:
        return Path(which).resolve()
    raise ToolError(
        f"{name}: executable not found.",
        tool=name,
        remediation=f"Install {name} or configure its path in settings.",
    )
