"""Owned currentness and projection policy for intervention preparation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..records import ArtifactRef, TargetComparison, TargetSnapshot
from ..targets import TargetPolicy
from .records import (
    CandidateSnapshot,
    ImplementationResult,
    InterventionImplementationRequest,
    InterventionSpec,
)


@dataclass(frozen=True, slots=True)
class InterventionPolicy:
    """Canonical candidate-only policy; it has no application operation."""

    def __post_init__(self) -> None:
        if type(self) is not InterventionPolicy:
            raise ValueError("intervention policy changes require a versioned contract")

    @staticmethod
    def require_current(
        intervention: InterventionSpec,
        current_snapshot: TargetSnapshot,
    ) -> TargetComparison:
        if not isinstance(intervention, InterventionSpec):
            raise TypeError("intervention currentness requires an InterventionSpec")
        if not isinstance(current_snapshot, TargetSnapshot):
            raise TypeError("intervention currentness requires a TargetSnapshot")
        return TargetPolicy().require_current(intervention.baseline, current_snapshot)

    @staticmethod
    def candidate(
        *,
        request: InterventionImplementationRequest,
        snapshot: TargetSnapshot,
        artifacts: Sequence[ArtifactRef] = (),
    ) -> CandidateSnapshot:
        return CandidateSnapshot.prepared(
            request=request,
            snapshot=snapshot,
            artifacts=artifacts,
        )

    @staticmethod
    def result(candidate: CandidateSnapshot) -> ImplementationResult:
        return ImplementationResult.prepared(candidate)
