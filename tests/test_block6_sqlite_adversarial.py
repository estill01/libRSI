from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from librsi import (
    Claim,
    Evidence,
    KnowledgeRelationship,
    KnowledgeWrite,
    SQLiteKnowledgeStore,
    TargetRef,
    TargetSnapshot,
)


def _records() -> tuple[
    TargetRef,
    TargetSnapshot,
    Claim,
    Evidence,
    KnowledgeRelationship,
]:
    target = TargetRef(target_id="adversarial", kind="simulation")
    snapshot = TargetSnapshot(target=target, revision="v1", state={"value": 1})
    claim = Claim(statement="The simulation is stable", target=target)
    evidence = Evidence(
        evidence_type="support",
        data={"value": 1},
        subject_refs=(claim.ref,),
        target_snapshot=snapshot,
        lineage=(claim.ref,),
    )
    relationship = KnowledgeRelationship(
        source=claim.ref,
        relationship="supported_by",
        target=evidence.ref,
    )
    return target, snapshot, claim, evidence, relationship


def _seed(
    database: Path,
) -> tuple[
    TargetRef,
    TargetSnapshot,
    Claim,
    Evidence,
    KnowledgeRelationship,
]:
    records = _records()
    with SQLiteKnowledgeStore(database) as store:
        store.put_many(tuple(KnowledgeWrite(record) for record in records))
    return records


def test_claimed_v1_schema_with_columns_but_without_constraints_is_rejected(
    tmp_path: Path,
) -> None:
    database = tmp_path / "malformed-v1.sqlite"
    with SQLiteKnowledgeStore(database):
        pass
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("ALTER TABLE knowledge_occurrences RENAME TO malformed_old")
        connection.execute(
            """
            CREATE TABLE knowledge_occurrences (
                occurrence_id INTEGER,
                record_root TEXT,
                source_run_id TEXT,
                valid INTEGER,
                stored_at TEXT
            )
            """
        )
        connection.execute("DROP TABLE malformed_old")
        connection.execute(
            """
            CREATE INDEX ix_knowledge_occurrences_run
            ON knowledge_occurrences(source_run_id, occurrence_id)
            """
        )

    with pytest.raises(ValueError, match="schema is incomplete"):
        SQLiteKnowledgeStore(database)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM knowledge_records").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM knowledge_occurrences").fetchone()[0] == 0


def test_case_altered_strftime_default_is_rejected_during_construction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "malformed-default.sqlite"
    with SQLiteKnowledgeStore(database):
        pass
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("ALTER TABLE knowledge_occurrences RENAME TO malformed_old")
        connection.execute(
            """
            CREATE TABLE knowledge_occurrences (
                occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_root TEXT NOT NULL REFERENCES knowledge_records(root),
                source_run_id TEXT,
                valid INTEGER NOT NULL CHECK (valid IN (0, 1)),
                stored_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%M-%DT%H:%M:%FZ', 'now')
                )
            )
            """
        )
        connection.execute("DROP TABLE malformed_old")
        connection.execute(
            """
            CREATE INDEX ix_knowledge_occurrences_run
            ON knowledge_occurrences(source_run_id, occurrence_id)
            """
        )

    with pytest.raises(ValueError, match="schema is incomplete"):
        SQLiteKnowledgeStore(database)


def test_failed_v0_migration_rolls_back_version_tables_indexes_and_existing_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "partial-v0.sqlite"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE knowledge_records(root TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO knowledge_records(root) VALUES ('sentinel')")

    with pytest.raises(ValueError, match="schema migration failed"):
        SQLiteKnowledgeStore(database)

    with closing(sqlite3.connect(database)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'knowledge_%'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'ix_knowledge_%'"
            )
        }
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert tables == {"knowledge_records"}
        assert indexes == set()
        assert connection.execute("SELECT root FROM knowledge_records").fetchone()[0] == "sentinel"


def test_missing_owned_index_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "missing-index.sqlite"
    with SQLiteKnowledgeStore(database):
        pass
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("DROP INDEX ix_knowledge_records_type")

    with pytest.raises(ValueError, match="index 'ix_knowledge_records_type'"):
        SQLiteKnowledgeStore(database)


def test_reconstruction_failure_rolls_back_the_entire_write(tmp_path: Path) -> None:
    database = tmp_path / "rollback-on-reconstruction.sqlite"
    _, _, _, evidence, _ = _records()
    with SQLiteKnowledgeStore(database) as store:
        store._connection.execute(  # type: ignore[attr-defined]
            """
            CREATE TRIGGER corrupt_subject_projection
            AFTER INSERT ON knowledge_subjects
            BEGIN
                UPDATE knowledge_subjects
                SET subject_type = 'hypothesis'
                WHERE record_root = NEW.record_root;
            END
            """
        )
        with pytest.raises(ValueError, match="projection diverges"):
            store.put(evidence)

        assert store.get(evidence.root) is None
        assert store.query() == ()
        assert (
            store._connection.execute(  # type: ignore[attr-defined]
                "SELECT COUNT(*) FROM knowledge_subjects"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    ("projection", "expected_error"),
    [
        ("target", "knowledge_targets"),
        ("snapshot", "knowledge_snapshots"),
        ("subject", "knowledge_subjects"),
        ("lineage", "knowledge_lineage"),
        ("evidence_type", "evidence type"),
        ("relationship", "relationship projection"),
    ],
)
def test_corrupted_auxiliary_projection_cannot_override_canonical_queries(
    tmp_path: Path,
    projection: str,
    expected_error: str,
) -> None:
    database = tmp_path / f"corrupt-{projection}.sqlite"
    _, _, claim, evidence, relationship = _seed(database)
    mutations = {
        "target": (
            "UPDATE knowledge_targets SET target_root = ? WHERE record_root = ?",
            ("a" * 64, evidence.root),
        ),
        "snapshot": (
            "UPDATE knowledge_snapshots SET snapshot_root = ? WHERE record_root = ?",
            ("b" * 64, evidence.root),
        ),
        "subject": (
            "UPDATE knowledge_subjects SET subject_type = ? WHERE record_root = ?",
            ("hypothesis", evidence.root),
        ),
        "lineage": (
            "UPDATE knowledge_lineage SET lineage_type = ? WHERE record_root = ?",
            ("hypothesis", evidence.root),
        ),
        "evidence_type": (
            "UPDATE knowledge_records SET evidence_type = ? WHERE root = ?",
            ("counterexample", evidence.root),
        ),
        "relationship": (
            "UPDATE knowledge_relationships SET source_type = ? WHERE relationship_root = ?",
            ("hypothesis", relationship.root),
        ),
    }
    statement, parameters = mutations[projection]
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(statement, parameters)

    with (
        SQLiteKnowledgeStore(database) as store,
        pytest.raises(ValueError, match=expected_error),
    ):
        if projection == "relationship":
            store.relationships(source=claim.ref)
        else:
            store.query()
