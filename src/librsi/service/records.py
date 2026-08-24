"""Operational records for the transport-independent service projection."""

from __future__ import annotations

from dataclasses import dataclass

SERVICE_SCHEMA = "librsi.service/v1"
SERVICE_SCHEMA_VERSION = 1


def _positive_integer(value: int, label: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


@dataclass(frozen=True)
class ServiceLimits:
    """Process-local operational limits that never enter semantic identity."""

    max_managed_actions: int = 100
    max_query_results: int = 100
    max_request_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_managed_actions",
            _positive_integer(self.max_managed_actions, "managed action limit"),
        )
        object.__setattr__(
            self,
            "max_query_results",
            _positive_integer(self.max_query_results, "knowledge query limit"),
        )
        object.__setattr__(
            self,
            "max_request_bytes",
            _positive_integer(self.max_request_bytes, "request byte limit"),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "max_managed_actions": self.max_managed_actions,
            "max_query_results": self.max_query_results,
            "max_request_bytes": self.max_request_bytes,
        }


@dataclass(frozen=True)
class ManagedBounds:
    """Explicit authority-neutral bound for one managed service invocation."""

    max_actions: int
    allow_application: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_actions",
            _positive_integer(self.max_actions, "managed invocation action limit"),
        )
        if type(self.allow_application) is not bool:
            raise TypeError("managed application authority must be a boolean")


@dataclass(frozen=True)
class ManagedExecution:
    """Non-semantic report for one bounded pass over canonical pending actions."""

    run_id: str
    stop_reason: str
    executed_action_roots: tuple[str, ...]
    terminal: bool
    status: str
    state_root: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.run_id, "managed run id"),
            (self.stop_reason, "managed stop reason"),
            (self.status, "managed status"),
            (self.state_root, "managed state root"),
        ):
            if type(value) is not str or not value.strip():
                raise ValueError(f"{label} is required")
        roots = tuple(self.executed_action_roots)
        if any(
            type(item) is not str
            or len(item) != 64
            or any(character not in "0123456789abcdef" for character in item)
            for item in roots
        ):
            raise ValueError("managed execution action roots must be canonical roots")
        if type(self.terminal) is not bool:
            raise TypeError("managed terminal flag must be a boolean")
        object.__setattr__(self, "executed_action_roots", roots)

    def to_dict(self) -> dict[str, object]:
        return {
            "$schema": SERVICE_SCHEMA,
            "schema_version": SERVICE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "stop_reason": self.stop_reason,
            "executed_action_roots": list(self.executed_action_roots),
            "terminal": self.terminal,
            "status": self.status,
            "state_root": self.state_root,
        }
