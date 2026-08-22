from __future__ import annotations

import pytest

from librsi import RSIKernel, TargetRef, TargetSnapshot


def _context():
    target = TargetRef(target_id="exactness", kind="software")
    snapshot = TargetSnapshot(target=target, revision="r1", state={"revision": "r1"})
    hypothesis = RSIKernel().hypotheses.create(
        target=target,
        statement="Exact command inputs affect the observed result",
        predictions=({"observable": "command output differs"},),
    )
    return hypothesis, snapshot


def test_canonical_command_preserves_exact_argv_and_cwd() -> None:
    hypothesis, snapshot = _context()
    policy = RSIKernel().experiments

    spec = policy.design_command(
        experiment_id="exact-command",
        hypothesis=hypothesis,
        target_snapshot=snapshot,
        design={"kind": "subprocess"},
        success_criteria={"accepted_exit_codes": [0]},
        command=["python", "  padded argument  ", ""],
        cwd="/workspace/trailing-space ",
    )
    execution = policy.prepare_command(spec)

    assert execution.command == ("python", "  padded argument  ", "")
    assert execution.cwd == "/workspace/trailing-space "
    assert spec.inputs["command"] == ("python", "  padded argument  ", "")
    assert spec.inputs["cwd"] == "/workspace/trailing-space "


def test_command_whitespace_is_identity_bearing_not_normalized_away() -> None:
    hypothesis, snapshot = _context()
    policy = RSIKernel().experiments
    common = {
        "experiment_id": "whitespace-identity",
        "hypothesis": hypothesis,
        "target_snapshot": snapshot,
        "design": {"kind": "subprocess"},
        "success_criteria": {"accepted_exit_codes": [0]},
    }

    padded = policy.design_command(
        **common,
        command=["python", "argument "],
        cwd="/workspace ",
    )
    plain = policy.design_command(
        **common,
        command=["python", "argument"],
        cwd="/workspace",
    )

    assert padded.root != plain.root
    assert policy.prepare_command(padded).command[1] == "argument "
    assert policy.prepare_command(padded).cwd == "/workspace "


def test_canonical_command_requires_a_nonempty_executable_but_allows_empty_arguments() -> None:
    hypothesis, snapshot = _context()
    policy = RSIKernel().experiments

    with pytest.raises(ValueError, match="executable"):
        policy.design_command(
            experiment_id="missing-executable",
            hypothesis=hypothesis,
            target_snapshot=snapshot,
            design={"kind": "subprocess"},
            success_criteria={"accepted_exit_codes": [0]},
            command=["", "argument"],
            cwd="/workspace",
        )

    spec = policy.design_command(
        experiment_id="empty-argument",
        hypothesis=hypothesis,
        target_snapshot=snapshot,
        design={"kind": "subprocess"},
        success_criteria={"accepted_exit_codes": [0]},
        command=["python", ""],
        cwd="/workspace",
    )
    assert policy.prepare_command(spec).command == ("python", "")


@pytest.mark.parametrize("criterion", ["stdout_contains", "stderr_not_contains"])
def test_command_criteria_reject_empty_string_predicates(criterion: str) -> None:
    hypothesis, snapshot = _context()

    with pytest.raises(ValueError, match="empty strings"):
        RSIKernel().experiments.design_command(
            experiment_id="degenerate-criterion",
            hypothesis=hypothesis,
            target_snapshot=snapshot,
            design={"kind": "subprocess"},
            success_criteria={"accepted_exit_codes": [0], criterion: [""]},
            command=["python"],
            cwd="/workspace",
        )


def test_canonical_hypothesis_rejects_empty_prediction_payloads() -> None:
    target = TargetRef(target_id="prediction", kind="software")

    with pytest.raises(ValueError, match="predictions cannot be empty"):
        RSIKernel().hypotheses.create(
            target=target,
            statement="An empty mapping is not an observable prediction",
            predictions=({},),
        )
