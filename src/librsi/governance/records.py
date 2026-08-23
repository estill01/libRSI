"""Identity-bound requirements and authorities for governed application."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from ..interventions import CandidateSnapshot
from ..records import RecordRef, SemanticRecord, TargetSnapshot, register_record_type


def _text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ApplicationGovernanceRequirement(SemanticRecord):
    """A target-bound requirement that application present a typed authority."""

    RECORD_TYPE: ClassVar[str] = "application_governance_requirement"

    requirement_id: str
    authority_record_type: str
    target_snapshot: TargetSnapshot
    governing_refs: tuple[RecordRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_id",
            _text(self.requirement_id, "governance requirement id"),
        )
        object.__setattr__(
            self,
            "authority_record_type",
            _text(self.authority_record_type, "governance authority record type"),
        )
        if type(self.target_snapshot) is not TargetSnapshot:
            raise TypeError("application governance requires an exact TargetSnapshot")
        if isinstance(self.governing_refs, (str, bytes, bytearray)) or not isinstance(
            self.governing_refs, Sequence
        ):
            raise TypeError("application governance references must be a sequence")
        refs = tuple(self.governing_refs)
        if not refs or any(not isinstance(item, RecordRef) for item in refs):
            raise TypeError("application governance requires typed governing references")
        if len(set(refs)) != len(refs):
            raise ValueError("application governance references must be unique")
        object.__setattr__(self, "governing_refs", refs)
        if tuple(self.lineage) != (self.target_snapshot.ref, *refs):
            raise ValueError("application governance requirement lineage is incomplete")
        super().__post_init__()


@dataclass(frozen=True, kw_only=True)
class ApplicationGovernanceAuthority(SemanticRecord):
    """Base contract for a canonical authority accepted by application workflows."""

    requirement: ApplicationGovernanceRequirement
    candidate: CandidateSnapshot
    current_snapshot: TargetSnapshot

    def __post_init__(self) -> None:
        if type(self.requirement) is not ApplicationGovernanceRequirement:
            raise TypeError("application authority requires its exact governance requirement")
        if self.record_type != self.requirement.authority_record_type:
            raise ValueError("application authority has the wrong governed record type")
        if type(self.candidate) is not CandidateSnapshot:
            raise TypeError("application authority requires an exact CandidateSnapshot")
        if type(self.current_snapshot) is not TargetSnapshot:
            raise TypeError("application authority requires an exact current TargetSnapshot")
        if (
            self.candidate.request.intervention.baseline != self.requirement.target_snapshot
            or self.current_snapshot != self.requirement.target_snapshot
        ):
            raise ValueError("application authority does not cover the governed target baseline")
        required = {self.requirement.ref, self.candidate.ref, self.current_snapshot.ref}
        if not required.issubset(self.lineage):
            raise ValueError("application authority lineage is incomplete")
        super().__post_init__()
