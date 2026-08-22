from __future__ import annotations

import inspect

import pytest

from librsi import (
    CommandObservation,
    Evidence,
    ExperimentSpec,
    Hypothesis,
    Question,
    RecordRef,
    RSIKernel,
    RSITransitionError,
    TargetRef,
    TargetSnapshot,
)


def _target() -> tuple[TargetRef, TargetSnapshot]:
    target = TargetRef(
        target_id="scheduler",
        kind="software",
        locator={"repo": "estill01/example", "component": "queue"},
    )
    snapshot = TargetSnapshot(
        target=target,
        revision="abc123",
        state={"revision": "abc123", "p95_ms": 120.0},
    )
    return target, snapshot


def _hypothesis() -> tuple[Hypothesis, TargetSnapshot]:
    target, snapshot = _target()
    question = Question(prompt="What causes queue latency?", target=target)
    hypothesis = RSIKernel().hypotheses.create(
        target=target,
        statement="Lock contention contributes to queue latency",
        causal_model={"cause": "global lock contention"},
        predictions=({"metric": "p95_ms", "direction": "decrease"},),
        source_refs=(question.ref,),
        confidence=0.5,
    )
    return hypothesis, snapshot


def _command_spec() -> tuple[Hypothesis, TargetSnapshot, ExperimentSpec]:
    hypothesis, snapshot = _hypothesis()
    spec = RSIKernel().experiments.design_command(
        experiment_id="latency-1",
        hypothesis=hypothesis,
        target_snapshot=snapshot,
        design={"isolation": "subprocess"},
        success_criteria={"accepted_exit_codes": [0], "stdout_contains": ["OK"]},
        command=["python", "probe.py"],
        cwd="/workspace",
    )
    return hypothesis, snapshot, spec


def _observation(
    spec: ExperimentSpec,
    *,
    exit_code: int | None = 0,
    stdout: str = "OK\n",
    stderr: str = "",
    invalid: bool = False,
) -> CommandObservation:
    return CommandObservation(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        invalid=invalid,
        exact_input_root=spec.root,
    )


def test_canonical_hypothesis_is_complete_and_origin_bound() -> None:
    target, _ = _target()
    question = Question(prompt="Why is the queue slow?", target=target)

    hypothesis = RSIKernel().hypotheses.create(
        target=target,
        statement="  lock contention raises queue latency  ",
        causal_model={"cause": "lock contention"},
        predictions=({"metric": "p95_ms", "direction": "decrease"},),
        source_refs=(question.ref,),
        confidence=0.6,
    )

    assert hypothesis.target == target
    assert hypothesis.statement == "lock contention raises queue latency"
    assert hypothesis.causal_model["cause"] == "lock contention"
    assert hypothesis.predictions[0]["metric"] == "p95_ms"
    assert hypothesis.source_refs == (question.ref,)
    assert hypothesis.confidence == 0.6
    assert hypothesis.status == "proposed"
    assert len(hypothesis.root) == 64


def test_canonical_hypothesis_creation_fails_closed() -> None:
    target, _ = _target()
    policy = RSIKernel().hypotheses

    with pytest.raises(ValueError, match="prediction"):
        policy.create(target=target, statement="H", predictions=())
    with pytest.raises(TypeError, match="sequence of mappings"):
        policy.create(
            target=target,
            statement="H",
            predictions="not-predictions",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="only mappings"):
        policy.create(
            target=target,
            statement="H",
            predictions=("not-a-mapping",),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="status"):
        policy.create(
            target=target,
            statement="H",
            predictions=({"observable": True},),
            status="unknown",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="TargetRef"):
        policy.create(
            target="scheduler",  # type: ignore[arg-type]
            statement="H",
            predictions=({"observable": True},),
        )
    with pytest.raises(TypeError, match="causal model"):
        policy.create(
            target=target,
            statement="H",
            predictions=({"observable": True},),
            causal_model=[],  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="metadata"):
        policy.create(
            target=target,
            statement="H",
            predictions=({"observable": True},),
            metadata=[],  # type: ignore[arg-type]
        )


def test_command_experiment_binds_all_material_inputs_and_exact_hypothesis() -> None:
    hypothesis, snapshot = _hypothesis()
    policy = RSIKernel().experiments
    spec = policy.design_command(
        experiment_id="latency-1",
        hypothesis=hypothesis,
        target_snapshot=snapshot,
        design={"isolation": "subprocess", "repetitions": 5},
        success_criteria={"accepted_exit_codes": [0], "stdout_contains": ["OK"]},
        command=["python", "probe.py"],
        cwd="/workspace",
        inputs={"workload": "representative"},
        environment={"python": "3.13"},
        requested_measurements=("command.passed", "p95_ms"),
    )
    command = policy.prepare_command(spec)

    assert spec.kind == "command"
    assert spec.target_snapshot == snapshot
    assert spec.lineage == (hypothesis.ref,)
    assert spec.criteria["stdout_contains"] == ("OK",)
    assert spec.inputs["parameters"]["workload"] == "representative"  # type: ignore[index]
    assert spec.environment["python"] == "3.13"
    assert spec.requested_measurements == ("command.passed", "p95_ms")
    assert command.exact_input_root == spec.root
    assert command.command == ("python", "probe.py")
    assert command.cwd == "/workspace"


def test_command_design_rejects_ambiguous_optional_inputs_and_measurements() -> None:
    hypothesis, snapshot = _hypothesis()
    policy = RSIKernel().experiments
    common = {
        "experiment_id": "strict-inputs",
        "hypothesis": hypothesis,
        "target_snapshot": snapshot,
        "design": {"isolation": "subprocess"},
        "success_criteria": {"accepted_exit_codes": [0]},
        "command": ["python"],
        "cwd": "/workspace",
    }

    with pytest.raises(TypeError, match="experiment inputs"):
        policy.design_command(**common, inputs=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="environment"):
        policy.design_command(**common, environment=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requested measurements"):
        policy.design_command(**common, requested_measurements="p95_ms")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least one requested measurement"):
        policy.design_command(**common, requested_measurements=())


def test_evaluation_consumes_spec_criteria_and_produces_exact_evidence() -> None:
    hypothesis, snapshot, spec = _command_spec()
    policy = RSIKernel().experiments
    observation = _observation(spec)

    evidence = policy.evaluate_command(spec=spec, observation=observation)

    assert evidence.evidence_type == "support"
    assert evidence.weight == 0.7
    assert evidence.subject_refs == (hypothesis.ref,)
    assert evidence.source_refs == (spec.ref,)
    assert evidence.target_snapshot == snapshot
    assert evidence.data["experiment_root"] == spec.root
    assert evidence.data["observation_input_root"] == spec.root
    assert evidence.data["criteria"]["stdout_contains"] == ("OK",)  # type: ignore[index]

    updated = RSIKernel().hypotheses.apply(hypothesis=hypothesis, evidence=evidence)
    assert updated.confidence > hypothesis.confidence
    assert updated.lineage[-2:] == (hypothesis.ref, evidence.ref)


def test_observation_must_echo_the_exact_input_root() -> None:
    _, _, spec = _command_spec()
    policy = RSIKernel().experiments

    with pytest.raises(ValueError, match="exact input root"):
        policy.evaluate_command(
            spec=spec,
            observation=CommandObservation(exit_code=0, stdout="OK\n", stderr=""),
        )
    with pytest.raises(ValueError, match="does not match"):
        policy.evaluate_command(
            spec=spec,
            observation=CommandObservation(
                exit_code=0,
                stdout="OK\n",
                stderr="",
                exact_input_root="a" * 64,
            ),
        )


def test_evidence_cannot_update_a_different_or_stale_hypothesis_version() -> None:
    hypothesis, _, spec = _command_spec()
    experiments = RSIKernel().experiments
    hypotheses = RSIKernel().hypotheses
    evidence = experiments.evaluate_command(spec=spec, observation=_observation(spec))
    updated = hypotheses.apply(hypothesis=hypothesis, evidence=evidence)

    with pytest.raises(ValueError, match="exact hypothesis"):
        hypotheses.apply(hypothesis=updated, evidence=evidence)

    other = hypotheses.create(
        target=hypothesis.target,  # type: ignore[arg-type]
        statement="A different mechanism drives latency",
        predictions=({"metric": "p95_ms", "direction": "increase"},),
    )
    with pytest.raises(ValueError, match="exact hypothesis"):
        hypotheses.apply(hypothesis=other, evidence=evidence)


def test_hypothesis_update_requires_exact_target_and_explicit_weight() -> None:
    hypothesis, _ = _hypothesis()
    other_target = TargetRef(target_id="other", kind="software")
    other_snapshot = TargetSnapshot(target=other_target, state={"revision": "other"})
    policy = RSIKernel().hypotheses

    wrong_target = Evidence(
        evidence_type="support",
        data={"ok": True},
        subject_refs=(hypothesis.ref,),
        target_snapshot=other_snapshot,
        weight=0.5,
    )
    with pytest.raises(ValueError, match="target does not match"):
        policy.apply(hypothesis=hypothesis, evidence=wrong_target)

    missing_weight = Evidence(
        evidence_type="support",
        data={"ok": True},
        subject_refs=(hypothesis.ref,),
    )
    with pytest.raises(ValueError, match="explicit weight"):
        policy.apply(hypothesis=hypothesis, evidence=missing_weight)


def test_experiment_criteria_cannot_be_replaced_at_evaluation_time() -> None:
    hypothesis, snapshot = _hypothesis()
    policy = RSIKernel().experiments
    criterion_a = policy.design_command(
        experiment_id="criteria-a",
        hypothesis=hypothesis,
        target_snapshot=snapshot,
        design={"isolation": "subprocess"},
        success_criteria={"accepted_exit_codes": [0], "stdout_contains": ["A"]},
        command=["python", "probe.py"],
        cwd="/workspace",
    )
    criterion_b = policy.design_command(
        experiment_id="criteria-a",
        hypothesis=hypothesis,
        target_snapshot=snapshot,
        design={"isolation": "subprocess"},
        success_criteria={"accepted_exit_codes": [0], "stdout_contains": ["B"]},
        command=["python", "probe.py"],
        cwd="/workspace",
    )
    observation_a = _observation(criterion_a, stdout="A\n")

    assert criterion_a.root != criterion_b.root
    assert (
        policy.evaluate_command(spec=criterion_a, observation=observation_a).evidence_type
        == "support"
    )
    with pytest.raises(ValueError, match="does not match"):
        policy.evaluate_command(spec=criterion_b, observation=observation_a)

    observation_b = _observation(criterion_b, stdout="A\n")
    assert (
        policy.evaluate_command(spec=criterion_b, observation=observation_b).evidence_type
        == "counterexample"
    )
    assert "success_criteria" not in inspect.signature(policy.evaluate_command).parameters


def test_invalid_execution_is_zero_weight_null_evidence_and_preserves_confidence() -> None:
    hypothesis, _, spec = _command_spec()
    experiments = RSIKernel().experiments
    hypotheses = RSIKernel().hypotheses
    evidence = experiments.evaluate_command(
        spec=spec,
        observation=_observation(
            spec,
            exit_code=None,
            stdout="",
            stderr="timed out",
            invalid=True,
        ),
    )
    updated = hypotheses.apply(hypothesis=hypothesis, evidence=evidence)

    assert evidence.evidence_type == "null"
    assert evidence.weight == 0.0
    assert evidence.data["disposition"] == "invalid"
    assert updated.confidence == hypothesis.confidence


def test_target_currentness_binding_fails_closed() -> None:
    hypothesis, _ = _hypothesis()
    other_target = TargetRef(target_id="other", kind="software")
    other_snapshot = TargetSnapshot(target=other_target, state={"revision": "other"})

    with pytest.raises(ValueError, match="does not match"):
        RSIKernel().experiments.design_command(
            experiment_id="wrong-target",
            hypothesis=hypothesis,
            target_snapshot=other_snapshot,
            design={"isolation": "subprocess"},
            success_criteria={"accepted_exit_codes": [0]},
            command=["python", "probe.py"],
            cwd="/workspace",
        )


def test_hand_built_malformed_specs_fail_before_execution_or_evaluation() -> None:
    hypothesis, snapshot = _hypothesis()
    policy = RSIKernel().experiments

    malformed = ExperimentSpec(
        experiment_id="manual",
        kind="command",
        target_snapshot=snapshot,
        design={"isolation": "subprocess"},
        criteria={"accepted_exit_codes": [0]},
        inputs={"command": ["python"], "cwd": "/workspace"},
        requested_measurements=("command.passed",),
    )
    with pytest.raises(ValueError, match="exactly one hypothesis"):
        policy.prepare_command(malformed)

    two_hypotheses = ExperimentSpec(
        experiment_id="manual-2",
        kind="command",
        target_snapshot=snapshot,
        design={"isolation": "subprocess"},
        criteria={"accepted_exit_codes": [0]},
        inputs={"command": ["python"], "cwd": "/workspace"},
        requested_measurements=("command.passed",),
        lineage=(hypothesis.ref, RecordRef("hypothesis", "a" * 64)),
    )
    with pytest.raises(ValueError, match="exactly one hypothesis"):
        policy.prepare_command(two_hypotheses)

    missing_cwd = ExperimentSpec(
        experiment_id="manual-3",
        kind="command",
        target_snapshot=snapshot,
        design={"isolation": "subprocess"},
        criteria={"accepted_exit_codes": [0]},
        inputs={"command": ["python"]},
        requested_measurements=("command.passed",),
        lineage=(hypothesis.ref,),
    )
    with pytest.raises(ValueError, match="canonical cwd"):
        policy.prepare_command(missing_cwd)


def test_command_criteria_fail_closed() -> None:
    hypothesis, snapshot = _hypothesis()
    policy = RSIKernel().experiments

    with pytest.raises(ValueError, match="unsupported command success criteria"):
        policy.design_command(
            experiment_id="unknown-criterion",
            hypothesis=hypothesis,
            target_snapshot=snapshot,
            design={"isolation": "subprocess"},
            success_criteria={"score": 1},
            command=["python"],
            cwd="/workspace",
        )
    with pytest.raises(TypeError, match="integers"):
        policy.design_command(
            experiment_id="bad-exit-code",
            hypothesis=hypothesis,
            target_snapshot=snapshot,
            design={"isolation": "subprocess"},
            success_criteria={"accepted_exit_codes": ["0"]},
            command=["python"],
            cwd="/workspace",
        )


def test_non_command_specs_and_invalid_policy_weights_fail_closed() -> None:
    hypothesis, snapshot = _hypothesis()
    non_command = ExperimentSpec(
        experiment_id="simulation",
        kind="simulation",
        target_snapshot=snapshot,
        design={"model": "x"},
        criteria={"accepted_exit_codes": [0]},
        lineage=(hypothesis.ref,),
    )
    with pytest.raises(RSITransitionError, match="not a command"):
        RSIKernel().experiments.prepare_command(non_command)
    with pytest.raises(RSITransitionError, match="not a command"):
        RSIKernel().experiments.evaluate_command(
            spec=non_command,
            observation=CommandObservation(exit_code=0, stdout="", stderr=""),
        )

    bad_weight_policy = type(RSIKernel().experiments)(conclusive_evidence_weight=1.5)
    spec = RSIKernel().experiments.design_command(
        experiment_id="weight",
        hypothesis=hypothesis,
        target_snapshot=snapshot,
        design={"isolation": "subprocess"},
        success_criteria={"accepted_exit_codes": [0]},
        command=["python"],
        cwd="/workspace",
    )
    with pytest.raises(ValueError, match="between zero and one"):
        bad_weight_policy.evaluate_command(spec=spec, observation=_observation(spec, stdout=""))


def test_legacy_wrappers_are_explicitly_deprecated_but_remain_available() -> None:
    kernel = RSIKernel()
    with pytest.warns(DeprecationWarning, match="legacy compatibility"):
        proposal = kernel.hypotheses.propose(
            scope_id="legacy",
            statement="Legacy hypothesis",
            causal_model={"cause": "x"},
            prediction={"result": "y"},
        )
    with pytest.warns(DeprecationWarning, match="legacy compatibility"):
        legacy_input = kernel.experiments.command_input(
            experiment_id="legacy",
            experiment_type="command",
            status="designed",
            design={"isolation": "subprocess"},
            success_criteria={"accepted_exit_codes": [0]},
            command=["python"],
            cwd="/workspace",
        )
    with pytest.warns(DeprecationWarning, match="legacy compatibility"):
        legacy_eval = kernel.experiments.evaluate_command_result(
            exact_input_root=legacy_input.exact_input_root,
            success_criteria={"accepted_exit_codes": [0]},
            observation=CommandObservation(exit_code=0, stdout="", stderr=""),
        )
    with pytest.warns(DeprecationWarning, match="legacy compatibility"):
        update = kernel.hypotheses.apply_evidence(
            current_confidence=proposal.confidence,
            evidence_type=legacy_eval.hypothesis_evidence_type,
            evidence_id=legacy_eval.evidence_root,
            weight=legacy_eval.hypothesis_evidence_weight,
        )

    assert proposal.statement == "Legacy hypothesis"
    assert legacy_eval.passed is True
    assert update.confidence > proposal.confidence
