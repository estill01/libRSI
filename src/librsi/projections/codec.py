"""Deterministic JSON codecs and reconstruction for projection envelopes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from ..identity import FrozenMap, canonical_json
from ..improvement import ImprovementResult
from ..investigation import InvestigationResult
from ..records import Outcome, record_from_dict
from ..rsi import RSIResult
from ..runtime import Event
from ..validation import ValidationResult
from .records import (
    EVENT_PROJECTION_SCHEMA,
    OUTCOME_PROJECTION_SCHEMA,
    PROJECTION_SCHEMA_VERSION,
    EventProjection,
    OutcomeProjection,
    Projection,
    ResultRecord,
)


def _event_fields(event: Event) -> dict[str, object]:
    return {
        "event_root": event.root,
        "run_root": event.run.root,
        "sequence": event.sequence,
        "kind": event.kind,
        "previous_event_root": (
            None if event.previous_event is None else event.previous_event.root
        ),
        "action_root": None if event.action is None else event.action.root,
        "result_root": None if event.result is None else event.result.root,
        "outcome_root": None if event.outcome is None else event.outcome.root,
        "failure_root": None if event.failure is None else event.failure.root,
        "emitted_action_roots": [item.root for item in event.emitted_actions],
    }


def projection_to_dict(projection: Projection) -> dict[str, object]:
    """Return the closed, versioned JSON object for one projection."""

    if type(projection) is OutcomeProjection:
        return {
            "$schema": projection.SCHEMA,
            "schema_version": projection.SCHEMA_VERSION,
            "projection_root": projection.projection_root,
            "workflow": projection.workflow,
            "result_root": projection.result.root,
            "outcome_root": projection.outcome.root,
            "result": projection.result.to_dict(),
            "outcome": projection.outcome.to_dict(),
            "metadata": cast(FrozenMap, projection.metadata).to_dict(),
        }
    if type(projection) is EventProjection:
        return {
            "$schema": projection.SCHEMA,
            "schema_version": projection.SCHEMA_VERSION,
            "projection_root": projection.projection_root,
            **_event_fields(projection.event),
            "event": projection.event.to_dict(),
            "metadata": cast(FrozenMap, projection.metadata).to_dict(),
        }
    raise TypeError("projection serialization requires an exact projection envelope")


def serialize_projection(projection: Projection) -> str:
    """Serialize a projection to stable canonical JSON text."""

    return canonical_json(projection_to_dict(projection))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} keys must be strings")
    return cast(Mapping[str, Any], value)


def projection_from_dict(payload: Mapping[str, Any]) -> Projection:
    """Reconstruct and exactness-check a supported projection object."""

    document = _mapping(payload, "projection")
    schema = document.get("$schema")
    version = document.get("schema_version")
    if type(version) is not int or version != PROJECTION_SCHEMA_VERSION:
        raise ValueError("unsupported projection schema version")
    metadata = _mapping(document.get("metadata"), "projection metadata")
    if schema == OUTCOME_PROJECTION_SCHEMA:
        result = record_from_dict(_mapping(document.get("result"), "projection result"))
        outcome = record_from_dict(_mapping(document.get("outcome"), "projection outcome"))
        if (
            type(result)
            not in {
                ValidationResult,
                InvestigationResult,
                ImprovementResult,
                RSIResult,
            }
            or type(outcome) is not Outcome
        ):
            raise ValueError("outcome projection contains unsupported canonical records")
        workflow = document.get("workflow")
        if not isinstance(workflow, str):
            raise ValueError("outcome projection workflow is required")
        projection: Projection = OutcomeProjection(
            workflow=workflow,
            result=cast(ResultRecord, result),
            outcome=outcome,
            metadata=metadata,
        )
    elif schema == EVENT_PROJECTION_SCHEMA:
        event = record_from_dict(_mapping(document.get("event"), "projection event"))
        if type(event) is not Event:
            raise ValueError("event projection does not contain a canonical Event")
        projection = EventProjection(event=event, metadata=metadata)
    else:
        raise ValueError("unsupported projection schema")
    if dict(document) != projection_to_dict(projection):
        raise ValueError("projection fields diverge from their canonical records")
    return projection


def deserialize_projection(serialized: str) -> Projection:
    """Deserialize and integrity-check a projection JSON document."""

    if not isinstance(serialized, str):
        raise TypeError("serialized projection must be text")
    try:
        payload = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise ValueError("serialized projection must contain valid JSON") from error
    return projection_from_dict(_mapping(payload, "serialized projection"))


def reconstruct_result(projection: OutcomeProjection) -> ResultRecord:
    """Return the exact canonical result retained by an outcome projection."""

    if type(projection) is not OutcomeProjection:
        raise TypeError("result reconstruction requires an OutcomeProjection")
    return projection.result
