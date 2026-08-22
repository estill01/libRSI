"""Owned schema and transactional migration for SQLite knowledge persistence."""

from __future__ import annotations

import sqlite3

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


def _normalize_sql(value: str) -> str:
    normalized: list[str] = []
    quote: str | None = None
    pending_space = False
    index = 0
    while index < len(value):
        character = value[index]
        if quote is not None:
            normalized.append(character)
            if character == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    normalized.append(value[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            if pending_space and normalized:
                normalized.append(" ")
            pending_space = False
            quote = character
            normalized.append(character)
        elif character.isspace():
            pending_space = True
        else:
            if pending_space and normalized:
                normalized.append(" ")
            pending_space = False
            normalized.append(character.upper())
        index += 1
    return "".join(normalized).strip()


def _create_if_missing(definition: str, *, kind: str) -> str:
    prefix = f"CREATE {kind} "
    return definition.replace(prefix, f"{prefix}IF NOT EXISTS ", 1)


def validate_knowledge_schema(connection: sqlite3.Connection) -> None:
    """Reject any claimed schema that differs from the complete owned v1 shape."""

    for kind, definitions in (
        ("table", _TABLE_DEFINITIONS),
        ("index", _INDEX_DEFINITIONS),
    ):
        for name, definition in definitions.items():
            row = connection.execute(
                "SELECT type, sql FROM sqlite_master WHERE name = ?",
                (name,),
            ).fetchone()
            if (
                row is None
                or row[0] != kind
                or not isinstance(row[1], str)
                or _normalize_sql(row[1]) != _normalize_sql(definition)
            ):
                raise ValueError(f"SQLite knowledge schema is incomplete for {kind} {name!r}")

    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("SQLite knowledge schema violates referential integrity")


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
            connection.execute(_create_if_missing(definition, kind="TABLE"))
        for definition in _INDEX_DEFINITIONS.values():
            connection.execute(_create_if_missing(definition, kind="INDEX"))
        validate_knowledge_schema(connection)
        connection.execute(f"PRAGMA user_version = {KNOWLEDGE_SCHEMA_VERSION}")
        connection.commit()
    except Exception as error:
        connection.rollback()
        if isinstance(error, ValueError):
            raise
        raise ValueError("SQLite knowledge schema migration failed") from error
