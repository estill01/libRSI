"""Strict provider-neutral schemas for structured reasoning proposals."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any

REASONING_KINDS = frozenset(
    {
        "reflection",
        "hypothesis-generation",
        "experiment-design",
        "explanation",
        "intervention-generation",
        "problem-decomposition",
        "approach-revision",
    }
)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise TypeError(f"{label} must be a string-keyed mapping")
    return value


def _shape(
    value: object,
    *,
    label: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    item = _mapping(value, label)
    keys = frozenset(item)
    missing = required - keys
    unexpected = keys - required - optional
    if missing:
        raise ValueError(f"{label} is missing fields: {sorted(missing)}")
    if unexpected:
        raise ValueError(f"{label} has unsupported fields: {sorted(unexpected)}")
    return item


def _items(value: object, label: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    result = tuple(value)
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _texts(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of text values")
    result = tuple(_require_text(item, label) for item in value)
    if not allow_empty and not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _reflection(content: Mapping[str, Any]) -> None:
    item = _shape(
        content,
        label="reflection result",
        required=frozenset({"summary", "observations", "open_questions"}),
    )
    _require_text(item["summary"], "reflection summary")
    _texts(item["observations"], "reflection observations")
    _texts(item["open_questions"], "reflection open questions", allow_empty=True)


def _hypothesis_generation(content: Mapping[str, Any]) -> None:
    item = _shape(
        content,
        label="hypothesis-generation result",
        required=frozenset({"hypotheses"}),
    )
    for proposal in _items(item["hypotheses"], "hypothesis proposals"):
        hypothesis = _shape(
            proposal,
            label="hypothesis proposal",
            required=frozenset({"statement", "causal_model", "predictions", "confidence"}),
        )
        _require_text(hypothesis["statement"], "hypothesis statement")
        _mapping(hypothesis["causal_model"], "hypothesis causal model")
        predictions = _items(hypothesis["predictions"], "hypothesis predictions")
        for prediction in predictions:
            _mapping(prediction, "hypothesis prediction")
        confidence = hypothesis["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise TypeError("hypothesis confidence must be a number")
        if not math.isfinite(float(confidence)) or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("hypothesis confidence must be finite and between zero and one")


def _experiment_design(content: Mapping[str, Any]) -> None:
    item = _shape(
        content,
        label="experiment-design result",
        required=frozenset({"experiments"}),
    )
    for proposal in _items(item["experiments"], "experiment proposals"):
        experiment = _shape(
            proposal,
            label="experiment proposal",
            required=frozenset({"objective", "design", "criteria", "requested_measurements"}),
        )
        _require_text(experiment["objective"], "experiment objective")
        _mapping(experiment["design"], "experiment design")
        _mapping(experiment["criteria"], "experiment criteria")
        _texts(experiment["requested_measurements"], "experiment measurements")


def _explanation(content: Mapping[str, Any]) -> None:
    item = _shape(
        content,
        label="explanation result",
        required=frozenset({"explanations"}),
    )
    for proposal in _items(item["explanations"], "explanation proposals"):
        explanation = _shape(
            proposal,
            label="explanation proposal",
            required=frozenset({"statement", "basis"}),
        )
        _require_text(explanation["statement"], "explanation statement")
        _texts(explanation["basis"], "explanation basis")


def _intervention_generation(content: Mapping[str, Any]) -> None:
    item = _shape(
        content,
        label="intervention-generation result",
        required=frozenset({"interventions"}),
    )
    for proposal in _items(item["interventions"], "intervention proposals"):
        intervention = _shape(
            proposal,
            label="intervention proposal",
            required=frozenset({"kind", "specification", "rationale", "expected_effects"}),
        )
        _require_text(intervention["kind"], "intervention kind")
        _mapping(intervention["specification"], "intervention specification")
        _mapping(intervention["rationale"], "intervention rationale")
        _mapping(intervention["expected_effects"], "intervention expected effects")


def _problem_decomposition(content: Mapping[str, Any]) -> None:
    item = _shape(
        content,
        label="problem-decomposition result",
        required=frozenset({"parts"}),
    )
    parts = _items(item["parts"], "decomposition parts")
    dependencies: dict[str, tuple[str, ...]] = {}
    for proposal in parts:
        part = _shape(
            proposal,
            label="decomposition part",
            required=frozenset({"part_id", "objective", "depends_on"}),
        )
        part_id = _require_text(part["part_id"], "decomposition part id")
        if part_id in dependencies:
            raise ValueError("decomposition part ids must be unique")
        _require_text(part["objective"], "decomposition objective")
        dependencies[part_id] = _texts(
            part["depends_on"], "decomposition dependencies", allow_empty=True
        )
    known = frozenset(dependencies)
    if any(dependency not in known for values in dependencies.values() for dependency in values):
        raise ValueError("decomposition dependencies must reference known parts")
    if any(part_id in values for part_id, values in dependencies.items()):
        raise ValueError("decomposition parts cannot depend on themselves")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(part_id: str) -> None:
        if part_id in visiting:
            raise ValueError("decomposition dependencies must be acyclic")
        if part_id in visited:
            return
        visiting.add(part_id)
        for dependency in dependencies[part_id]:
            visit(dependency)
        visiting.remove(part_id)
        visited.add(part_id)

    for part_id in dependencies:
        visit(part_id)


def _approach_revision(content: Mapping[str, Any]) -> None:
    item = _shape(
        content,
        label="approach-revision result",
        required=frozenset({"revisions"}),
    )
    for proposal in _items(item["revisions"], "approach revisions"):
        revision = _shape(
            proposal,
            label="approach revision",
            required=frozenset({"subject", "problem", "proposed_change", "rationale"}),
        )
        _require_text(revision["subject"], "revision subject")
        _require_text(revision["problem"], "revision problem")
        _mapping(revision["proposed_change"], "revision proposed change")
        _require_text(revision["rationale"], "revision rationale")


REASONING_SCHEMA_VALIDATORS: Mapping[str, Callable[[Mapping[str, Any]], None]] = MappingProxyType(
    {
        "reflection": _reflection,
        "hypothesis-generation": _hypothesis_generation,
        "experiment-design": _experiment_design,
        "explanation": _explanation,
        "intervention-generation": _intervention_generation,
        "problem-decomposition": _problem_decomposition,
        "approach-revision": _approach_revision,
    }
)


def validate_reasoning_content(kind: str, content: Mapping[str, Any]) -> None:
    """Validate one proposal against the exact schema for its reasoning kind."""

    normalized = _require_text(kind, "reasoning kind")
    validator = REASONING_SCHEMA_VALIDATORS.get(normalized)
    if validator is None:
        raise ValueError(f"unsupported reasoning kind: {normalized}")
    validator(_mapping(content, "reasoning content"))
