from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest

from librsi import (
    Claim,
    Evidence,
    KnowledgeQuery,
    KnowledgeRelationship,
    KnowledgeWrite,
    RecordRef,
    SemanticRecord,
    SQLiteKnowledgeStore,
    TargetRef,
    TargetSnapshot,
)


def _claim_and_evidence() -> tuple[Claim, Evidence]:
    target = TargetRef(target_id="process", kind="simulation")
    snapshot = TargetSnapshot(target=target, state={"value": 1})
    claim = Claim(statement="The process is stable", target=target)
    evidence = Evidence(
        evidence_type="support",
        data={"value": 1},
        subject_refs=(claim.ref,),
        source_refs=(claim.ref,),
        target_snapshot=snapshot,
        weight=0.7,
    )
    return claim, evidence


def test_batch_failure_rolls_back_records_occurrences_indexes_and_relationships() -> None:
    claim, _ = _claim_and_evidence()
    missing = RecordRef("evidence", "a" * 64)
    relationship = KnowledgeRelationship(
        source=claim.ref,
        relationship="supported_by",
        target=missing,
    )
    with SQLiteKnowledgeStore() as store:
        with pytest.raises(ValueError, match="endpoint is not stored"):
            store.put_many((KnowledgeWrite(claim), KnowledgeWrite(relationship)))

        assert store.get(claim.root) is None
        assert store.get(relationship.root) is None
        assert store.query() == ()
        assert store.relationships() == ()


def test_relationship_endpoint_type_must_match_the_stored_record() -> None:
    claim, evidence = _claim_and_evidence()
    wrong_type = RecordRef("claim", evidence.root)
    relationship = KnowledgeRelationship(
        source=claim.ref,
        relationship="supported_by",
        target=wrong_type,
    )
    with SQLiteKnowledgeStore() as store:
        store.put_many((KnowledgeWrite(claim), KnowledgeWrite(evidence)))
        with pytest.raises(ValueError, match="exact type/root"):
            store.put(relationship)
        assert store.get(relationship.root) is None


def test_duplicate_root_with_divergent_canonical_bytes_is_rejected() -> None:
    first = Claim(statement="same", metadata={"source": "first"})
    divergent = Claim(statement="same", metadata={"source": "second"})
    assert first.root == divergent.root
    with SQLiteKnowledgeStore() as store:
        store.put(first, source_run_id="run-1")
        with pytest.raises(ValueError, match="divergent canonical bytes"):
            store.put(divergent, source_run_id="run-2")

        store.put(first, source_run_id="run-2")
        assert len(store.query(KnowledgeQuery(record_types=("claim",)))) == 2


def test_forged_in_memory_root_is_rejected_before_write() -> None:
    claim = Claim(statement="canonical")
    object.__setattr__(claim, "root", "a" * 64)

    with SQLiteKnowledgeStore() as store:
        with pytest.raises(ValueError, match="root does not match"):
            store.put(claim)
        assert store.query() == ()


@dataclass(frozen=True, kw_only=True)
class _RuntimeStateMasquerade(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "run"

    run_id: str


def test_runtime_state_cannot_masquerade_as_knowledge() -> None:
    runtime = _RuntimeStateMasquerade(run_id="run-1")

    with pytest.raises(ValueError, match="not knowledge state"):
        KnowledgeWrite(runtime)
    with (
        SQLiteKnowledgeStore() as store,
        pytest.raises(ValueError, match="not knowledge state"),
    ):
        store.put(runtime)


def test_stored_record_type_and_serialized_root_tampering_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "tampered.sqlite"
    claim = Claim(statement="canonical")
    with SQLiteKnowledgeStore(database) as store:
        store.put(claim)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE knowledge_records SET record_type = 'evidence' WHERE root = ?",
            (claim.root,),
        )
    with SQLiteKnowledgeStore(database) as store:
        with pytest.raises(ValueError, match="root/type"):
            store.get(claim.root)
        with pytest.raises(ValueError, match="root/type"):
            store.query()

    with closing(sqlite3.connect(database)) as connection, connection:
        payload = json.loads(
            connection.execute(
                "SELECT serialized FROM knowledge_records WHERE root = ?",
                (claim.root,),
            ).fetchone()[0]
        )
        payload["record_type"] = "claim"
        payload["data"]["statement"] = "tampered"
        connection.execute(
            "UPDATE knowledge_records SET record_type = 'claim', serialized = ? WHERE root = ?",
            (json.dumps(payload), claim.root),
        )
    with (
        SQLiteKnowledgeStore(database) as store,
        pytest.raises(ValueError, match="root does not match"),
    ):
        store.get(claim.root)


def test_schema_migration_is_local_reopenable_and_rejects_future_versions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "migration.sqlite"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE preexisting_sentinel(value TEXT)")
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0

    with SQLiteKnowledgeStore(database) as store:
        assert store.schema_version == 1
        with closing(sqlite3.connect(database)) as inspection, inspection:
            table_names = {
                row[0]
                for row in inspection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
        assert not any(
            token in name for name in table_names for token in ("run", "event", "action")
        )
        store.put(Claim(statement="survives reopen"))
    with SQLiteKnowledgeStore(database) as reopened:
        assert reopened.query(KnowledgeQuery(record_types=("claim",)))[0].record == Claim(
            statement="survives reopen"
        )

    future = tmp_path / "future.sqlite"
    with closing(sqlite3.connect(future)) as connection, connection:
        connection.execute("PRAGMA user_version = 2")
    with pytest.raises(ValueError, match="newer"):
        SQLiteKnowledgeStore(future)

    incomplete = tmp_path / "incomplete.sqlite"
    with closing(sqlite3.connect(incomplete)) as connection, connection:
        connection.execute("CREATE TABLE knowledge_records(root TEXT PRIMARY KEY)")
        connection.execute("PRAGMA user_version = 1")
    with pytest.raises(ValueError, match="schema is incomplete"):
        SQLiteKnowledgeStore(incomplete)


def test_closed_and_malformed_store_operations_fail_closed(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "closed.sqlite")
    store.close()
    store.close()

    with pytest.raises(RuntimeError, match="closed"):
        store.query()
    with pytest.raises(RuntimeError, match="closed"):
        _ = store.schema_version
    with pytest.raises(TypeError, match="path"):
        SQLiteKnowledgeStore(1)  # type: ignore[arg-type]

    with SQLiteKnowledgeStore() as active:
        assert active.put_many(()) == ()
        with pytest.raises(TypeError, match="sequence"):
            active.put_many("write")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="KnowledgeWrite"):
            active.put_many((Claim(statement="bad"),))  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="root must be text"):
            active.get(1)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="KnowledgeQuery"):
            active.query(Claim(statement="bad"))  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="must be a RecordRef"):
            active.relationships(source=Claim(statement="bad"))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="filter is required"):
            active.relationships(relationship=" ")
