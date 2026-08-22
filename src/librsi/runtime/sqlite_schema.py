"""Exact owned schema and transactional migration for SQLite runtime history."""

from __future__ import annotations

import sqlite3

from ..sqlite_support import create_if_missing, validate_schema_objects

RUNTIME_SCHEMA_VERSION = 1
RUNTIME_SCHEMA_COMPONENT = "runtime"

_TABLE_DEFINITIONS = {
    "runtime_schema": """
        CREATE TABLE runtime_schema (
            component TEXT PRIMARY KEY CHECK (component = 'runtime'),
            version INTEGER NOT NULL CHECK (version > 0)
        )
    """,
    "runtime_runs": """
        CREATE TABLE runtime_runs (
            run_id TEXT PRIMARY KEY,
            run_root TEXT UNIQUE NOT NULL,
            serialized TEXT NOT NULL
        )
    """,
    "runtime_events": """
        CREATE TABLE runtime_events (
            run_id TEXT NOT NULL REFERENCES runtime_runs(run_id),
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            event_root TEXT UNIQUE NOT NULL,
            serialized TEXT NOT NULL,
            PRIMARY KEY (run_id, sequence)
        )
    """,
    "runtime_states": """
        CREATE TABLE runtime_states (
            state_root TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runtime_runs(run_id),
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            serialized TEXT NOT NULL,
            UNIQUE (run_id, sequence)
        )
    """,
    "runtime_transitions": """
        CREATE TABLE runtime_transitions (
            transition_root TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runtime_runs(run_id),
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            event_root TEXT UNIQUE NOT NULL REFERENCES runtime_events(event_root),
            prior_state_root TEXT REFERENCES runtime_states(state_root),
            next_state_root TEXT UNIQUE NOT NULL REFERENCES runtime_states(state_root),
            serialized TEXT NOT NULL,
            UNIQUE (run_id, sequence)
        )
    """,
    "runtime_current": """
        CREATE TABLE runtime_current (
            run_id TEXT PRIMARY KEY REFERENCES runtime_runs(run_id),
            state_root TEXT UNIQUE NOT NULL REFERENCES runtime_states(state_root),
            sequence INTEGER NOT NULL CHECK (sequence >= 0),
            transition_root TEXT UNIQUE NOT NULL
                REFERENCES runtime_transitions(transition_root)
        )
    """,
}


def validate_runtime_schema(connection: sqlite3.Connection) -> None:
    """Reject any runtime schema that differs from the complete owned v1 shape."""

    validate_schema_objects(
        connection,
        tables=_TABLE_DEFINITIONS,
        indexes={},
        label="runtime",
    )
    rows = [
        tuple(row)
        for row in connection.execute("SELECT component, version FROM runtime_schema").fetchall()
    ]
    if rows != [(RUNTIME_SCHEMA_COMPONENT, RUNTIME_SCHEMA_VERSION)]:
        raise ValueError("SQLite runtime schema metadata is incomplete or unsupported")


def migrate_runtime_schema(connection: sqlite3.Connection) -> None:
    """Create or validate runtime schema without sharing knowledge schema versioning."""

    connection.execute("BEGIN IMMEDIATE")
    try:
        owned_names = tuple(_TABLE_DEFINITIONS)
        existing = {
            row[0]
            for row in connection.execute(
                f"SELECT name FROM sqlite_master WHERE type = 'table' "
                f"AND name IN ({','.join('?' for _ in owned_names)})",
                owned_names,
            )
        }
        if "runtime_schema" in existing:
            validate_schema_objects(
                connection,
                tables={"runtime_schema": _TABLE_DEFINITIONS["runtime_schema"]},
                indexes={},
                label="runtime",
            )
            rows = connection.execute("SELECT component, version FROM runtime_schema").fetchall()
            if len(rows) != 1 or rows[0][0] != RUNTIME_SCHEMA_COMPONENT:
                raise ValueError("SQLite runtime schema metadata is incomplete or unsupported")
            version = int(rows[0][1])
            if version > RUNTIME_SCHEMA_VERSION:
                raise ValueError("SQLite runtime schema is newer than this libRSI version")
            if version != RUNTIME_SCHEMA_VERSION:
                raise ValueError("SQLite runtime schema version is unsupported")
            validate_runtime_schema(connection)
        else:
            if existing:
                raise ValueError("SQLite runtime schema is incomplete without metadata")
            for definition in _TABLE_DEFINITIONS.values():
                connection.execute(create_if_missing(definition, kind="TABLE"))
            connection.execute(
                "INSERT INTO runtime_schema(component, version) VALUES (?, ?)",
                (RUNTIME_SCHEMA_COMPONENT, RUNTIME_SCHEMA_VERSION),
            )
            validate_runtime_schema(connection)
        connection.commit()
    except Exception as error:
        connection.rollback()
        if isinstance(error, ValueError):
            raise
        raise ValueError("SQLite runtime schema migration failed") from error
