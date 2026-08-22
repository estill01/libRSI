from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Baseline,
    Constraint,
    EvaluationContract,
    Evidence,
    Guardrail,
    Metric,
    OperationalizationPolicy,
    OperationalizationProposal,
)
from tests.block13_support import intent_context


def test_nonfinite_measurements_and_missing_required_baselines_fail_closed() -> None:
    context = intent_context()
    with pytest.raises(ValueError, match="finite"):
        Baseline.create(snapshot=context.snapshot, measurements={"yield_pct": float("nan")})

    empty = Baseline.create(snapshot=context.snapshot, measurements={})
    with pytest.raises(ValueError, match="missing required baselines"):
        replace(
            context.contract,
            baseline=empty,
            lineage=(
                context.goal.ref,
                empty.ref,
                context.objective.ref,
                context.constraint.ref,
                context.guardrail.ref,
                context.stop.ref,
            ),
        )


def test_contradictory_typed_constraints_are_rejected_before_evaluation() -> None:
    context = intent_context()
    low = Constraint(statement="Safety score must be at most 5", target=context.target)
    high = Constraint(statement="Safety score must be at least 10", target=context.target)
    metric = Metric(metric_id="safety", direction="target", role="guardrail")
    low_rule = Guardrail.create(
        guardrail_id="low",
        metric=metric,
        semantics="must-satisfy",
        constraint=low,
        operator="<=",
        threshold=5.0,
    )
    high_rule = Guardrail.create(
        guardrail_id="high",
        metric=metric,
        semantics="must-satisfy",
        constraint=high,
        operator=">=",
        threshold=10.0,
    )
    with pytest.raises(ValueError, match="contradictory guardrails"):
        EvaluationContract.create(
            contract_id="contradictory",
            goal=context.goal,
            baseline=context.baseline,
            objectives=(context.objective,),
            constraints=(low, high),
            guardrails=(low_rule, high_rule),
            stopping_rules=(context.stop,),
        )


def test_goal_cannot_be_promoted_to_evidence_and_untyped_contract_is_rejected() -> None:
    context = intent_context()
    with pytest.raises(ValueError, match="Goals cannot be treated"):
        Evidence(
            evidence_type="support",
            data={"narration": "the goal says improvement is desired"},
            subject_refs=(context.goal.ref,),
            source_refs=(context.request.ref,),
            target_snapshot=context.snapshot,
        )
    with pytest.raises((TypeError, ValueError)):
        OperationalizationProposal(
            request=context.request,
            disposition="operationalized",
            contract={"metric": "made-up"},  # type: ignore[arg-type]
            lineage=(context.request.ref,),
        )


def test_stale_baseline_and_unoperationalized_constraints_fail_closed() -> None:
    context = intent_context()
    stale_snapshot = replace(context.snapshot, revision="batch-17")
    stale_baseline = Baseline.create(
        snapshot=stale_snapshot,
        measurements=context.baseline.measurements,
    )
    stale_contract = replace(
        context.contract,
        baseline=stale_baseline,
        lineage=(
            context.goal.ref,
            stale_baseline.ref,
            context.objective.ref,
            context.constraint.ref,
            context.guardrail.ref,
            context.stop.ref,
        ),
    )
    with pytest.raises(ValueError, match="stale"):
        OperationalizationPolicy.validate_contract(context.request, stale_contract)

    with pytest.raises(ValueError, match="every contract Constraint"):
        replace(context.contract, guardrails=())
