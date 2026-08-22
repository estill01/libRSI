"""Canonical records for claim-only validation workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from ..epistemics import EVIDENCE_RELATIONSHIPS, EpistemicPolicy
from ..identity import FrozenMap
from ..records import (
    BeliefState,
    Claim,
    Evidence,
    EvidenceRef,
    RecordRef,
    SemanticRecord,
    TargetRef,
    TargetSnapshot,
    register_record_type,
)
from ..runtime import Run, RunBudget

VALIDATION_DISPOSITIONS = frozenset({"supported", "contradicted", "bounded", "inconclusive"})
VALIDATION_BATCH_DISPOSITIONS = frozenset({"collected", "unavailable"})


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _positive_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _refs(value: Sequence[RecordRef], label: str) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of RecordRef values")
    refs = tuple(value)
    if any(not isinstance(item, RecordRef) for item in refs):
        raise TypeError(f"{label} must contain RecordRef values")
    if len(set(refs)) != len(refs):
        raise ValueError(f"{label} must be unique")
    return refs


def _evidence_refs(value: Sequence[EvidenceRef | RecordRef], label: str) -> tuple[EvidenceRef, ...]:
    refs = _refs(value, label)
    evidence_refs: list[EvidenceRef] = []
    for item in refs:
        if isinstance(item, EvidenceRef):
            evidence_refs.append(item)
        elif item.record_type == "evidence":
            evidence_refs.append(EvidenceRef(item.root))
        else:
            raise TypeError(f"{label} must contain EvidenceRef values")
    return tuple(evidence_refs)


def _texts(value: Sequence[str], label: str, *, required: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of text values")
    result = tuple(_require_text(item, label) for item in value)
    if required and not result:
        raise ValueError(f"{label} cannot be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must be unique")
    return result


def _evidence_items(value: Sequence[Evidence], label: str) -> tuple[Evidence, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of Evidence values")
    result = tuple(value)
    if any(not isinstance(item, Evidence) for item in result):
        raise TypeError(f"{label} must contain Evidence values")
    if len({item.ref for item in result}) != len(result):
        raise ValueError(f"{label} must be unique")
    return result


def _validate_evidence(
    validation: ValidationRequest,
    evidence: Evidence,
    *,
    accepted_types: frozenset[str] | None = None,
) -> None:
    if validation.claim.ref not in evidence.subject_refs:
        raise ValueError("validation evidence must identify the exact claim")
    if not evidence.source_refs:
        raise ValueError("validation evidence requires exact provenance")
    allowed = frozenset(validation.evidence_types) if accepted_types is None else accepted_types
    if evidence.evidence_type not in allowed:
        raise ValueError("validation evidence type is not accepted by the request")
    if evidence.weight is None:
        raise ValueError("validation evidence requires an explicit weight")
    if validation.target_snapshot is not None:
        if evidence.target_snapshot != validation.target_snapshot:
            raise ValueError("validation evidence is stale or bound to another target snapshot")
    elif evidence.target_snapshot is not None:
        raise ValueError("unbound validation cannot accept target-bound evidence")
    EpistemicPolicy().aggregate(
        subject=validation.claim,
        evidence=(evidence,),
        current_snapshot=validation.target_snapshot,
    )


def classify_validation(belief: BeliefState, evidence: Sequence[Evidence]) -> str:
    """Project belief/evidence into one public validation disposition."""

    if not isinstance(belief, BeliefState):
        raise TypeError("validation classification requires a BeliefState")
    items = _evidence_items(evidence, "validation classification evidence")
    relationships = {item.evidence_type for item in items if item.evidence_type != "null"}
    if relationships & {"boundary", "confounder"} or {
        "support",
        "counterexample",
    }.issubset(relationships):
        return "bounded"
    if belief.status == "supported":
        return "supported"
    if belief.status == "rejected":
        return "contradicted"
    return "inconclusive"


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ValidationRequest(SemanticRecord):
    """Claim-only validation intent with exact currentness and bounded work."""

    RECORD_TYPE: ClassVar[str] = "validation_request"

    validation_id: str
    claim: Claim
    target_snapshot: TargetSnapshot | None = None
    evidence_types: tuple[str, ...] = tuple(sorted(EVIDENCE_RELATIONSHIPS))
    max_evidence_actions: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "validation_id", _require_text(self.validation_id, "validation id")
        )
        if not isinstance(self.claim, Claim):
            raise TypeError("validation requests require a Claim")
        if self.claim.target is None:
            if self.target_snapshot is not None:
                raise ValueError("unbound claims cannot use a target snapshot")
        elif not isinstance(self.target_snapshot, TargetSnapshot):
            raise ValueError("target-bound validation requires a current TargetSnapshot")
        elif self.target_snapshot.target != self.claim.target:
            raise ValueError("validation target snapshot does not match the claim target")
        evidence_types = _texts(self.evidence_types, "validation evidence types", required=True)
        if any(item not in EVIDENCE_RELATIONSHIPS for item in evidence_types):
            raise ValueError("validation request has an unsupported evidence type")
        object.__setattr__(self, "evidence_types", tuple(sorted(evidence_types)))
        object.__setattr__(
            self,
            "max_evidence_actions",
            _positive_int(self.max_evidence_actions, "maximum evidence actions"),
        )
        expected_lineage = (self.claim.ref,) + (
            () if self.target_snapshot is None else (self.target_snapshot.ref,)
        )
        if _refs(self.lineage, "validation request lineage") != expected_lineage:
            raise ValueError("validation request lineage must retain its claim and snapshot")
        super().__post_init__()

    @classmethod
    def for_claim(
        cls,
        *,
        validation_id: str,
        claim: Claim,
        target_snapshot: TargetSnapshot | None = None,
        evidence_types: Sequence[str] = tuple(sorted(EVIDENCE_RELATIONSHIPS)),
        max_evidence_actions: int = 1,
        metadata: Mapping[str, Any] | None = None,
    ) -> ValidationRequest:
        if not isinstance(claim, Claim):
            raise TypeError("validation requests require a Claim")
        lineage = (claim.ref,) + (() if target_snapshot is None else (target_snapshot.ref,))
        return cls(
            validation_id=validation_id,
            claim=claim,
            target_snapshot=target_snapshot,
            evidence_types=tuple(evidence_types),
            max_evidence_actions=max_evidence_actions,
            lineage=lineage,
            metadata=FrozenMap(metadata),
        )

    def canonical_run(self) -> Run:
        """Return the one runtime authority envelope derived from this request."""

        return Run(
            run_id=self.validation_id,
            intent=self.claim.ref,
            target_snapshot=self.target_snapshot,
            budget=RunBudget(
                max_actions=self.max_evidence_actions,
                max_failures=self.max_evidence_actions,
                max_retries=0,
            ),
            lineage=(self.ref,),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ValidationEvidenceRequest(SemanticRecord):
    """Smallest explicit evidence gap emitted by a validation run."""

    RECORD_TYPE: ClassVar[str] = "validation_evidence_request"

    validation: ValidationRequest
    sequence: int
    known_evidence_refs: tuple[EvidenceRef, ...] = ()
    gaps: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.validation, ValidationRequest):
            raise TypeError("evidence requests require a ValidationRequest")
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "request sequence"))
        known = _evidence_refs(self.known_evidence_refs, "known validation evidence references")
        object.__setattr__(self, "known_evidence_refs", tuple(sorted(known, key=lambda x: x.root)))
        object.__setattr__(
            self, "gaps", _texts(self.gaps, "validation evidence gaps", required=True)
        )
        expected_lineage = (
            self.validation.ref,
            *self.validation.lineage,
            *self.known_evidence_refs,
        )
        if _refs(self.lineage, "validation evidence request lineage") != expected_lineage:
            raise ValueError("evidence request lineage must retain validation and known evidence")
        super().__post_init__()

    @classmethod
    def for_gaps(
        cls,
        *,
        validation: ValidationRequest,
        sequence: int,
        known_evidence_refs: Sequence[EvidenceRef],
        gaps: Sequence[str],
    ) -> ValidationEvidenceRequest:
        known = tuple(
            sorted(
                _evidence_refs(known_evidence_refs, "known validation evidence references"),
                key=lambda item: item.root,
            )
        )
        return cls(
            validation=validation,
            sequence=sequence,
            known_evidence_refs=known,
            gaps=tuple(gaps),
            lineage=(validation.ref, *validation.lineage, *known),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ValidationEvidenceBatch(SemanticRecord):
    """Exact evidence returned for one gap request, or explicit unavailability."""

    RECORD_TYPE: ClassVar[str] = "validation_evidence_batch"

    request: ValidationEvidenceRequest
    disposition: str
    evidence: tuple[Evidence, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, ValidationEvidenceRequest):
            raise TypeError("validation evidence batches require their exact request")
        disposition = _require_text(self.disposition, "evidence batch disposition")
        if disposition not in VALIDATION_BATCH_DISPOSITIONS:
            raise ValueError(f"unsupported evidence batch disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        evidence = tuple(
            sorted(
                _evidence_items(self.evidence, "validation batch evidence"), key=lambda x: x.root
            )
        )
        for item in evidence:
            _validate_evidence(self.request.validation, item)
        object.__setattr__(self, "evidence", evidence)
        if disposition == "collected":
            if not evidence:
                raise ValueError("collected evidence batches cannot be empty")
            if self.reason is not None:
                raise ValueError("collected evidence batches cannot contain an unavailable reason")
        else:
            if evidence:
                raise ValueError("unavailable evidence batches cannot contain evidence")
            if self.reason is None:
                raise ValueError("unavailable evidence batches require a reason")
            object.__setattr__(self, "reason", _require_text(self.reason, "unavailable reason"))
        expected_lineage = (
            self.request.ref,
            *self.request.lineage,
            *(item.ref for item in evidence),
        )
        if _refs(self.lineage, "validation evidence batch lineage") != expected_lineage:
            raise ValueError("evidence batch lineage must retain request and evidence")
        super().__post_init__()

    @classmethod
    def collected(
        cls,
        *,
        request: ValidationEvidenceRequest,
        evidence: Sequence[Evidence],
    ) -> ValidationEvidenceBatch:
        items = tuple(
            sorted(
                _evidence_items(evidence, "validation batch evidence"),
                key=lambda item: item.root,
            )
        )
        return cls(
            request=request,
            disposition="collected",
            evidence=items,
            lineage=(request.ref, *request.lineage, *(item.ref for item in items)),
        )

    @classmethod
    def unavailable(
        cls, *, request: ValidationEvidenceRequest, reason: str
    ) -> ValidationEvidenceBatch:
        return cls(
            request=request,
            disposition="unavailable",
            reason=reason,
            lineage=(request.ref, *request.lineage),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ValidationResult(SemanticRecord):
    """Consumable validation conclusion with complete evidence provenance."""

    RECORD_TYPE: ClassVar[str] = "validation_result"

    validation: ValidationRequest
    run: RecordRef
    disposition: str
    belief: BeliefState
    evidence: tuple[Evidence, ...] = ()
    reused_evidence_refs: tuple[EvidenceRef, ...] = ()
    gathered_evidence_refs: tuple[EvidenceRef, ...] = ()
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.validation, ValidationRequest):
            raise TypeError("validation results require a ValidationRequest")
        if not isinstance(self.run, RecordRef) or self.run.record_type != "run":
            raise TypeError("validation results must reference their exact Run")
        if self.run != self.validation.canonical_run().ref:
            raise ValueError("validation results must reference the canonical request Run")
        disposition = _require_text(self.disposition, "validation disposition")
        if disposition not in VALIDATION_DISPOSITIONS:
            raise ValueError(f"unsupported validation disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        if not isinstance(self.belief, BeliefState):
            raise TypeError("validation results require a BeliefState")
        if self.belief.subject_ref != self.validation.claim.ref:
            raise ValueError("validation belief does not identify the exact claim")
        if self.belief.target_snapshot != self.validation.target_snapshot:
            raise ValueError("validation belief does not retain target currentness")
        evidence = tuple(
            sorted(
                _evidence_items(self.evidence, "validation result evidence"), key=lambda x: x.root
            )
        )
        for item in evidence:
            _validate_evidence(self.validation, item)
        refs = tuple(EvidenceRef.from_evidence(item) for item in evidence)
        if self.belief.evidence_refs != refs:
            raise ValueError("validation belief does not cite the exact result evidence")
        canonical_belief = (
            EpistemicPolicy().initial(
                self.validation.claim,
                target_snapshot=self.validation.target_snapshot,
            )
            if not evidence
            else EpistemicPolicy().aggregate(
                subject=self.validation.claim,
                evidence=evidence,
                current_snapshot=self.validation.target_snapshot,
            )
        )
        if self.belief != canonical_belief:
            raise ValueError("validation belief is not the canonical evidence-derived state")
        object.__setattr__(self, "evidence", evidence)
        reused = tuple(
            sorted(
                _evidence_refs(self.reused_evidence_refs, "reused evidence references"),
                key=lambda x: x.root,
            )
        )
        gathered = tuple(
            sorted(
                _evidence_refs(self.gathered_evidence_refs, "gathered evidence references"),
                key=lambda x: x.root,
            )
        )
        if set(reused) & set(gathered) or set((*reused, *gathered)) != set(refs):
            raise ValueError("reused and gathered evidence must exactly partition result evidence")
        object.__setattr__(self, "reused_evidence_refs", reused)
        object.__setattr__(self, "gathered_evidence_refs", gathered)
        expected_disposition = classify_validation(self.belief, evidence)
        if disposition != expected_disposition:
            raise ValueError("validation disposition is unsupported by its belief and evidence")
        unresolved = _texts(self.unresolved, "validation unresolved items")
        if disposition in {"bounded", "inconclusive"} and not unresolved:
            raise ValueError("bounded or inconclusive validation requires unresolved items")
        if disposition in {"supported", "contradicted"} and unresolved:
            raise ValueError("decisive validation cannot retain unresolved items")
        object.__setattr__(self, "unresolved", unresolved)
        expected_lineage = (
            self.validation.ref,
            self.run,
            self.belief.ref,
            *(item.ref for item in evidence),
        )
        if _refs(self.lineage, "validation result lineage") != expected_lineage:
            raise ValueError(
                "validation result lineage must retain request, run, belief, and evidence"
            )
        super().__post_init__()

    @property
    def subject_ref(self) -> RecordRef:
        return self.validation.claim.ref

    @property
    def target(self) -> TargetRef | None:
        return self.validation.claim.target

    @property
    def target_snapshot(self) -> TargetSnapshot | None:
        return self.validation.target_snapshot
