"""General claim/evidence semantics and replaceable belief aggregation.

This module owns epistemic interpretation only. Canonical record identity remains in
``records``; persistence, experiment execution, reasoner calls, and workflow control
remain outside this boundary.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast, runtime_checkable

from .models import EvidenceType
from .records import (
    BeliefState,
    Claim,
    Evidence,
    EvidenceRef,
    Hypothesis,
    RecordRef,
    TargetRef,
    TargetSnapshot,
)

ClaimKind = Literal[
    "behavioral",
    "causal",
    "capability",
    "invariant",
    "observational",
    "assumption",
]
BeliefStatus = Literal[
    "proposed",
    "testing",
    "supported",
    "weakened",
    "rejected",
    "inconclusive",
]
EvidenceRelationship = EvidenceType
EpistemicSubject = Claim | Hypothesis

STANDARD_CLAIM_KINDS = frozenset(
    {"behavioral", "causal", "capability", "invariant", "observational", "assumption"}
)
EVIDENCE_RELATIONSHIPS = frozenset({"support", "counterexample", "boundary", "confounder", "null"})
BELIEF_STATUSES = frozenset(
    {"proposed", "testing", "supported", "weakened", "rejected", "inconclusive"}
)


@runtime_checkable
class EvidenceAggregator(Protocol):
    """Replaceable policy for deriving typed belief state from exact evidence."""

    def aggregate(
        self,
        *,
        subject: EpistemicSubject,
        evidence: Sequence[Evidence],
        prior: BeliefState | None = None,
        current_snapshot: TargetSnapshot | None = None,
    ) -> BeliefState: ...


@dataclass(frozen=True)
class _AggregationInput:
    subject: EpistemicSubject
    evidence: tuple[Evidence, ...]
    prior: BeliefState
    target_snapshot: TargetSnapshot | None


def _probability(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{label} must be between zero and one")
    return result


def _subject_target(subject: EpistemicSubject) -> TargetRef | None:
    if not isinstance(subject, (Claim, Hypothesis)):
        raise TypeError("epistemic aggregation requires a Claim or Hypothesis")
    return subject.target


def initial_belief(
    subject: EpistemicSubject,
    *,
    target_snapshot: TargetSnapshot | None = None,
) -> BeliefState:
    """Create the typed starting state for a canonical epistemic subject."""

    target = _subject_target(subject)
    if target_snapshot is not None and target is not None and target_snapshot.target != target:
        raise ValueError("belief target snapshot does not match the subject target")
    if isinstance(subject, Hypothesis):
        status = subject.status
        confidence = subject.confidence
    else:
        status = "proposed"
        confidence = 0.5
    if status not in BELIEF_STATUSES:
        raise ValueError(f"unsupported initial belief status: {status}")
    return BeliefState(
        subject_ref=subject.ref,
        status=status,
        confidence=confidence,
        target_snapshot=target_snapshot,
    )


def _is_invalid_execution(evidence: Evidence) -> bool:
    return (
        evidence.data.get("disposition") == "invalid"
        or evidence.data.get("valid") is False
        or evidence.data.get("infrastructure_failure") is True
    )


def _prepare_aggregation(
    *,
    subject: EpistemicSubject,
    evidence: Sequence[Evidence],
    prior: BeliefState | None,
    current_snapshot: TargetSnapshot | None,
) -> _AggregationInput:
    target = _subject_target(subject)
    if isinstance(evidence, (str, bytes, bytearray)) or not isinstance(evidence, Sequence):
        raise TypeError("epistemic evidence must be a sequence of Evidence records")
    evidence_items = tuple(evidence)
    if not evidence_items:
        raise ValueError("epistemic aggregation requires at least one evidence record")
    if any(not isinstance(item, Evidence) for item in evidence_items):
        raise TypeError("epistemic evidence must contain only Evidence records")

    if current_snapshot is not None:
        if not isinstance(current_snapshot, TargetSnapshot):
            raise TypeError("current snapshot must be a TargetSnapshot")
        if target is not None and current_snapshot.target != target:
            raise ValueError("current snapshot does not match the subject target")

    state = prior or initial_belief(subject, target_snapshot=current_snapshot)
    if not isinstance(state, BeliefState):
        raise TypeError("prior belief must be a BeliefState")
    if state.subject_ref != subject.ref:
        raise ValueError("prior belief does not identify the exact subject")
    if state.status not in BELIEF_STATUSES:
        raise ValueError(f"unsupported prior belief status: {state.status}")
    if (
        current_snapshot is not None
        and state.target_snapshot is not None
        and state.target_snapshot.root != current_snapshot.root
    ):
        raise ValueError("prior belief is not bound to the current target snapshot")
    if target is not None and state.evidence_refs and state.target_snapshot is None:
        raise ValueError("evidence-bearing prior belief lacks target currentness")

    expected_snapshot = current_snapshot or state.target_snapshot
    known_refs = set(state.evidence_refs)
    new_refs: set[EvidenceRef] = set()
    for item in evidence_items:
        if subject.ref not in item.subject_refs:
            raise ValueError("evidence does not identify the exact claim or hypothesis")
        if not item.source_refs:
            raise ValueError("epistemic evidence requires exact provenance references")
        if item.evidence_type not in EVIDENCE_RELATIONSHIPS:
            raise ValueError(f"unsupported evidence relationship: {item.evidence_type}")
        if item.weight is None:
            raise ValueError("epistemic evidence requires an explicit weight")
        _probability(item.weight, "evidence weight")
        if item.evidence_type == "null" and item.weight != 0.0:
            raise ValueError("null or inconclusive evidence must have zero weight")
        if _is_invalid_execution(item) and item.evidence_type != "null":
            raise ValueError("invalid or infrastructure-failed execution must be null evidence")

        snapshot = item.target_snapshot
        if target is not None:
            if snapshot is None:
                raise ValueError("target-bound evidence requires an exact target snapshot")
            if snapshot.target != target:
                raise ValueError("evidence target does not match the subject target")
        if expected_snapshot is None and snapshot is not None:
            expected_snapshot = snapshot
        elif expected_snapshot is not None and (
            snapshot is None or snapshot.root != expected_snapshot.root
        ):
            raise ValueError("evidence is not bound to the current target snapshot")

        reference = EvidenceRef.from_evidence(item)
        if reference in known_refs or reference in new_refs:
            raise ValueError("evidence has already been aggregated")
        new_refs.add(reference)

    return _AggregationInput(subject, evidence_items, state, expected_snapshot)


def _validate_aggregation_output(
    prepared: _AggregationInput,
    result: object,
) -> BeliefState:
    if not isinstance(result, BeliefState):
        raise TypeError("evidence aggregator must return a BeliefState")
    if result.subject_ref != prepared.subject.ref:
        raise ValueError("aggregator output does not identify the exact subject")
    if result.status not in BELIEF_STATUSES:
        raise ValueError(f"aggregator output has unsupported status: {result.status}")
    _probability(result.confidence, "aggregated confidence")
    expected_refs = prepared.prior.evidence_refs + tuple(
        EvidenceRef.from_evidence(item) for item in prepared.evidence
    )
    if result.evidence_refs != expected_refs:
        raise ValueError("aggregator output does not retain exact evidence provenance")
    expected_root = None if prepared.target_snapshot is None else prepared.target_snapshot.root
    result_root = None if result.target_snapshot is None else result.target_snapshot.root
    if result_root != expected_root:
        raise ValueError("aggregator output does not retain target currentness")
    return result


def aggregate_evidence(
    aggregator: EvidenceAggregator,
    *,
    subject: EpistemicSubject,
    evidence: Sequence[Evidence],
    prior: BeliefState | None = None,
    current_snapshot: TargetSnapshot | None = None,
) -> BeliefState:
    """Validate an aggregation boundary before and after a replaceable policy call."""

    if not isinstance(aggregator, EvidenceAggregator):
        raise TypeError("aggregator must implement EvidenceAggregator")
    prepared = _prepare_aggregation(
        subject=subject,
        evidence=evidence,
        prior=prior,
        current_snapshot=current_snapshot,
    )
    substantive = tuple(item for item in prepared.evidence if item.evidence_type != "null")
    if substantive:
        policy_input = _AggregationInput(
            prepared.subject,
            substantive,
            prepared.prior,
            prepared.target_snapshot,
        )
        result = aggregator.aggregate(
            subject=policy_input.subject,
            evidence=policy_input.evidence,
            prior=policy_input.prior,
            current_snapshot=policy_input.target_snapshot,
        )
        aggregated = _validate_aggregation_output(policy_input, result)
    else:
        aggregated = prepared.prior

    if len(substantive) == len(prepared.evidence):
        return aggregated
    neutral_result = BeliefState(
        subject_ref=prepared.subject.ref,
        status=aggregated.status,
        confidence=aggregated.confidence,
        evidence_refs=prepared.prior.evidence_refs
        + tuple(EvidenceRef.from_evidence(item) for item in prepared.evidence),
        target_snapshot=prepared.target_snapshot,
        lineage=(aggregated.ref, *(item.ref for item in prepared.evidence)),
    )
    return _validate_aggregation_output(prepared, neutral_result)


@dataclass(frozen=True)
class LinearEvidenceAggregator:
    """Deterministic built-in policy compatible with the original linear update."""

    support_scale: float = 0.2
    counterexample_scale: float = 0.2
    qualification_scale: float = 0.05
    supported_threshold: float = 0.75
    rejected_threshold: float = 0.2
    null_is_neutral: bool = True

    def __post_init__(self) -> None:
        for label in (
            "support_scale",
            "counterexample_scale",
            "qualification_scale",
            "supported_threshold",
            "rejected_threshold",
        ):
            _probability(getattr(self, label), label.replace("_", " "))
        if self.rejected_threshold >= self.supported_threshold:
            raise ValueError("rejected threshold must be lower than supported threshold")

    def transition(
        self,
        *,
        current_confidence: float,
        relationship: str,
        weight: float,
        current_status: str = "proposed",
    ) -> tuple[BeliefStatus, float]:
        """Apply one scalar transition; used by canonical and legacy adapters."""

        confidence = _probability(current_confidence, "belief confidence")
        strength = _probability(weight, "evidence weight")
        if relationship not in EVIDENCE_RELATIONSHIPS:
            raise ValueError(f"unsupported evidence relationship: {relationship}")
        if current_status not in BELIEF_STATUSES:
            raise ValueError(f"unsupported prior belief status: {current_status}")

        if relationship == "support":
            delta = strength * self.support_scale
        elif relationship == "counterexample":
            delta = -strength * self.counterexample_scale
        elif relationship == "null" and self.null_is_neutral:
            delta = 0.0
        else:
            delta = -strength * self.qualification_scale
        updated = min(1.0, max(0.0, confidence + delta))

        if updated >= self.supported_threshold:
            status: BeliefStatus = "supported"
        elif updated <= self.rejected_threshold:
            status = "rejected"
        elif relationship == "counterexample":
            status = "weakened"
        elif relationship == "null" and self.null_is_neutral:
            status = cast(BeliefStatus, current_status)
        else:
            status = "testing"
        return status, updated

    def aggregate(
        self,
        *,
        subject: EpistemicSubject,
        evidence: Sequence[Evidence],
        prior: BeliefState | None = None,
        current_snapshot: TargetSnapshot | None = None,
    ) -> BeliefState:
        prepared = _prepare_aggregation(
            subject=subject,
            evidence=evidence,
            prior=prior,
            current_snapshot=current_snapshot,
        )
        status = prepared.prior.status
        confidence = prepared.prior.confidence
        for item in prepared.evidence:
            status, confidence = self.transition(
                current_confidence=confidence,
                relationship=item.evidence_type,
                weight=item.weight if item.weight is not None else 0.0,
                current_status=status,
            )
        result = BeliefState(
            subject_ref=prepared.subject.ref,
            status=status,
            confidence=confidence,
            evidence_refs=prepared.prior.evidence_refs
            + tuple(EvidenceRef.from_evidence(item) for item in prepared.evidence),
            target_snapshot=prepared.target_snapshot,
            lineage=(prepared.prior.ref, *(item.ref for item in prepared.evidence)),
        )
        return _validate_aggregation_output(prepared, result)


@dataclass(frozen=True)
class EpistemicPolicy:
    """Facade for independent Claim creation and governed evidence aggregation."""

    aggregator: EvidenceAggregator = field(default_factory=LinearEvidenceAggregator)

    def create_claim(
        self,
        *,
        statement: str,
        kind: ClaimKind,
        target: TargetRef | None = None,
        scope: Mapping[str, Any] | None = None,
        source_refs: Sequence[RecordRef] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> Claim:
        if kind not in STANDARD_CLAIM_KINDS:
            raise ValueError(f"unsupported standard claim kind: {kind}")
        return Claim(
            statement=statement,
            kind=kind,
            target=target,
            scope={} if scope is None else scope,
            lineage=tuple(source_refs),
            metadata={} if metadata is None else metadata,
        )

    def initial(
        self,
        subject: EpistemicSubject,
        *,
        target_snapshot: TargetSnapshot | None = None,
    ) -> BeliefState:
        return initial_belief(subject, target_snapshot=target_snapshot)

    def aggregate(
        self,
        *,
        subject: EpistemicSubject,
        evidence: Sequence[Evidence],
        prior: BeliefState | None = None,
        current_snapshot: TargetSnapshot | None = None,
    ) -> BeliefState:
        return aggregate_evidence(
            self.aggregator,
            subject=subject,
            evidence=evidence,
            prior=prior,
            current_snapshot=current_snapshot,
        )
