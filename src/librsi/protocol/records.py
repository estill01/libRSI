"""Canonical records owned by the external-agent admission boundary."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar

from ..capabilities import CAPABILITY_FAMILIES, CAPABILITY_POSTURES, CapabilityRoute
from ..governance import ApplicationGovernanceRequirement
from ..identity import FrozenMap
from ..intent import EvaluationContract, Objective
from ..records import (
    Evidence,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    register_record_type,
)

_REQUIRED_RESOURCE_LIMITS = frozenset({"max_actions", "max_failures", "max_retries"})
_WORKFLOW_NAMES = frozenset({"validation", "investigation", "improvement", "rsi"})


def _text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


@register_record_type
@dataclass(frozen=True, kw_only=True)
class CapabilityBinding(SemanticRecord):
    """One admitted action kind and its exact authority posture."""

    RECORD_TYPE: ClassVar[str] = "capability_binding"

    action_kind: str
    family: str
    posture: str

    def __post_init__(self) -> None:
        action_kind = _text(self.action_kind, "capability action kind")
        family = _text(self.family, "capability family")
        posture = _text(self.posture, "capability posture")
        if family not in CAPABILITY_FAMILIES:
            raise ValueError(f"unsupported capability family: {family}")
        if posture not in CAPABILITY_POSTURES:
            raise ValueError(f"unsupported capability posture: {posture}")
        object.__setattr__(self, "action_kind", action_kind)
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "posture", posture)
        if self.lineage:
            raise ValueError("capability bindings do not accept semantic lineage")
        super().__post_init__()

    def route(self) -> CapabilityRoute:
        return CapabilityRoute(self.action_kind, self.family, self.posture)


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RunAdmissionBinding(SemanticRecord):
    """Immutable authority association between one run request and admission."""

    RECORD_TYPE: ClassVar[str] = "run_admission_binding"

    run_id: str
    workflow: str
    request: RecordRef
    admission: RecordRef
    initial_snapshot: RecordRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text(self.run_id, "bound run id"))
        workflow = _text(self.workflow, "bound workflow")
        if workflow not in _WORKFLOW_NAMES:
            raise ValueError(f"unsupported bound workflow: {workflow}")
        object.__setattr__(self, "workflow", workflow)
        if not isinstance(self.request, RecordRef):
            raise TypeError("run admission bindings require an exact request reference")
        if (
            not isinstance(self.admission, RecordRef)
            or self.admission.record_type != "target_admission"
        ):
            raise TypeError("run admission bindings require a TargetAdmission reference")
        if (
            not isinstance(self.initial_snapshot, RecordRef)
            or self.initial_snapshot.record_type != "target_snapshot"
        ):
            raise TypeError("run admission bindings require a TargetSnapshot reference")
        expected = (self.request, self.admission, self.initial_snapshot)
        if tuple(self.lineage) != expected:
            raise ValueError("run admission binding lineage is incomplete")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        workflow: str,
        request: SemanticRecord,
        admission: TargetAdmission,
        initial_snapshot: TargetSnapshot,
    ) -> RunAdmissionBinding:
        if not isinstance(request, SemanticRecord):
            raise TypeError("run admission binding creation requires a semantic request")
        if type(admission) is not TargetAdmission:
            raise TypeError("run admission binding creation requires a TargetAdmission")
        if type(initial_snapshot) is not TargetSnapshot:
            raise TypeError("run admission binding creation requires a TargetSnapshot")
        refs = (request.ref, admission.ref, initial_snapshot.ref)
        return cls(
            run_id=run_id,
            workflow=workflow,
            request=refs[0],
            admission=refs[1],
            initial_snapshot=refs[2],
            lineage=refs,
        )


def _bindings(value: Sequence[CapabilityBinding]) -> tuple[CapabilityBinding, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("target admission capabilities must be a sequence")
    items = tuple(value)
    if not items or any(type(item) is not CapabilityBinding for item in items):
        raise TypeError("target admission requires CapabilityBinding values")
    ordered = tuple(sorted(items, key=lambda item: item.action_kind))
    if len({item.action_kind for item in ordered}) != len(ordered):
        raise ValueError("target admission action kinds must be unique")
    return ordered


def _evidence(value: Sequence[Evidence]) -> tuple[Evidence, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("target admission evidence must be a sequence")
    items = tuple(value)
    if any(type(item) is not Evidence for item in items):
        raise TypeError("target admission evidence must contain Evidence values")
    ordered = tuple(sorted(items, key=lambda item: item.root))
    if len({item.root for item in ordered}) != len(ordered):
        raise ValueError("target admission evidence must be unique")
    return ordered


def _limits(value: Mapping[str, float]) -> FrozenMap:
    if not isinstance(value, Mapping):
        raise TypeError("target admission resource limits must be a mapping")
    normalized: dict[str, float] = {}
    for key, raw in value.items():
        name = _text(key, "resource limit name")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError("resource limits must be numeric")
        number = float(raw)
        if not math.isfinite(number) or number < 0.0:
            raise ValueError("resource limits must be finite and nonnegative")
        normalized[name] = number
    if not _REQUIRED_RESOURCE_LIMITS.issubset(normalized):
        raise ValueError("resource limits require max_actions, max_failures, and max_retries")
    return FrozenMap(normalized)


@register_record_type
@dataclass(frozen=True, kw_only=True)
class TargetAdmission(SemanticRecord):
    """Complete standalone target contract required before external runs begin."""

    RECORD_TYPE: ClassVar[str] = "target_admission"

    admission_id: str
    target_snapshot: TargetSnapshot
    objective: Objective
    evaluation_contract: EvaluationContract
    capabilities: tuple[CapabilityBinding, ...]
    evidence_baseline: tuple[Evidence, ...] = ()
    application_requirement: ApplicationGovernanceRequirement
    resource_limits: Mapping[str, float] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(self, "admission_id", _text(self.admission_id, "admission id"))
        if type(self.target_snapshot) is not TargetSnapshot:
            raise TypeError("target admission requires an exact TargetSnapshot")
        if type(self.objective) is not Objective:
            raise TypeError("target admission requires an exact Objective")
        if type(self.evaluation_contract) is not EvaluationContract:
            raise TypeError("target admission requires an exact EvaluationContract")
        if (
            self.evaluation_contract.baseline.snapshot != self.target_snapshot
            or self.objective not in self.evaluation_contract.objectives
        ):
            raise ValueError("target admission objective and contract must use the exact snapshot")
        capabilities = _bindings(self.capabilities)
        evidence = _evidence(self.evidence_baseline)
        if any(
            item.target_snapshot != self.target_snapshot or not item.source_refs
            for item in evidence
        ):
            raise ValueError("target admission evidence must be current and exactly sourced")
        if (
            type(self.application_requirement) is not ApplicationGovernanceRequirement
            or self.application_requirement.target_snapshot != self.target_snapshot
        ):
            raise ValueError("target admission requires target-current application governance")
        limits = _limits(self.resource_limits)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "evidence_baseline", evidence)
        object.__setattr__(self, "resource_limits", limits)
        expected = (
            self.target_snapshot.ref,
            self.objective.ref,
            self.evaluation_contract.ref,
            *(item.ref for item in capabilities),
            *(item.ref for item in evidence),
            self.application_requirement.ref,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("target admission lineage is incomplete")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        admission_id: str,
        target_snapshot: TargetSnapshot,
        objective: Objective,
        evaluation_contract: EvaluationContract,
        capabilities: Sequence[CapabilityBinding],
        evidence_baseline: Sequence[Evidence] = (),
        application_requirement: ApplicationGovernanceRequirement,
        resource_limits: Mapping[str, float],
    ) -> TargetAdmission:
        capability_items = _bindings(capabilities)
        evidence_items = _evidence(evidence_baseline)
        return cls(
            admission_id=admission_id,
            target_snapshot=target_snapshot,
            objective=objective,
            evaluation_contract=evaluation_contract,
            capabilities=capability_items,
            evidence_baseline=evidence_items,
            application_requirement=application_requirement,
            resource_limits=resource_limits,
            lineage=(
                target_snapshot.ref,
                objective.ref,
                evaluation_contract.ref,
                *(item.ref for item in capability_items),
                *(item.ref for item in evidence_items),
                application_requirement.ref,
            ),
        )

    def binding_for(self, action_kind: str) -> CapabilityBinding:
        normalized = _text(action_kind, "action kind")
        matches = tuple(item for item in self.capabilities if item.action_kind == normalized)
        if len(matches) != 1:
            raise ValueError(f"target admission does not bind action kind: {normalized}")
        return matches[0]
