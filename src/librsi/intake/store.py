"""Intake receipts are checkpoints, never a second workflow state machine."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from ..identity import canonical_json


class IntakeStore(Protocol):
    def load(self, request_id: str) -> dict[str, Any] | None: ...
    def save(self, request_id: str, receipt: Mapping[str, Any]) -> None: ...
    def close(self) -> None: ...


class SQLiteIntakeStore:
    """Single-owner store. The service serializes all operations on this store."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS intake_receipts (request_id TEXT PRIMARY KEY, document TEXT NOT NULL)"
        )

    def load(self, request_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT document FROM intake_receipts WHERE request_id = ?", (request_id,)
        ).fetchone()
        return None if row is None else json.loads(row[0])

    def save(self, request_id: str, receipt: Mapping[str, Any]) -> None:
        existing = self.load(request_id)
        if existing is not None and canonical_json(existing["input"]) != canonical_json(
            receipt["input"]
        ):
            raise ValueError("intake request id already names different input")
        encoded = canonical_json(dict(receipt))
        with self._connection:
            self._connection.execute(
                "INSERT INTO intake_receipts(request_id, document) VALUES (?, ?) "
                "ON CONFLICT(request_id) DO UPDATE SET document = excluded.document",
                (request_id, encoded),
            )

    def close(self) -> None:
        self._connection.close()
