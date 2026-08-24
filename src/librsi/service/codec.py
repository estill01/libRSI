"""Strict transport codecs for service-owned operational inputs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from ..knowledge import KnowledgeQuery
from ..records import RecordRef, TargetRef, TargetSnapshot, record_from_dict

_QUERY_FIELDS = frozenset(
    {
        "record_types",
        "target",
        "current_snapshot",
        "subject_refs",
        "evidence_types",
        "lineage_refs",
        "source_run_id",
        "valid",
        "currentness",
        "limit",
    }
)


def require_json_size(payload: object, *, limit: int, label: str) -> None:
    """Reject an operational JSON value beyond a process-owned byte ceiling."""

    if type(limit) is not int or limit <= 0:
        raise ValueError("JSON size limit must be a positive integer")
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be JSON serializable") from error
    if len(encoded) > limit:
        raise ValueError(f"{label} exceeds the configured request byte limit")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object with text keys")
    return cast(Mapping[str, Any], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an array")
    items = tuple(value)
    if any(type(item) is not str for item in items):
        raise ValueError(f"{label} must contain strings")
    return cast(tuple[str, ...], items)


def _ref(value: object, label: str) -> RecordRef:
    document = _mapping(value, label)
    if (
        set(document) != {"$schema", "record_type", "root"}
        or document.get("$schema") != "librsi.ref/v1"
    ):
        raise ValueError(f"{label} must be an exact canonical record reference")
    return RecordRef(document["record_type"], document["root"])


def _refs(value: object, label: str) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an array")
    return tuple(_ref(item, label) for item in value)


def knowledge_query_from_dict(payload: Mapping[str, Any]) -> KnowledgeQuery:
    """Decode a closed operational query without inventing a semantic record."""

    document = _mapping(payload, "knowledge query")
    unknown = set(document) - _QUERY_FIELDS
    if unknown:
        raise ValueError(f"knowledge query has unknown fields: {sorted(unknown)}")
    target: TargetRef | None = None
    if document.get("target") is not None:
        record = record_from_dict(_mapping(document["target"], "knowledge query target"))
        if type(record) is not TargetRef:
            raise ValueError("knowledge query target must be a canonical target")
        target = record
    current_snapshot: TargetSnapshot | None = None
    if document.get("current_snapshot") is not None:
        record = record_from_dict(
            _mapping(document["current_snapshot"], "knowledge query current snapshot")
        )
        if type(record) is not TargetSnapshot:
            raise ValueError("knowledge query current snapshot must be canonical")
        current_snapshot = record
    return KnowledgeQuery(
        record_types=_strings(document.get("record_types", ()), "knowledge record types"),
        target=target,
        current_snapshot=current_snapshot,
        subject_refs=_refs(document.get("subject_refs", ()), "knowledge subject references"),
        evidence_types=_strings(document.get("evidence_types", ()), "knowledge evidence types"),
        lineage_refs=_refs(document.get("lineage_refs", ()), "knowledge lineage references"),
        source_run_id=document.get("source_run_id"),
        valid=document.get("valid"),
        currentness=document.get("currentness"),
        limit=document.get("limit"),
    )


def knowledge_query_to_dict(query: KnowledgeQuery) -> dict[str, Any]:
    """Project an operational query for transport-neutral size accounting."""

    if not isinstance(query, KnowledgeQuery):
        raise TypeError("knowledge query projection requires KnowledgeQuery")
    return {
        "record_types": list(query.record_types),
        "target": None if query.target is None else query.target.to_dict(),
        "current_snapshot": (
            None if query.current_snapshot is None else query.current_snapshot.to_dict()
        ),
        "subject_refs": [item.to_dict() for item in query.subject_refs],
        "evidence_types": list(query.evidence_types),
        "lineage_refs": [item.to_dict() for item in query.lineage_refs],
        "source_run_id": query.source_run_id,
        "valid": query.valid,
        "currentness": query.currentness,
        "limit": query.limit,
    }


def canonical_record_from_dict(payload: Mapping[str, Any], *, label: str) -> object:
    """Reconstruct a canonical record and reject any transport-side field drift."""

    document = _mapping(payload, label)
    record = record_from_dict(document)
    if record.to_dict() != dict(document):
        raise ValueError(f"{label} fields diverge from the canonical record")
    return record
