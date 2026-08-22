"""Backend-neutral contracts and semantics for reusable knowledge persistence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from .records import (
    KnowledgeRelationship,
    RecordRef,
    SemanticRecord,
    TargetRef,
    TargetSnapshot,
    deserialize_record,
    serialize_record,
)
from .targets import TargetPolicy

KnowledgeCurrentness = Literal["current", "stale", "unbound", "incomparable", "unassessed"]

KNOWLEDGE_RECORD_TYPES = frozenset(
    {
        "artifact",
        "belief_state",
        "candidate",
        "claim",
        "constraint",
        "decision_rule",
        "evaluation",
        "evidence",
        "experiment_spec",
        "goal",
        "hypothesis",
        "intervention",
        "knowledge_relationship",
        "measurement",
        "metric",
        "observation",
        "outcome",
        "question",
        "target",
        "target_capabilities",
        "target_component",
        "target_snapshot",
        "trial",
        "trial_result",
    }
)
_CURRENTNESS_LABELS = frozenset({"current", "stale", "unbound", "incomparable", "unassessed"})


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _items(value: Sequence[object], *, label: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    return tuple(value)


def _text_items(value: Sequence[str], *, label: str) -> tuple[str, ...]:
    items = _items(value, label=label)
    normalized = tuple(_require_text(item, label) for item in items)  # type: ignore[arg-type]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must be unique")
    return tuple(sorted(normalized))


def _ref_items(value: Sequence[RecordRef], *, label: str) -> tuple[RecordRef, ...]:
    items = _items(value, label=label)
    if any(not isinstance(item, RecordRef) for item in items):
        raise TypeError(f"{label} must contain RecordRef values")
    refs = tuple(items)
    if len(set(refs)) != len(refs):
        raise ValueError(f"{label} must be unique")
    return refs  # type: ignore[return-value]


def validate_knowledge_record(record: SemanticRecord) -> str:
    """Return canonical bytes only for a reconstructable non-runtime knowledge record."""

    if not isinstance(record, SemanticRecord):
        raise TypeError("knowledge stores accept SemanticRecord values")
    if record.record_type not in KNOWLEDGE_RECORD_TYPES:
        raise ValueError(f"record type {record.record_type!r} is not knowledge state")
    serialized = serialize_record(record)
    reconstructed = deserialize_record(serialized)
    if reconstructed.root != record.root or reconstructed.record_type != record.record_type:
        raise ValueError("knowledge record does not reconstruct to its exact root and type")
    return serialized


def bound_target_snapshots(record: SemanticRecord) -> tuple[TargetSnapshot, ...]:
    """Return distinct top-level target snapshots that qualify a knowledge record."""

    if not isinstance(record, SemanticRecord):
        raise TypeError("bound snapshot inspection requires a SemanticRecord")
    if isinstance(record, TargetSnapshot):
        return (record,)

    snapshots: list[TargetSnapshot] = []
    for name in ("target_snapshot", "baseline_snapshot", "candidate_snapshot"):
        value = getattr(record, name, None)
        if isinstance(value, TargetSnapshot):
            snapshots.append(value)
    for name in ("observations", "measurements"):
        values = getattr(record, name, ())
        if isinstance(values, tuple):
            for value in values:
                snapshot = getattr(value, "target_snapshot", None)
                if isinstance(snapshot, TargetSnapshot):
                    snapshots.append(snapshot)

    unique: dict[str, TargetSnapshot] = {}
    for snapshot in snapshots:
        unique.setdefault(snapshot.root, snapshot)
    return tuple(unique.values())


def target_refs(record: SemanticRecord) -> tuple[TargetRef, ...]:
    """Return exact directly bound targets for query indexing."""

    refs: dict[str, TargetRef] = {}
    if isinstance(record, TargetRef):
        refs[record.root] = record
    target = getattr(record, "target", None)
    if isinstance(target, TargetRef):
        refs[target.root] = target
    for snapshot in bound_target_snapshots(record):
        refs[snapshot.target.root] = snapshot.target
    return tuple(refs.values())


def subject_refs(record: SemanticRecord) -> tuple[RecordRef, ...]:
    refs: list[RecordRef] = []
    singular = getattr(record, "subject_ref", None)
    if isinstance(singular, RecordRef):
        refs.append(singular)
    plural = getattr(record, "subject_refs", ())
    if isinstance(plural, tuple):
        refs.extend(item for item in plural if isinstance(item, RecordRef))
    return tuple(dict.fromkeys(refs))


def label_currentness(
    record: SemanticRecord,
    current_snapshot: TargetSnapshot | None,
) -> KnowledgeCurrentness:
    if current_snapshot is None:
        return "unassessed"
    if not isinstance(current_snapshot, TargetSnapshot):
        raise TypeError("knowledge currentness requires a TargetSnapshot")
    snapshots = bound_target_snapshots(record)
    if not snapshots:
        return "unbound"
    if len(snapshots) != 1 or snapshots[0].target != current_snapshot.target:
        return "incomparable"
    disposition = TargetPolicy().compare(snapshots[0], current_snapshot).disposition
    return "current" if disposition == "current" else "stale"


@dataclass(frozen=True)
class KnowledgeWrite:
    record: SemanticRecord
    source_run_id: str | None = None
    valid: bool = True

    def __post_init__(self) -> None:
        validate_knowledge_record(self.record)
        if self.source_run_id is not None:
            object.__setattr__(
                self,
                "source_run_id",
                _require_text(self.source_run_id, "source run id"),
            )
        if type(self.valid) is not bool:
            raise TypeError("knowledge validity must be a boolean")


@dataclass(frozen=True)
class KnowledgeQuery:
    record_types: tuple[str, ...] = ()
    target: TargetRef | None = None
    current_snapshot: TargetSnapshot | None = None
    subject_refs: tuple[RecordRef, ...] = ()
    evidence_types: tuple[str, ...] = ()
    lineage_refs: tuple[RecordRef, ...] = ()
    source_run_id: str | None = None
    valid: bool | None = None
    currentness: KnowledgeCurrentness | None = None
    limit: int | None = None

    def __post_init__(self) -> None:
        record_types = _text_items(self.record_types, label="knowledge record types")
        if any(item not in KNOWLEDGE_RECORD_TYPES for item in record_types):
            raise ValueError("knowledge queries cannot request runtime or unknown record types")
        object.__setattr__(self, "record_types", record_types)
        if self.target is not None and not isinstance(self.target, TargetRef):
            raise TypeError("knowledge query target must be a TargetRef")
        if self.current_snapshot is not None:
            if not isinstance(self.current_snapshot, TargetSnapshot):
                raise TypeError("knowledge query current snapshot must be a TargetSnapshot")
            if self.target is not None and self.current_snapshot.target != self.target:
                raise ValueError("knowledge query current snapshot does not match its target")
        object.__setattr__(
            self,
            "subject_refs",
            _ref_items(self.subject_refs, label="knowledge subject references"),
        )
        object.__setattr__(
            self,
            "evidence_types",
            _text_items(self.evidence_types, label="knowledge evidence types"),
        )
        object.__setattr__(
            self,
            "lineage_refs",
            _ref_items(self.lineage_refs, label="knowledge lineage references"),
        )
        if self.source_run_id is not None:
            object.__setattr__(
                self,
                "source_run_id",
                _require_text(self.source_run_id, "source run id"),
            )
        if self.valid is not None and type(self.valid) is not bool:
            raise TypeError("knowledge query validity must be a boolean")
        if self.currentness is not None:
            if self.currentness not in _CURRENTNESS_LABELS - {"unassessed"}:
                raise ValueError("unsupported knowledge currentness filter")
            if self.current_snapshot is None:
                raise ValueError("currentness filters require a current target snapshot")
        if self.limit is not None:
            if isinstance(self.limit, bool) or not isinstance(self.limit, int):
                raise TypeError("knowledge query limit must be an integer")
            if self.limit <= 0:
                raise ValueError("knowledge query limit must be positive")


@dataclass(frozen=True)
class StoredKnowledge:
    record: SemanticRecord
    source_run_id: str | None
    valid: bool
    stored_at: str
    currentness: KnowledgeCurrentness = "unassessed"

    def __post_init__(self) -> None:
        validate_knowledge_record(self.record)
        if self.source_run_id is not None:
            object.__setattr__(
                self,
                "source_run_id",
                _require_text(self.source_run_id, "source run id"),
            )
        if type(self.valid) is not bool:
            raise TypeError("stored knowledge validity must be a boolean")
        object.__setattr__(self, "stored_at", _require_text(self.stored_at, "stored at"))
        if self.currentness not in _CURRENTNESS_LABELS:
            raise ValueError("unsupported stored knowledge currentness")


@runtime_checkable
class KnowledgeStore(Protocol):
    """Replaceable persistence contract for canonical reusable knowledge."""

    def put(
        self,
        record: SemanticRecord,
        *,
        source_run_id: str | None = None,
        valid: bool = True,
    ) -> StoredKnowledge: ...

    def put_many(self, writes: Sequence[KnowledgeWrite]) -> tuple[StoredKnowledge, ...]: ...

    def get(self, root: str) -> SemanticRecord | None: ...

    def query(self, query: KnowledgeQuery | None = None) -> tuple[StoredKnowledge, ...]: ...

    def relationships(
        self,
        *,
        source: RecordRef | None = None,
        relationship: str | None = None,
        target: RecordRef | None = None,
    ) -> tuple[KnowledgeRelationship, ...]: ...

    def close(self) -> None: ...
