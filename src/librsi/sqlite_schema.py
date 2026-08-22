"""Owned schema and transactional migration for SQLite knowledge persistence."""

from __future__ import annotations

import sqlite3

from .sqlite_support import create_if_missing, validate_schema_objects

KNOWLEDGE_SCHEMA_VERSION = 1

_TABLE_DEFINITIONS = {
    "knowledge_records": """
        CREATE TABLE knowledge_records (
            root TEXT PRIMARY KEY,
            record_type TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            serialized TEXT NOT NULL,
            evidence_type TEXT
        )
    """,
    "knowledge_occurrences": """
        CREATE TABLE knowledge_occurrences (
            occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_root TEXT NOT NULL REFERENCES knowledge_records(root),
            source_run_id TEXT,
            valid INTEGER NOT NULL CHECK (valid IN (0, 1)),
            stored_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
        )
    """,
    "knowledge_targets": """
        CREATE TABLE knowledge_targets (
            record_root TEXT NOT NULL REFERENCES knowledge_records(root),
            target_root TEXT NOT NULL,
            PRIMARY KEY (record_root, target_root)
        )
    """,
    "knowledge_snapshots": """
        CREATE TABLE knowledge_snapshots (
            record_root TEXT NOT NULL REFERENCES knowledge_records(root),
            snapshot_root TEXT NOT NULL,
            PRIMARY KEY (record_root, snapshot_root)
        )
    """,
    "knowledge_subjects": """
        CREATE TABLE knowledge_subjects (
            record_root TEXT NOT NULL REFERENCES knowledge_records(root),
            subject_type TEXT NOT NULL,
            subject_root TEXT NOT NULL,
            PRIMARY KEY (record_root, subject_type, subject_root)
        )
    """,
    "knowledge_lineage": """
        CREATE TABLE knowledge_lineage (
            record_root TEXT NOT NULL REFERENCES knowledge_records(root),
            lineage_type TEXT NOT NULL,
            lineage_root TEXT NOT NULL,
            PRIMARY KEY (record_root, lineage_type, lineage_root)
        )
    """,
    "knowledge_relationships": """
        CREATE TABLE knowledge_relationships (
            relationship_root TEXT PRIMARY KEY REFERENCES knowledge_records(root),
            source_type TEXT NOT NULL,
            source_root TEXT NOT NULL REFERENCES knowledge_records(root),
            relationship TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_root TEXT NOT NULL REFERENCES knowledge_records(root)
        )
    """,
}

_INDEX_DEFINITIONS = {
    "ix_knowledge_occurrences_run": """
        CREATE INDEX ix_knowledge_occurrences_run
        ON knowledge_occurrences(source_run_id, occurrence_id)
    """,
    "ix_knowledge_records_type": """
        CREATE INDEX ix_knowledge_records_type ON knowledge_records(record_type)
    """,
}


def validate_knowledge_schema(connection: sqlite3.Connection) -> None:
    """Reject any claimed schema that differs from the complete owned v1 shape."""

    validate_schema_objects(
        connection,
        tables=_TABLE_DEFINITIONS,
        indexes=_INDEX_DEFINITIONS,
        label="knowledge",
    )


def migrate_knowledge_schema(connection: sqlite3.Connection) -> None:
    """Create or validate one schema version without committing partial migration."""

    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version > KNOWLEDGE_SCHEMA_VERSION:
        raise ValueError("SQLite knowledge schema is newer than this libRSI version")
    if version == KNOWLEDGE_SCHEMA_VERSION:
        validate_knowledge_schema(connection)
        return

    connection.execute("BEGIN IMMEDIATE")
    try:
        for definition in _TABLE_DEFINITIONS.values():
            connection.execute(create_if_missing(definition, kind="TABLE"))
        for definition in _INDEX_DEFINITIONS.values():
            connection.execute(create_if_missing(definition, kind="INDEX"))
        validate_knowledge_schema(connection)
        connection.execute(f"PRAGMA user_version = {KNOWLEDGE_SCHEMA_VERSION}")
        connection.commit()
    except Exception as error:
        connection.rollback()
        if isinstance(error, ValueError):
            raise
        raise ValueError("SQLite knowledge schema migration failed") from error
