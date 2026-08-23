"""Deterministic external-agent response and error envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..identity import canonical_json
from .schemas import EXTERNAL_AGENT_SCHEMA, EXTERNAL_AGENT_SCHEMA_VERSION, EXTERNAL_ERROR_SCHEMA


def response_document(
    operation: str,
    *,
    data: Mapping[str, Any],
    run_id: str | None = None,
    state_root: str | None = None,
) -> dict[str, Any]:
    if type(operation) is not str or not operation.strip():
        raise ValueError("external operation is required")
    if not isinstance(data, Mapping):
        raise TypeError("external response data must be a mapping")
    return {
        "$schema": EXTERNAL_AGENT_SCHEMA,
        "schema_version": EXTERNAL_AGENT_SCHEMA_VERSION,
        "operation": operation.strip(),
        "run_id": run_id,
        "state_root": state_root,
        "data": dict(data),
    }


def serialize_response(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping):
        raise TypeError("external response must be a mapping")
    return canonical_json(dict(document))


def error_document(error: Exception) -> dict[str, Any]:
    if not isinstance(error, Exception):
        raise TypeError("external errors require an Exception")
    return {
        "$schema": EXTERNAL_ERROR_SCHEMA,
        "schema_version": EXTERNAL_AGENT_SCHEMA_VERSION,
        "error_type": type(error).__name__,
        "message": str(error),
    }
