"""Deterministic semantic owner for evidence-bound comparative selection."""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..errors import RSITransitionError
from ..evaluation import ExperimentEvaluator
from ..intent import EvaluationContract, Guardrail, Objective
from ..records import RecordRef
from .records import (
    CandidateAssessment,
    CandidateTrialBatch,
    CriterionAssessment,
    RankedCandidate,
    RiskPolicy,
    SelectionDecision,
    UncertaintyInterval,
)
from .statistics import favorable_effect, mean_interval


def _metric_contract(contract: EvaluationContract) -> dict[str, tuple[str, str | None, set[str]]]:
    definitions: dict[str, tuple[str, str | None, set[str]]] = {}
    criteria: tuple[Objective | Guardrail, ...] = (*contract.objectives, *contract.guardrails)
    for criterion in criteria:
        metric = criterion.metric
        existing = definitions.get(metric.metric_id)
        if existing is None:
            definitions[metric.metric_id] = (metric.direction, metric.unit, {metric.role})
        else:
            direction, unit, roles = existing
            if (direction, unit) != (metric.direction, metric.unit):
                raise ValueError("contract contains incomparable metric definitions")
            roles.add(metric.role)
    return definitions


def _validate_comparability(batch: CandidateTrialBatch) -> None:
    contract = batch.contract
    baseline = contract.baseline.snapshot
    candidate = batch.candidate
    experiment = batch.experiment
    if candidate.request.intervention.baseline != baseline:
        raise ValueError("candidate was prepared from an incomparable baseline")
    if experiment.baseline_snapshot != baseline:
        raise ValueError("experiment does not use the exact contract baseline")
    if experiment.candidate_snapshot != candidate.snapshot:
        raise ValueError("experiment does not use the exact candidate snapshot")
    if candidate.snapshot.target != baseline.target:
        raise ValueError("candidate and baseline belong to different targets")
    definitions = _metric_contract(contract)
    experiment_metrics = {item.metric_id: item for item in experiment.metrics}
    if len(experiment_metrics) != len(experiment.metrics) or set(experiment_metrics) != set(
        definitions
    ):
        raise ValueError("experiment metrics must match the exact evaluation contract")
    for metric_id, metric in experiment_metrics.items():
        direction, unit, roles = definitions[metric_id]
        if (metric.direction, metric.unit) != (direction, unit) or metric.role not in roles:
            raise ValueError("experiment metric semantics diverge from the evaluation contract")
    recomputed = ExperimentEvaluator.evaluate(experiment, results=batch.results)
    if recomputed != batch.evaluation:
        raise ValueError("candidate evaluation is not the exact result of its TrialResults")


def _samples(
    batch: CandidateTrialBatch,
) -> tuple[dict[tuple[str, str], list[float]], dict[str, int], dict[str, int]]:
    values: dict[tuple[str, str], list[float]] = {}
    valid_counts = {"baseline": 0, "candidate": 0}
    invalid_counts = {"baseline": 0, "candidate": 0}
    for result in batch.results:
        role = result.trial.role
        if role not in valid_counts:
            raise ValueError("comparative selection requires baseline/candidate trials")
        if result.disposition != "valid":
            invalid_counts[role] += 1
            continue
        valid_counts[role] += 1
        for measurement in result.measurements:
            value = measurement.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("comparative measurements must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("comparative measurements must be finite")
            values.setdefault((role, measurement.metric), []).append(number)
    return values, valid_counts, invalid_counts


def _intervals(
    batch: CandidateTrialBatch,
    policy: RiskPolicy,
) -> dict[str, tuple[UncertaintyInterval, UncertaintyInterval]]:
    values, _, _ = _samples(batch)
    intervals: dict[str, tuple[UncertaintyInterval, UncertaintyInterval]] = {}
    for metric_id in _metric_contract(batch.contract):
        baseline = values.get(("baseline", metric_id), [])
        candidate = values.get(("candidate", metric_id), [])
        if (
            len(baseline) < policy.minimum_valid_trials
            or len(candidate) < policy.minimum_valid_trials
        ):
            continue
        intervals[metric_id] = (
            mean_interval(baseline, confidence_multiplier=policy.confidence_multiplier),
            mean_interval(candidate, confidence_multiplier=policy.confidence_multiplier),
        )
    return intervals


def _compare_interval(interval: UncertaintyInterval, operator: str, threshold: float) -> bool:
    if operator == ">":
        return interval.lower > threshold
    if operator == ">=":
        return interval.lower >= threshold
    if operator == "<":
        return interval.upper < threshold
    if operator == "<=":
        return interval.upper <= threshold
    if operator == "==":
        return interval.lower == interval.upper == threshold
    raise ValueError(f"unsupported comparison operator: {operator}")


def _target_effect(
    baseline: UncertaintyInterval,
    candidate: UncertaintyInterval,
    *,
    target: float,
) -> UncertaintyInterval:
    baseline_worst = max(abs(baseline.lower - target), abs(baseline.upper - target))
    baseline_best = (
        0.0
        if baseline.lower <= target <= baseline.upper
        else min(abs(baseline.lower - target), abs(baseline.upper - target))
    )
    candidate_worst = max(abs(candidate.lower - target), abs(candidate.upper - target))
    candidate_best = (
        0.0
        if candidate.lower <= target <= candidate.upper
        else min(abs(candidate.lower - target), abs(candidate.upper - target))
    )
    return UncertaintyInterval(
        estimate=abs(baseline.estimate - target) - abs(candidate.estimate - target),
        lower=baseline_best - candidate_worst,
        upper=baseline_worst - candidate_best,
        sample_count=min(baseline.sample_count, candidate.sample_count),
    )


def _objective_assessment(
    objective: Objective,
    baseline: UncertaintyInterval,
    candidate: UncertaintyInterval,
) -> CriterionAssessment:
    if objective.semantics == "target":
        assert objective.target_value is not None
        effect = _target_effect(baseline, candidate, target=objective.target_value)
        passed = (
            candidate.lower >= objective.target_value - objective.tolerance
            and candidate.upper <= objective.target_value + objective.tolerance
        )
        reason = (
            "candidate uncertainty interval is within the target tolerance"
            if passed
            else "candidate uncertainty interval is outside the target tolerance"
        )
    else:
        effect = favorable_effect(baseline, candidate, direction=objective.metric.direction)
        passed = effect.lower >= objective.minimum_effect
        reason = (
            "conservative favorable effect meets the minimum meaningful effect"
            if passed
            else "conservative favorable effect misses the minimum meaningful effect"
        )
    return CriterionAssessment(
        criterion_kind="objective",
        criterion_ref=objective.ref,
        criterion_id=objective.objective_id,
        metric_id=objective.metric.metric_id,
        baseline=baseline,
        candidate=candidate,
        favorable_effect=effect,
        disposition="passed" if passed else "failed",
        reason=reason,
        lineage=(objective.ref, baseline.ref, candidate.ref, effect.ref),
    )


def _guardrail_assessment(
    guardrail: Guardrail,
    baseline: UncertaintyInterval,
    candidate: UncertaintyInterval,
) -> CriterionAssessment:
    effect = favorable_effect(baseline, candidate, direction=guardrail.metric.direction)
    if guardrail.semantics == "no-regression":
        passed = effect.lower >= -guardrail.allowed_regression
        reason = (
            "conservative effect remains within the allowed regression"
            if passed
            else "conservative effect violates the no-regression bound"
        )
    else:
        assert guardrail.operator is not None and guardrail.threshold is not None
        passed = _compare_interval(candidate, guardrail.operator, guardrail.threshold)
        reason = (
            "candidate uncertainty interval satisfies the guardrail threshold"
            if passed
            else "candidate uncertainty interval violates the guardrail threshold"
        )
    return CriterionAssessment(
        criterion_kind="guardrail",
        criterion_ref=guardrail.ref,
        criterion_id=guardrail.guardrail_id,
        metric_id=guardrail.metric.metric_id,
        baseline=baseline,
        candidate=candidate,
        favorable_effect=effect,
        disposition="passed" if passed else "failed",
        reason=reason,
        lineage=(guardrail.ref, baseline.ref, candidate.ref, effect.ref),
    )


def _inconclusive_criterion(criterion: Objective | Guardrail) -> CriterionAssessment:
    if isinstance(criterion, Objective):
        criterion_kind = "objective"
        criterion_id = criterion.objective_id
    else:
        criterion_kind = "guardrail"
        criterion_id = criterion.guardrail_id
    return CriterionAssessment(
        criterion_kind=criterion_kind,
        criterion_ref=criterion.ref,
        criterion_id=criterion_id,
        metric_id=criterion.metric.metric_id,
        baseline=None,
        candidate=None,
        favorable_effect=None,
        disposition="inconclusive",
        reason="valid baseline and candidate samples are unavailable",
        lineage=(criterion.ref,),
    )


def _assessment_projection(
    batch: CandidateTrialBatch,
    policy: RiskPolicy,
) -> tuple[tuple[CriterionAssessment, ...], str, tuple[str, ...], int, int]:
    _validate_comparability(batch)
    values, valid_counts, invalid_counts = _samples(batch)
    intervals = _intervals(batch, policy)
    risk_reasons: list[str] = []
    if any(count < policy.minimum_valid_trials for count in valid_counts.values()):
        risk_reasons.append("insufficient valid baseline or candidate trials")
    if batch.evaluation.disposition != "passed":
        risk_reasons.append("experiment evaluation is not conclusive passing evidence")
    total = sum(valid_counts.values()) + sum(invalid_counts.values())
    invalid = sum(invalid_counts.values())
    if total == 0 or invalid / total > policy.maximum_invalid_fraction:
        risk_reasons.append("invalid-trial fraction exceeds the risk policy")
    if policy.require_independent_review:
        from ..selections import SelectionPolicy

        accepting_review = any(item.disposition == "accepted" for item in batch.independent_reviews)
        try:
            SelectionPolicy.require_selectable(
                status=batch.candidate.status,
                has_accepting_review=accepting_review,
            )
        except RSITransitionError:
            risk_reasons.append("independent accepting review is required but absent")

    criteria: list[CriterionAssessment] = []
    missing_metrics = [
        metric_id for metric_id in _metric_contract(batch.contract) if metric_id not in intervals
    ]
    if missing_metrics:
        risk_reasons.append(
            f"insufficient comparative metric samples: {', '.join(missing_metrics)}"
        )
    for objective in batch.contract.objectives:
        if objective.metric.metric_id not in intervals:
            criteria.append(_inconclusive_criterion(objective))
        else:
            baseline, candidate = intervals[objective.metric.metric_id]
            criteria.append(_objective_assessment(objective, baseline, candidate))
    for guardrail in batch.contract.guardrails:
        if guardrail.metric.metric_id not in intervals:
            criteria.append(_inconclusive_criterion(guardrail))
        else:
            baseline, candidate = intervals[guardrail.metric.metric_id]
            criteria.append(_guardrail_assessment(guardrail, baseline, candidate))

    failed = [item for item in criteria if item.disposition == "failed"]
    if failed:
        disposition = "rejected"
        reasons = tuple(item.reason for item in failed)
    elif risk_reasons:
        disposition = "inconclusive"
        reasons = tuple(risk_reasons)
    else:
        disposition = "accepted"
        reasons = ("all objectives and guardrails pass the explicit risk policy",)
    return (
        tuple(criteria),
        disposition,
        reasons,
        sum(valid_counts.values()),
        invalid,
    )


def _assessment(batch: CandidateTrialBatch, policy: RiskPolicy) -> CandidateAssessment:
    criteria, disposition, reasons, valid_trials, invalid_trials = _assessment_projection(
        batch, policy
    )
    return CandidateAssessment(
        batch=batch,
        risk_policy=policy,
        criteria=criteria,
        disposition=disposition,
        reasons=reasons,
        valid_trials=valid_trials,
        invalid_trials=invalid_trials,
        lineage=(batch.ref, policy.ref, *(item.ref for item in criteria)),
    )


def _objective_vector(assessment: CandidateAssessment) -> tuple[float, ...]:
    values: list[float] = []
    for item in assessment.criteria:
        if item.criterion_kind == "objective":
            if item.favorable_effect is None:  # pragma: no cover - accepted invariant
                raise RuntimeError("accepted candidate lost an objective interval")
            values.append(item.favorable_effect.lower)
    return tuple(values)


def _dominates(left: CandidateAssessment, right: CandidateAssessment) -> bool:
    left_values = _objective_vector(left)
    right_values = _objective_vector(right)
    if len(left_values) != len(right_values) or not left_values:
        raise ValueError("candidate objective vectors are incomparable")
    return all(a >= b for a, b in zip(left_values, right_values, strict=True)) and any(
        a > b for a, b in zip(left_values, right_values, strict=True)
    )


def _rank(assessments: Sequence[CandidateAssessment]) -> tuple[RankedCandidate, ...]:
    accepted = tuple(sorted(assessments, key=lambda item: item.candidate_ref.root))
    dominates: dict[RecordRef, set[RecordRef]] = {item.candidate_ref: set() for item in accepted}
    dominated_by: dict[RecordRef, set[RecordRef]] = {item.candidate_ref: set() for item in accepted}
    by_ref = {item.candidate_ref: item for item in accepted}
    for left in accepted:
        for right in accepted:
            if left is right:
                continue
            if _dominates(left, right):
                dominates[left.candidate_ref].add(right.candidate_ref)
                dominated_by[right.candidate_ref].add(left.candidate_ref)

    remaining = set(by_ref)
    ranks: dict[RecordRef, int] = {}
    rank = 1
    while remaining:
        front = {ref for ref in remaining if not (dominated_by[ref] & remaining)}
        if not front:  # pragma: no cover - strict dominance cannot cycle
            raise RuntimeError("candidate dominance graph is cyclic")
        for ref in front:
            ranks[ref] = rank
        remaining -= front
        rank += 1

    records = []
    for ref in sorted(by_ref, key=lambda item: item.root):
        dominators = tuple(sorted(dominated_by[ref], key=lambda item: item.root))
        dominated = tuple(sorted(dominates[ref], key=lambda item: item.root))
        assessment = by_ref[ref]
        records.append(
            RankedCandidate(
                assessment=assessment,
                rank=ranks[ref],
                dominated_by=dominators,
                dominates=dominated,
                lineage=(assessment.ref, *dominators, *dominated),
            )
        )
    return tuple(sorted(records, key=lambda item: (item.rank, item.assessment.candidate_ref.root)))


def _selection_projection(
    assessments: Sequence[CandidateAssessment],
) -> tuple[tuple[RankedCandidate, ...], tuple[RecordRef, ...], str]:
    accepted = tuple(item for item in assessments if item.disposition == "accepted")
    rankings = _rank(accepted) if accepted else ()
    selected = tuple(item.assessment.candidate_ref for item in rankings if item.rank == 1)
    if not selected:
        disposition = "none-accepted"
    elif len(selected) == 1:
        disposition = "selected"
    else:
        disposition = "pareto"
    return rankings, selected, disposition


class ComparativeSelectionPolicy:
    """Recomputes every candidate assessment before issuing a selection decision."""

    @staticmethod
    def assess(batch: CandidateTrialBatch, *, risk_policy: RiskPolicy) -> CandidateAssessment:
        if type(batch) is not CandidateTrialBatch:
            raise TypeError("comparative assessment requires a CandidateTrialBatch")
        if type(risk_policy) is not RiskPolicy:
            raise TypeError("comparative assessment requires a RiskPolicy")
        return _assessment(batch, risk_policy)

    @staticmethod
    def select(
        *,
        selection_id: str,
        contract: EvaluationContract,
        batches: Sequence[CandidateTrialBatch],
        risk_policy: RiskPolicy,
    ) -> SelectionDecision:
        if type(contract) is not EvaluationContract:
            raise TypeError("comparative selection requires an EvaluationContract")
        if type(risk_policy) is not RiskPolicy:
            raise TypeError("comparative selection requires a RiskPolicy")
        if isinstance(batches, (str, bytes, bytearray)) or not isinstance(batches, Sequence):
            raise TypeError("comparative selection batches must be a sequence")
        batch_items = tuple(batches)
        if not batch_items:
            raise ValueError("comparative selection requires candidate batches")
        if any(type(item) is not CandidateTrialBatch for item in batch_items):
            raise TypeError("comparative selection requires CandidateTrialBatch values")
        if len({item.candidate.ref for item in batch_items}) != len(batch_items):
            raise ValueError("comparative selection candidates must be unique")
        if any(item.contract != contract for item in batch_items):
            raise ValueError("parallel candidate lanes must use one exact evaluation contract")
        assessments = tuple(
            sorted(
                (_assessment(item, risk_policy) for item in batch_items),
                key=lambda item: item.candidate_ref.root,
            )
        )
        rankings, selected, disposition = _selection_projection(assessments)
        return SelectionDecision(
            selection_id=selection_id,
            contract=contract,
            risk_policy=risk_policy,
            assessments=assessments,
            rankings=rankings,
            disposition=disposition,
            selected=selected,
            lineage=(
                contract.ref,
                risk_policy.ref,
                *(item.ref for item in assessments),
                *(item.ref for item in rankings),
                *selected,
            ),
        )
