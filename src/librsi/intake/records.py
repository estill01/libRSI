"""Host registrations and plain-language inputs for service intake."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..comparison import RiskPolicy
from ..identity import FrozenMap, thaw
from ..improvement import ImprovementBudget
from ..intent import Guardrail
from ..protocol import CapabilityBinding
from ..records import Constraint, Evidence, Metric, Observation, TargetSnapshot


def text(value: str, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


@dataclass(frozen=True)
class IntakeRequest:
    request_id: str
    goal: str
    context: Mapping[str, Any] = field(default_factory=FrozenMap)
    adapter_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", text(self.request_id, "request id"))
        object.__setattr__(self, "goal", text(self.goal, "goal"))
        if not isinstance(self.context, Mapping):
            raise TypeError("intake context must be an object")
        object.__setattr__(self, "context", FrozenMap(self.context))
        if self.adapter_id is not None:
            object.__setattr__(self, "adapter_id", text(self.adapter_id, "adapter id"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "goal": self.goal,
            "context": thaw(self.context),
            "adapter_id": self.adapter_id,
        }

    @property
    def record(self) -> Observation:
        return Observation(kind="intake.request", value=self.to_dict())


class IntakeNeedsInformation(ValueError):
    """A collector knows which facts are required before it can observe a target."""

    def __init__(self, *questions: str) -> None:
        if not questions:
            raise ValueError("missing-information results require questions")
        self.questions = tuple(text(item, "question") for item in questions)
        super().__init__("intake requires additional information")


@dataclass(frozen=True)
class IntakeMetric:
    metric: Metric
    baseline: float
    minimum_effect: float
    description: str

    def __post_init__(self) -> None:
        if (
            type(self.metric) is not Metric
            or self.metric.role != "objective"
            or self.metric.direction not in {"increase", "decrease"}
        ):
            raise ValueError("intake requires an increasing or decreasing objective metric")
        for value in (self.baseline, self.minimum_effect):
            if type(value) not in {int, float} or not math.isfinite(value):
                raise ValueError("intake measurements and effect floors must be finite")
        if self.minimum_effect <= 0:
            raise ValueError("minimum effect floor must be positive")
        text(self.description, "metric description")

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric.to_dict(),
            "baseline": self.baseline,
            "minimum_effect": self.minimum_effect,
            "description": self.description,
        }


@dataclass(frozen=True)
class IntakeContext:
    """Read-only host observations; never inferred measurements from a model."""

    snapshot: TargetSnapshot
    metrics: tuple[IntakeMetric, ...]
    facts: Mapping[str, Any] = field(default_factory=FrozenMap)
    constraints: tuple[Constraint, ...] = ()
    guardrails: tuple[Guardrail, ...] = ()
    guardrail_measurements: Mapping[str, float] = field(default_factory=FrozenMap)
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        if type(self.snapshot) is not TargetSnapshot:
            raise TypeError("intake observations require an exact snapshot")
        metrics = tuple(self.metrics)
        if not metrics or any(type(item) is not IntakeMetric for item in metrics):
            raise ValueError("intake observations require measured metric choices")
        if len({item.metric.metric_id for item in metrics}) != len(metrics):
            raise ValueError("intake metric ids must be unique")
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "facts", FrozenMap(self.facts))
        object.__setattr__(self, "guardrail_measurements", FrozenMap(self.guardrail_measurements))
        for name, kind in (
            ("constraints", Constraint),
            ("guardrails", Guardrail),
            ("evidence", Evidence),
        ):
            items = tuple(getattr(self, name))
            if any(type(item) is not kind for item in items):
                raise TypeError(f"invalid intake {name}")
            object.__setattr__(self, name, items)

    def record(self, request: IntakeRequest) -> Observation:
        return Observation(
            kind="intake.context",
            target_snapshot=self.snapshot,
            source_refs=(request.record.ref,),
            value={
                "metrics": [item.to_dict() for item in self.metrics],
                "facts": thaw(self.facts),
                "constraints": [item.to_dict() for item in self.constraints],
                "guardrails": [item.to_dict() for item in self.guardrails],
                "guardrail_measurements": thaw(self.guardrail_measurements),
                "evidence": [item.to_dict() for item in self.evidence],
            },
        )


@dataclass(frozen=True)
class IntakeAdapter:
    """Register one target family once; callers then submit ordinary goals/context.

    collect is read-only and bounded by the host. Version adapter_id when its
    observation, measurement, or execution semantics change.
    """

    adapter_id: str
    description: str
    collect: Callable[[IntakeRequest], IntakeContext]
    capabilities: tuple[CapabilityBinding, ...]
    workflows: tuple[str, ...] = ("improvement", "investigation")
    budget: ImprovementBudget = field(default_factory=ImprovementBudget)
    risk_policy: RiskPolicy = field(default_factory=lambda: RiskPolicy(policy_id="intake-risk-v1"))
    max_hypotheses: int = 4

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", text(self.adapter_id, "adapter id"))
        object.__setattr__(self, "description", text(self.description, "adapter description"))
        if not callable(self.collect):
            raise TypeError("intake adapter requires a context collector")
        if type(self.budget) is not ImprovementBudget or type(self.risk_policy) is not RiskPolicy:
            raise TypeError("intake adapter requires native budget and risk policies")
        if type(self.max_hypotheses) is not int or not 2 <= self.max_hypotheses <= 32:
            raise ValueError("intake hypothesis limit must be between 2 and 32")
        workflows = tuple(self.workflows)
        if (
            not workflows
            or len(set(workflows)) != len(workflows)
            or not set(workflows) <= {"improvement", "investigation"}
        ):
            raise ValueError("unsupported or duplicate intake workflows")
        bindings = tuple(self.capabilities)
        if any(type(item) is not CapabilityBinding for item in bindings):
            raise TypeError("intake capabilities require exact bindings")
        kinds = {item.action_kind for item in bindings}
        if len(kinds) != len(bindings):
            raise ValueError("duplicate intake capability bindings")
        required = set()
        if "improvement" in workflows:
            required.add("improvement-cycle")
        if "investigation" in workflows:
            required.update(("investigation-reason", "investigation-experiment"))
        if not required <= kinds:
            raise ValueError("adapter is missing workflow capability bindings")
        object.__setattr__(self, "workflows", workflows)
        object.__setattr__(self, "capabilities", bindings)

    def description_record(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "description": self.description,
            "workflows": list(self.workflows),
            "max_hypotheses": self.max_hypotheses,
            "budget": self.budget.to_dict(),
            "risk_policy": self.risk_policy.to_dict(),
            "capabilities": [item.to_dict() for item in self.capabilities],
        }
