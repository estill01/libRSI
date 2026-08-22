from __future__ import annotations

from dataclasses import dataclass

from librsi import (
    Baseline,
    Constraint,
    EvaluationContract,
    Goal,
    Guardrail,
    Metric,
    Objective,
    OperationalizationRequest,
    StoppingRule,
    TargetRef,
    TargetSnapshot,
)


@dataclass(frozen=True)
class IntentContext:
    target: TargetRef
    snapshot: TargetSnapshot
    goal: Goal
    baseline: Baseline
    objective: Objective
    constraint: Constraint
    guardrail: Guardrail
    stop: StoppingRule
    contract: EvaluationContract
    request: OperationalizationRequest


def intent_context() -> IntentContext:
    target = TargetRef(target_id="fermenter-7", kind="physical-process")
    snapshot = TargetSnapshot(
        target=target,
        revision="batch-18",
        state={"temperature_c": 31.0, "yield_pct": 72.0, "contamination_ppm": 2.0},
    )
    goal = Goal(
        statement="Increase fermentation yield without increasing contamination",
        target=target,
    )
    baseline = Baseline.create(
        snapshot=snapshot,
        measurements={"yield_pct": 72.0, "contamination_ppm": 2.0},
    )
    yield_metric = Metric(
        metric_id="yield_pct",
        direction="increase",
        role="objective",
        unit="percent",
    )
    objective = Objective.create(
        objective_id="increase-yield",
        metric=yield_metric,
        semantics="maximize",
        goal=goal,
        minimum_effect=1.0,
    )
    constraint = Constraint(
        statement="Contamination must not increase",
        target=target,
    )
    contamination = Metric(
        metric_id="contamination_ppm",
        direction="decrease",
        role="guardrail",
        unit="ppm",
    )
    guardrail = Guardrail.create(
        guardrail_id="contamination-no-regression",
        metric=contamination,
        semantics="no-regression",
        constraint=constraint,
    )
    stop = StoppingRule(
        rule_id="criteria-complete",
        kind="criteria-sufficient",
        condition="Stop operationalization when every objective and constraint is measurable",
    )
    contract = EvaluationContract.create(
        contract_id="fermenter-yield-v1",
        goal=goal,
        baseline=baseline,
        objectives=(objective,),
        constraints=(constraint,),
        guardrails=(guardrail,),
        stopping_rules=(stop,),
    )
    request = OperationalizationRequest.create(
        request_id="fermenter-goal",
        goal=goal,
        current_snapshot=snapshot,
        known_facts={"yield_source": "inline refractometer"},
    )
    return IntentContext(
        target=target,
        snapshot=snapshot,
        goal=goal,
        baseline=baseline,
        objective=objective,
        constraint=constraint,
        guardrail=guardrail,
        stop=stop,
        contract=contract,
        request=request,
    )
