"""Small shared helpers for exact, fail-closed SQLite schema ownership."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping


def normalize_schema_sql(value: str) -> str:
    """Normalize SQL syntax while preserving every byte inside quoted literals."""

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


def create_if_missing(definition: str, *, kind: str) -> str:
    prefix = f"CREATE {kind} "
    return definition.replace(prefix, f"{prefix}IF NOT EXISTS ", 1)


def validate_schema_objects(
    connection: sqlite3.Connection,
    *,
    tables: Mapping[str, str],
    indexes: Mapping[str, str],
    label: str,
) -> None:
    for kind, definitions in (("table", tables), ("index", indexes)):
        for name, definition in definitions.items():
            row = connection.execute(
                "SELECT type, sql FROM sqlite_master WHERE name = ?",
                (name,),
            ).fetchone()
            if (
                row is None
                or row[0] != kind
                or not isinstance(row[1], str)
                or normalize_schema_sql(row[1]) != normalize_schema_sql(definition)
            ):
                raise ValueError(f"SQLite {label} schema is incomplete for {kind} {name!r}")

    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError(f"SQLite {label} schema violates referential integrity")
