from __future__ import annotations

import json
import math
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, TypeVar

from .identity import FrozenMap, canonical_json, digest, freeze, thaw

_RECORD_SCHEMA = "librsi.record/v1"
_REF_SCHEMA = "librsi.ref/v1"
_MAP_SCHEMA = "librsi.map/v1"
_RECORD_TYPES: dict[str, type[Any]] = {}
_HEX = frozenset(string.hexdigits.lower())


def _require_text(value: str, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _validate_root(value: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(character not in _HEX for character in normalized):
        raise ValueError("record roots must be lowercase SHA-256 hex digests")
    return normalized


def _freeze_map(value: Mapping[str, Any] | FrozenMap | None) -> FrozenMap:
    return value if isinstance(value, FrozenMap) else FrozenMap(value)


def _text_tuple(value: Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    return tuple(_require_text(item, "text item") for item in value)


def _record_refs(
    value: Sequence[RecordRef] | None,
    *,
    label: str = "record references",
) -> tuple[RecordRef, ...]:
    refs = tuple(value or ())
    if any(not isinstance(item, RecordRef) for item in refs):
        raise TypeError(f"{label} must contain RecordRef values")
    return refs


def _evidence_refs(
    value: Sequence[EvidenceRef | RecordRef] | None,
) -> tuple[EvidenceRef, ...]:
    refs: list[EvidenceRef] = []
    for item in value or ():
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
    return tuple(_freeze_map(item) for item in (value or ()))


def _finite_number(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


@dataclass(frozen=True)
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

    @classmethod
    def from_record(cls, record: SemanticRecord) -> RecordRef:
        return cls(record.record_type, record.root)

    def matches(self, record: SemanticRecord) -> bool:
        return self.record_type == record.record_type and self.root == record.root

    def require(self, record: SemanticRecord) -> SemanticRecord:
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
    def from_evidence(cls, evidence: Evidence) -> EvidenceRef:
        if not isinstance(evidence, Evidence):
            raise TypeError("EvidenceRef requires an Evidence record")
        return cls(evidence.root)


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


def _serialize_map(value: FrozenMap) -> dict[str, Any]:
    return {
        "$schema": _MAP_SCHEMA,
        "items": {key: _serialize_value(item) for key, item in value.items()},
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, SemanticRecord):
        return value.to_dict()
    if isinstance(value, RecordRef):
        return value.to_dict()
    if isinstance(value, FrozenMap):
        return _serialize_map(value)
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported record value type: {type(value).__name__}")


def _decode_value(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_decode_value(item) for item in value)
    if not isinstance(value, Mapping):
        return value

    schema = value.get("$schema")
    if schema == _RECORD_SCHEMA:
        return record_from_dict(value)
    if schema == _REF_SCHEMA:
        record_type = value.get("record_type")
        root = value.get("root")
        if not isinstance(record_type, str) or not isinstance(root, str):
            raise ValueError("serialized record reference is incomplete")
        if record_type == "evidence":
            return EvidenceRef(root)
        return RecordRef(record_type, root)
    if schema == _MAP_SCHEMA:
        items = value.get("items")
        if not isinstance(items, Mapping):
            raise ValueError("serialized immutable mapping is incomplete")
        return {str(key): _decode_value(item) for key, item in items.items()}
    return {str(key): _decode_value(item) for key, item in value.items()}


@dataclass(frozen=True, kw_only=True)
class SemanticRecord:
    """Immutable, self-identifying, durably serializable semantic record."""

    RECORD_TYPE: ClassVar[str] = "record"
    SCHEMA_VERSION: ClassVar[int] = 1

    lineage: tuple[RecordRef, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(
        default_factory=FrozenMap,
        repr=False,
    )
    root: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "lineage",
            _record_refs(self.lineage, label="record lineage"),
        )
        object.__setattr__(
            self,
            "metadata",
            _freeze_map(self.metadata),
        )
        object.__setattr__(
            self,
            "root",
            digest(self.identity_payload()),
        )

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
        data = {
            item.name: _serialize_value(getattr(self, item.name))
            for item in fields(self)
            if item.name not in {"metadata", "root"}
        }
        return {
            "$schema": _RECORD_SCHEMA,
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "root": self.root,
            "data": data,
            "metadata": thaw(_freeze_map(self.metadata)),
        }


RecordT = TypeVar("RecordT", bound=SemanticRecord)


def _register(record_cls: type[RecordT]) -> type[RecordT]:
    record_type = record_cls.RECORD_TYPE
    if record_type in _RECORD_TYPES:
        raise RuntimeError(f"duplicate semantic record type: {record_type}")
    _RECORD_TYPES[record_type] = record_cls
    return record_cls


@_register
@dataclass(frozen=True, kw_only=True)
class TargetRef(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "target"

    target_id: str
    kind: str = "generic"
    locator: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_id",
            _require_text(self.target_id, "target id"),
        )
        object.__setattr__(
            self,
            "kind",
            _require_text(self.kind, "target kind"),
        )
        object.__setattr__(
            self,
            "locator",
            _freeze_map(self.locator),
        )
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
        object.__setattr__(self, "components", components)
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
        object.__setattr__(
            self,
            "statement",
            _require_text(self.statement, "claim statement"),
        )
        object.__setattr__(
            self,
            "kind",
            _require_text(self.kind, "claim kind"),
        )
        if self.target is not None and not isinstance(
            self.target,
            TargetRef,
        ):
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
        object.__setattr__(
            self,
            "prompt",
            _require_text(self.prompt, "question prompt"),
        )
        if self.target is not None and not isinstance(
            self.target,
            TargetRef,
        ):
            raise TypeError("question target must be a TargetRef")
        object.__setattr__(
            self,
            "context",
            _freeze_map(self.context),
        )
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Goal(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "goal"

    statement: str
    target: TargetRef | None = None
    scope: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "statement",
            _require_text(self.statement, "goal statement"),
        )
        if self.target is not None and not isinstance(
            self.target,
            TargetRef,
        ):
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
        if self.target is not None and not isinstance(
            self.target,
            TargetRef,
        ):
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
        if self.target is not None and not isinstance(
            self.target,
            TargetRef,
        ):
            raise TypeError("hypothesis target must be a TargetRef")
        object.__setattr__(
            self,
            "causal_model",
            _freeze_map(self.causal_model),
        )
        object.__setattr__(
            self,
            "predictions",
            _mapping_tuple(self.predictions),
        )
        object.__setattr__(
            self,
            "source_refs",
            _record_refs(
                self.source_refs,
                label="hypothesis source references",
            ),
        )
        confidence = _finite_number(
            self.confidence,
            "hypothesis confidence",
        )
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("hypothesis confidence must be between zero and one")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(
            self,
            "status",
            _require_text(self.status, "hypothesis status"),
        )
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
            _record_refs(
                self.subject_refs,
                label="evidence subject references",
            ),
        )
        object.__setattr__(
            self,
            "source_refs",
            _record_refs(
                self.source_refs,
                label="evidence source references",
            ),
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

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "experiment_id",
            _require_text(self.experiment_id, "experiment id"),
        )
        object.__setattr__(
            self,
            "kind",
            _require_text(self.kind, "experiment kind"),
        )
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("experiment target snapshot must be a TargetSnapshot")
        object.__setattr__(self, "design", _freeze_map(self.design))
        object.__setattr__(
            self,
            "criteria",
            _freeze_map(self.criteria),
        )
        object.__setattr__(self, "inputs", _freeze_map(self.inputs))
        object.__setattr__(
            self,
            "environment",
            _freeze_map(self.environment),
        )
        object.__setattr__(
            self,
            "requested_measurements",
            _text_tuple(self.requested_measurements),
        )
        super().__post_init__()


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
        object.__setattr__(
            self,
            "kind",
            _require_text(self.kind, "observation kind"),
        )
        object.__setattr__(self, "value", freeze(self.value))
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("observation target snapshot must be a TargetSnapshot")
        object.__setattr__(
            self,
            "source_refs",
            _record_refs(
                self.source_refs,
                label="observation source references",
            ),
        )
        object.__setattr__(self, "valid", bool(self.valid))
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

    def __post_init__(self) -> None:
        if (
            not isinstance(self.experiment, RecordRef)
            or self.experiment.record_type != "experiment_spec"
        ):
            raise TypeError("trial experiment must reference an ExperimentSpec")
        index = int(self.index)
        if index < 0:
            raise ValueError("trial index must be nonnegative")
        object.__setattr__(self, "index", index)
        object.__setattr__(
            self,
            "status",
            _require_text(self.status, "trial status"),
        )
        object.__setattr__(
            self,
            "observation_refs",
            _record_refs(
                self.observation_refs,
                label="trial observation references",
            ),
        )
        object.__setattr__(self, "data", _freeze_map(self.data))
        super().__post_init__()


@_register
@dataclass(frozen=True, kw_only=True)
class Measurement(SemanticRecord):
    RECORD_TYPE: ClassVar[str] = "measurement"

    metric: str
    value: Any
    unit: str | None = None
    target_snapshot: TargetSnapshot | None = None
    observation_refs: tuple[RecordRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metric",
            _require_text(self.metric, "measurement metric"),
        )
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
            _record_refs(
                self.observation_refs,
                label="measurement observation references",
            ),
        )
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
            _record_refs(
                self.subject_refs,
                label="evaluation subject references",
            ),
        )
        if not self.subject_refs:
            raise ValueError("evaluation requires at least one subject reference")
        object.__setattr__(
            self,
            "disposition",
            _require_text(
                self.disposition,
                "evaluation disposition",
            ),
        )
        measurements = tuple(self.measurements)
        if any(not isinstance(item, Measurement) for item in measurements):
            raise TypeError("evaluation measurements must be Measurement records")
        object.__setattr__(self, "measurements", measurements)
        object.__setattr__(
            self,
            "findings",
            _freeze_map(self.findings),
        )
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
        object.__setattr__(
            self,
            "uri",
            _require_text(self.uri, "artifact uri"),
        )
        object.__setattr__(
            self,
            "content_digest",
            None
            if self.content_digest is None
            else _require_text(
                self.content_digest,
                "artifact content digest",
            ),
        )
        object.__setattr__(
            self,
            "media_type",
            None
            if self.media_type is None
            else _require_text(
                self.media_type,
                "artifact media type",
            ),
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
        object.__setattr__(
            self,
            "kind",
            _require_text(self.kind, "intervention kind"),
        )
        object.__setattr__(
            self,
            "specification",
            _freeze_map(self.specification),
        )
        object.__setattr__(
            self,
            "rationale",
            _freeze_map(self.rationale),
        )
        object.__setattr__(
            self,
            "expected_effects",
            _freeze_map(self.expected_effects),
        )
        constraints = tuple(self.constraints)
        if any(not isinstance(item, Constraint) for item in constraints):
            raise TypeError("intervention constraints must be Constraint records")
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(
            self,
            "validation_plan",
            _freeze_map(self.validation_plan),
        )
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
        object.__setattr__(
            self,
            "status",
            _require_text(self.status, "candidate status"),
        )
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
        object.__setattr__(
            self,
            "status",
            _require_text(self.status, "outcome status"),
        )
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot,
            TargetSnapshot,
        ):
            raise TypeError("outcome target snapshot must be a TargetSnapshot")
        object.__setattr__(
            self,
            "conclusions",
            _text_tuple(self.conclusions),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence_refs(self.evidence_refs),
        )
        interventions = _record_refs(
            self.intervention_refs,
            label="outcome intervention references",
        )
        if any(item.record_type != "intervention" for item in interventions):
            raise TypeError("outcome intervention references must point to interventions")
        object.__setattr__(
            self,
            "intervention_refs",
            interventions,
        )
        artifacts = tuple(self.artifacts)
        if any(not isinstance(item, ArtifactRef) for item in artifacts):
            raise TypeError("outcome artifacts must be ArtifactRef records")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(
            self,
            "unresolved",
            _text_tuple(self.unresolved),
        )
        object.__setattr__(
            self,
            "next_actions",
            _text_tuple(self.next_actions),
        )
        super().__post_init__()


def record_from_dict(payload: Mapping[str, Any]) -> SemanticRecord:
    """Reconstruct and integrity-check a record from durable data."""

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

    decoded = _decode_value(data)
    if not isinstance(decoded, Mapping):
        raise ValueError("serialized semantic record data must be a mapping")
    record = record_cls(
        **dict(decoded),
        metadata=dict(metadata),
    )
    if record.root != expected_root:
        raise ValueError("serialized semantic record root does not match its identity-bearing data")
    return record


def serialize_record(record: SemanticRecord) -> str:
    """Serialize a canonical record deterministically to JSON text."""

    if not isinstance(record, SemanticRecord):
        raise TypeError("serialize_record requires a SemanticRecord")
    return canonical_json(record.to_dict())


def deserialize_record(serialized: str) -> SemanticRecord:
    """Deserialize and integrity-check deterministic record JSON."""

    payload = json.loads(serialized)
    if not isinstance(payload, Mapping):
        raise ValueError("serialized semantic record must contain a JSON object")
    return record_from_dict(payload)
