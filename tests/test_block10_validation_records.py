from __future__ import annotations

from pathlib import Path

import pytest

from librsi import (
    BeliefState,
    Claim,
    Evidence,
    EvidenceRef,
    RecordRef,
    SemanticRecord,
    SQLiteKnowledgeStore,
    TargetRef,
    TargetSnapshot,
    ValidationEvidenceBatch,
    ValidationEvidenceRequest,
    ValidationPolicy,
    ValidationRequest,
    ValidationResult,
    deserialize_record,
    serialize_record,
)


def _context() -> tuple[Claim, TargetSnapshot, ValidationRequest]:
    target = TargetRef(target_id="validation-process", kind="process")
    snapshot = TargetSnapshot(target=target, revision="v4", state={"rate": 8})
    claim = Claim(statement="The process remains stable", kind="behavioral", target=target)
    request = ValidationRequest.for_claim(
        validation_id="validate-stability",
        claim=claim,
        target_snapshot=snapshot,
        max_evidence_actions=2,
    )
    return claim, snapshot, request


def _evidence(
    claim: Claim,
    snapshot: TargetSnapshot,
    relationship: str,
    index: int,
    *,
    weight: float = 1.0,
) -> Evidence:
    return Evidence(
        evidence_type=relationship,
        data={"sample": index},
        subject_refs=(claim.ref,),
        source_refs=(snapshot.ref,),
        target_snapshot=snapshot,
        weight=weight,
    )


def test_validation_request_gap_and_batch_records_round_trip_with_exact_lineage() -> None:
    claim, snapshot, validation = _context()
    evidence = _evidence(claim, snapshot, "support", 1)
    gap = ValidationEvidenceRequest.for_gaps(
        validation=validation,
        sequence=1,
        known_evidence_refs=(),
        gaps=("obtain current evidence",),
    )
    batch = ValidationEvidenceBatch.collected(request=gap, evidence=(evidence,))

    assert validation.lineage == (claim.ref, snapshot.ref)
    assert gap.lineage == (validation.ref, claim.ref, snapshot.ref)
    assert batch.lineage == (gap.ref, *gap.lineage, evidence.ref)
    for record in (validation, gap, batch):
        assert deserialize_record(serialize_record(record)) == record


@pytest.mark.parametrize(
    ("relationships", "expected"),
    [
        (("support", "support"), "supported"),
        (("counterexample", "counterexample"), "contradicted"),
        (("boundary",), "bounded"),
        (("confounder",), "bounded"),
        (("support", "counterexample"), "bounded"),
        (("null",), "inconclusive"),
        (("support",), "inconclusive"),
    ],
)
def test_validation_policy_distinguishes_public_outcomes(
    relationships: tuple[str, ...], expected: str
) -> None:
    claim, snapshot, validation = _context()
    evidence = tuple(
        _evidence(
            claim,
            snapshot,
            relationship,
            index,
            weight=0.0 if relationship == "null" else 1.0,
        )
        for index, relationship in enumerate(relationships)
    )
    policy = ValidationPolicy()
    belief = policy.belief(validation, evidence)

    assert policy.disposition(belief, evidence) == expected
    assert bool(policy.gaps(belief, evidence)) == (expected in {"bounded", "inconclusive"})


def test_validation_result_rejects_unsupported_success_and_incomplete_provenance() -> None:
    claim, snapshot, validation = _context()
    belief = BeliefState(
        subject_ref=claim.ref,
        status="proposed",
        confidence=0.5,
        target_snapshot=snapshot,
    )
    run_ref = validation.canonical_run().ref
    with pytest.raises(ValueError, match="unsupported by its belief"):
        ValidationResult(
            validation=validation,
            run=run_ref,
            disposition="supported",
            belief=belief,
            unresolved=(),
            lineage=(validation.ref, run_ref, belief.ref),
        )


def test_validation_result_rejects_substituted_run_and_belief_on_all_boundaries(
    tmp_path: Path,
) -> None:
    claim, snapshot, validation = _context()
    canonical_belief = ValidationPolicy().belief(validation, ())
    substituted_run = RecordRef("run", "0" * 64)
    with pytest.raises(ValueError, match="canonical request Run"):
        ValidationResult(
            validation=validation,
            run=substituted_run,
            disposition="inconclusive",
            belief=canonical_belief,
            unresolved=("unknown",),
            lineage=(validation.ref, substituted_run, canonical_belief.ref),
        )

    fabricated_success = BeliefState(
        subject_ref=claim.ref,
        status="supported",
        confidence=1.0,
        target_snapshot=snapshot,
    )
    run_ref = validation.canonical_run().ref
    with pytest.raises(ValueError, match="canonical evidence-derived"):
        ValidationResult(
            validation=validation,
            run=run_ref,
            disposition="supported",
            belief=fabricated_success,
            lineage=(validation.ref, run_ref, fabricated_success.ref),
        )

    forged = object.__new__(ValidationResult)
    object.__setattr__(forged, "validation", validation)
    object.__setattr__(forged, "run", substituted_run)
    object.__setattr__(forged, "disposition", "inconclusive")
    object.__setattr__(forged, "belief", canonical_belief)
    object.__setattr__(forged, "evidence", ())
    object.__setattr__(forged, "reused_evidence_refs", ())
    object.__setattr__(forged, "gathered_evidence_refs", ())
    object.__setattr__(forged, "unresolved", ("unknown",))
    object.__setattr__(
        forged,
        "lineage",
        (validation.ref, substituted_run, canonical_belief.ref),
    )
    object.__setattr__(forged, "metadata", {})
    SemanticRecord.__post_init__(forged)
    serialized = serialize_record(forged)
    with pytest.raises(ValueError, match="canonical request Run"):
        deserialize_record(serialized)
    with (
        SQLiteKnowledgeStore(tmp_path / "substituted-result.sqlite") as store,
        pytest.raises(ValueError, match="canonical request Run"),
    ):
        store.put(forged)

    evidence = _evidence(claim, snapshot, "support", 1)
    supported_belief = ValidationPolicy().belief(validation, (evidence,))
    with pytest.raises(ValueError, match="exactly partition"):
        ValidationResult(
            validation=validation,
            run=run_ref,
            disposition="inconclusive",
            belief=supported_belief,
            evidence=(evidence,),
            unresolved=("more evidence",),
            lineage=(validation.ref, run_ref, supported_belief.ref, evidence.ref),
        )


def test_validation_records_reject_stale_unprovenanced_or_malformed_evidence() -> None:
    claim, snapshot, validation = _context()
    stale = TargetSnapshot(target=snapshot.target, revision="v3", state={"rate": 7})
    gap = ValidationEvidenceRequest.for_gaps(
        validation=validation,
        sequence=1,
        known_evidence_refs=(),
        gaps=("current evidence",),
    )
    stale_evidence = Evidence(
        evidence_type="support",
        data={"sample": 1},
        subject_refs=(claim.ref,),
        source_refs=(stale.ref,),
        target_snapshot=stale,
        weight=1.0,
    )
    with pytest.raises(ValueError, match="stale"):
        ValidationEvidenceBatch.collected(request=gap, evidence=(stale_evidence,))

    missing_source = Evidence(
        evidence_type="support",
        data={"sample": 1},
        subject_refs=(claim.ref,),
        target_snapshot=snapshot,
        weight=1.0,
    )
    with pytest.raises(ValueError, match="exact provenance"):
        ValidationEvidenceBatch.collected(request=gap, evidence=(missing_source,))
    with pytest.raises(ValueError, match="cannot be empty"):
        ValidationEvidenceBatch(
            request=gap,
            disposition="collected",
            lineage=(gap.ref, *gap.lineage),
        )
    with pytest.raises(ValueError, match="require a reason"):
        ValidationEvidenceBatch(
            request=gap,
            disposition="unavailable",
            lineage=(gap.ref, *gap.lineage),
        )


def test_target_bound_claim_requires_exact_snapshot_and_unbound_claim_rejects_one() -> None:
    claim, snapshot, _ = _context()
    with pytest.raises(ValueError, match="requires a current"):
        ValidationRequest.for_claim(validation_id="missing", claim=claim)
    other = TargetSnapshot(target=TargetRef(target_id="other"), revision="v1", state={"rate": 1})
    with pytest.raises(ValueError, match="does not match"):
        ValidationRequest.for_claim(validation_id="wrong", claim=claim, target_snapshot=other)
    unbound = Claim(statement="A general mathematical claim", kind="invariant")
    with pytest.raises(ValueError, match="unbound claims"):
        ValidationRequest.for_claim(
            validation_id="unbound", claim=unbound, target_snapshot=snapshot
        )


def test_evidence_ref_partitions_are_exact_and_type_safe() -> None:
    claim, snapshot, validation = _context()
    first = _evidence(claim, snapshot, "support", 1)
    second = _evidence(claim, snapshot, "support", 2)
    belief = ValidationPolicy().belief(validation, (first, second))
    run_ref = validation.canonical_run().ref
    ordered = tuple(sorted((first, second), key=lambda item: item.root))
    result = ValidationResult(
        validation=validation,
        run=run_ref,
        disposition="supported",
        belief=belief,
        evidence=(first, second),
        reused_evidence_refs=(EvidenceRef.from_evidence(first),),
        gathered_evidence_refs=(EvidenceRef.from_evidence(second),),
        lineage=(validation.ref, run_ref, belief.ref, *(item.ref for item in ordered)),
    )
    assert result.subject_ref == claim.ref
    assert result.target == snapshot.target
    assert result.target_snapshot == snapshot
    assert deserialize_record(serialize_record(result)) == result
