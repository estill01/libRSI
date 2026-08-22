from __future__ import annotations

import pytest

from librsi import (
    Constraint,
    Guardrail,
    Metric,
    Objective,
    StoppingRule,
    record_from_dict,
)
from tests.block13_support import intent_context


def test_evaluation_contract_round_trips_with_exact_goal_and_baseline_identity() -> None:
    context = intent_context()

    assert context.contract.goal == context.goal
    assert context.contract.baseline.snapshot == context.snapshot
    assert context.contract.objectives == (context.objective,)
    assert context.contract.guardrails == (context.guardrail,)
    assert record_from_dict(context.contract.to_dict()) == context.contract
    assert record_from_dict(context.request.to_dict()) == context.request


@pytest.mark.parametrize(
    ("semantics", "direction", "target_value"),
    (("minimize", "decrease", None), ("maximize", "increase", None), ("target", "target", 7.5)),
)
def test_objective_semantics_are_typed_and_metric_aligned(
    semantics: str,
    direction: str,
    target_value: float | None,
) -> None:
    context = intent_context()
    objective = Objective.create(
        objective_id=f"objective-{semantics}",
        metric=Metric(metric_id=f"metric-{semantics}", direction=direction),
        semantics=semantics,
        goal=context.goal,
        target_value=target_value,
    )

    assert objective.semantics == semantics
    assert objective.target_value == target_value


def test_guardrails_distinguish_no_regression_from_absolute_constraint() -> None:
    context = intent_context()
    constraint = Constraint(
        statement="Contamination must remain below 4 ppm", target=context.target
    )
    absolute = Guardrail.create(
        guardrail_id="absolute-contamination",
        metric=context.guardrail.metric,
        semantics="must-satisfy",
        constraint=constraint,
        operator="<=",
        threshold=4.0,
    )

    assert context.guardrail.semantics == "no-regression"
    assert absolute.semantics == "must-satisfy"
    assert absolute.threshold == 4.0


def test_stopping_rules_are_closed_and_explicit() -> None:
    with pytest.raises(ValueError, match="unsupported stopping rule"):
        StoppingRule(rule_id="opaque", kind="whatever", condition="stop sometime")
