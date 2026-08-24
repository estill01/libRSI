"""In-repository consumer fixture using only public libRSI contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from librsi import (
    Baseline,
    CandidateSnapshot,
    CandidateTrialBatch,
    Claim,
    Constraint,
    DecisionRule,
    EvaluationContract,
    Evidence,
    ExperimentEvaluator,
    Goal,
    Hypothesis,
    InterventionImplementationRequest,
    InterventionSpec,
    Measurement,
    Metric,
    Objective,
    Observation,
    RSIResult,
    StoppingRule,
    TargetSnapshot,
    ValidationResult,
    validate,
)
from librsi.conformance import ComponentState, CompositeSnapshot, map_composite_snapshot
from tests.block19_support import workflow_results


@dataclass(frozen=True, slots=True)
class OrdinaryConsumerRun:
    mapped: CompositeSnapshot
    validation: ValidationResult
    candidate: CandidateSnapshot
    candidate_trials: CandidateTrialBatch


def _candidate_trials(
    mapped: CompositeSnapshot, candidate: CandidateSnapshot
) -> CandidateTrialBatch:
    metric = Metric(metric_id="quality", direction="increase", unit="points")
    goal = Goal(statement="Increase composite-system quality", target=mapped.target)
    objective = Objective.create(
        objective_id="increase-quality",
        metric=metric,
        semantics="maximize",
        goal=goal,
        minimum_effect=1.0,
    )
    contract = EvaluationContract.create(
        contract_id="reference-composite-contract",
        goal=goal,
        baseline=Baseline.create(snapshot=mapped.snapshot, measurements={"quality": 80.0}),
        objectives=(objective,),
        stopping_rules=(
            StoppingRule(
                rule_id="evidence-returned",
                kind="criteria-sufficient",
                condition="Stop after two exact baseline and candidate observations",
            ),
        ),
    )
    evaluator = ExperimentEvaluator()
    hypothesis = Hypothesis(
        statement="The candidate increases quality on the exact composite target",
        target=mapped.target,
        causal_model={"change": "bounded service component revision"},
        predictions=({"quality_delta": ">= 1"},),
        lineage=(candidate.ref, contract.ref),
    )
    experiment = evaluator.design(
        experiment_id="reference-composite-comparison",
        subject=hypothesis,
        kind="deterministic-composite-comparison",
        metrics=(metric,),
        decision_rules=(
            DecisionRule(
                metric=metric.ref,
                kind="baseline_delta",
                minimum_effect=1.0,
                required_valid_trials=2,
            ),
        ),
        baseline_snapshot=mapped.snapshot,
        candidate_snapshot=candidate.snapshot,
        repetitions=2,
        seeds=(1, 2),
    )
    results = []
    trial_groups: tuple[
        tuple[Literal["baseline", "candidate"], TargetSnapshot, tuple[float, float]], ...
    ] = (
        ("baseline", mapped.snapshot, (80.0, 80.0)),
        ("candidate", candidate.snapshot, (82.0, 82.0)),
    )
    for role, snapshot, values in trial_groups:
        for index, value in enumerate(values):
            trial = evaluator.prepare_trial(experiment, index=index, role=role)
            observation = Observation(
                kind="reference.quality",
                value=value,
                target_snapshot=snapshot,
                source_refs=(trial.ref,),
            )
            measurement = Measurement(
                metric=metric.metric_id,
                metric_ref=metric.ref,
                value=value,
                unit=metric.unit,
                target_snapshot=snapshot,
                observation_refs=(observation.ref,),
            )
            results.append(
                evaluator.record_result(
                    experiment,
                    trial=trial,
                    disposition="valid",
                    observations=(observation,),
                    measurements=(measurement,),
                )
            )
    return CandidateTrialBatch.create(
        contract=contract,
        candidate=candidate,
        experiment=experiment,
        results=results,
    )


def ordinary_multi_component_run() -> OrdinaryConsumerRun:
    mapped = map_composite_snapshot(
        target_id="reference-system",
        kind="software-system",
        components=(
            ComponentState(
                component_id="service",
                kind="source-tree",
                revision="service-v1",
                state={"tests": "passing", "quality": 80},
                locator={"uri": "memory://service"},
            ),
            ComponentState(
                component_id="library",
                kind="source-tree",
                revision="library-v3",
                state={"tests": "passing", "quality": 78},
                locator={"uri": "memory://library"},
            ),
        ),
    )
    claim = Claim(
        statement="The exact composite baseline passes its declared checks",
        target=mapped.target,
        lineage=(mapped.snapshot.ref,),
    )
    evidence = tuple(
        Evidence(
            evidence_type="support",
            data={"observed": "passing", "replicate": replicate},
            subject_refs=(claim.ref,),
            source_refs=(mapped.snapshot.ref,),
            target_snapshot=mapped.snapshot,
            weight=1.0,
            lineage=(claim.ref, mapped.snapshot.ref),
        )
        for replicate in (1, 2)
    )
    validation = validate(
        claim=claim,
        target_snapshot=mapped.snapshot,
        validation_id="reference-composite-validation",
        evidence=evidence,
    )
    constraint = Constraint(
        statement="All component checks remain passing",
        target=mapped.target,
        lineage=(mapped.snapshot.ref,),
    )
    intervention = InterventionSpec.create(
        intervention_id="reference-candidate",
        baseline=mapped.snapshot,
        kind="bounded-component-change",
        specification={"component": "service", "change": "candidate-only"},
        rationale=("Exercise a non-authoritative candidate workspace",),
        supporting_refs=(claim.ref,),
        evidence=evidence,
        expected_effects={"quality": "increase"},
        risks=("Cross-component regression",),
        constraints=(constraint,),
        validation_plan={"compare": "exact baseline and candidate"},
        rollback_expectations={"restore": mapped.snapshot.root},
    )
    candidate_mapping = map_composite_snapshot(
        target_id="reference-system",
        kind="software-system",
        components=(
            ComponentState(
                component_id="service",
                kind="source-tree",
                revision="service-candidate",
                state={"tests": "passing", "quality": 82},
                locator={"uri": "memory://service"},
            ),
            ComponentState(
                component_id="library",
                kind="source-tree",
                revision="library-v3",
                state={"tests": "passing", "quality": 78},
                locator={"uri": "memory://library"},
            ),
        ),
    )
    if candidate_mapping.target != mapped.target:
        raise RuntimeError("reference component topology changed")
    request = InterventionImplementationRequest.for_intervention(
        intervention, candidate_id="reference-candidate"
    )
    candidate = CandidateSnapshot.prepared(request=request, snapshot=candidate_mapping.snapshot)
    return OrdinaryConsumerRun(
        mapped=mapped,
        validation=validation,
        candidate=candidate,
        candidate_trials=_candidate_trials(mapped, candidate),
    )


def governed_application_disabled_run() -> RSIResult:
    result = workflow_results()[3]
    if not isinstance(result, RSIResult):
        raise RuntimeError("reference governed run did not return RSIResult")
    return result
