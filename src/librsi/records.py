from __future__ import annotations

import hashlib
import json
import math
import string
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, TypeVar

from .identity import FrozenMap, canonical_json, digest, freeze, thaw

_RECORD_SCHEMA = "librsi.record/v1"
_REF_SCHEMA = "librsi.ref/v1"
_MAP_SCHEMA = "librsi.map/v1"
_RECORD_TYPES: dict[str, type[Any]] = {}
_HEX = frozenset(string.hexdigits.lower())
_METRIC_DIRECTIONS = frozenset({"increase", "decrease", "target"})
_METRIC_ROLES = frozenset({"objective", "guardrail", "diagnostic"})
_DECISION_RULE_KINDS = frozenset({"threshold", "baseline_delta"})
_DECISION_OPERATORS = frozenset({"<", "<=", "==", ">=", ">"})
_TRIAL_ROLES = frozenset({"subject", "baseline", "candidate"})
_TRIAL_RESULT_DISPOSITIONS = frozenset({"valid", "invalid", "inconclusive"})
_TARGET_CURRENTNESS_DISPOSITIONS = frozenset({"current", "stale"})


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _validate_root(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("record root must be a string")
    normalized = value.lower()
    if len(normalized) != 64 or any(character not in _HEX for character in normalized):
        raise ValueError("record roots must be SHA-256 hex digests")
    return normalized


def _freeze_map(value: Mapping[str, Any] | FrozenMap | None) -> FrozenMap:
    if value is None:
        return FrozenMap()
    if isinstance(value, FrozenMap):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("canonical mapping fields require a mapping")
    return FrozenMap(value)


def _text_tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    if isinstance(value, (bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("text collections require a sequence of strings")
    return tuple(_require_text(item, "text item") for item in value)


def _record_refs(
    value: Sequence[RecordRef] | None,
    *,
    label: str = "record references",
) -> tuple[RecordRef, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of RecordRef values")
    refs = tuple(value)
    if any(not isinstance(item, RecordRef) for item in refs):
        raise TypeError(f"{label} must contain RecordRef values")
    return refs


def _evidence_refs(
    value: Sequence[EvidenceRef | RecordRef] | None,
) -> tuple[EvidenceRef, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("evidence references must be a sequence of record references")
    refs: list[EvidenceRef] = []
    for item in value:
        if isinstance(item, EvidenceRef):
            refs.append(item)
        elif isinstance(item, RecordRef) and item.record_type == "evidence":
            refs.append(EvidenceRef(item.root))
        else:
            raise TypeError("evidence references must point to evidence records")
    return tuple(refs)


def _mapping_tuple(
    value: Sequence[Mapping[str, Any] | FrozenMap] | None,
) -> tuple[FrozenMap, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("mapping collections require a sequence of mappings")
    return tuple(_freeze_map(item) for item in value)


def _finite_number(value: float | int, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _require_bool(value: bool, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be a boolean")
    return value


def _nonnegative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _nonnegative_int_tuple(
    value: Sequence[int] | None,
    *,
    label: str,
) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of integers")
    return tuple(_nonnegative_int(item, label) for item in value)


@dataclass(frozen=True, eq=False)
class RecordRef:
    """Exact, type-bound reference to a canonical semantic record."""

    record_type: str
    root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_type",
            _require_text(self.record_type, "record type"),
        )
        object.__setattr__(self, "root", _validate_root(self.root))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RecordRef):
            return NotImplemented
        return self.record_type == other.record_type and self.root == other.root

    def __hash__(self) -> int:
        return hash((self.record_type, self.root))

    @classmethod
    def from_record(cls, record: SemanticRecord) -> RecordRef:
        if not isinstance(record, SemanticRecord):
            raise TypeError("RecordRef requires a SemanticRecord")
        return cls(record.record_type, record.root)

    def matches(self, record: SemanticRecord) -> bool:
        return (
            isinstance(record, SemanticRecord)
            and self.record_type == record.record_type
            and self.root == record.root
        )

    def require(self, record: SemanticRecord) -> SemanticRecord:
        if not isinstance(record, SemanticRecord):
            raise TypeError("record reference matching requires a SemanticRecord")
        if not self.matches(record):
            raise ValueError("record reference does not match the supplied semantic record")
        return record

    def to_dict(self) -> dict[str, str]:
        return {
            "$schema": _REF_SCHEMA,
            "record_type": self.record_type,
            "root": self.root,
        }


class EvidenceRef(RecordRef):
    """Type-safe exact reference to an Evidence record."""

    __slots__ = ()

    def __init__(self, root: str) -> None:
        super().__init__("evidence", root)

    @classmethod
    def from_record(cls, record: SemanticRecord) -> EvidenceRef:
        if not isinstance(record, Evidence):
            raise TypeError("EvidenceRef requires an Evidence record")
        return cls(record.root)

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> EvidenceRef:
        return cls.from_record(evidence)


def _identity_value(value: Any) -> Any:
    if isinstance(value, SemanticRecord):
        return value.ref.to_dict()
    if isinstance(value, RecordRef):
        return value.to_dict()
    if isinstance(value, FrozenMap):
        return thaw(value)
    if isinstance(value, tuple):
        return [_identity_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported identity value type: {type(value).__name__}")


def _serialize_map(value: FrozenMap, convert: Callable[[Any], Any]) -> dict[str, Any]:
    return {
        "$schema": _MAP_SCHEMA,
        "items": {key: convert(item) for key, item in value.items()},
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, SemanticRecord):
        return value.to_dict()
    if isinstance(value, RecordRef):
        return value.to_dict()
    if isinstance(value, FrozenMap):
        return _serialize_map(value, _serialize_value)
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported record value type: {type(value).__name__}")


def _record_document(record: SemanticRecord, convert: Callable[[Any], Any]) -> dict[str, Any]:
    return {
        "$schema": _RECORD_SCHEMA,
        "record_type": record.record_type,
        "schema_version": record.schema_version,
        "root": record.root,
        "data": {
            item.name: convert(getattr(record, item.name))
            for item in fields(record)
            if item.name not in {"metadata", "root"}
        },
        "metadata": thaw(_freeze_map(record.metadata)),
    }


def _decode_value(value: Any, cache: _DecodeCache) -> Any:
    if isinstance(value, list):
        return tuple(_decode_value(item, cache) for item in value)
    if not isinstance(value, Mapping):
        return value

    schema = value.get("$schema")
    if schema == _RECORD_SCHEMA:
        return _record_from_dict(value, cache)
    if schema == _REF_SCHEMA:
        record_type = value.get("record_type")
        root = value.get("root")
        if not isinstance(record_type, str) or not isinstance(root, str):
            raise ValueError("serialized record reference is incomplete")
        return RecordRef(record_type, root)
    if schema == _MAP_SCHEMA:
        items = value.get("items")
        if not isinstance(items, Mapping):
            raise ValueError("serialized immutable mapping is incomplete")
        return {str(key): _decode_value(item, cache) for key, item in items.items()}
    return {str(key): _decode_value(item, cache) for key, item in value.items()}


@dataclass(frozen=True, kw_only=True)
class SemanticRecord:
    """Immutable, self-identifying, durably serializable semantic record."""

    RECORD_TYPE: ClassVar[str] = "record"
    SCHEMA_VERSION: ClassVar[int] = 1

    lineage: tuple[RecordRef, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(
        default_factory=FrozenMap,
        repr=False,
        compare=False,
        hash=False,
    )
    root: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "lineage",
            _record_refs(self.lineage, label="record lineage"),
        )
        object.__setattr__(self, "metadata", _freeze_map(self.metadata))
        object.__setattr__(self, "root", digest(self.identity_payload()))

    @property
    def record_type(self) -> str:
        return self.RECORD_TYPE

    @property
    def schema_version(self) -> int:
        return self.SCHEMA_VERSION

    @property
    def ref(self) -> RecordRef:
        return RecordRef.from_record(self)

    def identity_data(self) -> dict[str, Any]:
        return {
            item.name: _identity_value(getattr(self, item.name))
            for item in fields(self)
            if item.name not in {"metadata", "root"}
        }

    def identity_payload(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "data": self.identity_data(),
        }

    def to_dict(self) -> dict[str, Any]:
        return _record_document(self, _serialize_value)


RecordT = TypeVar("RecordT", bound=SemanticRecord)


def _register(record_cls: type[RecordT]) -> type[RecordT]:
    record_type = record_cls.RECORD_TYPE
    if record_type in _RECORD_TYPES:
        raise RuntimeError(f"duplicate semantic record type: {record_type}")
    _RECORD_TYPES[record_type] = record_cls
    return record_cls


def register_record_type(record_cls: type[RecordT]) -> type[RecordT]:
    """Register a structured libRSI submodule's canonical record type."""

    return _register(record_cls)


def registered_record_class(record_type: str) -> type[SemanticRecord]:
    """Return the one canonical concrete class registered for a record type."""

    normalized = _require_text(record_type, "record type")
    record_cls = _RECORD_TYPES.get(normalized)
    if record_cls is None or not issubclass(record_cls, SemanticRecord):
        raise ValueError(f"unknown semantic record type: {normalized}")
    return record_cls


@_register
@dataclass(frozen=True, kw_only=True)
class TargetRef(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "target"

    target_id: str
    kind: str = "generic"
    locator: Mapping[str, Any] = field(default_factory=FrozenMap)
    components: tuple[TargetComponent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _require_text(self.target_id, "target id"))
        object.__setattr__(self, "kind", _require_text(self.kind, "target kind"))
        object.__setattr__(self, "locator", _freeze_map(self.locator))
        components = tuple(self.components)
        if any(not isinstance(item, TargetComponent) for item in components):
            raise TypeError("target components must be TargetComponent records")
        if len({item.component_id for item in components}) != len(components):
            raise ValueError("target component ids must be unique")
        if len({item.target.ref for item in components}) != len(components):
            raise ValueError("target component targets must be unique")
        object.__setattr__(
            self, "components", tuple(sorted(components, key=lambda item: item.component_id))
        )
        super().__post_init__()

    def identity_data(self) -> dict[str, Any]:
        data = super().identity_data()
        if not self.components:
            data.pop("components")
        return data


@_register
@dataclass(frozen=True, kw_only=True)
class TargetCapabilities(SemanticRecord):
    """Capabilities declared for a target and the subset available to this host."""

    RECORD_TYPE: ClassVar[str] = "target_capabilities"

    target: TargetRef
    supported: tuple[str, ...] = field(default_factory=tuple)
    locally_available: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.target, TargetRef):
            raise TypeError("target capabilities require a TargetRef")
        supported = _text_tuple(self.supported)
        if len(set(supported)) != len(supported):
            raise ValueError("supported target capabilities must be unique")
        supported = tuple(sorted(supported))
        available = _text_tuple(self.locally_available)
        if len(set(available)) != len(available):
            raise ValueError("locally available target capabilities must be unique")
        if not set(available).issubset(supported):
            raise ValueError("locally available capabilities must be declared as supported")
        object.__setattr__(self, "supported", supported)
        object.__setattr__(self, "locally_available", tuple(sorted(available)))
        super().__post_init__()

    def supports(self, capability: str) -> bool:
        return _require_text(capability, "target capability") in self.supported

    def is_locally_available(self, capability: str) -> bool:
        return _require_text(capability, "target capability") in self.locally_available


@_register
@dataclass(frozen=True, kw_only=True)
class TargetComponent(SemanticRecord):
    """One named target within a composite target."""

    RECORD_TYPE: ClassVar[str] = "target_component"

    component_id: str
    target: TargetRef
    capabilities: TargetCapabilities | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            _require_text(self.component_id, "target component id"),
        )
        if not isinstance(self.target, TargetRef):
            raise TypeError("target components require a TargetRef")
        if self.capabilities is not None:
            if not isinstance(self.capabilities, TargetCapabilities):
                raise TypeError("target component capabilities must be TargetCapabilities")
            if self.capabilities.target != self.target:
                raise ValueError("target component capabilities do not match the component target")
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class TargetSnapshot(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "target_snapshot"

    target: TargetRef
    state: Mapping[str, Any]
    revision: str | None = None
    components: tuple[TargetSnapshot, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.target, TargetRef):
            raise TypeError("target snapshots require a TargetRef")
        object.__setattr__(self, "state", _freeze_map(self.state))
        object.__setattr__(
            self,
            "revision",
            None if self.revision is None else _require_text(self.revision, "target revision"),
        )
        components = tuple(self.components)
        if any(not isinstance(item, TargetSnapshot) for item in components):
            raise TypeError("target snapshot components must be TargetSnapshot records")
        if not self.target.components and components:
            raise ValueError("atomic target snapshots cannot contain component snapshots")
        if self.target.components:
            component_targets = tuple(item.target.ref for item in self.target.components)
            supplied = tuple(item.target.ref for item in components)
            if len(set(supplied)) != len(supplied):
                raise ValueError("target snapshot components must be unique")
            if set(supplied) != set(component_targets):
                raise ValueError("target snapshot must contain every exact target component")
            by_target = {item.target.ref: item for item in components}
            components = tuple(by_target[item.target.ref] for item in self.target.components)
        object.__setattr__(self, "components", components)
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class TargetComparison(SemanticRecord):
    """Exact currentness comparison between two snapshots of one target."""

    RECORD_TYPE: ClassVar[str] = "target_comparison"

    baseline: TargetSnapshot
    current: TargetSnapshot
    disposition: str
    component_currentness: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        if not isinstance(self.baseline, TargetSnapshot) or not isinstance(
            self.current,
            TargetSnapshot,
        ):
            raise TypeError("target comparison requires TargetSnapshot records")
        if self.baseline.target != self.current.target:
            raise ValueError("target comparison snapshots must reference the exact same target")
        disposition = _require_text(self.disposition, "target currentness disposition")
        if disposition not in _TARGET_CURRENTNESS_DISPOSITIONS:
            raise ValueError(f"unsupported target currentness disposition: {disposition}")
        expected_disposition = "current" if self.baseline.root == self.current.root else "stale"
        if disposition != expected_disposition:
            raise ValueError("target currentness disposition does not match the snapshot roots")
        object.__setattr__(self, "disposition", disposition)

        component_currentness = _freeze_map(self.component_currentness)
        if any(type(value) is not bool for value in component_currentness.values()):
            raise TypeError("target component currentness values must be booleans")
        expected_components: dict[str, bool] = {}
        for index, component in enumerate(self.baseline.target.components):
            expected_components[component.component_id] = (
                self.baseline.components[index].root == self.current.components[index].root
            )
        if component_currentness != expected_components:
            raise ValueError("target comparison must account for every exact component snapshot")
        object.__setattr__(self, "component_currentness", component_currentness)
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class KnowledgeRelationship(SemanticRecord):
    """One exact, typed relationship between canonical knowledge records."""

    RECORD_TYPE: ClassVar[str] = "knowledge_relationship"

    source: RecordRef
    relationship: str
    target: RecordRef
    attributes: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        if not isinstance(self.source, RecordRef) or not isinstance(self.target, RecordRef):
            raise TypeError("knowledge relationship endpoints must be RecordRef values")
        object.__setattr__(
            self,
            "relationship",
            _require_text(self.relationship, "knowledge relationship"),
        )
        object.__setattr__(self, "attributes", _freeze_map(self.attributes))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Claim(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "claim"

    statement: str
    kind: str = "claim"
    target: TargetRef | None = None
    scope: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _require_text(self.statement, "claim statement"))
        object.__setattr__(self, "kind", _require_text(self.kind, "claim kind"))
        if self.target is not None and not isinstance(self.target, TargetRef):
            raise TypeError("claim target must be a TargetRef")
        object.__setattr__(self, "scope", _freeze_map(self.scope))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Question(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "question"

    prompt: str
    target: TargetRef | None = None
    context: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt", _require_text(self.prompt, "question prompt"))
        if self.target is not None and not isinstance(self.target, TargetRef):
            raise TypeError("question target must be a TargetRef")
        object.__setattr__(self, "context", _freeze_map(self.context))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Goal(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "goal"

    statement: str
    target: TargetRef | None = None
    scope: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _require_text(self.statement, "goal statement"))
        if self.target is not None and not isinstance(self.target, TargetRef):
            raise TypeError("goal target must be a TargetRef")
        object.__setattr__(self, "scope", _freeze_map(self.scope))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Constraint(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "constraint"

    statement: str
    target: TargetRef | None = None
    scope: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "statement",
            _require_text(self.statement, "constraint statement"),
        )
        if self.target is not None and not isinstance(self.target, TargetRef):
            raise TypeError("constraint target must be a TargetRef")
        object.__setattr__(self, "scope", _freeze_map(self.scope))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Hypothesis(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "hypothesis"

    statement: str
    target: TargetRef | None = None
    causal_model: Mapping[str, Any] = field(default_factory=FrozenMap)
    predictions: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    source_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    confidence: float = 0.5
    status: str = "proposed"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "statement",
            _require_text(self.statement, "hypothesis statement"),
        )
        if self.target is not None and not isinstance(self.target, TargetRef):
            raise TypeError("hypothesis target must be a TargetRef")
        object.__setattr__(self, "causal_model", _freeze_map(self.causal_model))
        object.__setattr__(self, "predictions", _mapping_tuple(self.predictions))
        object.__setattr__(
            self,
            "source_refs",
            _record_refs(self.source_refs, label="hypothesis source references"),
        )
        confidence = _finite_number(self.confidence, "hypothesis confidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("hypothesis confidence must be between zero and one")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "status", _require_text(self.status, "hypothesis status"))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Evidence(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "evidence"

    evidence_type: str
    data: Mapping[str, Any]
    subject_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    source_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    target_snapshot: TargetSnapshot | None = None
    weight: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_type",
            _require_text(self.evidence_type, "evidence type"),
        )
        object.__setattr__(self, "data", _freeze_map(self.data))
        object.__setattr__(
            self,
            "subject_refs",
            _record_refs(self.subject_refs, label="evidence subject references"),
        )
        if any(item.record_type == "goal" for item in self.subject_refs):
            raise ValueError("declarative Goals cannot be treated as evidentiary subjects")
        object.__setattr__(
            self,
            "source_refs",
            _record_refs(self.source_refs, label="evidence source references"),
        )
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("evidence target snapshot must be a TargetSnapshot")
        if self.weight is not None:
            object.__setattr__(
                self,
                "weight",
                _finite_number(self.weight, "evidence weight"),
            )
        super().__post_init__()

    @property
    def evidence_ref(self) -> EvidenceRef:
        return EvidenceRef.from_evidence(self)


@_register
@dataclass(frozen=True, kw_only=True)
class BeliefState(SemanticRecord):
    """Typed, provenance-bearing aggregation state for a Claim or Hypothesis."""

    RECORD_TYPE: ClassVar[str] = "belief_state"

    subject_ref: RecordRef
    status: str = "proposed"
    confidence: float = 0.5
    evidence_refs: tuple[EvidenceRef, ...] = field(default_factory=tuple)
    target_snapshot: TargetSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject_ref, RecordRef):
            raise TypeError("belief state subject must be a RecordRef")
        if self.subject_ref.record_type not in {"claim", "hypothesis"}:
            raise ValueError("belief state subject must reference a claim or hypothesis")
        object.__setattr__(self, "status", _require_text(self.status, "belief status"))
        confidence = _finite_number(self.confidence, "belief confidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("belief confidence must be between zero and one")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "evidence_refs", _evidence_refs(self.evidence_refs))
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("belief state target snapshot must be a TargetSnapshot")
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Metric(SemanticRecord):
    """Exact definition of a measured quantity and its evaluation role."""

    RECORD_TYPE: ClassVar[str] = "metric"

    metric_id: str
    direction: str
    role: str = "objective"
    unit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _require_text(self.metric_id, "metric id"))
        direction = _require_text(self.direction, "metric direction")
        if direction not in _METRIC_DIRECTIONS:
            raise ValueError(f"unsupported metric direction: {direction}")
        object.__setattr__(self, "direction", direction)
        role = _require_text(self.role, "metric role")
        if role not in _METRIC_ROLES:
            raise ValueError(f"unsupported metric role: {role}")
        object.__setattr__(self, "role", role)
        object.__setattr__(
            self,
            "unit",
            None if self.unit is None else _require_text(self.unit, "metric unit"),
        )
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class DecisionRule(SemanticRecord):
    """Deterministic threshold or baseline-delta rule for one exact Metric."""

    RECORD_TYPE: ClassVar[str] = "decision_rule"

    metric: RecordRef
    kind: str
    operator: str | None = None
    threshold: float | None = None
    minimum_effect: float = 0.0
    aggregation: str = "mean"
    required_valid_trials: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.metric, RecordRef) or self.metric.record_type != "metric":
            raise TypeError("decision rule metric must reference a Metric")
        kind = _require_text(self.kind, "decision rule kind")
        if kind not in _DECISION_RULE_KINDS:
            raise ValueError(f"unsupported decision rule kind: {kind}")
        object.__setattr__(self, "kind", kind)
        if self.aggregation != "mean":
            raise ValueError("the built-in decision rule supports mean aggregation only")
        minimum_effect = _finite_number(self.minimum_effect, "minimum meaningful effect")
        if minimum_effect < 0.0:
            raise ValueError("minimum meaningful effect must be nonnegative")
        object.__setattr__(self, "minimum_effect", minimum_effect)
        required = _nonnegative_int(self.required_valid_trials, "required valid trials")
        if required == 0:
            raise ValueError("required valid trials must be positive")
        object.__setattr__(self, "required_valid_trials", required)

        if kind == "threshold":
            if minimum_effect != 0.0:
                raise ValueError("threshold rules do not accept a minimum meaningful effect")
            if self.operator not in _DECISION_OPERATORS:
                raise ValueError("threshold rules require a supported operator")
            if self.threshold is None:
                raise ValueError("threshold rules require a finite threshold")
            object.__setattr__(self, "threshold", _finite_number(self.threshold, "threshold"))
        elif self.operator is not None or self.threshold is not None:
            raise ValueError("baseline-delta rules do not accept operator or threshold")
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class ExperimentSpec(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "experiment_spec"

    experiment_id: str
    kind: str
    target_snapshot: TargetSnapshot | None = None
    design: Mapping[str, Any] = field(default_factory=FrozenMap)
    criteria: Mapping[str, Any] = field(default_factory=FrozenMap)
    inputs: Mapping[str, Any] = field(default_factory=FrozenMap)
    environment: Mapping[str, Any] = field(default_factory=FrozenMap)
    requested_measurements: tuple[str, ...] = field(default_factory=tuple)
    metrics: tuple[Metric, ...] = field(default_factory=tuple)
    decision_rules: tuple[DecisionRule, ...] = field(default_factory=tuple)
    repetitions: int = 1
    seeds: tuple[int, ...] = field(default_factory=tuple)
    budget: Mapping[str, Any] = field(default_factory=FrozenMap)
    validity_requirements: Mapping[str, Any] = field(default_factory=FrozenMap)
    baseline_snapshot: TargetSnapshot | None = None
    candidate_snapshot: TargetSnapshot | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "experiment_id",
            _require_text(self.experiment_id, "experiment id"),
        )
        object.__setattr__(self, "kind", _require_text(self.kind, "experiment kind"))
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("experiment target snapshot must be a TargetSnapshot")
        object.__setattr__(self, "design", _freeze_map(self.design))
        object.__setattr__(self, "criteria", _freeze_map(self.criteria))
        object.__setattr__(self, "inputs", _freeze_map(self.inputs))
        object.__setattr__(self, "environment", _freeze_map(self.environment))
        object.__setattr__(
            self,
            "requested_measurements",
            _text_tuple(self.requested_measurements),
        )
        metrics = tuple(self.metrics)
        if any(not isinstance(item, Metric) for item in metrics):
            raise TypeError("experiment metrics must be Metric records")
        if len({item.metric_id for item in metrics}) != len(metrics):
            raise ValueError("experiment metric ids must be unique")
        object.__setattr__(self, "metrics", metrics)
        rules = tuple(self.decision_rules)
        if any(not isinstance(item, DecisionRule) for item in rules):
            raise TypeError("experiment decision rules must be DecisionRule records")
        metric_refs = {item.ref for item in metrics}
        if any(item.metric not in metric_refs for item in rules):
            raise ValueError("experiment decision rules must reference an exact experiment metric")
        object.__setattr__(self, "decision_rules", rules)
        repetitions = _nonnegative_int(self.repetitions, "experiment repetitions")
        if repetitions == 0:
            raise ValueError("experiment repetitions must be positive")
        object.__setattr__(self, "repetitions", repetitions)
        seeds = _nonnegative_int_tuple(self.seeds, label="experiment seeds")
        if seeds and len(seeds) != repetitions:
            raise ValueError("experiment seeds must match the repetition count")
        object.__setattr__(self, "seeds", seeds)
        object.__setattr__(self, "budget", _freeze_map(self.budget))
        object.__setattr__(self, "validity_requirements", _freeze_map(self.validity_requirements))
        for label in ("baseline", "candidate"):
            snapshot = getattr(self, f"{label}_snapshot")
            if snapshot is not None and not isinstance(snapshot, TargetSnapshot):
                raise TypeError(f"experiment {label} snapshot must be a TargetSnapshot")
            if (
                snapshot is not None
                and self.target_snapshot is not None
                and snapshot.target != self.target_snapshot.target
            ):
                raise ValueError(f"experiment {label} snapshot target does not match")
        if (
            self.baseline_snapshot is not None
            and self.candidate_snapshot is not None
            and self.baseline_snapshot.target != self.candidate_snapshot.target
        ):
            raise ValueError("experiment baseline and candidate targets must match")
        super().__post_init__()

    def identity_data(self) -> dict[str, Any]:
        data = super().identity_data()
        defaults = {
            "metrics": (),
            "decision_rules": (),
            "repetitions": 1,
            "seeds": (),
            "budget": FrozenMap(),
            "validity_requirements": FrozenMap(),
            "baseline_snapshot": None,
            "candidate_snapshot": None,
        }
        for name, default in defaults.items():
            if getattr(self, name) == default:
                data.pop(name)
        return data


@_register
@dataclass(frozen=True, kw_only=True)
class Observation(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "observation"

    kind: str
    value: Any
    target_snapshot: TargetSnapshot | None = None
    source_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    valid: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _require_text(self.kind, "observation kind"))
        object.__setattr__(self, "value", freeze(self.value))
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("observation target snapshot must be a TargetSnapshot")
        object.__setattr__(
            self,
            "source_refs",
            _record_refs(self.source_refs, label="observation source references"),
        )
        object.__setattr__(self, "valid", _require_bool(self.valid, "observation valid"))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Trial(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "trial"

    experiment: RecordRef
    index: int
    status: str
    observation_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    data: Mapping[str, Any] = field(default_factory=FrozenMap)
    role: str = "subject"
    seed: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.experiment, RecordRef)
            or self.experiment.record_type != "experiment_spec"
        ):
            raise TypeError("trial experiment must reference an ExperimentSpec")
        object.__setattr__(self, "index", _nonnegative_int(self.index, "trial index"))
        object.__setattr__(self, "status", _require_text(self.status, "trial status"))
        object.__setattr__(
            self,
            "observation_refs",
            _record_refs(self.observation_refs, label="trial observation references"),
        )
        object.__setattr__(self, "data", _freeze_map(self.data))
        role = _require_text(self.role, "trial role")
        if role not in _TRIAL_ROLES:
            raise ValueError(f"unsupported trial role: {role}")
        object.__setattr__(self, "role", role)
        if self.seed is not None:
            object.__setattr__(self, "seed", _nonnegative_int(self.seed, "trial seed"))
        super().__post_init__()

    def identity_data(self) -> dict[str, Any]:
        data = super().identity_data()
        if self.role == "subject":
            data.pop("role")
        if self.seed is None:
            data.pop("seed")
        return data


@_register
@dataclass(frozen=True, kw_only=True)
class Measurement(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "measurement"

    metric: str
    value: Any
    unit: str | None = None
    target_snapshot: TargetSnapshot | None = None
    observation_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    metric_ref: RecordRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", _require_text(self.metric, "measurement metric"))
        object.__setattr__(self, "value", freeze(self.value))
        object.__setattr__(
            self,
            "unit",
            None if self.unit is None else _require_text(self.unit, "measurement unit"),
        )
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("measurement target snapshot must be a TargetSnapshot")
        object.__setattr__(
            self,
            "observation_refs",
            _record_refs(self.observation_refs, label="measurement observation references"),
        )
        if self.metric_ref is not None and (
            not isinstance(self.metric_ref, RecordRef) or self.metric_ref.record_type != "metric"
        ):
            raise TypeError("measurement metric_ref must reference a Metric")
        super().__post_init__()

    def identity_data(self) -> dict[str, Any]:
        data = super().identity_data()
        if self.metric_ref is None:
            data.pop("metric_ref")
        return data


@_register
@dataclass(frozen=True, kw_only=True)
class TrialResult(SemanticRecord):
    """Exactly correlated measurements and validity for one Trial."""

    RECORD_TYPE: ClassVar[str] = "trial_result"

    trial: Trial
    disposition: str
    observations: tuple[Observation, ...] = field(default_factory=tuple)
    measurements: tuple[Measurement, ...] = field(default_factory=tuple)
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.trial, Trial):
            raise TypeError("trial result requires a Trial")
        disposition = _require_text(self.disposition, "trial result disposition")
        if disposition not in _TRIAL_RESULT_DISPOSITIONS:
            raise ValueError(f"unsupported trial result disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        observations = tuple(self.observations)
        if any(not isinstance(item, Observation) for item in observations):
            raise TypeError("trial result observations must be Observation records")
        if len({item.ref for item in observations}) != len(observations):
            raise ValueError("trial result observations must be distinct")
        object.__setattr__(self, "observations", observations)
        measurements = tuple(self.measurements)
        if any(not isinstance(item, Measurement) for item in measurements):
            raise TypeError("trial result measurements must be Measurement records")
        if disposition == "valid" and not measurements:
            raise ValueError("valid trial results require measurements")
        if disposition == "valid" and not observations:
            raise ValueError("valid trial results require observations")
        object.__setattr__(self, "measurements", measurements)
        object.__setattr__(
            self,
            "reason",
            None if self.reason is None else _require_text(self.reason, "trial result reason"),
        )
        if disposition != "valid" and self.reason is None:
            raise ValueError("invalid or inconclusive trial results require a reason")
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Evaluation(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "evaluation"

    subject_refs: tuple[RecordRef, ...]
    disposition: str
    measurements: tuple[Measurement, ...] = field(default_factory=tuple)
    findings: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject_refs",
            _record_refs(self.subject_refs, label="evaluation subject references"),
        )
        if not self.subject_refs:
            raise ValueError("evaluation requires at least one subject reference")
        object.__setattr__(
            self,
            "disposition",
            _require_text(self.disposition, "evaluation disposition"),
        )
        measurements = tuple(self.measurements)
        if any(not isinstance(item, Measurement) for item in measurements):
            raise TypeError("evaluation measurements must be Measurement records")
        object.__setattr__(self, "measurements", measurements)
        object.__setattr__(self, "findings", _freeze_map(self.findings))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class ArtifactRef(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "artifact"

    artifact_id: str
    uri: str
    content_digest: str | None = None
    media_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _require_text(self.artifact_id, "artifact id"),
        )
        object.__setattr__(self, "uri", _require_text(self.uri, "artifact uri"))
        object.__setattr__(
            self,
            "content_digest",
            None
            if self.content_digest is None
            else _require_text(self.content_digest, "artifact content digest"),
        )
        object.__setattr__(
            self,
            "media_type",
            None
            if self.media_type is None
            else _require_text(self.media_type, "artifact media type"),
        )
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Intervention(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "intervention"

    target: TargetRef
    kind: str
    specification: Mapping[str, Any]
    rationale: Mapping[str, Any] = field(default_factory=FrozenMap)
    expected_effects: Mapping[str, Any] = field(default_factory=FrozenMap)
    constraints: tuple[Constraint, ...] = field(default_factory=tuple)
    validation_plan: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        if not isinstance(self.target, TargetRef):
            raise TypeError("intervention target must be a TargetRef")
        object.__setattr__(self, "kind", _require_text(self.kind, "intervention kind"))
        object.__setattr__(self, "specification", _freeze_map(self.specification))
        object.__setattr__(self, "rationale", _freeze_map(self.rationale))
        object.__setattr__(self, "expected_effects", _freeze_map(self.expected_effects))
        constraints = tuple(self.constraints)
        if any(not isinstance(item, Constraint) for item in constraints):
            raise TypeError("intervention constraints must be Constraint records")
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "validation_plan", _freeze_map(self.validation_plan))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Candidate(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "candidate"

    intervention: RecordRef
    target_snapshot: TargetSnapshot
    status: str = "prepared"
    artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.intervention, RecordRef)
            or self.intervention.record_type != "intervention"
        ):
            raise TypeError("candidate intervention must reference an Intervention")
        if not isinstance(self.target_snapshot, TargetSnapshot):
            raise TypeError("candidate target snapshot must be a TargetSnapshot")
        object.__setattr__(self, "status", _require_text(self.status, "candidate status"))
        artifacts = tuple(self.artifacts)
        if any(not isinstance(item, ArtifactRef) for item in artifacts):
            raise TypeError("candidate artifacts must be ArtifactRef records")
        object.__setattr__(self, "artifacts", artifacts)
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Outcome(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "outcome"

    intent: RecordRef
    status: str
    target_snapshot: TargetSnapshot | None = None
    conclusions: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[EvidenceRef, ...] = field(default_factory=tuple)
    intervention_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    unresolved: tuple[str, ...] = field(default_factory=tuple)
    next_actions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.intent, RecordRef):
            raise TypeError("outcome intent must be a RecordRef")
        object.__setattr__(self, "status", _require_text(self.status, "outcome status"))
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("outcome target snapshot must be a TargetSnapshot")
        object.__setattr__(self, "conclusions", _text_tuple(self.conclusions))
        object.__setattr__(self, "evidence_refs", _evidence_refs(self.evidence_refs))
        interventions = _record_refs(
            self.intervention_refs,
            label="outcome intervention references",
        )
        if any(item.record_type != "intervention" for item in interventions):
            raise TypeError("outcome intervention references must point to interventions")
        object.__setattr__(self, "intervention_refs", interventions)
        artifacts = tuple(self.artifacts)
        if any(not isinstance(item, ArtifactRef) for item in artifacts):
            raise TypeError("outcome artifacts must be ArtifactRef records")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "unresolved", _text_tuple(self.unresolved))
        object.__setattr__(self, "next_actions", _text_tuple(self.next_actions))
        super().__post_init__()


def record_from_dict(payload: Mapping[str, Any]) -> SemanticRecord:
    """Reconstruct and integrity-check a record from durable data."""

    return _DecodeCache().decode(payload)


class _DecodeCache:
    """Reuse exact subdocuments within a public decode or one store operation."""

    def __init__(self) -> None:
        self.records: dict[bytes, SemanticRecord] = {}
        self.fingerprints: dict[int, tuple[Any, bytes]] = {}
        self.scalars: dict[tuple[type, Any], bytes] = {}

    def decode(self, payload: Mapping[str, Any]) -> SemanticRecord:
        try:
            return _record_from_dict(payload, self)
        finally:
            # Input-container identities are useful only for this document.
            # Keep only bounded, content-keyed validated records between rows.
            self.fingerprints.clear()

    def deserialize(self, serialized: str) -> SemanticRecord:
        if not isinstance(serialized, str):
            raise TypeError("serialized semantic record must be text")
        payload = json.loads(serialized)
        if not isinstance(payload, Mapping):
            raise ValueError("serialized semantic record must contain a JSON object")
        return self.decode(payload)

    def fingerprint(self, value: Any) -> bytes:
        value_type = type(value)
        if value_type in (dict, list):
            cached = self.fingerprints.get(id(value))
            if cached is not None:
                return cached[1]
            digest = hashlib.sha256(b"map" if value_type is dict else b"list")
            if value_type is dict:
                if any(type(key) is not str for key in value):
                    raise TypeError("uncacheable mapping keys")
                for key in sorted(value):
                    digest.update(self.fingerprint(key))
                    digest.update(self.fingerprint(value[key]))
            else:
                for item in value:
                    digest.update(self.fingerprint(item))
            result = digest.digest()
            self.fingerprints[id(value)] = (value, result)
            return result
        if value_type not in (type(None), bool, int, float, str):
            raise TypeError("uncacheable record input")
        key = (value_type, value.hex() if value_type is float else value)
        cached_scalar = self.scalars.get(key)
        if cached_scalar is not None:
            return cached_scalar
        # Fixed-size child hashes and separate container tags prevent ambiguous
        # concatenation. JSON distinguishes booleans, integers, floats, and -0.0.
        scalar = json.dumps(value, allow_nan=False, ensure_ascii=True).encode("ascii")
        result = hashlib.sha256(b"scalar" + scalar).digest()
        if len(self.scalars) < 512 and len(scalar) <= 256:
            self.scalars[key] = result
        return result


def _record_from_dict(payload: Mapping[str, Any], cache: _DecodeCache) -> SemanticRecord:
    if not isinstance(payload, Mapping):
        raise TypeError("record payload must be a mapping")
    if payload.get("$schema") != _RECORD_SCHEMA:
        raise ValueError("unsupported semantic record schema")

    record_type = payload.get("record_type")
    schema_version = payload.get("schema_version")
    expected_root = payload.get("root")
    data = payload.get("data")
    metadata = payload.get("metadata", {})

    if not isinstance(record_type, str) or record_type not in _RECORD_TYPES:
        raise ValueError("unknown semantic record type")
    record_cls = _RECORD_TYPES[record_type]
    if schema_version != record_cls.SCHEMA_VERSION:
        raise ValueError("unsupported semantic record version")
    if not isinstance(expected_root, str) or not isinstance(data, Mapping):
        raise ValueError("serialized semantic record is incomplete")
    expected_root = _validate_root(expected_root)
    if not isinstance(metadata, Mapping):
        raise ValueError("serialized semantic record metadata must be a mapping")

    # Composed workflows embed the same claim, snapshot, experiment, and evidence
    # records many times. Reconstruct an exact envelope once per outer decode.
    # Include metadata and all input data, never trust a claimed root as a key.
    # Public calls use fresh caches. Stores share one only inside a single
    # operation, before any decoded records are returned to callers.
    cache_key = None
    try:
        cache_key = cache.fingerprint(payload)
    except (TypeError, ValueError):
        # Preserve the decoder's handling of input mappings that are not
        # themselves canonical JSON; ordinary construction still validates.
        pass
    else:
        cached = cache.records.get(cache_key)
        if cached is not None and type(cached) is record_cls:
            return cached

    decoded = _decode_value(data, cache)
    if not isinstance(decoded, Mapping):
        raise ValueError("serialized semantic record data must be a mapping")
    record = record_cls(**dict(decoded), metadata=dict(metadata))
    if record.root != expected_root:
        raise ValueError("serialized semantic record root does not match its identity-bearing data")
    if cache_key is not None and len(cache.records) < 256:
        cache.records[cache_key] = record
    return record


def serialize_record(record: SemanticRecord) -> str:
    """Serialize a canonical record deterministically to JSON text."""

    return _RecordEncoder().serialize(record)


class _RecordEncoder:
    """Build shared immutable subrecords once within a serialization operation."""

    def __init__(self) -> None:
        self.documents: dict[int, tuple[Any, Any]] = {}

    def serialize(self, record: SemanticRecord) -> str:
        if not isinstance(record, SemanticRecord):
            raise TypeError("serialize_record requires a SemanticRecord")
        return canonical_json(self.value(record))

    def value(self, value: Any) -> Any:
        if isinstance(value, (SemanticRecord, FrozenMap, tuple)):
            cached = self.documents.get(id(value))
            if cached is not None:
                return cached[1]
            document: Any
            if isinstance(value, SemanticRecord):
                if type(value).to_dict is not SemanticRecord.to_dict:
                    document = value.to_dict()
                else:
                    document = _record_document(value, self.value)
            elif isinstance(value, FrozenMap):
                document = _serialize_map(value, self.value)
            else:
                document = [self.value(item) for item in value]
            self.documents[id(value)] = (value, document)
            return document
        if isinstance(value, RecordRef):
            return value.to_dict()
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        raise TypeError(f"unsupported record value type: {type(value).__name__}")


def deserialize_record(serialized: str) -> SemanticRecord:
    """Deserialize and integrity-check deterministic record JSON."""

    return _DecodeCache().deserialize(serialized)
