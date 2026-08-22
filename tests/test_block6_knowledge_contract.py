from __future__ import annotations

import pytest

from librsi import (
    KNOWLEDGE_RECORD_TYPES,
    Claim,
    Evidence,
    KnowledgeQuery,
    KnowledgeRelationship,
    KnowledgeWrite,
    RecordRef,
    StoredKnowledge,
    TargetRef,
    TargetSnapshot,
    bound_target_snapshots,
    deserialize_record,
    label_currentness,
    serialize_record,
)
from librsi.knowledge import subject_refs, target_refs, validate_knowledge_record


def _records() -> tuple[TargetRef, TargetSnapshot, Claim, Evidence]:
    target = TargetRef(target_id="knowledge-contract", kind="simulation")
    snapshot = TargetSnapshot(target=target, revision="v1", state={"value": 1})
    claim = Claim(statement="The target is stable", target=target)
    evidence = Evidence(
        evidence_type="support",
        data={"value": 1},
        subject_refs=(claim.ref,),
        target_snapshot=snapshot,
        lineage=(claim.ref,),
    )
    return target, snapshot, claim, evidence


def test_relationship_is_canonical_typed_and_immutable() -> None:
    _, _, claim, evidence = _records()
    relationship = KnowledgeRelationship(
        source=claim.ref,
        relationship=" supported_by ",
        target=evidence.ref,
        attributes={"role": "primary"},
    )

    assert relationship.relationship == "supported_by"
    assert deserialize_record(serialize_record(relationship)) == relationship
    with pytest.raises(TypeError):
        relationship.attributes["role"] = "changed"  # type: ignore[index]

    with pytest.raises(TypeError, match="endpoints"):
        KnowledgeRelationship(  # type: ignore[arg-type]
            source=claim,
            relationship="supports",
            target=evidence.ref,
        )
    with pytest.raises(ValueError, match="relationship is required"):
        KnowledgeRelationship(source=claim.ref, relationship=" ", target=evidence.ref)


def test_knowledge_write_and_stored_result_validate_their_envelope() -> None:
    _, _, claim, _ = _records()

    assert KnowledgeWrite(claim, source_run_id=" run-1 ").source_run_id == "run-1"
    with pytest.raises(TypeError, match="SemanticRecord"):
        KnowledgeWrite("claim")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="source run id is required"):
        KnowledgeWrite(claim, source_run_id=" ")
    with pytest.raises(TypeError, match="validity"):
        KnowledgeWrite(claim, valid=1)  # type: ignore[arg-type]

    stored = StoredKnowledge(claim, " run-1 ", True, " now ")
    assert (stored.source_run_id, stored.stored_at) == ("run-1", "now")
    with pytest.raises(TypeError, match="validity"):
        StoredKnowledge(claim, None, 1, "now")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stored at is required"):
        StoredKnowledge(claim, None, True, " ")
    with pytest.raises(ValueError, match="unsupported stored"):
        StoredKnowledge(claim, None, True, "now", "future")  # type: ignore[arg-type]


@pytest.mark.parametrize("record_type", ["run", "event", "action", "unknown"])
def test_queries_reject_runtime_and_unknown_record_types(record_type: str) -> None:
    with pytest.raises(ValueError, match="runtime or unknown"):
        KnowledgeQuery(record_types=(record_type,))
    assert record_type not in KNOWLEDGE_RECORD_TYPES


def test_query_normalizes_filters_and_rejects_ambiguous_values() -> None:
    target, snapshot, claim, _ = _records()
    query = KnowledgeQuery(
        record_types=("hypothesis", "claim"),
        subject_refs=(claim.ref,),
        evidence_types=("support", "counterexample"),
        lineage_refs=(claim.ref,),
        source_run_id=" run-1 ",
        valid=False,
        limit=2,
    )

    assert query.record_types == ("claim", "hypothesis")
    assert query.evidence_types == ("counterexample", "support")
    assert query.source_run_id == "run-1"

    with pytest.raises(TypeError, match="record types must be a sequence"):
        KnowledgeQuery(record_types="claim")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="record types must be unique"):
        KnowledgeQuery(record_types=("claim", "claim"))
    with pytest.raises(TypeError, match="target must be a TargetRef"):
        KnowledgeQuery(target=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a TargetSnapshot"):
        KnowledgeQuery(current_snapshot=target)  # type: ignore[arg-type]

    other = TargetRef(target_id="other", kind="simulation")
    with pytest.raises(ValueError, match="does not match"):
        KnowledgeQuery(target=other, current_snapshot=snapshot)
    with pytest.raises(TypeError, match="must contain RecordRef"):
        KnowledgeQuery(subject_refs=(claim,))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="references must be unique"):
        KnowledgeQuery(lineage_refs=(claim.ref, claim.ref))
    with pytest.raises(TypeError, match="evidence types must be a sequence"):
        KnowledgeQuery(evidence_types="support")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="evidence types must be unique"):
        KnowledgeQuery(evidence_types=("support", "support"))
    with pytest.raises(ValueError, match="source run id is required"):
        KnowledgeQuery(source_run_id=" ")
    with pytest.raises(TypeError, match="validity"):
        KnowledgeQuery(valid=1)  # type: ignore[arg-type]


def test_currentness_and_limit_filters_fail_closed() -> None:
    _, snapshot, _, _ = _records()

    with pytest.raises(ValueError, match="require a current target snapshot"):
        KnowledgeQuery(currentness="current")
    with pytest.raises(ValueError, match="unsupported knowledge currentness"):
        KnowledgeQuery(current_snapshot=snapshot, currentness="unassessed")
    with pytest.raises(ValueError, match="unsupported knowledge currentness"):
        KnowledgeQuery(current_snapshot=snapshot, currentness="future")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="limit must be an integer"):
        KnowledgeQuery(limit=True)
    with pytest.raises(ValueError, match="limit must be positive"):
        KnowledgeQuery(limit=0)


def test_target_subject_and_currentness_helpers_preserve_exact_semantics() -> None:
    target, snapshot, claim, evidence = _records()

    assert target_refs(target) == (target,)
    assert target_refs(evidence) == (target,)
    assert subject_refs(evidence) == (claim.ref,)
    assert bound_target_snapshots(snapshot) == (snapshot,)
    assert bound_target_snapshots(evidence) == (snapshot,)
    assert label_currentness(evidence, snapshot) == "current"
    assert validate_knowledge_record(claim) == serialize_record(claim)

    with pytest.raises(TypeError, match="SemanticRecord"):
        validate_knowledge_record("claim")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="SemanticRecord"):
        bound_target_snapshots("claim")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TargetSnapshot"):
        label_currentness(evidence, target)  # type: ignore[arg-type]


def test_subject_and_lineage_queries_match_both_reference_type_and_root() -> None:
    from librsi import SQLiteKnowledgeStore

    _, _, claim, evidence = _records()
    wrong_type = RecordRef("hypothesis", claim.root)
    with SQLiteKnowledgeStore() as store:
        store.put(evidence)

        assert store.query(KnowledgeQuery(subject_refs=(claim.ref,)))
        assert store.query(KnowledgeQuery(lineage_refs=(claim.ref,)))
        assert store.query(KnowledgeQuery(subject_refs=(wrong_type,))) == ()
        assert store.query(KnowledgeQuery(lineage_refs=(wrong_type,))) == ()
