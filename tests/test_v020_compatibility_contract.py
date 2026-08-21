from __future__ import annotations

import json
from pathlib import Path

import pytest

import librsi
from librsi import CommandObservation, RSIKernel, RSITransitionError

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "v020_contract.json").read_text(encoding="utf-8")
)


def test_v020_public_exports_remain_available_and_public() -> None:
    legacy_exports = set(_FIXTURE["legacy_exports"])
    assert legacy_exports <= set(librsi.__all__)
    for name in legacy_exports:
        assert hasattr(librsi, name), name


def test_v020_hypothesis_reflection_and_evidence_contract() -> None:
    kernel = RSIKernel()
    proposal = kernel.hypotheses.propose(
        scope_id="legacy-system",
        statement="  generation checks prevent stale callback reuse  ",
        causal_model={"cause": "stale generation"},
        prediction={"recurrence": "zero"},
        reflection_id="reflection-1",
        confidence=_FIXTURE["hypothesis"]["initial_confidence"],
    )
    assert proposal.statement == "generation checks prevent stale callback reuse"
    assert proposal.hypothesis_root == _FIXTURE["roots"]["hypothesis_root"]

    reflection = kernel.reflections.identify(
        reflection_type="checkpoint",
        source_type="incident",
        source_id="incident-1",
        evidence_ids=["trace-b", "trace-a", "trace-b"],
        observations={"recurrence": 2},
        confidence=0.7,
    )
    assert reflection.evidence_ids == ("trace-a", "trace-b")
    assert reflection.prompt_root == _FIXTURE["roots"]["reflection_root"]

    support = kernel.hypotheses.apply_evidence(
        current_confidence=proposal.confidence,
        evidence_type="support",
        evidence_id="experiment-pass",
        weight=0.7,
    )
    assert support.confidence == pytest.approx(_FIXTURE["hypothesis"]["support_confidence"])
    assert support.status == _FIXTURE["hypothesis"]["support_status"]

    counterexample = kernel.hypotheses.apply_evidence(
        current_confidence=support.confidence,
        evidence_type="counterexample",
        evidence_id="experiment-fail",
        weight=0.7,
    )
    assert counterexample.confidence == pytest.approx(
        _FIXTURE["hypothesis"]["counterexample_confidence_after_support"]
    )
    assert counterexample.status == _FIXTURE["hypothesis"]["counterexample_status"]

    null = kernel.hypotheses.apply_evidence(
        current_confidence=counterexample.confidence,
        evidence_type="null",
        evidence_id="experiment-invalid",
        weight=0.0,
    )
    assert null.confidence == counterexample.confidence
    assert null.status == "testing"


def test_v020_command_experiment_identity_and_interpretation_contract() -> None:
    experiments = RSIKernel().experiments
    experiment = experiments.command_input(
        experiment_id="legacy-experiment",
        experiment_type="command",
        status="designed",
        design={"isolation": "subprocess"},
        success_criteria={"accepted_exit_codes": [0], "stdout_contains": ["OK"]},
        command=["python", "probe.py"],
        cwd="/workspace",
    )
    assert experiment.exact_input_root == _FIXTURE["roots"]["experiment_root"]
    assert experiment.command == ("python", "probe.py")

    passed = experiments.evaluate_command_result(
        exact_input_root=experiment.exact_input_root,
        success_criteria={"accepted_exit_codes": [0], "stdout_contains": ["OK"]},
        observation=CommandObservation(exit_code=0, stdout="OK\n", stderr=""),
    )
    assert passed.passed is True
    assert passed.disposition == _FIXTURE["experiment"]["pass_disposition"]
    assert passed.evidence_root == _FIXTURE["roots"]["experiment_pass_evidence_root"]
    assert passed.hypothesis_evidence_type == _FIXTURE["experiment"]["pass_evidence_type"]
    assert passed.hypothesis_evidence_weight == _FIXTURE["experiment"]["pass_evidence_weight"]

    failed = experiments.evaluate_command_result(
        exact_input_root=experiment.exact_input_root,
        success_criteria={"accepted_exit_codes": [0]},
        observation=CommandObservation(exit_code=7, stdout="", stderr="assertion failed"),
    )
    assert failed.passed is False
    assert failed.disposition == _FIXTURE["experiment"]["fail_disposition"]
    assert failed.hypothesis_evidence_type == _FIXTURE["experiment"]["fail_evidence_type"]

    invalid = experiments.evaluate_command_result(
        exact_input_root=experiment.exact_input_root,
        success_criteria={"accepted_exit_codes": [0]},
        observation=CommandObservation(exit_code=None, stdout="", stderr="timed out", invalid=True),
    )
    assert invalid.passed is False
    assert invalid.disposition == _FIXTURE["experiment"]["invalid_disposition"]
    assert invalid.hypothesis_evidence_type == _FIXTURE["experiment"]["invalid_evidence_type"]
    assert invalid.hypothesis_evidence_weight == _FIXTURE["experiment"]["invalid_evidence_weight"]


def test_v020_checkpoint_program_and_portfolio_contract() -> None:
    kernel = RSIKernel()
    checkpoint = kernel.checkpoints.evaluate(
        state={"quality": 0.82, "revision": "candidate-7"},
        evidence_ids=["trace-2", "eval-19", "trace-2"],
        previous_fingerprint=None,
    )
    assert checkpoint.state_fingerprint == _FIXTURE["roots"]["checkpoint_root"]
    assert checkpoint.material is True
    assert checkpoint.action == "record"

    unchanged = kernel.checkpoints.evaluate(
        state={"quality": 0.82, "revision": "candidate-7"},
        evidence_ids=["eval-19", "trace-2"],
        previous_fingerprint=checkpoint.state_fingerprint,
    )
    assert unchanged.material is False
    assert unchanged.action == "no_change"

    program_root = kernel.programs.candidate_root(
        scope_id="legacy-scope",
        program_id="program-1",
        change_kind="code",
        rationale={"why": "reduce latency"},
        change_spec={"patch": "abc"},
        requested_range_root="a" * 16,
        accepted_history_root="b" * 16,
        currentness_root="c" * 16,
    )
    assert program_root == _FIXTURE["roots"]["program_root"]
    kernel.programs.require_application(
        review_status="accepted",
        application_status="pending",
        reviewed_currentness_root="current-root",
        currentness_root="current-root",
    )
    with pytest.raises(RSITransitionError, match="currentness root is stale"):
        kernel.programs.require_application(
            review_status="accepted",
            application_status="pending",
            reviewed_currentness_root="reviewed-root",
            currentness_root="changed-root",
        )

    lanes = [{"id": "lane-a"}, {"id": "lane-b"}]
    activated = kernel.portfolios.activate(
        mode="sequential",
        lanes=lanes,
        status="planned",
        baseline_currentness_root="root",
        currentness_root="root",
    )
    assert activated.active_lane_ids == ("lane-a",)
    assert activated.completed_lane_ids == ()
    assert activated.status == "active"

    advanced = kernel.portfolios.complete_lane(
        mode="sequential",
        lanes=lanes,
        status=activated.status,
        active_lane_ids=activated.active_lane_ids,
        completed_lane_ids=activated.completed_lane_ids,
        lane_id="lane-a",
        succeeded=True,
    )
    assert advanced.active_lane_ids == ("lane-b",)
    assert advanced.completed_lane_ids == ("lane-a",)
    assert advanced.status == "active"

    completed = kernel.portfolios.complete_lane(
        mode="sequential",
        lanes=lanes,
        status=advanced.status,
        active_lane_ids=advanced.active_lane_ids,
        completed_lane_ids=advanced.completed_lane_ids,
        lane_id="lane-b",
        succeeded=True,
    )
    assert completed.active_lane_ids == ()
    assert completed.completed_lane_ids == ("lane-a", "lane-b")
    assert completed.status == "completed"


def test_v020_review_selection_and_selector_policy_contract() -> None:
    kernel = RSIKernel()

    kernel.reviews.require_independent_actor(
        author_id="author-a", reviewer_id="reviewer-b", subject="candidate"
    )
    with pytest.raises(RSITransitionError, match="cannot independently review"):
        kernel.reviews.require_independent_actor(
            author_id="same-actor", reviewer_id="same-actor", subject="candidate"
        )

    review_root = kernel.selections.review_root(
        selection_id="selection-1",
        disposition="accepted",
        findings={"quality": "good"},
        evidence_ids=["eval-b", "eval-a", "eval-b"],
    )
    assert review_root == _FIXTURE["roots"]["selection_review_root"]
    kernel.selections.require_selectable(status="candidate", has_accepting_review=True)
    with pytest.raises(RSITransitionError, match="independent accepting review"):
        kernel.selections.require_selectable(status="candidate", has_accepting_review=False)

    selector_root = kernel.selector_policies.candidate_root({"policy": "v2", "threshold": 0.8})
    assert selector_root == _FIXTURE["roots"]["selector_candidate_root"]

    historical = kernel.selector_policies.evaluation_update(
        evaluation_type="historical", disposition="passed"
    )
    assert historical.status_field == "historical_status"
    assert historical.normalized_disposition == "passed"

    review = kernel.selector_policies.evaluation_update(
        evaluation_type="independent_review", disposition="passed"
    )
    assert review.status_field == "review_status"
    assert review.normalized_disposition == "accepted"

    kernel.selector_policies.require_activation(
        historical_status="passed", forward_status="passed", review_status="accepted"
    )
    with pytest.raises(RSITransitionError, match="historical, forward-shadow"):
        kernel.selector_policies.require_activation(
            historical_status="passed", forward_status="failed", review_status="accepted"
        )

    kernel.selector_policies.require_rollback(status="active", evidence_ids=["regression-1"])
    with pytest.raises(ValueError, match="rollback requires evidence"):
        kernel.selector_policies.require_rollback(status="active", evidence_ids=[])
