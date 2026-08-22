from __future__ import annotations

from collections.abc import Sequence

import pytest

from librsi import (
    BeliefState,
    Claim,
    EpistemicPolicy,
    Evidence,
    EvidenceRef,
    Hypothesis,
    HypothesisPolicy,
    LinearEvidenceAggregator,
    RecordRef,
    RSIKernel,
    TargetRef,
    TargetSnapshot,
    aggregate_evidence,
    deserialize_record,
    serialize_record,
)


def _target_context() -> tuple[TargetRef, TargetSnapshot, TargetSnapshot]:
    target = TargetRef(target_id="reactor", kind="simulation")
    current = TargetSnapshot(target=target, revision="r2", state={"temperature": 20.0})
    stale = TargetSnapshot(target=target, revision="r1", state={"temperature": 21.0})
    return target, current, stale


def _evidence(
    subject: Claim | Hypothesis,
    snapshot: TargetSnapshot,
    *,
    relationship: str,
    weight: float,
    source_root: str,
    data: dict[str, object] | None = None,
) -> Evidence:
    return Evidence(
        evidence_type=relationship,
        data={"reading": source_root} if data is None else data,
        subject_refs=(subject.ref,),
        source_refs=(RecordRef("observation", source_root * 64),),
        target_snapshot=snapshot,
        weight=weight,
    )


def test_claims_are_independent_epistemic_subjects_with_typed_initial_state() -> None:
    target, current, _ = _target_context()
    policy = EpistemicPolicy()
    source = RecordRef("question", "a" * 64)
    claim = policy.create_claim(
        statement="Temperature remains below the operating boundary",
        kind="invariant",
        target=target,
        scope={"maximum": 25.0},
        source_refs=(source,),
        metadata={"display": "temperature guard"},
    )
    state = policy.initial(claim, target_snapshot=current)

    assert claim.kind == "invariant"
    assert claim.lineage == (source,)
    assert state.subject_ref == claim.ref
    assert state.status == "proposed"
    assert state.confidence == 0.5
    assert state.target_snapshot == current
    assert deserialize_record(serialize_record(state)) == state

    with pytest.raises(ValueError, match="claim kind"):
        policy.create_claim(statement="unknown", kind="prediction")  # type: ignore[arg-type]


def test_conflicting_evidence_coexists_with_exact_provenance_and_currentness() -> None:
    target, current, _ = _target_context()
    claim = EpistemicPolicy().create_claim(
        statement="Cooling reduces temperature",
        kind="behavioral",
        target=target,
    )
    support = _evidence(
        claim,
        current,
        relationship="support",
        weight=0.8,
        source_root="b",
    )
    counterexample = _evidence(
        claim,
        current,
        relationship="counterexample",
        weight=0.4,
        source_root="c",
    )

    state = RSIKernel().epistemics.aggregate(
        subject=claim,
        evidence=(support, counterexample),
        current_snapshot=current,
    )

    assert state.status == "weakened"
    assert state.confidence == pytest.approx(0.58)
    assert state.evidence_refs == (
        EvidenceRef.from_evidence(support),
        EvidenceRef.from_evidence(counterexample),
    )
    assert state.target_snapshot == current


def test_null_infrastructure_evidence_is_neutral_but_retained() -> None:
    target, current, _ = _target_context()
    claim = Claim(statement="The probe is stable", kind="capability", target=target)
    prior = EpistemicPolicy().initial(claim, target_snapshot=current)
    invalid = _evidence(
        claim,
        current,
        relationship="null",
        weight=0.0,
        source_root="d",
        data={"disposition": "invalid", "reason": "runner unavailable"},
    )

    hostile = HostileNullAggregator()
    state = EpistemicPolicy(aggregator=hostile).aggregate(
        subject=claim,
        evidence=(invalid,),
        prior=prior,
    )

    assert not hostile.called
    assert state.confidence == prior.confidence
    assert state.status == prior.status
    assert state.evidence_refs == (EvidenceRef.from_evidence(invalid),)

    misclassified = _evidence(
        claim,
        current,
        relationship="counterexample",
        weight=0.5,
        source_root="e",
        data={"infrastructure_failure": True},
    )
    with pytest.raises(ValueError, match="must be null evidence"):
        EpistemicPolicy().aggregate(subject=claim, evidence=(misclassified,), prior=prior)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("different-subject", "exact claim or hypothesis"),
        ("different-target", "subject target"),
        ("stale", "current target snapshot"),
        ("unsupported", "unsupported evidence relationship"),
        ("missing-provenance", "provenance"),
        ("nonzero-null", "zero weight"),
    ],
)
def test_epistemic_binding_rejects_invalid_relationships(
    case: str,
    message: str,
) -> None:
    target, current, stale = _target_context()
    claim = Claim(statement="Bound claim", kind="observational", target=target)
    relationship = "novel" if case == "unsupported" else "support"
    weight = 0.4
    snapshot = stale if case == "stale" else current
    evidence = _evidence(
        claim,
        snapshot,
        relationship=relationship,
        weight=weight,
        source_root="f",
    )
    if case == "different-subject":
        evidence = Evidence(
            evidence_type="support",
            data={},
            subject_refs=(Claim(statement="Other").ref,),
            source_refs=evidence.source_refs,
            target_snapshot=current,
            weight=0.4,
        )
    elif case == "different-target":
        other_target = TargetRef(target_id="other", kind="simulation")
        evidence = Evidence(
            evidence_type="support",
            data={},
            subject_refs=(claim.ref,),
            source_refs=evidence.source_refs,
            target_snapshot=TargetSnapshot(target=other_target, state={}),
            weight=0.4,
        )
    elif case == "missing-provenance":
        evidence = Evidence(
            evidence_type="support",
            data={},
            subject_refs=(claim.ref,),
            target_snapshot=current,
            weight=0.4,
        )
    elif case == "nonzero-null":
        evidence = _evidence(
            claim,
            current,
            relationship="null",
            weight=0.2,
            source_root="f",
        )

    with pytest.raises(ValueError, match=message):
        EpistemicPolicy().aggregate(
            subject=claim,
            evidence=(evidence,),
            current_snapshot=current,
        )


def test_aggregation_rejects_reuse_and_malformed_inputs() -> None:
    target, current, _ = _target_context()
    claim = Claim(statement="No duplicates", target=target)
    evidence = _evidence(
        claim,
        current,
        relationship="support",
        weight=0.5,
        source_root="1",
    )
    policy = EpistemicPolicy()
    state = policy.aggregate(subject=claim, evidence=(evidence,), current_snapshot=current)

    with pytest.raises(ValueError, match="already been aggregated"):
        policy.aggregate(subject=claim, evidence=(evidence,), prior=state)
    with pytest.raises(ValueError, match="at least one"):
        policy.aggregate(subject=claim, evidence=())
    with pytest.raises(TypeError, match="sequence"):
        policy.aggregate(subject=claim, evidence="bad")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="only Evidence"):
        policy.aggregate(subject=claim, evidence=(claim,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Claim or Hypothesis"):
        policy.aggregate(subject=current, evidence=(evidence,))  # type: ignore[arg-type]


def test_prior_belief_cannot_be_rebound_across_target_snapshots() -> None:
    target, current, stale = _target_context()
    claim = Claim(statement="Snapshot-bound belief", target=target)
    stale_prior = EpistemicPolicy().initial(claim, target_snapshot=stale)
    current_evidence = _evidence(
        claim,
        current,
        relationship="support",
        weight=0.5,
        source_root="5",
    )

    with pytest.raises(ValueError, match="prior belief.*current target snapshot"):
        EpistemicPolicy().aggregate(
            subject=claim,
            evidence=(current_evidence,),
            prior=stale_prior,
            current_snapshot=current,
        )


class DecisiveAggregator:
    def aggregate(
        self,
        *,
        subject: Claim | Hypothesis,
        evidence: Sequence[Evidence],
        prior: BeliefState | None = None,
        current_snapshot: TargetSnapshot | None = None,
    ) -> BeliefState:
        assert prior is not None
        return BeliefState(
            subject_ref=subject.ref,
            status="supported",
            confidence=1.0,
            evidence_refs=prior.evidence_refs
            + tuple(EvidenceRef.from_evidence(item) for item in evidence),
            target_snapshot=current_snapshot,
        )


class HostileNullAggregator:
    def __init__(self) -> None:
        self.called = False

    def aggregate(
        self,
        *,
        subject: Claim | Hypothesis,
        evidence: Sequence[Evidence],
        prior: BeliefState | None = None,
        current_snapshot: TargetSnapshot | None = None,
    ) -> BeliefState:
        self.called = True
        assert prior is not None
        return BeliefState(
            subject_ref=subject.ref,
            status="rejected",
            confidence=0.0,
            evidence_refs=prior.evidence_refs
            + tuple(EvidenceRef.from_evidence(item) for item in evidence),
            target_snapshot=current_snapshot,
        )


class InvalidAggregator:
    def aggregate(
        self,
        *,
        subject: Claim | Hypothesis,
        evidence: Sequence[Evidence],
        prior: BeliefState | None = None,
        current_snapshot: TargetSnapshot | None = None,
    ) -> BeliefState:
        del subject, evidence, prior, current_snapshot
        return "not state"  # type: ignore[return-value]


def test_replaceable_aggregators_are_validated_at_the_authority_boundary() -> None:
    target, current, _ = _target_context()
    claim = Claim(statement="A pluggable claim", target=target)
    evidence = _evidence(
        claim,
        current,
        relationship="support",
        weight=0.1,
        source_root="2",
    )

    state = aggregate_evidence(
        DecisiveAggregator(),
        subject=claim,
        evidence=(evidence,),
        current_snapshot=current,
    )
    assert state.status == "supported"
    assert state.confidence == 1.0

    with pytest.raises(TypeError, match="return a BeliefState"):
        aggregate_evidence(
            InvalidAggregator(),
            subject=claim,
            evidence=(evidence,),
            current_snapshot=current,
        )
    with pytest.raises(TypeError, match="implement EvidenceAggregator"):
        aggregate_evidence(
            object(),  # type: ignore[arg-type]
            subject=claim,
            evidence=(evidence,),
            current_snapshot=current,
        )


def test_hypothesis_policy_delegates_canonical_updates_and_preserves_legacy_linear_mode() -> None:
    target, current, _ = _target_context()
    hypothesis = HypothesisPolicy().create(
        target=target,
        statement="Cooling controls the reactor",
        predictions=({"temperature": "decrease"},),
        confidence=0.4,
    )
    evidence = _evidence(
        hypothesis,
        current,
        relationship="support",
        weight=0.1,
        source_root="3",
    )

    updated = HypothesisPolicy(aggregator=DecisiveAggregator()).apply(
        hypothesis=hypothesis,
        evidence=evidence,
    )
    assert updated.status == "supported"
    assert updated.confidence == 1.0

    legacy = LinearEvidenceAggregator(null_is_neutral=False)
    status, confidence = legacy.transition(
        current_confidence=0.5,
        relationship="null",
        weight=0.5,
    )
    assert status == "testing"
    assert confidence == pytest.approx(0.475)


def test_belief_state_rejects_invalid_subjects_and_values() -> None:
    claim = Claim(statement="Validated state")
    with pytest.raises(ValueError, match="claim or hypothesis"):
        BeliefState(subject_ref=RecordRef("goal", "4" * 64))
    with pytest.raises(ValueError, match="between zero and one"):
        BeliefState(subject_ref=claim.ref, confidence=1.1)
    with pytest.raises(TypeError, match="RecordRef"):
        BeliefState(subject_ref="claim")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="threshold"):
        LinearEvidenceAggregator(supported_threshold=0.2, rejected_threshold=0.2)
