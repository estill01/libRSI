from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Evidence,
    ExperimentSpec,
    Hypothesis,
    InvestigationEvidenceBatch,
    InvestigationExperimentRequest,
    InvestigationFinding,
    InvestigationPolicy,
    InvestigationRequest,
    Question,
    RecordRef,
    Run,
    RunBudget,
    TargetRef,
    TargetSnapshot,
    investigation_batch_from_action_result,
    investigation_experiment_request_from_action,
    make_investigation_experiment_action,
    make_investigation_experiment_result,
    record_from_dict,
)


def _context():
    target = TargetRef(target_id="investigation-target", kind="system")
    snapshot = TargetSnapshot(target=target, revision="r1", state={"mode": "stable"})
    question = Question(prompt="Which cause explains the response?", target=target)
    hypotheses = tuple(
        Hypothesis(
            statement=f"Cause {label} explains the response",
            target=target,
            causal_model={"cause": label},
            predictions=({"signal": label},),
            source_refs=(question.ref,),
            confidence=confidence,
            status="proposed",
            lineage=(question.ref,),
        )
        for label, confidence in (("A", 0.99), ("B", 0.01))
    )
    investigation = InvestigationRequest.for_question(
        investigation_id="record-contract",
        question=question,
        target_snapshot=snapshot,
        initial_hypotheses=hypotheses,
        portfolio_mode="sequential",
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    return target, snapshot, question, hypotheses, investigation


def _completed_branch(index: int, relationship: str):
    _, snapshot, _, hypotheses, investigation = _context()
    policy = InvestigationPolicy()
    branches = tuple(
        policy.initial_branch(
            investigation=investigation,
            branch_id=f"hypothesis-{position}",
            hypothesis=hypothesis,
        )
        for position, hypothesis in enumerate(hypotheses, start=1)
    )
    branch = branches[index - 1]
    experiment = ExperimentSpec(
        experiment_id=f"experiment-{index}",
        kind="investigation",
        target_snapshot=snapshot,
        design={"measure": "response"},
        criteria={"decisive": True},
        requested_measurements=("response",),
        lineage=(branch.hypothesis.ref,),
    )
    designed = policy.add_experiment(branch, experiment)
    roster = tuple(designed if item.branch_id == branch.branch_id else item for item in branches)
    request = InvestigationExperimentRequest.for_branch(
        branches=roster,
        branch=designed,
        sequence=index,
    )
    evidence = tuple(
        Evidence(
            evidence_type=relationship,
            data={"sample": sample},
            subject_refs=(designed.hypothesis.ref,),
            source_refs=(experiment.ref,),
            target_snapshot=snapshot,
            weight=1.0,
        )
        for sample in (1, 2)
    )
    batch = InvestigationEvidenceBatch.collected(request=request, evidence=evidence)
    return policy.apply_batch(designed, batch), request, batch


def test_request_binds_question_competing_hypotheses_and_runtime_budget() -> None:
    _, snapshot, question, hypotheses, investigation = _context()

    assert investigation.question == question
    assert investigation.initial_hypotheses == hypotheses
    assert investigation.canonical_run().budget.max_actions == 4
    assert record_from_dict(investigation.to_dict()) == investigation

    with pytest.raises(ValueError, match="competing hypotheses"):
        InvestigationRequest.for_question(
            investigation_id="one",
            question=question,
            target_snapshot=snapshot,
            initial_hypotheses=(hypotheses[0],),
        )
    with pytest.raises(ValueError, match="cite the exact question"):
        InvestigationRequest.for_question(
            investigation_id="wrong-source",
            question=question,
            target_snapshot=snapshot,
            initial_hypotheses=(
                replace(hypotheses[0], source_refs=()),
                hypotheses[1],
            ),
        )
    with pytest.raises(ValueError, match="unvalidated proposals"):
        InvestigationRequest.for_question(
            investigation_id="pre-promoted",
            question=question,
            target_snapshot=snapshot,
            initial_hypotheses=(
                replace(hypotheses[0], status="supported"),
                hypotheses[1],
            ),
        )


def test_proposal_confidence_is_not_initial_epistemic_authority() -> None:
    _, _, _, hypotheses, investigation = _context()
    policy = InvestigationPolicy()
    branches = tuple(
        policy.initial_branch(
            investigation=investigation,
            branch_id=f"hypothesis-{index}",
            hypothesis=hypothesis,
        )
        for index, hypothesis in enumerate(hypotheses, start=1)
    )

    assert tuple(item.hypothesis.confidence for item in branches) == (0.99, 0.01)
    assert tuple(item.belief.confidence for item in branches) == (0.5, 0.5)
    assert tuple(item.status for item in branches) == ("active", "active")


def test_experiment_action_and_batch_round_trip_exactly() -> None:
    branch, request, batch = _completed_branch(1, "support")
    action = make_investigation_experiment_action(
        run=request.investigation.canonical_run(),
        request=request,
    )
    result = make_investigation_experiment_result(action=action, batch=batch)

    assert investigation_experiment_request_from_action(action) == request
    assert investigation_batch_from_action_result(result) == batch
    assert record_from_dict(branch.to_dict()) == branch
    assert record_from_dict(batch.to_dict()) == batch

    with pytest.raises(ValueError, match="only its request"):
        investigation_experiment_request_from_action(
            replace(action, payload={"request": request.to_dict(), "narrative": "passed"})
        )
    with pytest.raises(ValueError, match="lineage has drifted"):
        investigation_experiment_request_from_action(replace(action, input_refs=()))
    with pytest.raises(ValueError, match="exact dispatched request"):
        other_request = _completed_branch(2, "support")[1]
        make_investigation_experiment_result(
            action=action,
            batch=InvestigationEvidenceBatch.unavailable(
                request=other_request,
                reason="unavailable",
            ),
        )
    with pytest.raises(ValueError, match="only its evidence batch"):
        investigation_batch_from_action_result(replace(result, payload={"narrative": "supported"}))


def test_branch_and_result_reject_evidence_leakage_and_synthesized_findings() -> None:
    supported, _, _ = _completed_branch(1, "support")
    rejected, _, _ = _completed_branch(2, "counterexample")
    policy = InvestigationPolicy()
    result = policy.build_result(
        investigation=supported.investigation,
        branches=(supported, rejected),
    )

    assert result.disposition == "answered"
    assert result.findings == (InvestigationFinding.from_branch(supported),)
    assert record_from_dict(result.to_dict()) == result

    leaked = replace(
        supported.evidence[0],
        subject_refs=(rejected.hypothesis.ref,),
    )
    with pytest.raises(ValueError, match="leaked between hypotheses"):
        replace(
            supported,
            evidence=(leaked, *supported.evidence[1:]),
            reused_evidence_refs=(),
            gathered_evidence_refs=(leaked.evidence_ref, supported.evidence[1].evidence_ref),
        )
    with pytest.raises(ValueError, match="cannot synthesize"):
        replace(result.findings[0], statement="A narrative answer")
    with pytest.raises(ValueError, match="canonical Run"):
        replace(result, run=Run(run_id="other", intent=result.investigation.question.ref).ref)
    with pytest.raises(ValueError, match="exact supported branches"):
        replace(result, findings=())
    with pytest.raises(ValueError, match="nonretired"):
        replace(supported, retired_reason="no-action")


def test_request_rejects_drifted_target_and_runtime_envelope() -> None:
    target, snapshot, question, hypotheses, investigation = _context()
    other = TargetRef(target_id="other", kind="system")
    with pytest.raises(ValueError, match="does not match the question"):
        InvestigationRequest.for_question(
            investigation_id="wrong-target",
            question=question,
            target_snapshot=TargetSnapshot(target=other, state={}),
            initial_hypotheses=hypotheses,
        )
    drifted = Run(
        run_id=investigation.investigation_id,
        intent=question.ref,
        target_snapshot=snapshot,
        budget=RunBudget(max_actions=99),
        lineage=(investigation.ref,),
    )
    assert drifted != investigation.canonical_run()
    assert target == snapshot.target
    assert RecordRef("question", question.root) == question.ref
