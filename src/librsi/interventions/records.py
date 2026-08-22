"""Canonical records for intervention-to-candidate preparation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from ..epistemics import EVIDENCE_RELATIONSHIPS
from ..identity import FrozenMap
from ..records import (
    ArtifactRef,
    Candidate,
    Constraint,
    Evidence,
    EvidenceRef,
    Intervention,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    register_record_type,
)
from ..runtime import Action, Run, RunBudget

CANDIDATE_PREPARATION_STATUSES = frozenset({"prepared"})
IMPLEMENTATION_DISPOSITIONS = frozenset({"prepared"})
IMPLEMENTATION_CAPABILITY_FAMILY = "implementer"
IMPLEMENTATION_AUTHORITY = "candidate-only"
IMPLEMENT_INTERVENTION_ACTION_KIND = "implement-intervention"


def _require_text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _texts(
    value: Sequence[str],
    label: str,
    *,
    required: bool = False,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of text values")
    items = tuple(_require_text(item, label) for item in value)
    if required and not items:
        raise ValueError(f"{label} cannot be empty")
    if len(set(items)) != len(items):
        raise ValueError(f"{label} must be unique")
    return items


def _refs(
    value: Sequence[RecordRef],
    label: str,
    *,
    required: bool = False,
) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of RecordRef values")
    items = tuple(value)
    if any(not isinstance(item, RecordRef) for item in items):
        raise TypeError(f"{label} must contain RecordRef values")
    if required and not items:
        raise ValueError(f"{label} cannot be empty")
    if len(set(items)) != len(items):
        raise ValueError(f"{label} must be unique")
    return items


def _evidence(value: Sequence[Evidence]) -> tuple[Evidence, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("intervention evidence must be a sequence of Evidence values")
    items = tuple(sorted(value, key=lambda item: item.root if isinstance(item, Evidence) else ""))
    if any(not isinstance(item, Evidence) for item in items):
        raise TypeError("intervention evidence must contain Evidence values")
    if not items:
        raise ValueError("interventions require current supporting evidence")
    if len({item.ref for item in items}) != len(items):
        raise ValueError("intervention evidence must be unique")
    return items


def _constraints(value: Sequence[Constraint]) -> tuple[Constraint, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("intervention constraints must be a sequence")
    items = tuple(value)
    if any(not isinstance(item, Constraint) for item in items):
        raise TypeError("intervention constraints must contain Constraint records")
    if len({item.ref for item in items}) != len(items):
        raise ValueError("intervention constraints must be unique")
    return items


def _artifacts(value: Sequence[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("candidate artifacts must be a sequence")
    items = tuple(value)
    if any(not isinstance(item, ArtifactRef) for item in items):
        raise TypeError("candidate artifacts must contain ArtifactRef records")
    if len({item.ref for item in items}) != len(items):
        raise ValueError("candidate artifacts must be unique")
    return items


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InterventionSpec(SemanticRecord):
    """Universal intervention envelope with domain data isolated in specification."""

    RECORD_TYPE: ClassVar[str] = "intervention_spec"

    intervention_id: str
    baseline: TargetSnapshot
    kind: str
    specification: Mapping[str, Any]
    rationale: tuple[str, ...]
    supporting_refs: tuple[RecordRef, ...]
    evidence: tuple[Evidence, ...]
    expected_effects: Mapping[str, Any]
    risks: tuple[str, ...]
    constraints: tuple[Constraint, ...]
    validation_plan: Mapping[str, Any]
    rollback_expectations: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "intervention_id",
            _require_text(self.intervention_id, "intervention id"),
        )
        if not isinstance(self.baseline, TargetSnapshot):
            raise TypeError("intervention specifications require a baseline TargetSnapshot")
        object.__setattr__(self, "kind", _require_text(self.kind, "intervention kind"))
        specification = FrozenMap(self.specification)
        if not specification:
            raise ValueError("intervention specification cannot be empty")
        object.__setattr__(self, "specification", specification)
        object.__setattr__(
            self,
            "rationale",
            _texts(self.rationale, "intervention rationale", required=True),
        )
        supporting = _refs(
            self.supporting_refs,
            "intervention supporting references",
            required=True,
        )
        object.__setattr__(self, "supporting_refs", supporting)
        evidence = _evidence(self.evidence)
        for item in evidence:
            if item.target_snapshot != self.baseline:
                raise ValueError("intervention evidence is stale or target-mismatched")
            if not item.source_refs:
                raise ValueError("intervention evidence requires exact provenance")
            if item.evidence_type not in EVIDENCE_RELATIONSHIPS:
                raise ValueError("intervention evidence relationship is unsupported")
            if item.weight is None:
                raise ValueError("intervention evidence requires an explicit weight")
            if not item.subject_refs or not set(item.subject_refs).issubset(supporting):
                raise ValueError("intervention evidence must cite its supporting rationale")
        object.__setattr__(self, "evidence", evidence)
        expected_effects = FrozenMap(self.expected_effects)
        if not expected_effects:
            raise ValueError("intervention expected effects cannot be empty")
        object.__setattr__(self, "expected_effects", expected_effects)
        object.__setattr__(
            self,
            "risks",
            _texts(self.risks, "intervention risks", required=True),
        )
        constraints = _constraints(self.constraints)
        for constraint in constraints:
            if constraint.target is not None and constraint.target != self.baseline.target:
                raise ValueError("intervention constraint belongs to another target")
        object.__setattr__(self, "constraints", constraints)
        validation_plan = FrozenMap(self.validation_plan)
        if not validation_plan:
            raise ValueError("intervention validation plan cannot be empty")
        object.__setattr__(self, "validation_plan", validation_plan)
        rollback = FrozenMap(self.rollback_expectations)
        if not rollback:
            raise ValueError("intervention rollback expectations cannot be empty")
        object.__setattr__(self, "rollback_expectations", rollback)
        expected_lineage = (
            self.baseline.ref,
            *supporting,
            *(item.ref for item in evidence),
            *(item.ref for item in constraints),
        )
        if _refs(self.lineage, "intervention specification lineage") != expected_lineage:
            raise ValueError("intervention specification lineage is incomplete")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        intervention_id: str,
        baseline: TargetSnapshot,
        kind: str,
        specification: Mapping[str, Any],
        rationale: Sequence[str],
        supporting_refs: Sequence[RecordRef],
        evidence: Sequence[Evidence],
        expected_effects: Mapping[str, Any],
        risks: Sequence[str],
        constraints: Sequence[Constraint],
        validation_plan: Mapping[str, Any],
        rollback_expectations: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> InterventionSpec:
        supporting = _refs(
            supporting_refs,
            "intervention supporting references",
            required=True,
        )
        evidence_items = _evidence(evidence)
        constraint_items = _constraints(constraints)
        return cls(
            intervention_id=intervention_id,
            baseline=baseline,
            kind=kind,
            specification=specification,
            rationale=tuple(rationale),
            supporting_refs=supporting,
            evidence=evidence_items,
            expected_effects=expected_effects,
            risks=tuple(risks),
            constraints=constraint_items,
            validation_plan=validation_plan,
            rollback_expectations=rollback_expectations,
            lineage=(
                baseline.ref,
                *supporting,
                *(item.ref for item in evidence_items),
                *(item.ref for item in constraint_items),
            ),
            metadata=FrozenMap(metadata),
        )

    def canonical_run(self) -> Run:
        return Run(
            run_id=f"{self.intervention_id}:implementation",
            intent=self.ref,
            target_snapshot=self.baseline,
            budget=RunBudget(max_actions=1, max_failures=1, max_retries=0),
            lineage=(self.ref,),
        )

    def to_intervention(self) -> Intervention:
        """Project to the stable low-level Intervention compatibility record."""

        return Intervention(
            target=self.baseline.target,
            kind=self.kind,
            specification=self.specification,
            rationale={
                "statements": self.rationale,
                "supporting_refs": tuple(item.to_dict() for item in self.supporting_refs),
                "evidence_refs": tuple(item.evidence_ref.to_dict() for item in self.evidence),
            },
            expected_effects={
                "effects": self.expected_effects,
                "risks": self.risks,
                "rollback": self.rollback_expectations,
            },
            constraints=self.constraints,
            validation_plan=self.validation_plan,
            lineage=(self.ref, *self.lineage),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InterventionImplementationRequest(SemanticRecord):
    """Exact candidate-only implementation request for one current baseline."""

    RECORD_TYPE: ClassVar[str] = "intervention_implementation_request"

    intervention: InterventionSpec
    candidate_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.intervention, InterventionSpec):
            raise TypeError("implementation requests require an InterventionSpec")
        object.__setattr__(self, "candidate_id", _require_text(self.candidate_id, "candidate id"))
        expected_lineage = (
            self.intervention.ref,
            self.intervention.baseline.ref,
            *(item.ref for item in self.intervention.evidence),
        )
        if _refs(self.lineage, "implementation request lineage") != expected_lineage:
            raise ValueError("implementation request lineage is incomplete")
        super().__post_init__()

    @classmethod
    def for_intervention(
        cls,
        intervention: InterventionSpec,
        *,
        candidate_id: str,
    ) -> InterventionImplementationRequest:
        if not isinstance(intervention, InterventionSpec):
            raise TypeError("implementation requests require an InterventionSpec")
        return cls(
            intervention=intervention,
            candidate_id=candidate_id,
            lineage=(
                intervention.ref,
                intervention.baseline.ref,
                *(item.ref for item in intervention.evidence),
            ),
        )

    def canonical_action(self) -> Action:
        """Return the sole exact candidate-preparation action for this request."""

        run = self.intervention.canonical_run()
        return Action(
            run=run.ref,
            action_id=f"implement-intervention-{self.candidate_id}",
            kind=IMPLEMENT_INTERVENTION_ACTION_KIND,
            input_refs=(self.ref, *self.lineage),
            payload={"request": self.to_dict()},
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class CandidateSnapshot(SemanticRecord):
    """Prospective target state produced without authoritative application."""

    RECORD_TYPE: ClassVar[str] = "candidate_snapshot"

    request: InterventionImplementationRequest
    snapshot: TargetSnapshot
    status: str = "prepared"
    evidence_refs: tuple[EvidenceRef, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.request, InterventionImplementationRequest):
            raise TypeError("candidate snapshots require their implementation request")
        if not isinstance(self.snapshot, TargetSnapshot):
            raise TypeError("candidate snapshots require a prospective TargetSnapshot")
        baseline = self.request.intervention.baseline
        if self.snapshot.target != baseline.target:
            raise ValueError("candidate snapshot belongs to another target")
        if self.snapshot == baseline:
            raise ValueError("candidate snapshot must differ from the authoritative baseline")
        status = _require_text(self.status, "candidate status")
        if status not in CANDIDATE_PREPARATION_STATUSES:
            raise ValueError(f"unsupported candidate preparation status: {status}")
        object.__setattr__(self, "status", status)
        expected_evidence = tuple(
            EvidenceRef.from_evidence(item) for item in self.request.intervention.evidence
        )
        supplied = tuple(self.evidence_refs)
        if supplied != expected_evidence:
            raise ValueError("candidate evidence must match the intervention rationale exactly")
        object.__setattr__(self, "evidence_refs", supplied)
        artifacts = _artifacts(self.artifacts)
        object.__setattr__(self, "artifacts", artifacts)
        expected_lineage = (
            self.request.ref,
            self.request.intervention.ref,
            baseline.ref,
            self.snapshot.ref,
            *expected_evidence,
            *(item.ref for item in artifacts),
        )
        if _refs(self.lineage, "candidate snapshot lineage") != expected_lineage:
            raise ValueError("candidate snapshot lineage is incomplete")
        super().__post_init__()

    @classmethod
    def prepared(
        cls,
        *,
        request: InterventionImplementationRequest,
        snapshot: TargetSnapshot,
        artifacts: Sequence[ArtifactRef] = (),
    ) -> CandidateSnapshot:
        if not isinstance(request, InterventionImplementationRequest):
            raise TypeError("candidate snapshots require an implementation request")
        evidence_refs = tuple(
            EvidenceRef.from_evidence(item) for item in request.intervention.evidence
        )
        artifact_items = _artifacts(artifacts)
        return cls(
            request=request,
            snapshot=snapshot,
            status="prepared",
            evidence_refs=evidence_refs,
            artifacts=artifact_items,
            lineage=(
                request.ref,
                request.intervention.ref,
                request.intervention.baseline.ref,
                snapshot.ref,
                *evidence_refs,
                *(item.ref for item in artifact_items),
            ),
        )

    def to_candidate(self) -> Candidate:
        return Candidate(
            intervention=self.request.intervention.to_intervention().ref,
            target_snapshot=self.snapshot,
            status="prepared",
            artifacts=self.artifacts,
            lineage=(self.ref, self.request.intervention.ref, *self.evidence_refs),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ImplementationResult(SemanticRecord):
    """Successful implementer output; authoritative target remains the baseline."""

    RECORD_TYPE: ClassVar[str] = "implementation_result"

    request: InterventionImplementationRequest
    disposition: str
    candidate: CandidateSnapshot
    authoritative_snapshot: TargetSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.request, InterventionImplementationRequest):
            raise TypeError("implementation results require their exact request")
        disposition = _require_text(self.disposition, "implementation disposition")
        if disposition not in IMPLEMENTATION_DISPOSITIONS:
            raise ValueError(f"unsupported implementation disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        if not isinstance(self.candidate, CandidateSnapshot):
            raise TypeError("implementation results require a CandidateSnapshot")
        if self.candidate.request != self.request:
            raise ValueError("implementation candidate does not answer the exact request")
        if (
            not isinstance(self.authoritative_snapshot, TargetSnapshot)
            or self.authoritative_snapshot != self.request.intervention.baseline
        ):
            raise ValueError("candidate implementation cannot replace authoritative target state")
        expected_lineage = (
            self.request.ref,
            self.candidate.ref,
            self.authoritative_snapshot.ref,
            self.candidate.snapshot.ref,
            *self.candidate.evidence_refs,
            *(item.ref for item in self.candidate.artifacts),
        )
        if _refs(self.lineage, "implementation result lineage") != expected_lineage:
            raise ValueError("implementation result lineage is incomplete")
        super().__post_init__()

    @classmethod
    def prepared(
        cls,
        candidate: CandidateSnapshot,
    ) -> ImplementationResult:
        if not isinstance(candidate, CandidateSnapshot):
            raise TypeError("implementation results require a CandidateSnapshot")
        request = candidate.request
        baseline = request.intervention.baseline
        return cls(
            request=request,
            disposition="prepared",
            candidate=candidate,
            authoritative_snapshot=baseline,
            lineage=(
                request.ref,
                candidate.ref,
                baseline.ref,
                candidate.snapshot.ref,
                *candidate.evidence_refs,
                *(item.ref for item in candidate.artifacts),
            ),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ImplementationHandoff(SemanticRecord):
    """Complete external handoff when no local Implementer is supplied."""

    RECORD_TYPE: ClassVar[str] = "implementation_handoff"

    request: InterventionImplementationRequest
    action: Action
    capability_family: str = IMPLEMENTATION_CAPABILITY_FAMILY
    authority: str = IMPLEMENTATION_AUTHORITY
    expected_output_record_type: str = ImplementationResult.RECORD_TYPE

    def __post_init__(self) -> None:
        if not isinstance(self.request, InterventionImplementationRequest):
            raise TypeError("implementation handoffs require an exact request")
        if not isinstance(self.action, Action):
            raise TypeError("implementation handoffs require an Action")
        if self.action != self.request.canonical_action():
            raise ValueError("implementation handoff action is not canonically request-derived")
        if (
            _require_text(self.capability_family, "implementation handoff capability")
            != IMPLEMENTATION_CAPABILITY_FAMILY
        ):
            raise ValueError("implementation handoff capability must be implementer")
        if (
            _require_text(self.authority, "implementation handoff authority")
            != IMPLEMENTATION_AUTHORITY
        ):
            raise ValueError("implementation handoff authority must remain candidate-only")
        if (
            _require_text(
                self.expected_output_record_type,
                "implementation handoff output type",
            )
            != ImplementationResult.RECORD_TYPE
        ):
            raise ValueError("implementation handoff output type has drifted")
        expected_lineage = (
            self.request.ref,
            self.action.ref,
            self.request.intervention.ref,
            self.request.intervention.baseline.ref,
        )
        if _refs(self.lineage, "implementation handoff lineage") != expected_lineage:
            raise ValueError("implementation handoff lineage is incomplete")
        super().__post_init__()
