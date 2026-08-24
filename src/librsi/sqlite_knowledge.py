"""Minimal transactional SQLite reference backend for ``KnowledgeStore``."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

from .knowledge import (
    KnowledgeQuery,
    KnowledgeWrite,
    StoredKnowledge,
    bound_target_snapshots,
    label_currentness,
    subject_refs,
    target_refs,
    validate_knowledge_record,
)
from .records import (
    Evidence,
    KnowledgeRelationship,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    deserialize_record,
)
from .sqlite_schema import KNOWLEDGE_SCHEMA_VERSION, migrate_knowledge_schema


class SQLiteKnowledgeStore:
    """Thin, zero-service reference storage for reusable canonical knowledge."""

    SCHEMA_VERSION = KNOWLEDGE_SCHEMA_VERSION

    def __init__(self, path: str | Path = ":memory:") -> None:
        if not isinstance(path, (str, Path)):
            raise TypeError("SQLite knowledge path must be text or a Path")
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            migrate_knowledge_schema(self._connection)
        except Exception:
            self._connection.close()
            self._closed = True
            raise

    @property
    def schema_version(self) -> int:
        self._ensure_open()
        return int(self._connection.execute("PRAGMA user_version").fetchone()[0])

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQLite knowledge store is closed")

    @staticmethod
    def _write_items(writes: Sequence[KnowledgeWrite]) -> tuple[KnowledgeWrite, ...]:
        if isinstance(writes, (str, bytes, bytearray)) or not isinstance(writes, Sequence):
            raise TypeError("knowledge writes must be a sequence")
        items = tuple(writes)
        if any(not isinstance(item, KnowledgeWrite) for item in items):
            raise TypeError("knowledge writes must contain KnowledgeWrite values")
        return items

    def _insert_record(self, record: SemanticRecord, serialized: str) -> None:
        existing = self._connection.execute(
            """
            SELECT root, record_type, schema_version, serialized, evidence_type
            FROM knowledge_records WHERE root = ?
            """,
            (record.root,),
        ).fetchone()
        if existing is not None:
            if (
                existing["record_type"] != record.record_type
                or existing["schema_version"] != record.schema_version
                or existing["serialized"] != serialized
                or existing["evidence_type"]
                != (record.evidence_type if isinstance(record, Evidence) else None)
            ):
                raise ValueError("duplicate semantic root has divergent canonical bytes or type")
            return
        evidence_type = record.evidence_type if isinstance(record, Evidence) else None
        self._connection.execute(
            """
            INSERT INTO knowledge_records
                (root, record_type, schema_version, serialized, evidence_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.root,
                record.record_type,
                record.schema_version,
                serialized,
                evidence_type,
            ),
        )

    def _index_record(self, record: SemanticRecord) -> None:
        for target in target_refs(record):
            self._connection.execute(
                "INSERT OR IGNORE INTO knowledge_targets(record_root, target_root) VALUES (?, ?)",
                (record.root, target.root),
            )
        for snapshot in bound_target_snapshots(record):
            self._connection.execute(
                "INSERT OR IGNORE INTO knowledge_snapshots(record_root, snapshot_root) "
                "VALUES (?, ?)",
                (record.root, snapshot.root),
            )
        for subject in subject_refs(record):
            self._connection.execute(
                "INSERT OR IGNORE INTO knowledge_subjects"
                "(record_root, subject_type, subject_root) VALUES (?, ?, ?)",
                (record.root, subject.record_type, subject.root),
            )
        for lineage in record.lineage:
            self._connection.execute(
                "INSERT OR IGNORE INTO knowledge_lineage"
                "(record_root, lineage_type, lineage_root) VALUES (?, ?, ?)",
                (record.root, lineage.record_type, lineage.root),
            )

    def _require_endpoint(self, endpoint: RecordRef) -> None:
        row = self._connection.execute(
            """
            SELECT root, record_type, schema_version, serialized, evidence_type
            FROM knowledge_records WHERE root = ?
            """,
            (endpoint.root,),
        ).fetchone()
        if row is None or not endpoint.matches(self._decode_row(row)):
            raise ValueError("knowledge relationship endpoint is not stored at its exact type/root")

    def _index_relationship(self, relationship: KnowledgeRelationship) -> None:
        self._require_endpoint(relationship.source)
        self._require_endpoint(relationship.target)
        self._connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_relationships
                (relationship_root, source_type, source_root, relationship,
                 target_type, target_root)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                relationship.root,
                relationship.source.record_type,
                relationship.source.root,
                relationship.relationship,
                relationship.target.record_type,
                relationship.target.root,
            ),
        )

    @staticmethod
    def _decode_record(
        serialized: str,
        *,
        expected_root: str,
        expected_type: str,
    ) -> SemanticRecord:
        record = deserialize_record(serialized)
        if record.root != expected_root or record.record_type != expected_type:
            raise ValueError("stored knowledge root/type does not match canonical bytes")
        return record

    @classmethod
    def _decode_row(cls, row: sqlite3.Row) -> SemanticRecord:
        record = cls._decode_record(
            row["serialized"],
            expected_root=row["root"],
            expected_type=row["record_type"],
        )
        if row["schema_version"] != record.schema_version:
            raise ValueError("stored knowledge schema version does not match canonical bytes")
        evidence_type = record.evidence_type if isinstance(record, Evidence) else None
        if row["evidence_type"] != evidence_type:
            raise ValueError("stored knowledge evidence type does not match canonical bytes")
        return record

    def _projection(
        self,
        table: str,
        columns: str,
        record_root: str,
    ) -> set[tuple[object, ...]]:
        return {
            tuple(row)
            for row in self._connection.execute(
                f"SELECT {columns} FROM {table} WHERE record_root = ?",
                (record_root,),
            )
        }

    def _validate_projection(self, record: SemanticRecord) -> None:
        expected = {
            "knowledge_targets": {(item.root,) for item in target_refs(record)},
            "knowledge_snapshots": {(item.root,) for item in bound_target_snapshots(record)},
            "knowledge_subjects": {(item.record_type, item.root) for item in subject_refs(record)},
            "knowledge_lineage": {(item.record_type, item.root) for item in record.lineage},
        }
        actual = {
            "knowledge_targets": self._projection("knowledge_targets", "target_root", record.root),
            "knowledge_snapshots": self._projection(
                "knowledge_snapshots", "snapshot_root", record.root
            ),
            "knowledge_subjects": self._projection(
                "knowledge_subjects", "subject_type, subject_root", record.root
            ),
            "knowledge_lineage": self._projection(
                "knowledge_lineage", "lineage_type, lineage_root", record.root
            ),
        }
        for table in expected:
            if actual[table] != expected[table]:
                raise ValueError(
                    f"stored knowledge projection diverges from canonical record in {table}"
                )

        relationship_rows = {
            tuple(row)
            for row in self._connection.execute(
                """
                SELECT source_type, source_root, relationship, target_type, target_root
                FROM knowledge_relationships WHERE relationship_root = ?
                """,
                (record.root,),
            )
        }
        if isinstance(record, KnowledgeRelationship):
            expected_relationships = {
                (
                    record.source.record_type,
                    record.source.root,
                    record.relationship,
                    record.target.record_type,
                    record.target.root,
                )
            }
            self._require_endpoint(record.source)
            self._require_endpoint(record.target)
        else:
            expected_relationships = set()
        if relationship_rows != expected_relationships:
            raise ValueError(
                "stored knowledge relationship projection diverges from canonical record"
            )

    def _validated_row(self, row: sqlite3.Row) -> SemanticRecord:
        record = self._decode_row(row)
        self._validate_projection(record)
        return record

    def _stored(
        self,
        occurrence_id: int,
        *,
        current_snapshot: TargetSnapshot | None = None,
    ) -> StoredKnowledge:
        row = self._connection.execute(
            """
            SELECT r.root, o.source_run_id, o.valid, o.stored_at,
                   r.record_type, r.schema_version, r.serialized, r.evidence_type
            FROM knowledge_occurrences AS o
            JOIN knowledge_records AS r ON r.root = o.record_root
            WHERE o.occurrence_id = ?
            """,
            (occurrence_id,),
        ).fetchone()
        if row is None:  # pragma: no cover - internal transaction invariant
            raise RuntimeError("knowledge occurrence disappeared during retrieval")
        record = self._validated_row(row)
        if type(row["valid"]) is not int or row["valid"] not in (0, 1):
            raise ValueError("stored knowledge validity is not canonical")
        return StoredKnowledge(
            record=record,
            source_run_id=row["source_run_id"],
            valid=row["valid"] == 1,
            stored_at=row["stored_at"],
            currentness=label_currentness(record, current_snapshot),
        )

    def put(
        self,
        record: SemanticRecord,
        *,
        source_run_id: str | None = None,
        valid: bool = True,
    ) -> StoredKnowledge:
        return self.put_many(
            (KnowledgeWrite(record=record, source_run_id=source_run_id, valid=valid),)
        )[0]

    def put_many(self, writes: Sequence[KnowledgeWrite]) -> tuple[StoredKnowledge, ...]:
        self._ensure_open()
        items = self._write_items(writes)
        if not items:
            return ()
        serialized = tuple(validate_knowledge_record(item.record) for item in items)
        occurrence_ids: list[int] = []
        relationships: list[KnowledgeRelationship] = []
        with self._connection:
            for item, payload in zip(items, serialized, strict=True):
                self._insert_record(item.record, payload)
                self._index_record(item.record)
                cursor = self._connection.execute(
                    """
                    INSERT INTO knowledge_occurrences(record_root, source_run_id, valid)
                    VALUES (?, ?, ?)
                    """,
                    (item.record.root, item.source_run_id, int(item.valid)),
                )
                if cursor.lastrowid is None:  # pragma: no cover - SQLite INSERT invariant
                    raise RuntimeError("knowledge occurrence insert produced no identity")
                occurrence_ids.append(cursor.lastrowid)
                if isinstance(item.record, KnowledgeRelationship):
                    relationships.append(item.record)
            for relationship in relationships:
                self._index_relationship(relationship)
            stored = tuple(self._stored(item) for item in occurrence_ids)
        return stored

    def get(self, root: str) -> SemanticRecord | None:
        self._ensure_open()
        if not isinstance(root, str):
            raise TypeError("knowledge root must be text")
        row = self._connection.execute(
            """
            SELECT root, record_type, schema_version, serialized, evidence_type
            FROM knowledge_records WHERE root = ?
            """,
            (root,),
        ).fetchone()
        if row is None:
            return None
        return self._validated_row(row)

    def query(self, query: KnowledgeQuery | None = None) -> tuple[StoredKnowledge, ...]:
        self._ensure_open()
        query = KnowledgeQuery() if query is None else query
        if not isinstance(query, KnowledgeQuery):
            raise TypeError("knowledge query must be a KnowledgeQuery")
        rows = self._connection.execute(
            """
            SELECT o.occurrence_id
            FROM knowledge_occurrences AS o
            JOIN knowledge_records AS r ON r.root = o.record_root
            ORDER BY o.occurrence_id DESC
            """,
        ).fetchall()

        results: list[StoredKnowledge] = []
        for row in rows:
            stored = self._stored(
                int(row["occurrence_id"]),
                current_snapshot=query.current_snapshot,
            )
            record = stored.record
            if query.record_types and record.record_type not in query.record_types:
                continue
            if query.target is not None and query.target.ref not in {
                item.ref for item in target_refs(record)
            }:
                continue
            if not set(query.subject_refs).issubset(subject_refs(record)):
                continue
            if not set(query.lineage_refs).issubset(record.lineage):
                continue
            if query.evidence_types and (
                not isinstance(record, Evidence) or record.evidence_type not in query.evidence_types
            ):
                continue
            if query.source_run_id is not None and stored.source_run_id != query.source_run_id:
                continue
            if query.valid is not None and stored.valid is not query.valid:
                continue
            if query.currentness is not None and stored.currentness != query.currentness:
                continue
            results.append(stored)
            if query.limit is not None and len(results) >= query.limit:
                break
        return tuple(results)

    def relationships(
        self,
        *,
        source: RecordRef | None = None,
        relationship: str | None = None,
        target: RecordRef | None = None,
    ) -> tuple[KnowledgeRelationship, ...]:
        self._ensure_open()
        for label, value in (("source", source), ("target", target)):
            if value is not None and not isinstance(value, RecordRef):
                raise TypeError(f"knowledge relationship {label} must be a RecordRef")
        if relationship is not None:
            if not isinstance(relationship, str):
                raise TypeError("knowledge relationship filter must be text")
            relationship = relationship.strip()
            if not relationship:
                raise ValueError("knowledge relationship filter is required")
        rows = self._connection.execute(
            """
            SELECT root, record_type, schema_version, serialized, evidence_type
            FROM knowledge_records ORDER BY root
            """,
        ).fetchall()
        records: list[KnowledgeRelationship] = []
        for row in rows:
            record = self._validated_row(row)
            if not isinstance(record, KnowledgeRelationship):
                continue
            if source is not None and record.source != source:
                continue
            if relationship is not None and record.relationship != relationship:
                continue
            if target is not None and record.target != target:
                continue
            records.append(record)
        return tuple(records)

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> SQLiteKnowledgeStore:
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
