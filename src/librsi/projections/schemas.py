"""Published JSON Schema documents for stable projection envelopes."""

from __future__ import annotations

from ..identity import FrozenMap
from .records import EVENT_PROJECTION_SCHEMA, OUTCOME_PROJECTION_SCHEMA

_RECORD_SCHEMA = {
    "type": "object",
    "required": ["$schema", "record_type", "schema_version", "root", "data", "metadata"],
    "properties": {
        "$schema": {"const": "librsi.record/v1"},
        "record_type": {"type": "string", "minLength": 1},
        "schema_version": {"type": "integer", "const": 1},
        "root": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "data": {"type": "object"},
        "metadata": {"type": "object"},
    },
    "additionalProperties": False,
}

OUTCOME_PROJECTION_JSON_SCHEMA = FrozenMap(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": OUTCOME_PROJECTION_SCHEMA,
        "type": "object",
        "required": [
            "$schema",
            "schema_version",
            "projection_root",
            "workflow",
            "result_root",
            "outcome_root",
            "result",
            "outcome",
            "metadata",
        ],
        "properties": {
            "$schema": {"const": OUTCOME_PROJECTION_SCHEMA},
            "schema_version": {"type": "integer", "const": 1},
            "projection_root": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "workflow": {"enum": ["validation", "investigation", "improvement", "rsi"]},
            "result_root": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "outcome_root": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "result": _RECORD_SCHEMA,
            "outcome": _RECORD_SCHEMA,
            "metadata": {"type": "object"},
        },
        "additionalProperties": False,
    }
)

EVENT_PROJECTION_JSON_SCHEMA = FrozenMap(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": EVENT_PROJECTION_SCHEMA,
        "type": "object",
        "required": [
            "$schema",
            "schema_version",
            "projection_root",
            "event_root",
            "run_root",
            "sequence",
            "kind",
            "previous_event_root",
            "action_root",
            "result_root",
            "outcome_root",
            "failure_root",
            "emitted_action_roots",
            "event",
            "metadata",
        ],
        "properties": {
            "$schema": {"const": EVENT_PROJECTION_SCHEMA},
            "schema_version": {"type": "integer", "const": 1},
            "projection_root": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "event_root": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "run_root": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "sequence": {"type": "integer", "minimum": 0},
            "kind": {"type": "string", "minLength": 1},
            "previous_event_root": {"type": ["string", "null"]},
            "action_root": {"type": ["string", "null"]},
            "result_root": {"type": ["string", "null"]},
            "outcome_root": {"type": ["string", "null"]},
            "failure_root": {"type": ["string", "null"]},
            "emitted_action_roots": {"type": "array", "items": {"type": "string"}},
            "event": _RECORD_SCHEMA,
            "metadata": {"type": "object"},
        },
        "additionalProperties": False,
    }
)


def projection_schema(schema: str) -> FrozenMap:
    """Return the immutable published schema for a supported projection kind."""

    if schema == OUTCOME_PROJECTION_SCHEMA:
        return OUTCOME_PROJECTION_JSON_SCHEMA
    if schema == EVENT_PROJECTION_SCHEMA:
        return EVENT_PROJECTION_JSON_SCHEMA
    raise ValueError("unsupported projection schema")
