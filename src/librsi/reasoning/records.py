"""Canonical provider-neutral reasoning request and proposal records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..identity import FrozenMap
from ..records import RecordRef, SemanticRecord, TargetSnapshot, register_record_type
from .schemas import REASONING_KINDS, validate_reasoning_content


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _refs(value: Sequence[RecordRef], label: str) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of RecordRef values")
    result = tuple(value)
    if any(not isinstance(item, RecordRef) for item in result):
        raise TypeError(f"{label} must contain RecordRef values")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must be unique")
    return result


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ReasoningRequest(SemanticRecord):
    """Exact cognitive task whose inputs and target currentness are explicit."""

    RECORD_TYPE: ClassVar[str] = "reasoning_request"

    request_id: str
    kind: str
    instruction: str
    input_refs: tuple[RecordRef, ...]
    target_snapshot: TargetSnapshot | None = None
    context: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_text(self.request_id, "request id"))
        kind = _require_text(self.kind, "reasoning kind")
        if kind not in REASONING_KINDS:
            raise ValueError(f"unsupported reasoning kind: {kind}")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "instruction", _require_text(self.instruction, "instruction"))
        inputs = _refs(self.input_refs, "reasoning inputs")
        if not inputs:
            raise ValueError("reasoning requests require input lineage")
        object.__setattr__(self, "input_refs", inputs)
        if self.target_snapshot is not None:
            if not isinstance(self.target_snapshot, TargetSnapshot):
                raise TypeError("reasoning target snapshot must be a TargetSnapshot")
            if self.target_snapshot.ref not in inputs:
                raise ValueError("reasoning target snapshot must be retained in input lineage")
        if not isinstance(self.context, Mapping):
            raise TypeError("reasoning context must be a mapping")
        object.__setattr__(self, "context", FrozenMap(self.context))
        lineage = _refs(self.lineage, "reasoning request lineage")
        if lineage != inputs:
            raise ValueError("reasoning request lineage must exactly match its input references")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ReasoningResult(SemanticRecord):
    """Validated structured proposal; it is not evidence, truth, or application authority."""

    RECORD_TYPE: ClassVar[str] = "reasoning_result"

    request: ReasoningRequest
    kind: str
    content: Mapping[str, Any]
    narration: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, ReasoningRequest):
            raise TypeError("reasoning result must contain its exact ReasoningRequest")
        kind = _require_text(self.kind, "reasoning result kind")
        if kind not in REASONING_KINDS:
            raise ValueError(f"unsupported reasoning kind: {kind}")
        if kind != self.request.kind:
            raise ValueError("reasoning result kind must match the exact request")
        object.__setattr__(self, "kind", kind)
        if not isinstance(self.content, Mapping):
            raise TypeError("reasoning result content must be a mapping")
        validate_reasoning_content(kind, self.content)
        object.__setattr__(self, "content", FrozenMap(self.content))
        if self.narration is not None:
            object.__setattr__(
                self, "narration", _require_text(self.narration, "reasoning narration")
            )
        expected_lineage = (self.request.ref, *self.request.input_refs)
        lineage = _refs(self.lineage, "reasoning result lineage")
        if lineage != expected_lineage:
            raise ValueError(
                "reasoning result lineage must retain the exact request and all inputs"
            )
        super().__post_init__()

    @classmethod
    def propose(
        cls,
        *,
        request: ReasoningRequest,
        content: Mapping[str, Any],
        narration: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ReasoningResult:
        """Construct a proposal with complete input/request lineage."""

        if not isinstance(request, ReasoningRequest):
            raise TypeError("reasoning proposal requires a ReasoningRequest")
        return cls(
            request=request,
            kind=request.kind,
            content=content,
            narration=narration,
            lineage=(request.ref, *request.input_refs),
            metadata=FrozenMap(metadata),
        )
