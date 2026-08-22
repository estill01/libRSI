from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from librsi import (
    Evidence,
    ExperimentSpec,
    Hypothesis,
    KnowledgeQuery,
    KnowledgeRelationship,
    KnowledgeStore,
    KnowledgeWrite,
    RecordRef,
    SemanticRecord,
    SQLiteKnowledgeStore,
    StoredKnowledge,
    TargetRef,
    TargetSnapshot,
)


def _fixture() -> tuple[
    TargetRef,
    TargetSnapshot,
    TargetSnapshot,
    Hypothesis,
    Evidence,
    Evidence,
]:
    target = TargetRef(target_id="thermal-simulation", kind="simulation")
    baseline = TargetSnapshot(target=target, revision="v1", state={"gain": 0.4})
    current = TargetSnapshot(target=target, revision="v2", state={"gain": 0.5})
    hypothesis = Hypothesis(
        statement="The simulation remains bounded",
        target=target,
        predictions=({"maximum": "< 25"},),
    )
    stale = Evidence(
        evidence_type="support",
        data={"maximum": 24.0},
        subject_refs=(hypothesis.ref,),
        source_refs=(hypothesis.ref,),
        target_snapshot=baseline,
        weight=0.7,
        lineage=(hypothesis.ref,),
    )
    fresh = Evidence(
        evidence_type="counterexample",
        data={"maximum": 27.0},
        subject_refs=(hypothesis.ref,),
        source_refs=(hypothesis.ref,),
        target_snapshot=current,
        weight=0.7,
        lineage=(hypothesis.ref,),
    )
    return target, baseline, current, hypothesis, stale, fresh


def test_second_store_instance_reuses_current_and_labels_stale_knowledge(
    tmp_path: Path,
) -> None:
    target, baseline, current, hypothesis, stale, fresh = _fixture()
    database = tmp_path / "knowledge.sqlite"
    with SQLiteKnowledgeStore(database) as first_run:
        first_run.put_many(
            tuple(
                KnowledgeWrite(record=record, source_run_id="run-1")
                for record in (target, baseline, current, hypothesis, stale, fresh)
            )
        )

    with SQLiteKnowledgeStore(database) as second_run:
        current_results = second_run.query(
            KnowledgeQuery(
                record_types=("evidence",),
                target=target,
                current_snapshot=current,
                currentness="current",
                source_run_id="run-1",
                valid=True,
            )
        )
        stale_results = second_run.query(
            KnowledgeQuery(
                record_types=("evidence",),
                target=target,
                current_snapshot=current,
                currentness="stale",
            )
        )

        assert tuple(item.record for item in current_results) == (fresh,)
        assert tuple(item.record for item in stale_results) == (stale,)
        assert current_results[0].source_run_id == "run-1"
        assert second_run.get(hypothesis.root) == hypothesis
        assert second_run.schema_version == 1


def test_queries_filter_exact_subject_lineage_evidence_run_validity_and_limit() -> None:
    target, _, current, hypothesis, stale, fresh = _fixture()
    with SQLiteKnowledgeStore() as store:
        store.put(stale, source_run_id="run-1", valid=True)
        store.put(fresh, source_run_id="run-2", valid=False)

        exact = store.query(
            KnowledgeQuery(
                record_types=("evidence",),
                target=target,
                current_snapshot=current,
                subject_refs=(hypothesis.ref,),
                evidence_types=("support",),
                lineage_refs=(hypothesis.ref,),
                source_run_id="run-1",
                valid=True,
                currentness="stale",
            )
        )
        latest = store.query(KnowledgeQuery(record_types=("evidence",), limit=1))
        invalid = store.query(KnowledgeQuery(valid=False))

        assert tuple(item.record for item in exact) == (stale,)
        assert latest[0].record == fresh
        assert latest[0].currentness == "unassessed"
        assert invalid[0].record == fresh
        assert invalid[0].valid is False


def test_unbound_and_multi_snapshot_knowledge_are_not_mislabeled_current() -> None:
    target, baseline, current, hypothesis, _, _ = _fixture()
    comparison_spec = ExperimentSpec(
        experiment_id="comparison",
        kind="simulation",
        baseline_snapshot=baseline,
        candidate_snapshot=current,
    )
    with SQLiteKnowledgeStore() as store:
        store.put(hypothesis)
        store.put(comparison_spec)

        unbound = store.query(KnowledgeQuery(current_snapshot=current, currentness="unbound"))
        incomparable = store.query(
            KnowledgeQuery(current_snapshot=current, currentness="incomparable")
        )

        assert tuple(item.record for item in unbound) == (hypothesis,)
        assert tuple(item.record for item in incomparable) == (comparison_spec,)
        assert target == current.target


def test_exact_relationships_round_trip_and_filter_without_graph_platform() -> None:
    _, _, _, hypothesis, _, fresh = _fixture()
    relationship = KnowledgeRelationship(
        source=hypothesis.ref,
        relationship="supported_by",
        target=fresh.ref,
        attributes={"role": "discriminating evidence"},
    )
    with SQLiteKnowledgeStore() as store:
        store.put_many(
            (
                KnowledgeWrite(hypothesis, source_run_id="run-1"),
                KnowledgeWrite(fresh, source_run_id="run-1"),
                KnowledgeWrite(relationship, source_run_id="run-1"),
            )
        )

        assert store.relationships(source=hypothesis.ref) == (relationship,)
        assert store.relationships(relationship="supported_by") == (relationship,)
        assert store.relationships(target=fresh.ref) == (relationship,)
        assert store.relationships(source=RecordRef("claim", hypothesis.root)) == ()
        assert store.relationships(target=RecordRef("claim", fresh.root)) == ()
        assert tuple(
            item.record
            for item in store.query(KnowledgeQuery(record_types=("knowledge_relationship",)))
        ) == (relationship,)


class _AlternativeKnowledgeStore:
    """Tiny structural substitute proving the protocol does not depend on SQLite."""

    def put(
        self,
        record: SemanticRecord,
        *,
        source_run_id: str | None = None,
        valid: bool = True,
    ) -> StoredKnowledge:
        del source_run_id, valid
        return StoredKnowledge(record, None, True, "now")

    def put_many(self, writes: Sequence[KnowledgeWrite]) -> tuple[StoredKnowledge, ...]:
        return tuple(self.put(item.record) for item in writes)

    def get(self, root: str) -> SemanticRecord | None:
        del root
        return None

    def query(self, query: KnowledgeQuery | None = None) -> tuple[StoredKnowledge, ...]:
        del query
        return ()

    def relationships(
        self,
        *,
        source: RecordRef | None = None,
        relationship: str | None = None,
        target: RecordRef | None = None,
    ) -> tuple[KnowledgeRelationship, ...]:
        del source, relationship, target
        return ()

    def close(self) -> None:
        return None


def test_another_backend_can_satisfy_the_knowledge_store_contract() -> None:
    with SQLiteKnowledgeStore() as store:
        assert isinstance(store, KnowledgeStore)
    assert isinstance(_AlternativeKnowledgeStore(), KnowledgeStore)
