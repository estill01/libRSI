"""Domain-neutral experiment design, trial correlation, and deterministic evaluation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .identity import FrozenMap
from .records import (
    Claim,
    DecisionRule,
    Evaluation,
    Evidence,
    ExperimentSpec,
    Hypothesis,
    Measurement,
    Metric,
    Observation,
    RecordRef,
    TargetRef,
    TargetSnapshot,
    Trial,
    TrialResult,
)

TrialRole = Literal["subject", "baseline", "candidate"]
TrialDisposition = Literal["valid", "invalid", "inconclusive"]
EvaluationDisposition = Literal["passed", "failed", "inconclusive"]

_TRIAL_ROLES = frozenset({"subject", "baseline", "candidate"})
_TRIAL_DISPOSITIONS = frozenset({"valid", "invalid", "inconclusive"})
_OPERATORS = frozenset({"<", "<=", "==", ">=", ">"})


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _positive_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _items(value: Sequence[Any], *, label: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    return tuple(value)


def _subject_target(subject: Claim | Hypothesis) -> TargetRef | None:
    if not isinstance(subject, (Claim, Hypothesis)):
        raise TypeError("experiment subjects must be a Claim or Hypothesis")
    return subject.target


def _snapshot_for_role(spec: ExperimentSpec, role: str) -> TargetSnapshot | None:
    if role == "baseline":
        return spec.baseline_snapshot
    if role == "candidate":
        return spec.candidate_snapshot
    return spec.target_snapshot


def _roles(spec: ExperimentSpec) -> tuple[TrialRole, ...]:
    if spec.baseline_snapshot is not None or spec.candidate_snapshot is not None:
        if spec.baseline_snapshot is None or spec.candidate_snapshot is None:
            raise ValueError("comparison experiments require baseline and candidate snapshots")
        return ("baseline", "candidate")
    return ("subject",)


def _metric_map(spec: ExperimentSpec) -> dict[RecordRef, Metric]:
    return {metric.ref: metric for metric in spec.metrics}


def _validate_spec(spec: ExperimentSpec) -> None:
    if not isinstance(spec, ExperimentSpec):
        raise TypeError("generic evaluation requires an ExperimentSpec")
    if not spec.metrics:
        raise ValueError("generic experiments require at least one Metric")
    if not spec.decision_rules:
        raise ValueError("generic experiments require at least one DecisionRule")
    if spec.requested_measurements != tuple(metric.metric_id for metric in spec.metrics):
        raise ValueError("requested measurements must match the exact experiment Metrics")
    if not spec.lineage or any(
        ref.record_type not in {"claim", "hypothesis"} for ref in spec.lineage
    ):
        raise ValueError("generic experiments require exact Claim or Hypothesis lineage")
    roles = _roles(spec)
    for rule in spec.decision_rules:
        metric = _metric_map(spec)[rule.metric]
        if rule.required_valid_trials > spec.repetitions:
            raise ValueError("required valid trials cannot exceed experiment repetitions")
        if rule.kind == "baseline_delta" and roles != ("baseline", "candidate"):
            raise ValueError("baseline-delta rules require a comparison experiment")
        if rule.kind == "baseline_delta" and metric.direction == "target":
            raise ValueError("target-direction metrics require threshold rules")


def _validate_measurements(
    *,
    spec: ExperimentSpec,
    trial: Trial,
    observations: Sequence[Observation],
    measurements: Sequence[Measurement],
    require_all: bool,
    require_valid_observations: bool,
) -> tuple[Measurement, ...]:
    observation_items = _items(observations, label="trial observations")
    if any(not isinstance(item, Observation) for item in observation_items):
        raise TypeError("trial observations must contain Observation records")
    if len({item.ref for item in observation_items}) != len(observation_items):
        raise ValueError("trial observations must be distinct")
    if require_valid_observations and any(not item.valid for item in observation_items):
        raise ValueError("valid trial results require valid observations")
    expected_snapshot = _snapshot_for_role(spec, trial.role)
    for observation in observation_items:
        if trial.ref not in observation.source_refs:
            raise ValueError("observation is not bound to the exact Trial")
        if expected_snapshot is not None and (
            observation.target_snapshot is None
            or observation.target_snapshot.root != expected_snapshot.root
        ):
            raise ValueError("observation is not bound to the trial target snapshot")
    observation_refs = {item.ref for item in observation_items}
    items = _items(measurements, label="trial measurements")
    if any(not isinstance(item, Measurement) for item in items):
        raise TypeError("trial measurements must contain Measurement records")
    metrics = _metric_map(spec)
    seen: set[RecordRef] = set()
    for item in items:
        if item.metric_ref is None or item.metric_ref not in metrics:
            raise ValueError("measurement does not reference an exact experiment Metric")
        metric = metrics[item.metric_ref]
        if item.metric != metric.metric_id:
            raise ValueError("measurement name does not match its exact Metric")
        if metric.unit != item.unit:
            raise ValueError("measurement unit does not match its exact Metric")
        if item.metric_ref in seen:
            raise ValueError("a trial may report each Metric at most once")
        seen.add(item.metric_ref)
        _number(item.value, f"measurement {item.metric}")
        if not item.observation_refs:
            raise ValueError("measurements require exact observation provenance")
        if not set(item.observation_refs).issubset(observation_refs):
            raise ValueError("measurement provenance does not identify exact trial observations")
        if expected_snapshot is not None and (
            item.target_snapshot is None or item.target_snapshot.root != expected_snapshot.root
        ):
            raise ValueError("measurement is not bound to the trial target snapshot")
    if require_all and seen != set(metrics):
        raise ValueError("valid trials must report every requested Metric")
    return items


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _compare(value: float, operator: str, threshold: float) -> bool:
    if operator not in _OPERATORS:
        raise ValueError(f"unsupported comparison operator: {operator}")
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    if operator == ">=":
        return value >= threshold
    return value > threshold


@dataclass(frozen=True)
class ExperimentEvaluator:
    """Reference semantic owner for generic experiment interpretation."""

    conclusive_evidence_weight: float = 0.7

    def __post_init__(self) -> None:
        weight = _number(self.conclusive_evidence_weight, "conclusive evidence weight")
        if not 0.0 <= weight <= 1.0:
            raise ValueError("conclusive evidence weight must be between zero and one")

    def design(
        self,
        *,
        experiment_id: str,
        subject: Claim | Hypothesis,
        kind: str,
        metrics: Sequence[Metric],
        decision_rules: Sequence[DecisionRule],
        target_snapshot: TargetSnapshot | None = None,
        baseline_snapshot: TargetSnapshot | None = None,
        candidate_snapshot: TargetSnapshot | None = None,
        repetitions: int = 1,
        seeds: Sequence[int] = (),
        budget: Mapping[str, Any] | None = None,
        validity_requirements: Mapping[str, Any] | None = None,
        design: Mapping[str, Any] | None = None,
        inputs: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
    ) -> ExperimentSpec:
        """Create an immutable generic experiment with identity-bound rules."""

        target = _subject_target(subject)
        for snapshot in (target_snapshot, baseline_snapshot, candidate_snapshot):
            if snapshot is not None and target is not None and snapshot.target != target:
                raise ValueError("experiment snapshot does not match the subject target")
        metric_items = _items(metrics, label="experiment metrics")
        rule_items = _items(decision_rules, label="experiment decision rules")
        if any(not isinstance(item, Metric) for item in metric_items):
            raise TypeError("experiment metrics must contain Metric records")
        if any(not isinstance(item, DecisionRule) for item in rule_items):
            raise TypeError("experiment decision rules must contain DecisionRule records")
        repeat_count = _positive_int(repetitions, "experiment repetitions")
        seed_items = _items(seeds, label="experiment seeds")
        if any(
            isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 for seed in seed_items
        ):
            raise ValueError("experiment seeds must be nonnegative integers")
        if seed_items and len(seed_items) != repeat_count:
            raise ValueError("experiment seeds must match the repetition count")
        requirements = {"require_all_metrics": True}
        if validity_requirements is not None:
            if not isinstance(validity_requirements, Mapping):
                raise TypeError("validity requirements must be a mapping")
            requirements.update(validity_requirements)
        if not isinstance(requirements.get("require_all_metrics"), bool):
            raise TypeError("require_all_metrics must be a boolean")

        spec = ExperimentSpec(
            experiment_id=_require_text(experiment_id, "experiment id"),
            kind=_require_text(kind, "experiment kind"),
            target_snapshot=target_snapshot,
            baseline_snapshot=baseline_snapshot,
            candidate_snapshot=candidate_snapshot,
            design={} if design is None else design,
            inputs={} if inputs is None else inputs,
            environment={} if environment is None else environment,
            requested_measurements=tuple(item.metric_id for item in metric_items),
            metrics=metric_items,
            decision_rules=rule_items,
            repetitions=repeat_count,
            seeds=seed_items,
            budget={} if budget is None else budget,
            validity_requirements=requirements,
            lineage=(subject.ref,),
        )
        _validate_spec(spec)
        return spec

    @staticmethod
    def prepare_trial(
        spec: ExperimentSpec,
        *,
        index: int,
        role: TrialRole = "subject",
    ) -> Trial:
        """Create an externally executable Trial retaining exact spec identity."""

        _validate_spec(spec)
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("trial index must be an integer")
        if not 0 <= index < spec.repetitions:
            raise ValueError("trial index is outside the experiment repetition range")
        if role not in _roles(spec):
            raise ValueError(f"trial role {role!r} is not valid for this experiment")
        seed = spec.seeds[index] if spec.seeds else None
        return Trial(
            experiment=spec.ref,
            index=index,
            status="planned",
            role=role,
            seed=seed,
            data={"budget": spec.budget},
            lineage=(spec.ref,),
        )

    @staticmethod
    def record_result(
        spec: ExperimentSpec,
        *,
        trial: Trial,
        disposition: TrialDisposition,
        observations: Sequence[Observation] = (),
        measurements: Sequence[Measurement] = (),
        reason: str | None = None,
    ) -> TrialResult:
        """Correlate measurements/validity to one exact prepared Trial."""

        _validate_spec(spec)
        if not isinstance(trial, Trial) or trial.experiment != spec.ref:
            raise ValueError("trial does not reference the exact ExperimentSpec")
        if not 0 <= trial.index < spec.repetitions:
            raise ValueError("trial index is outside the ExperimentSpec")
        if trial.status != "planned":
            raise ValueError("only a planned Trial can record a result")
        if trial.role not in _roles(spec):
            raise ValueError("trial role does not match the ExperimentSpec")
        if trial.seed != (spec.seeds[trial.index] if spec.seeds else None):
            raise ValueError("trial seed does not match the ExperimentSpec")
        expected_trial = ExperimentEvaluator.prepare_trial(
            spec,
            index=trial.index,
            role=trial.role,
        )
        if trial.root != expected_trial.root:
            raise ValueError("trial is not the exact prepared Trial")
        if disposition not in _TRIAL_DISPOSITIONS:
            raise ValueError(f"unsupported trial disposition: {disposition}")
        require_all = bool(spec.validity_requirements.get("require_all_metrics", True))
        measurement_items = _validate_measurements(
            spec=spec,
            trial=trial,
            observations=observations,
            measurements=measurements,
            require_all=disposition == "valid" and require_all,
            require_valid_observations=disposition == "valid",
        )
        return TrialResult(
            trial=trial,
            disposition=disposition,
            observations=tuple(observations),
            measurements=measurement_items,
            reason=reason,
            lineage=(spec.ref, trial.ref),
        )

    @staticmethod
    def evaluate(
        spec: ExperimentSpec,
        *,
        results: Sequence[TrialResult],
    ) -> Evaluation:
        """Evaluate exact trial results using only the rules frozen in ``spec``."""

        _validate_spec(spec)
        result_items = _items(results, label="trial results")
        if not result_items:
            raise ValueError("experiment evaluation requires trial results")
        if any(not isinstance(item, TrialResult) for item in result_items):
            raise TypeError("trial results must contain TrialResult records")
        expected_roles = _roles(spec)
        seen_trials: set[tuple[str, int]] = set()
        values: dict[tuple[str, RecordRef], list[float]] = {}
        retained_measurements: list[Measurement] = []
        valid_counts = {role: 0 for role in expected_roles}
        invalid_counts = {role: 0 for role in expected_roles}

        for result in result_items:
            trial = result.trial
            if trial.experiment != spec.ref:
                raise ValueError("trial result belongs to a different ExperimentSpec")
            if trial.role not in expected_roles or not 0 <= trial.index < spec.repetitions:
                raise ValueError("trial result role or index is outside the ExperimentSpec")
            if trial.status != "planned":
                raise ValueError("trial result does not contain an exact prepared Trial")
            if trial.seed != (spec.seeds[trial.index] if spec.seeds else None):
                raise ValueError("trial result seed does not match the ExperimentSpec")
            expected_trial = ExperimentEvaluator.prepare_trial(
                spec,
                index=trial.index,
                role=trial.role,
            )
            if trial.root != expected_trial.root:
                raise ValueError("trial result does not contain the exact prepared Trial")
            trial_key = (trial.role, trial.index)
            if trial_key in seen_trials:
                raise ValueError("experiment evaluation received a duplicate Trial")
            seen_trials.add(trial_key)
            measurements = _validate_measurements(
                spec=spec,
                trial=trial,
                observations=result.observations,
                measurements=result.measurements,
                require_all=result.disposition == "valid"
                and bool(spec.validity_requirements.get("require_all_metrics", True)),
                require_valid_observations=result.disposition == "valid",
            )
            if result.disposition != "valid":
                invalid_counts[trial.role] += 1
                continue
            valid_counts[trial.role] += 1
            retained_measurements.extend(measurements)
            for measurement in measurements:
                assert measurement.metric_ref is not None
                values.setdefault((trial.role, measurement.metric_ref), []).append(
                    _number(measurement.value, f"measurement {measurement.metric}")
                )

        expected_trials = {
            (role, index) for role in expected_roles for index in range(spec.repetitions)
        }
        if seen_trials != expected_trials:
            raise ValueError("experiment evaluation requires a result for every planned Trial")

        metrics = _metric_map(spec)
        rule_findings: list[dict[str, Any]] = []
        any_failed = False
        any_inconclusive = False
        for rule in spec.decision_rules:
            metric = metrics[rule.metric]
            required = rule.required_valid_trials
            if rule.kind == "threshold":
                role = "candidate" if "candidate" in expected_roles else "subject"
                samples = values.get((role, metric.ref), [])
                if len(samples) < required:
                    passed: bool | None = None
                    any_inconclusive = True
                else:
                    aggregate = _mean(samples)
                    assert rule.operator is not None and rule.threshold is not None
                    passed = _compare(aggregate, rule.operator, rule.threshold)
                    any_failed = any_failed or not passed
                rule_findings.append(
                    {
                        "rule_root": rule.root,
                        "metric": metric.metric_id,
                        "role": role,
                        "valid_trials": len(samples),
                        "passed": passed,
                        "aggregate": None if not samples else _mean(samples),
                    }
                )
            else:
                baseline = values.get(("baseline", metric.ref), [])
                candidate = values.get(("candidate", metric.ref), [])
                if len(baseline) < required or len(candidate) < required:
                    passed = None
                    any_inconclusive = True
                    effect = None
                else:
                    raw_effect = _mean(candidate) - _mean(baseline)
                    effect = raw_effect if metric.direction == "increase" else -raw_effect
                    passed = effect >= rule.minimum_effect
                    any_failed = any_failed or not passed
                rule_findings.append(
                    {
                        "rule_root": rule.root,
                        "metric": metric.metric_id,
                        "valid_baseline_trials": len(baseline),
                        "valid_candidate_trials": len(candidate),
                        "passed": passed,
                        "effect": effect,
                    }
                )

        disposition: EvaluationDisposition
        if any_failed:
            disposition = "failed"
        elif any_inconclusive:
            disposition = "inconclusive"
        else:
            disposition = "passed"
        return Evaluation(
            subject_refs=(spec.ref,),
            disposition=disposition,
            measurements=tuple(retained_measurements),
            findings={
                "spec_root": spec.root,
                "rules": rule_findings,
                "valid_trials": valid_counts,
                "invalid_trials": invalid_counts,
            },
            lineage=tuple(result.ref for result in result_items),
        )

    def evidence(
        self,
        spec: ExperimentSpec,
        evaluation: Evaluation,
        *,
        results: Sequence[TrialResult],
    ) -> Evidence:
        """Project a generic Evaluation to exact epistemic Evidence."""

        _validate_spec(spec)
        if not isinstance(evaluation, Evaluation):
            raise TypeError("evidence projection requires an Evaluation")
        expected_evaluation = self.evaluate(spec, results=results)
        if evaluation.root != expected_evaluation.root:
            raise ValueError("evaluation is not the exact result of the supplied TrialResults")
        if evaluation.disposition == "passed":
            relationship = "support"
            weight = float(self.conclusive_evidence_weight)
        elif evaluation.disposition == "failed":
            relationship = "counterexample"
            weight = float(self.conclusive_evidence_weight)
        elif evaluation.disposition == "inconclusive":
            relationship = "null"
            weight = 0.0
        else:
            raise ValueError(f"unsupported evaluation disposition: {evaluation.disposition}")
        snapshot = spec.candidate_snapshot or spec.target_snapshot or spec.baseline_snapshot
        return Evidence(
            evidence_type=relationship,
            data={
                "experiment_root": spec.root,
                "evaluation_root": evaluation.root,
                "disposition": evaluation.disposition,
            },
            subject_refs=spec.lineage,
            source_refs=(evaluation.ref,),
            target_snapshot=snapshot,
            weight=weight,
        )

    @staticmethod
    def projection(spec: ExperimentSpec) -> FrozenMap:
        """Return the minimal identity envelope an external executor must preserve."""

        _validate_spec(spec)
        return FrozenMap(
            {
                "experiment_id": spec.experiment_id,
                "spec_root": spec.root,
                "kind": spec.kind,
                "repetitions": spec.repetitions,
                "roles": _roles(spec),
                "seeds": spec.seeds,
                "budget": spec.budget,
                "requested_measurements": spec.requested_measurements,
            }
        )
