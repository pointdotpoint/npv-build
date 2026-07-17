"""Typed error hierarchy for the npv-build pipeline (spec ERR-1).

Every error carries a user-facing message, an optional remediation hint,
and optional technical details. Frontends render user_message/remediation;
details go to the log.
"""

from __future__ import annotations

from collections.abc import Sequence


class NpvError(Exception):
    def __init__(
        self,
        user_message: str,
        *,
        remediation: str = "",
        details: str = "",
        module_name: str = "",
    ) -> None:
        self.user_message = user_message
        self.remediation = remediation
        self.details = details
        self.module_name = module_name
        super().__init__(user_message)

    def __str__(self) -> str:
        parts = [self.user_message]
        if self.details:
            parts.append(self.details)
        if self.remediation:
            parts.append(self.remediation)
        return "\n".join(parts)


class SaveFormatError(NpvError):
    pass


class UnsupportedPatchError(NpvError):
    pass


class MappingResolutionError(NpvError):
    pass


class ToolError(NpvError):
    def __init__(
        self,
        user_message: str,
        *,
        tool: str = "",
        argv: Sequence[str] = (),
        exit_code: int | None = None,
        **kwargs: str,
    ) -> None:
        self.tool = tool
        self.argv = list(argv)
        self.exit_code = exit_code
        super().__init__(user_message, **kwargs)


class ToolTimeoutError(ToolError):
    pass


class BakeVerificationError(NpvError):
    pass


class InstallError(NpvError):
    pass


class PackagingError(NpvError):
    pass


class SecurityError(NpvError):
    pass


class PipelineCancelled(NpvError):
    pass
