from __future__ import annotations

import pytest

from librsi import (
    Claim,
    CommandObservation,
    DecisionRule,
    ExperimentEvaluator,
    ExperimentSpec,
    Measurement,
    Metric,
    Observation,
    RecordRef,
    RSIKernel,
    TargetRef,
    TargetSnapshot,
    Trial,
    TrialResult,
    deserialize_record,
    serialize_record,
)


def _context() -> tuple[Claim, TargetSnapshot, TargetSnapshot]:
    target = TargetRef(target_id="process", kind="simulation")
    baseline = TargetSnapshot(target=target, revision="baseline", state={"configuration": 1})
    candidate = TargetSnapshot(target=target, revision="candidate", state={"configuration": 2})
    claim = Claim(
        statement="The candidate lowers latency without violating throughput",
        kind="behavioral",
        target=target,
    )
    return claim, baseline, candidate


def _comparison_contract() -> tuple[Metric, Metric, DecisionRule, DecisionRule]:
    latency = Metric(metric_id="latency", direction="decrease", role="objective", unit="ms")
    throughput = Metric(
        metric_id="throughput",
        direction="increase",
        role="guardrail",
        unit="items/s",
    )
    latency_rule = DecisionRule(
        metric=latency.ref,
        kind="baseline_delta",
        minimum_effect=10.0,
        required_valid_trials=2,
    )
    throughput_rule = DecisionRule(
        metric=throughput.ref,
        kind="threshold",
        operator=">=",
        threshold=90.0,
        required_valid_trials=2,
    )
    return latency, throughput, latency_rule, throughput_rule


def _comparison_spec() -> ExperimentSpec:
    claim, baseline, candidate = _context()
    latency, throughput, latency_rule, throughput_rule = _comparison_contract()
    return ExperimentEvaluator().design(
        experiment_id="process-comparison",
        subject=claim,
        kind="simulation",
        metrics=(latency, throughput),
        decision_rules=(latency_rule, throughput_rule),
        baseline_snapshot=baseline,
        candidate_snapshot=candidate,
        repetitions=3,
        seeds=(11, 12, 13),
        budget={"max_steps": 30},
        validity_requirements={"require_all_metrics": True},
        design={"isolation": "deterministic"},
        environment={"simulator": "v1"},
    )


def _valid_result(
    spec: ExperimentSpec,
    *,
    role: str,
    index: int,
    latency: float,
    throughput: float,
) -> TrialResult:
    evaluator = ExperimentEvaluator()
    trial = evaluator.prepare_trial(spec, index=index, role=role)  # type: ignore[arg-type]
    snapshot = spec.baseline_snapshot if role == "baseline" else spec.candidate_snapshot
    assert snapshot is not None
    observations = (
        Observation(
            kind="simulation.latency",
            value=latency,
            target_snapshot=snapshot,
            source_refs=(trial.ref,),
        ),
        Observation(
            kind="simulation.throughput",
            value=throughput,
            target_snapshot=snapshot,
            source_refs=(trial.ref,),
        ),
    )
    metrics = {metric.metric_id: metric for metric in spec.metrics}
    measurements = (
        Measurement(
            metric="latency",
            metric_ref=metrics["latency"].ref,
            value=latency,
            unit="ms",
            target_snapshot=snapshot,
            observation_refs=(observations[0].ref,),
        ),
        Measurement(
            metric="throughput",
            metric_ref=metrics["throughput"].ref,
            value=throughput,
            unit="items/s",
            target_snapshot=snapshot,
            observation_refs=(observations[1].ref,),
        ),
    )
    return evaluator.record_result(
        spec,
        trial=trial,
        disposition="valid",
        observations=observations,
        measurements=measurements,
    )


def _passing_results(spec: ExperimentSpec) -> tuple[TrialResult, ...]:
    baseline_values = ((100.0, 100.0), (102.0, 99.0), (98.0, 101.0))
    candidate_values = ((80.0, 95.0), (82.0, 94.0), (78.0, 96.0))
    return tuple(
        _valid_result(
            spec,
            role=role,
            index=index,
            latency=values[0],
            throughput=values[1],
        )
        for role, rows in (("baseline", baseline_values), ("candidate", candidate_values))
        for index, values in enumerate(rows)
    )


def test_repeated_baseline_candidate_evaluation_passes_with_mean_rules() -> None:
    spec = _comparison_spec()
    evaluator = RSIKernel().evaluator
    results = _passing_results(spec)

    evaluation = evaluator.evaluate(spec, results=results)
    evidence = evaluator.evidence(spec, evaluation, results=results)

    assert evaluation.disposition == "passed"
    assert len(evaluation.measurements) == 12
    assert evaluation.findings["valid_trials"] == {"baseline": 3, "candidate": 3}
    rules = evaluation.findings["rules"]
    assert rules[0]["effect"] == pytest.approx(20.0)  # type: ignore[index]
    assert all(rule["passed"] for rule in rules)  # type: ignore[index]
    assert evidence.evidence_type == "support"
    assert evidence.subject_refs == spec.lineage
    assert evidence.source_refs == (evaluation.ref,)
    assert evidence.target_snapshot == spec.candidate_snapshot
    assert ExperimentEvaluator.projection(spec)["spec_root"] == spec.root


def test_valid_execution_that_violates_a_guardrail_fails() -> None:
    spec = _comparison_spec()
    results = list(_passing_results(spec))
    results[-1] = _valid_result(
        spec,
        role="candidate",
        index=2,
        latency=78.0,
        throughput=50.0,
    )
    results[-2] = _valid_result(
        spec,
        role="candidate",
        index=1,
        latency=82.0,
        throughput=50.0,
    )

    evaluation = ExperimentEvaluator().evaluate(spec, results=results)
    evidence = ExperimentEvaluator().evidence(spec, evaluation, results=results)

    assert evaluation.disposition == "failed"
    assert evaluation.findings["rules"][1]["passed"] is False  # type: ignore[index]
    assert evidence.evidence_type == "counterexample"


def test_invalid_trials_are_inconclusive_and_never_negative_evidence() -> None:
    spec = _comparison_spec()
    evaluator = ExperimentEvaluator()
    results = list(_passing_results(spec)[:3])
    for index in range(spec.repetitions):
        trial = evaluator.prepare_trial(spec, index=index, role="candidate")
        results.append(
            evaluator.record_result(
                spec,
                trial=trial,
                disposition="invalid",
                reason="executor unavailable",
            )
        )

    evaluation = evaluator.evaluate(spec, results=results)
    evidence = evaluator.evidence(spec, evaluation, results=results)

    assert evaluation.disposition == "inconclusive"
    assert evaluation.findings["invalid_trials"] == {"baseline": 0, "candidate": 3}
    assert evidence.evidence_type == "null"
    assert evidence.weight == 0.0


def test_claims_can_be_tested_without_a_candidate_change() -> None:
    claim, baseline, _ = _context()
    metric = Metric(metric_id="temperature", direction="target", unit="C")
    rule = DecisionRule(
        metric=metric.ref,
        kind="threshold",
        operator="<=",
        threshold=25.0,
    )
    evaluator = ExperimentEvaluator()
    spec = evaluator.design(
        experiment_id="claim-only",
        subject=claim,
        kind="observation",
        metrics=(metric,),
        decision_rules=(rule,),
        target_snapshot=baseline,
        repetitions=1,
    )
    trial = evaluator.prepare_trial(spec, index=0)
    observation = Observation(
        kind="thermometer",
        value=22.0,
        target_snapshot=baseline,
        source_refs=(trial.ref,),
    )
    result = evaluator.record_result(
        spec,
        trial=trial,
        disposition="valid",
        observations=(observation,),
        measurements=(
            Measurement(
                metric="temperature",
                metric_ref=metric.ref,
                value=22.0,
                unit="C",
                target_snapshot=baseline,
                observation_refs=(observation.ref,),
            ),
        ),
    )

    assert evaluator.evaluate(spec, results=(result,)).disposition == "passed"
    assert trial.role == "subject"


def test_trials_preserve_external_identity_repetitions_roles_seeds_and_budget() -> None:
    spec = _comparison_spec()
    evaluator = ExperimentEvaluator()
    baseline = evaluator.prepare_trial(spec, index=0, role="baseline")
    candidate = evaluator.prepare_trial(spec, index=0, role="candidate")
    repeated = evaluator.prepare_trial(spec, index=1, role="candidate")

    assert baseline.experiment == spec.ref == candidate.experiment
    assert len({baseline.root, candidate.root, repeated.root}) == 3
    assert baseline.seed == 11
    assert repeated.seed == 12
    assert baseline.data["budget"] == {"max_steps": 30}
    assert deserialize_record(serialize_record(spec)) == spec
    assert deserialize_record(serialize_record(candidate)) == candidate


def test_command_experiments_are_adapters_over_generic_metric_rules() -> None:
    target = TargetRef(target_id="repo", kind="software")
    snapshot = TargetSnapshot(target=target, revision="abc", state={"revision": "abc"})
    hypothesis = RSIKernel().hypotheses.create(
        target=target,
        statement="The command emits OK",
        predictions=({"stdout": "OK"},),
    )
    policy = RSIKernel().experiments
    spec = policy.design_command(
        experiment_id="command-adapter",
        hypothesis=hypothesis,
        target_snapshot=snapshot,
        design={"isolation": "subprocess"},
        success_criteria={"accepted_exit_codes": [0], "stdout_contains": ["OK"]},
        command=["python", "probe.py"],
        cwd="/workspace",
    )
    observation = CommandObservation(
        exit_code=0,
        stdout="OK\n",
        stderr="",
        exact_input_root=spec.root,
    )

    assert spec.metrics[0].metric_id == "command.passed"
    assert spec.decision_rules[0].metric == spec.metrics[0].ref
    assert policy.prepare_command(spec).command == ("python", "probe.py")
    assert policy.evaluate_command(spec=spec, observation=observation).evidence_type == "support"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Metric(metric_id="m", direction="sideways"),
        lambda: Metric(metric_id="m", direction="increase", role="owner"),
        lambda: DecisionRule(metric=RecordRef("claim", "a" * 64), kind="threshold"),
        lambda: DecisionRule(
            metric=RecordRef("metric", "a" * 64),
            kind="threshold",
            operator="!=",
            threshold=1.0,
        ),
        lambda: DecisionRule(
            metric=RecordRef("metric", "a" * 64),
            kind="baseline_delta",
            minimum_effect=-1.0,
        ),
        lambda: DecisionRule(
            metric=RecordRef("metric", "a" * 64),
            kind="threshold",
            operator=">=",
            threshold=1.0,
            minimum_effect=0.1,
        ),
        lambda: Measurement(metric="m", value=float("inf")),
    ],
)
def test_malformed_metrics_measurements_and_rules_fail_closed(factory: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


def test_design_rejects_mixed_rules_seeds_and_target_directions() -> None:
    claim, baseline, candidate = _context()
    metric = Metric(metric_id="m", direction="target")
    other = Metric(metric_id="other", direction="increase")
    wrong_rule = DecisionRule(
        metric=other.ref,
        kind="threshold",
        operator=">=",
        threshold=1.0,
    )
    evaluator = ExperimentEvaluator()

    with pytest.raises(ValueError, match="exact experiment metric"):
        evaluator.design(
            experiment_id="mixed",
            subject=claim,
            kind="simulation",
            metrics=(metric,),
            decision_rules=(wrong_rule,),
            target_snapshot=baseline,
        )
    delta = DecisionRule(metric=metric.ref, kind="baseline_delta")
    with pytest.raises(ValueError, match="target-direction"):
        evaluator.design(
            experiment_id="target-delta",
            subject=claim,
            kind="simulation",
            metrics=(metric,),
            decision_rules=(delta,),
            baseline_snapshot=baseline,
            candidate_snapshot=candidate,
        )
    threshold = DecisionRule(
        metric=metric.ref,
        kind="threshold",
        operator=">=",
        threshold=1.0,
    )
    with pytest.raises(ValueError, match="seeds.*repetition"):
        evaluator.design(
            experiment_id="bad-seeds",
            subject=claim,
            kind="simulation",
            metrics=(metric,),
            decision_rules=(threshold,),
            target_snapshot=baseline,
            repetitions=2,
            seeds=(1,),
        )
    impossible_rule = DecisionRule(
        metric=metric.ref,
        kind="threshold",
        operator=">=",
        threshold=1.0,
        required_valid_trials=2,
    )
    with pytest.raises(ValueError, match="cannot exceed experiment repetitions"):
        evaluator.design(
            experiment_id="impossible-valid-count",
            subject=claim,
            kind="simulation",
            metrics=(metric,),
            decision_rules=(impossible_rule,),
            target_snapshot=baseline,
            repetitions=1,
        )


def test_result_and_evaluation_reject_identity_provenance_and_currentness_errors() -> None:
    spec = _comparison_spec()
    evaluator = ExperimentEvaluator()
    trial = evaluator.prepare_trial(spec, index=0, role="candidate")
    latency = spec.metrics[0]
    assert spec.candidate_snapshot is not None and spec.baseline_snapshot is not None
    valid_observation = Observation(
        kind="latency",
        value=80.0,
        target_snapshot=spec.candidate_snapshot,
        source_refs=(trial.ref,),
    )
    wrong_snapshot = Measurement(
        metric="latency",
        metric_ref=latency.ref,
        value=80.0,
        unit="ms",
        target_snapshot=spec.baseline_snapshot,
        observation_refs=(valid_observation.ref,),
    )
    with pytest.raises(ValueError, match="trial target snapshot"):
        evaluator.record_result(
            spec,
            trial=trial,
            disposition="valid",
            observations=(valid_observation,),
            measurements=(wrong_snapshot,),
        )

    missing_provenance = Measurement(
        metric="latency",
        metric_ref=latency.ref,
        value=80.0,
        unit="ms",
        target_snapshot=spec.candidate_snapshot,
    )
    with pytest.raises(ValueError, match="provenance"):
        evaluator.record_result(
            spec,
            trial=trial,
            disposition="valid",
            observations=(valid_observation,),
            measurements=(missing_provenance,),
        )

    substituted_provenance = Measurement(
        metric="latency",
        metric_ref=latency.ref,
        value=80.0,
        unit="ms",
        target_snapshot=spec.candidate_snapshot,
        observation_refs=(Claim(statement="not an observation").ref,),
    )
    with pytest.raises(ValueError, match="exact trial observations"):
        evaluator.record_result(
            spec,
            trial=trial,
            disposition="valid",
            observations=(valid_observation,),
            measurements=(substituted_provenance,),
        )

    invalid_observation = Observation(
        kind="latency",
        value=80.0,
        valid=False,
        target_snapshot=spec.candidate_snapshot,
        source_refs=(trial.ref,),
    )
    invalid_observation_measurement = Measurement(
        metric="latency",
        metric_ref=latency.ref,
        value=80.0,
        unit="ms",
        target_snapshot=spec.candidate_snapshot,
        observation_refs=(invalid_observation.ref,),
    )
    with pytest.raises(ValueError, match="valid observations"):
        evaluator.record_result(
            spec,
            trial=trial,
            disposition="valid",
            observations=(invalid_observation,),
            measurements=(invalid_observation_measurement,),
        )
    with pytest.raises(ValueError, match="valid observations"):
        evaluator.evaluate(
            spec,
            results=(
                TrialResult(
                    trial=trial,
                    disposition="valid",
                    observations=(invalid_observation,),
                    measurements=(invalid_observation_measurement,),
                ),
            ),
        )

    results = _passing_results(spec)
    substituted_trial = evaluator.prepare_trial(spec, index=1, role="candidate")
    stale_invalid_observation = Observation(
        kind="stale-invalid",
        value=None,
        valid=False,
        target_snapshot=spec.baseline_snapshot,
        source_refs=(substituted_trial.ref,),
    )
    invalid_with_substituted_provenance = TrialResult(
        trial=evaluator.prepare_trial(spec, index=2, role="candidate"),
        disposition="invalid",
        observations=(stale_invalid_observation,),
        reason="invalid observation",
    )
    with pytest.raises(ValueError, match="exact Trial"):
        evaluator.evaluate(
            spec,
            results=(*results[:-1], invalid_with_substituted_provenance),
        )
    with pytest.raises(ValueError, match="every planned Trial"):
        evaluator.evaluate(spec, results=results[:-1])
    with pytest.raises(ValueError, match="duplicate Trial"):
        evaluator.evaluate(spec, results=(*results, results[0]))
    other = ExperimentSpec(experiment_id="other", kind="simulation")
    mixed_trial = Trial(experiment=other.ref, index=0, status="planned")
    mixed = TrialResult(
        trial=mixed_trial,
        disposition="invalid",
        reason="wrong spec",
    )
    with pytest.raises(ValueError, match="different ExperimentSpec"):
        evaluator.evaluate(spec, results=(mixed,))


def test_legacy_record_identity_omits_default_block4_extensions() -> None:
    spec = ExperimentSpec(experiment_id="legacy", kind="benchmark")
    trial = Trial(experiment=spec.ref, index=0, status="done")
    measurement = Measurement(metric="legacy", value=1.0)

    assert "metrics" not in spec.identity_data()
    assert "decision_rules" not in spec.identity_data()
    assert "role" not in trial.identity_data()
    assert "seed" not in trial.identity_data()
    assert "metric_ref" not in measurement.identity_data()


def test_design_and_spec_validation_fail_closed() -> None:
    claim, baseline, candidate = _context()
    metric = Metric(metric_id="temperature", direction="target", unit="C")
    rule = DecisionRule(
        metric=metric.ref,
        kind="threshold",
        operator="<=",
        threshold=25.0,
    )
    evaluator = ExperimentEvaluator()
    common = {
        "experiment_id": "strict",
        "subject": claim,
        "kind": "observation",
        "metrics": (metric,),
        "decision_rules": (rule,),
        "target_snapshot": baseline,
    }

    with pytest.raises(TypeError, match="experiment id"):
        evaluator.design(**{**common, "experiment_id": 1})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="experiment kind"):
        evaluator.design(**{**common, "kind": " "})
    with pytest.raises(TypeError, match="Claim or Hypothesis"):
        evaluator.design(**{**common, "subject": baseline})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="repetitions"):
        evaluator.design(**common, repetitions=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        evaluator.design(**common, repetitions=0)
    with pytest.raises(TypeError, match="metrics.*sequence"):
        evaluator.design(**{**common, "metrics": "metric"})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Metric records"):
        evaluator.design(**{**common, "metrics": (claim,)})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="DecisionRule records"):
        evaluator.design(**{**common, "decision_rules": (claim,)})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="nonnegative integers"):
        evaluator.design(**common, repetitions=1, seeds=(-1,))
    with pytest.raises(TypeError, match="validity requirements"):
        evaluator.design(**common, validity_requirements=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require_all_metrics"):
        evaluator.design(**common, validity_requirements={"require_all_metrics": "yes"})

    other = TargetRef(target_id="other", kind="simulation")
    with pytest.raises(ValueError, match="subject target"):
        evaluator.design(
            **{
                **common,
                "target_snapshot": TargetSnapshot(target=other, state={}),
            }
        )

    with pytest.raises(ValueError, match="at least one Metric"):
        evaluator.projection(ExperimentSpec(experiment_id="empty", kind="x"))
    with pytest.raises(ValueError, match="DecisionRule"):
        evaluator.projection(
            ExperimentSpec(
                experiment_id="no-rule",
                kind="x",
                metrics=(metric,),
                requested_measurements=(metric.metric_id,),
                lineage=(claim.ref,),
            )
        )
    with pytest.raises(ValueError, match="requested measurements"):
        evaluator.projection(
            ExperimentSpec(
                experiment_id="wrong-request",
                kind="x",
                metrics=(metric,),
                decision_rules=(rule,),
                requested_measurements=("other",),
                lineage=(claim.ref,),
            )
        )
    with pytest.raises(ValueError, match="requested measurements"):
        evaluator.projection(
            ExperimentSpec(
                experiment_id="duplicate-request",
                kind="x",
                metrics=(metric,),
                decision_rules=(rule,),
                requested_measurements=(metric.metric_id, metric.metric_id),
                lineage=(claim.ref,),
            )
        )
    with pytest.raises(ValueError, match="lineage"):
        evaluator.projection(
            ExperimentSpec(
                experiment_id="no-lineage",
                kind="x",
                metrics=(metric,),
                decision_rules=(rule,),
                requested_measurements=(metric.metric_id,),
            )
        )
    with pytest.raises(ValueError, match="baseline and candidate"):
        evaluator.design(
            experiment_id="half-comparison",
            subject=claim,
            kind="x",
            metrics=(metric,),
            decision_rules=(rule,),
            baseline_snapshot=baseline,
        )
    delta_metric = Metric(metric_id="score", direction="increase")
    delta_rule = DecisionRule(metric=delta_metric.ref, kind="baseline_delta")
    with pytest.raises(ValueError, match="comparison experiment"):
        evaluator.design(
            experiment_id="delta-without-comparison",
            subject=claim,
            kind="x",
            metrics=(delta_metric,),
            decision_rules=(delta_rule,),
            target_snapshot=candidate,
        )


def test_measurement_trial_and_result_validation_fail_closed() -> None:
    spec = _comparison_spec()
    evaluator = ExperimentEvaluator()
    trial = evaluator.prepare_trial(spec, index=0, role="candidate")
    good_result = _valid_result(
        spec,
        role="candidate",
        index=0,
        latency=80.0,
        throughput=95.0,
    )
    good = good_result.measurements
    observations = good_result.observations
    latency, throughput = spec.metrics
    assert spec.candidate_snapshot is not None
    source = good[0].observation_refs

    invalid_measurements = (
        Measurement(
            metric="latency",
            value=80.0,
            unit="ms",
            target_snapshot=spec.candidate_snapshot,
            observation_refs=source,
        ),
        Measurement(
            metric="wrong-name",
            metric_ref=latency.ref,
            value=80.0,
            unit="ms",
            target_snapshot=spec.candidate_snapshot,
            observation_refs=source,
        ),
        Measurement(
            metric="latency",
            metric_ref=latency.ref,
            value=80.0,
            unit="seconds",
            target_snapshot=spec.candidate_snapshot,
            observation_refs=source,
        ),
        Measurement(
            metric="latency",
            metric_ref=latency.ref,
            value="fast",
            unit="ms",
            target_snapshot=spec.candidate_snapshot,
            observation_refs=source,
        ),
    )
    messages = ("exact experiment Metric", "name", "unit", "numeric")
    for measurement, message in zip(invalid_measurements, messages, strict=True):
        with pytest.raises((TypeError, ValueError), match=message):
            evaluator.record_result(
                spec,
                trial=trial,
                disposition="valid",
                observations=observations,
                measurements=(measurement, good[1]),
            )
    with pytest.raises(TypeError, match="Measurement records"):
        evaluator.record_result(
            spec,
            trial=trial,
            disposition="valid",
            observations=observations,
            measurements=(Claim(statement="not a measurement"),),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="at most once"):
        evaluator.record_result(
            spec,
            trial=trial,
            disposition="valid",
            observations=observations,
            measurements=(good[0], good[0], good[1]),
        )
    with pytest.raises(ValueError, match="every requested Metric"):
        evaluator.record_result(
            spec,
            trial=trial,
            disposition="valid",
            observations=observations,
            measurements=(good[0],),
        )

    with pytest.raises(TypeError, match="trial index"):
        evaluator.prepare_trial(spec, index=True, role="candidate")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="repetition range"):
        evaluator.prepare_trial(spec, index=spec.repetitions, role="candidate")
    with pytest.raises(ValueError, match="not valid"):
        evaluator.prepare_trial(spec, index=0, role="subject")
    other = ExperimentSpec(experiment_id="other", kind="x")
    with pytest.raises(ValueError, match="exact ExperimentSpec"):
        evaluator.record_result(
            spec,
            trial=Trial(experiment=other.ref, index=0, status="planned"),
            disposition="invalid",
            reason="wrong",
        )
    with pytest.raises(ValueError, match="planned"):
        evaluator.record_result(
            spec,
            trial=Trial(
                experiment=spec.ref,
                index=0,
                status="completed",
                role="candidate",
                seed=11,
            ),
            disposition="invalid",
            reason="wrong",
        )
    with pytest.raises(ValueError, match="seed"):
        evaluator.record_result(
            spec,
            trial=Trial(
                experiment=spec.ref,
                index=0,
                status="planned",
                role="candidate",
                seed=99,
            ),
            disposition="invalid",
            reason="wrong",
        )
    forged_trial = Trial(
        experiment=spec.ref,
        index=0,
        status="planned",
        role="candidate",
        seed=11,
        data={"budget": spec.budget, "forged": True},
        lineage=(spec.ref,),
    )
    with pytest.raises(ValueError, match="exact prepared Trial"):
        evaluator.record_result(
            spec,
            trial=forged_trial,
            disposition="invalid",
            reason="substituted trial",
        )
    with pytest.raises(ValueError, match="exact prepared Trial"):
        evaluator.evaluate(
            spec,
            results=(
                TrialResult(
                    trial=forged_trial,
                    disposition="invalid",
                    reason="substituted trial",
                ),
            ),
        )
    with pytest.raises(ValueError, match="disposition"):
        evaluator.record_result(
            spec,
            trial=trial,
            disposition="failed",  # type: ignore[arg-type]
            reason="wrong",
        )
    assert throughput.ref != latency.ref


@pytest.mark.parametrize(
    ("operator", "threshold", "value", "expected"),
    [
        ("<", 5.0, 4.0, True),
        ("<=", 5.0, 5.0, True),
        ("==", 5.0, 5.0, True),
        (">", 5.0, 6.0, True),
    ],
)
def test_threshold_operators_are_deterministic(
    operator: str,
    threshold: float,
    value: float,
    expected: bool,
) -> None:
    claim, snapshot, _ = _context()
    metric = Metric(metric_id="score", direction="target")
    rule = DecisionRule(
        metric=metric.ref,
        kind="threshold",
        operator=operator,
        threshold=threshold,
    )
    evaluator = ExperimentEvaluator()
    spec = evaluator.design(
        experiment_id=f"operator-{operator}",
        subject=claim,
        kind="measurement",
        metrics=(metric,),
        decision_rules=(rule,),
        target_snapshot=snapshot,
    )
    trial = evaluator.prepare_trial(spec, index=0)
    observation = Observation(
        kind="score",
        value=value,
        target_snapshot=snapshot,
        source_refs=(trial.ref,),
    )
    result = evaluator.record_result(
        spec,
        trial=trial,
        disposition="valid",
        observations=(observation,),
        measurements=(
            Measurement(
                metric="score",
                metric_ref=metric.ref,
                value=value,
                target_snapshot=snapshot,
                observation_refs=(observation.ref,),
            ),
        ),
    )
    finding = evaluator.evaluate(spec, results=(result,)).findings["rules"][0]
    assert finding["passed"] is expected


def test_evaluation_and_evidence_outputs_reject_mixed_or_malformed_state() -> None:
    spec = _comparison_spec()
    evaluator = ExperimentEvaluator()
    with pytest.raises(ValueError, match="requires trial results"):
        evaluator.evaluate(spec, results=())
    with pytest.raises(TypeError, match="TrialResult"):
        evaluator.evaluate(spec, results=(Claim(statement="bad"),))  # type: ignore[arg-type]

    wrong_seed = TrialResult(
        trial=Trial(
            experiment=spec.ref,
            index=0,
            status="planned",
            role="candidate",
            seed=99,
        ),
        disposition="invalid",
        reason="wrong seed",
    )
    with pytest.raises(ValueError, match="seed"):
        evaluator.evaluate(spec, results=(wrong_seed,))
    wrong_status = TrialResult(
        trial=Trial(
            experiment=spec.ref,
            index=0,
            status="completed",
            role="candidate",
            seed=11,
        ),
        disposition="invalid",
        reason="wrong status",
    )
    with pytest.raises(ValueError, match="prepared Trial"):
        evaluator.evaluate(spec, results=(wrong_status,))

    results = _passing_results(spec)
    good_evaluation = evaluator.evaluate(spec, results=results)
    with pytest.raises(ValueError, match="exact result"):
        evaluator.evidence(
            spec,
            type(good_evaluation)(
                subject_refs=(Claim(statement="other").ref,),
                disposition="passed",
            ),
            results=results,
        )
    forged = type(good_evaluation)(subject_refs=(spec.ref,), disposition="passed")
    with pytest.raises(ValueError, match="exact result"):
        evaluator.evidence(spec, forged, results=results)
    with pytest.raises(TypeError, match="requires an Evaluation"):
        evaluator.evidence(spec, Claim(statement="wrong type"), results=results)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="numeric"):
        ExperimentEvaluator(conclusive_evidence_weight=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="between zero and one"):
        ExperimentEvaluator(conclusive_evidence_weight=1.1)


def test_new_record_validation_rejects_ambiguous_states() -> None:
    metric_ref = RecordRef("metric", "b" * 64)
    with pytest.raises(ValueError, match="rule kind"):
        DecisionRule(metric=metric_ref, kind="heuristic")
    with pytest.raises(ValueError, match="mean aggregation"):
        DecisionRule(
            metric=metric_ref,
            kind="baseline_delta",
            aggregation="median",
        )
    with pytest.raises(ValueError, match="positive"):
        DecisionRule(
            metric=metric_ref,
            kind="baseline_delta",
            required_valid_trials=0,
        )
    with pytest.raises(ValueError, match="finite threshold"):
        DecisionRule(metric=metric_ref, kind="threshold", operator=">=")
    with pytest.raises(ValueError, match="do not accept"):
        DecisionRule(
            metric=metric_ref,
            kind="baseline_delta",
            operator=">=",
            threshold=1.0,
        )
    spec_ref = RecordRef("experiment_spec", "c" * 64)
    with pytest.raises(ValueError, match="trial role"):
        Trial(experiment=spec_ref, index=0, status="planned", role="control")
    with pytest.raises(ValueError, match="nonnegative"):
        Trial(experiment=spec_ref, index=0, status="planned", seed=-1)
    with pytest.raises(TypeError, match="metric_ref"):
        Measurement(
            metric="m",
            metric_ref=RecordRef("claim", "d" * 64),
            value=1.0,
        )
    trial = Trial(experiment=spec_ref, index=0, status="planned")
    with pytest.raises(TypeError, match="requires a Trial"):
        TrialResult(trial="bad", disposition="invalid", reason="bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="disposition"):
        TrialResult(trial=trial, disposition="failed", reason="bad")
    with pytest.raises(ValueError, match="require measurements"):
        TrialResult(trial=trial, disposition="valid")
    with pytest.raises(TypeError, match="Measurement records"):
        TrialResult(
            trial=trial,
            disposition="valid",
            measurements=(Claim(statement="bad"),),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="require a reason"):
        TrialResult(trial=trial, disposition="invalid")
