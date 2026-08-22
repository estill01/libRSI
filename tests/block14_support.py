from __future__ import annotations

from dataclasses import dataclass

from librsi import (
    CandidateSnapshot,
    CandidateTrialBatch,
    Claim,
    Constraint,
    DecisionRule,
    EvaluationContract,
    Evidence,
    ExperimentEvaluator,
    Goal,
    Guardrail,
    Hypothesis,
    InterventionImplementationRequest,
    InterventionSpec,
    Measurement,
    Metric,
    Objective,
    Observation,
    RiskPolicy,
    StoppingRule,
    TargetRef,
    TargetSnapshot,
)


@dataclass(frozen=True)
class ComparisonContext:
    target: TargetRef
    baseline_snapshot: TargetSnapshot
    contract: EvaluationContract
    yield_metric: Metric
    energy_metric: Metric
    contamination_metric: Metric
    constraint: Constraint
    risk_policy: RiskPolicy


def comparison_context() -> ComparisonContext:
    target = TargetRef(target_id="fermenter-7", kind="physical-process")
    snapshot = TargetSnapshot(
        target=target,
        revision="batch-19",
        state={"yield_pct": 72.0, "energy_kwh": 18.0, "contamination_ppm": 2.0},
    )
    goal = Goal(
        statement="Increase yield and reduce energy without increasing contamination",
        target=target,
    )
    from librsi import Baseline

    baseline = Baseline.create(
        snapshot=snapshot,
        measurements={"yield_pct": 72.0, "energy_kwh": 18.0, "contamination_ppm": 2.0},
    )
    yield_metric = Metric(
        metric_id="yield_pct", direction="increase", role="objective", unit="percent"
    )
    energy_metric = Metric(
        metric_id="energy_kwh", direction="decrease", role="objective", unit="kWh"
    )
    contamination_metric = Metric(
        metric_id="contamination_ppm", direction="decrease", role="guardrail", unit="ppm"
    )
    objectives = (
        Objective.create(
            objective_id="increase-yield",
            metric=yield_metric,
            semantics="maximize",
            goal=goal,
            minimum_effect=1.0,
        ),
        Objective.create(
            objective_id="reduce-energy",
            metric=energy_metric,
            semantics="minimize",
            goal=goal,
            minimum_effect=0.5,
        ),
    )
    constraint = Constraint(
        statement="Contamination cannot regress",
        target=target,
        lineage=(snapshot.ref,),
    )
    guardrail = Guardrail.create(
        guardrail_id="contamination-no-regression",
        metric=contamination_metric,
        semantics="no-regression",
        constraint=constraint,
    )
    stop = StoppingRule(
        rule_id="selection-complete",
        kind="criteria-sufficient",
        condition="Stop after evidence-bound comparison",
    )
    contract = EvaluationContract.create(
        contract_id="fermenter-multi-objective-v1",
        goal=goal,
        baseline=baseline,
        objectives=objectives,
        constraints=(constraint,),
        guardrails=(guardrail,),
        stopping_rules=(stop,),
    )
    return ComparisonContext(
        target=target,
        baseline_snapshot=snapshot,
        contract=contract,
        yield_metric=yield_metric,
        energy_metric=energy_metric,
        contamination_metric=contamination_metric,
        constraint=constraint,
        risk_policy=RiskPolicy(policy_id="conservative", confidence_multiplier=1.0),
    )


def candidate_for(context: ComparisonContext, candidate_id: str) -> CandidateSnapshot:
    claim = Claim(
        statement=f"Candidate {candidate_id} may improve the fermenter",
        target=context.target,
        lineage=(context.baseline_snapshot.ref,),
    )
    evidence = Evidence(
        evidence_type="support",
        data={"candidate": candidate_id},
        subject_refs=(claim.ref,),
        source_refs=(context.baseline_snapshot.ref,),
        target_snapshot=context.baseline_snapshot,
        weight=0.7,
        lineage=(claim.ref, context.baseline_snapshot.ref),
    )
    intervention = InterventionSpec.create(
        intervention_id=f"intervention-{candidate_id}",
        baseline=context.baseline_snapshot,
        kind="process.parameter_change",
        specification={"candidate": candidate_id},
        rationale=("Bounded fermenter parameter change",),
        supporting_refs=(claim.ref,),
        evidence=(evidence,),
        expected_effects={"yield_pct": "increase", "energy_kwh": "decrease"},
        risks=("Contamination may increase",),
        constraints=(context.constraint,),
        validation_plan={"repetitions": 3},
        rollback_expectations={"restore": context.baseline_snapshot.revision},
    )
    request = InterventionImplementationRequest.for_intervention(
        intervention,
        candidate_id=candidate_id,
    )
    snapshot = TargetSnapshot(
        target=context.target,
        revision=f"candidate-{candidate_id}",
        state={"candidate": candidate_id},
    )
    return CandidateSnapshot.prepared(request=request, snapshot=snapshot)


def trial_batch(
    context: ComparisonContext,
    candidate: CandidateSnapshot,
    *,
    baseline_rows: tuple[tuple[float, float, float], ...] = (
        (72.0, 18.0, 2.0),
        (72.0, 18.0, 2.0),
        (72.0, 18.0, 2.0),
    ),
    candidate_rows: tuple[tuple[float, float, float], ...] = (
        (76.0, 16.0, 2.0),
        (76.0, 16.0, 2.0),
        (76.0, 16.0, 2.0),
    ),
    invalid: tuple[tuple[str, int], ...] = (),
    baseline_snapshot: TargetSnapshot | None = None,
    sparse_metrics: bool = False,
) -> CandidateTrialBatch:
    evaluator = ExperimentEvaluator()
    metrics = (
        context.yield_metric,
        context.energy_metric,
        context.contamination_metric,
    )
    yield_rule = (
        DecisionRule(
            metric=context.yield_metric.ref,
            kind="threshold",
            operator=">=",
            threshold=0.0,
            required_valid_trials=2,
        )
        if context.yield_metric.direction == "target"
        else DecisionRule(
            metric=context.yield_metric.ref,
            kind="baseline_delta",
            minimum_effect=1.0,
            required_valid_trials=2,
        )
    )
    rules = (
        yield_rule,
        DecisionRule(
            metric=context.energy_metric.ref,
            kind="baseline_delta",
            minimum_effect=0.5,
            required_valid_trials=2,
        ),
        DecisionRule(
            metric=context.contamination_metric.ref,
            kind="threshold",
            operator="<=",
            threshold=2.0,
            required_valid_trials=2,
        ),
    )
    hypothesis = Hypothesis(
        statement=f"Candidate {candidate.request.candidate_id} improves the exact baseline",
        target=context.target,
        lineage=(candidate.ref, context.contract.ref),
    )
    experiment = evaluator.design(
        experiment_id=f"compare-{candidate.request.candidate_id}",
        subject=hypothesis,
        kind="controlled-process-trial",
        metrics=metrics,
        decision_rules=rules,
        baseline_snapshot=baseline_snapshot or context.baseline_snapshot,
        candidate_snapshot=candidate.snapshot,
        repetitions=3,
        seeds=(1, 2, 3),
        validity_requirements={"require_all_metrics": not sparse_metrics},
    )
    results = []
    metric_by_id = {item.metric_id: item for item in metrics}
    invalid_set = set(invalid)
    for role, rows in (("baseline", baseline_rows), ("candidate", candidate_rows)):
        snapshot = experiment.baseline_snapshot if role == "baseline" else candidate.snapshot
        assert snapshot is not None
        for index, (yield_value, energy_value, contamination_value) in enumerate(rows):
            trial = evaluator.prepare_trial(experiment, index=index, role=role)  # type: ignore[arg-type]
            if (role, index) in invalid_set:
                results.append(
                    evaluator.record_result(
                        experiment,
                        trial=trial,
                        disposition="invalid",
                        reason="sensor calibration failed",
                    )
                )
                continue
            reported = (
                (
                    ("yield_pct", yield_value),
                    ("energy_kwh", energy_value),
                    ("contamination_ppm", contamination_value),
                )
                if not sparse_metrics
                else (
                    (
                        ("yield_pct", yield_value),
                        ("energy_kwh", energy_value),
                        ("contamination_ppm", contamination_value),
                    )[index],
                )
            )
            observations = tuple(
                Observation(
                    kind=f"fermenter.{metric_id}",
                    value=value,
                    target_snapshot=snapshot,
                    source_refs=(trial.ref,),
                )
                for metric_id, value in reported
            )
            measurements = tuple(
                Measurement(
                    metric=metric_id,
                    metric_ref=metric_by_id[metric_id].ref,
                    value=value,
                    unit=metric_by_id[metric_id].unit,
                    target_snapshot=snapshot,
                    observation_refs=(observation.ref,),
                )
                for observation, (metric_id, value) in zip(observations, reported, strict=True)
            )
            results.append(
                evaluator.record_result(
                    experiment,
                    trial=trial,
                    disposition="valid",
                    observations=observations,
                    measurements=measurements,
                )
            )
    return CandidateTrialBatch.create(
        contract=context.contract,
        candidate=candidate,
        experiment=experiment,
        results=results,
    )
