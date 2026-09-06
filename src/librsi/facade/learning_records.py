"""Small host-facing inputs for adaptive strategy composition."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..identity import FrozenMap
from ..records import Metric, Observation


@dataclass(frozen=True)
class LearningCase:
    case_id: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("learning case requires an id")
        if not isinstance(self.payload, Mapping):
            raise TypeError("case payload must be a JSON object")
        object.__setattr__(self, "payload", FrozenMap(self.payload))

    @property
    def record(self) -> Observation:
        return Observation(
            kind="learning.case",
            value={"case_id": self.case_id, "payload": self.payload},
        )


@dataclass(frozen=True)
class TaskMeasurement:
    """Actual host output and its measured value for the configured objective."""

    output: Mapping[str, Any]
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.output, Mapping):
            raise TypeError("task output must be a JSON object")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError("task measurement must be numeric")
        if not math.isfinite(self.value):
            raise ValueError("task measurement must be finite")
        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "output", FrozenMap(self.output))


@runtime_checkable
class LearningAdapter(Protocol):
    """The consumer owns configuration semantics, actual work, and measurement.

    Change adapter_id whenever execution or scoring semantics change. Evaluation
    must keep candidates isolated from the consumer's authoritative live target.
    """

    adapter_id: str

    def validate_configuration(self, configuration: Mapping[str, Any]) -> None: ...

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement: ...


@dataclass(frozen=True)
class LearningPolicy:
    """One bounded generation per pass; the host decides when to request a pass."""

    objective: str
    metric: Metric
    minimum_effect: float
    min_new_feedback: int = 2
    max_feedback: int = 8
    max_candidates: int = 2
    max_cases: int = 8

    def __post_init__(self) -> None:
        if not isinstance(self.objective, str) or not self.objective.strip():
            raise ValueError("learning requires a measurable objective")
        if (
            not isinstance(self.metric, Metric)
            or self.metric.role != "objective"
            or self.metric.direction not in {"increase", "decrease"}
        ):
            raise ValueError("learning requires one increasing or decreasing objective metric")
        if (
            isinstance(self.minimum_effect, bool)
            or not isinstance(self.minimum_effect, (int, float))
            or not math.isfinite(self.minimum_effect)
            or self.minimum_effect <= 0
        ):
            raise ValueError("minimum effect must be positive and finite")
        for name in ("min_new_feedback", "max_feedback", "max_candidates", "max_cases"):
            value = getattr(self, name)
            if type(value) is not int or value < 2:
                raise ValueError(f"{name} must be an integer of at least 2")
        if self.min_new_feedback > min(self.max_feedback, self.max_cases):
            raise ValueError("feedback and case allowances cannot be smaller than the trigger")

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "metric": self.metric.to_dict(),
            "minimum_effect": self.minimum_effect,
            "min_new_feedback": self.min_new_feedback,
            "max_feedback": self.max_feedback,
            "max_candidates": self.max_candidates,
            "max_cases": self.max_cases,
        }
