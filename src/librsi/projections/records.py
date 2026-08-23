"""Typed, transport-neutral projection envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, TypeAlias

from ..identity import FrozenMap, digest
from ..improvement import ImprovementResult
from ..investigation import InvestigationResult
from ..records import Outcome, TargetSnapshot
from ..rsi import RSIResult
from ..runtime import Event
from ..validation import ValidationResult

ResultRecord: TypeAlias = ValidationResult | InvestigationResult | ImprovementResult | RSIResult

OUTCOME_PROJECTION_SCHEMA = "librsi.outcome-projection/v1"
EVENT_PROJECTION_SCHEMA = "librsi.event-projection/v1"
PROJECTION_SCHEMA_VERSION = 1


def _metadata(value: Mapping[str, Any]) -> FrozenMap:
    if not isinstance(value, Mapping):
        raise TypeError("projection metadata must be a mapping")
    return FrozenMap(value)


@dataclass(frozen=True, slots=True)
class OutcomeProjection:
    """Stable external envelope over one exact canonical workflow result."""

    SCHEMA: ClassVar[str] = OUTCOME_PROJECTION_SCHEMA
    SCHEMA_VERSION: ClassVar[int] = PROJECTION_SCHEMA_VERSION

    workflow: str
    result: ResultRecord
    outcome: Outcome
    metadata: Mapping[str, Any] = field(default_factory=FrozenMap, compare=False, repr=False)
    projection_root: str = field(init=False)

    def __post_init__(self) -> None:
        from .outcomes import outcome_for_result, workflow_for_result

        expected_workflow = workflow_for_result(self.result)
        if self.workflow != expected_workflow:
            raise ValueError("outcome projection workflow does not match its result type")
        expected_outcome = outcome_for_result(self.result)
        if type(self.outcome) is not Outcome or self.outcome != expected_outcome:
            raise ValueError("outcome projection is not the exact result-derived outcome")
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        object.__setattr__(self, "projection_root", digest(self.identity_data()))

    def identity_data(self) -> dict[str, object]:
        """Return identity-bearing fields; transport metadata is deliberately excluded."""

        return {
            "schema": self.SCHEMA,
            "schema_version": self.SCHEMA_VERSION,
            "workflow": self.workflow,
            "result_root": self.result.root,
            "outcome_root": self.outcome.root,
        }

    def require_current(self, snapshot: TargetSnapshot) -> None:
        """Reject a projection whose authoritative target snapshot is no longer current."""

        if type(snapshot) is not TargetSnapshot:
            raise TypeError("projection currentness requires an exact TargetSnapshot")
        if self.outcome.target_snapshot != snapshot:
            raise ValueError("outcome projection target snapshot is stale")


@dataclass(frozen=True, slots=True)
class EventProjection:
    """Stable external envelope over one append-only canonical runtime event."""

    SCHEMA: ClassVar[str] = EVENT_PROJECTION_SCHEMA
    SCHEMA_VERSION: ClassVar[int] = PROJECTION_SCHEMA_VERSION

    event: Event
    metadata: Mapping[str, Any] = field(default_factory=FrozenMap, compare=False, repr=False)
    projection_root: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.event) is not Event:
            raise TypeError("event projections require an exact canonical Event")
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        object.__setattr__(self, "projection_root", digest(self.identity_data()))

    def identity_data(self) -> dict[str, object]:
        """Return the stable event identity independently of transport metadata."""

        return {
            "schema": self.SCHEMA,
            "schema_version": self.SCHEMA_VERSION,
            "event_root": self.event.root,
            "run_root": self.event.run.root,
            "sequence": self.event.sequence,
        }


Projection: TypeAlias = OutcomeProjection | EventProjection
