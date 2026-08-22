from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from librsi import (
    Action,
    ActionResult,
    Evidence,
    Hypothesis,
    InvestigationEvidenceBatch,
    InvestigationFrontier,
    InvestigationPolicy,
    InvestigationRequest,
    InvestigationWorkflow,
    Outcome,
    Question,
    ReasoningResult,
    RuntimeFailure,
    SQLiteRuntimeStore,
    investigation_experiment_request_from_action,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action_result,
    make_reasoning_failure,
    persist_transitions,
    reasoning_request_from_action,
    record_from_dict,
)
from librsi.investigation.actions import _make_investigation_design_reasoning_action


def _request() -> InvestigationRequest:
    question = Question(prompt="Which seeded explanation survives?")
    hypotheses = tuple(
        Hypothesis(
            statement=f"Seeded explanation {index}",
            causal_model={"cause": index},
            predictions=({"signal": index},),
            source_refs=(question.ref,),
            status="proposed",
            lineage=(question.ref,),
        )
        for index in (1, 2)
    )
    return InvestigationRequest.for_question(
        investigation_id="persisted-investigation",
        question=question,
        initial_hypotheses=hypotheses,
        portfolio_mode="sequential",
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )


def _design_result(action: Action) -> ActionResult:
    request = reasoning_request_from_action(action)
    proposal = ReasoningResult.propose(
        request=request,
        content=make_investigation_observation_content(
            request,
            measurements=("signal",),
        ),
    )
    return make_reasoning_action_result(action=action, result=proposal)


def _experiment_result(action: Action) -> ActionResult:
    request = investigation_experiment_request_from_action(action)
    relationship = "counterexample" if request.branch.branch_id.endswith("1") else "support"
    evidence = tuple(
        Evidence(
            evidence_type=relationship,
            data={"sample": sample},
            subject_refs=(request.branch.hypothesis.ref,),
            source_refs=(request.experiment.ref,),
            weight=1.0,
        )
        for sample in (1, 2)
    )
    return make_investigation_experiment_result(
        action=action,
        batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
    )


def test_each_persisted_transition_resumes_to_the_same_frontier(tmp_path: Path) -> None:
    request = _request()
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    assert tuple(item.event.kind for item in started.transitions) == (
        "run_started",
        "action_requested",
    )

    with SQLiteRuntimeStore(tmp_path / "investigation-runtime.sqlite") as store:
        active = store.append(started.transitions[0])
        resumed_active = workflow.resume(request, active)
        assert resumed_active.progress == started.progress
        assert resumed_active.transitions == (started.transitions[1],)
        assert persist_transitions(store, resumed_active.transitions) == started.progress.state

        pending = store.resume(request.investigation_id)
        resumed_pending = workflow.resume(request, pending)
        assert resumed_pending.progress == started.progress
        assert resumed_pending.transitions == ()

        designed = workflow.submit(
            started.progress,
            _design_result(started.progress.state.pending_actions[0]),
        )
        assert tuple(item.event.kind for item in designed.transitions) == (
            "action_succeeded",
            "action_requested",
        )
        after_design = store.append(designed.transitions[0])
        resumed_design = workflow.resume(request, after_design)
        assert resumed_design.progress == designed.progress
        assert resumed_design.transitions == (designed.transitions[1],)
        persist_transitions(store, resumed_design.transitions)

        tested = workflow.submit(
            designed.progress,
            _experiment_result(designed.progress.state.pending_actions[0]),
        )
        persist_transitions(store, tested.transitions)

        current = tested
        while current.progress.result is None:
            action = current.progress.state.pending_actions[0]
            result = (
                _design_result(action)
                if action.kind == "investigation-reason"
                else _experiment_result(action)
            )
            current = workflow.submit(current.progress, result)
            persist_transitions(store, current.transitions)

        completed_state = store.resume(request.investigation_id)
        resumed_completed = workflow.resume(request, completed_state)
        assert resumed_completed.progress == current.progress
        assert resumed_completed.transitions == ()
        assert tuple(event.kind for event in store.events(request.investigation_id)) == (
            "run_started",
            "action_requested",
            "action_succeeded",
            "action_requested",
            "action_succeeded",
            "action_requested",
            "action_succeeded",
            "action_requested",
            "action_succeeded",
            "run_completed",
        )


def test_resume_rejects_action_and_outcome_drift() -> None:
    request = _request()
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    drifted_action = replace(action, action_id="investigation-design-hypothesis-2-1")
    drifted_state = replace(
        started.progress.state,
        actions=(drifted_action,),
        pending_actions=(drifted_action,),
    )
    with pytest.raises(ValueError, match="not policy-derived"):
        workflow.resume(request, drifted_state)

    current = workflow.submit(started.progress, _design_result(action))
    while current.progress.result is None:
        pending = current.progress.state.pending_actions[0]
        result = (
            _design_result(pending)
            if pending.kind == "investigation-reason"
            else _experiment_result(pending)
        )
        current = workflow.submit(current.progress, result)
    assert current.progress.state.outcome is not None
    narrative = replace(
        current.progress.state.outcome,
        conclusions=("Narrative asserted a different cause",),
    )
    with pytest.raises(ValueError, match="outcome has drifted"):
        workflow.resume(request, replace(current.progress.state, outcome=narrative))


def test_reasoning_failure_is_inconclusive_without_inventing_hypotheses() -> None:
    request = InvestigationRequest.for_question(
        investigation_id="generation-failure",
        question=Question(prompt="What is happening?"),
        max_hypotheses=2,
        max_experiments=2,
    )
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    failed = workflow.submit(
        started.progress,
        make_reasoning_failure(
            action=started.progress.state.pending_actions[0],
            failure=RuntimeFailure(
                classification="execution",
                message="reasoner unavailable",
            ),
        ),
    )

    assert failed.progress.result is not None
    assert failed.progress.result.disposition == "inconclusive"
    assert failed.progress.result.stop_reason == "runtime-failure"
    assert failed.progress.result.branches == ()
    assert failed.progress.result.findings == ()
    assert failed.progress.result.unresolved == ("hypothesis generation did not complete",)
    assert failed.progress.result.failure_result == failed.progress.state.results[-1]
    assert record_from_dict(failed.progress.result.to_dict()) == failed.progress.result
    assert failed.progress.state.status == "failed"
    assert failed.progress.state.outcome == Outcome(
        intent=request.question.ref,
        status="failed",
        unresolved=("reasoner unavailable",),
        lineage=(
            failed.progress.state.results[-1].ref,
            failed.progress.state.failures[-1].ref,
        ),
    )
    with pytest.raises(ValueError, match="competing hypothesis"):
        replace(failed.progress.result, failure_result=None)
    other_run = replace(request.canonical_run(), run_id="other-failure-run")
    drifted_action = replace(
        failed.progress.state.results[-1].action,
        run=other_run.ref,
    )
    drifted_failure = replace(
        failed.progress.state.results[-1],
        action=drifted_action,
    )
    with pytest.raises(ValueError, match="exact failed workflow result"):
        replace(failed.progress.result, failure_result=drifted_failure)


def test_runtime_failure_result_requires_the_complete_canonical_branch_settlement() -> None:
    request = _request()
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    failed = workflow.submit(
        started.progress,
        make_reasoning_failure(
            action=started.progress.state.pending_actions[0],
            failure=RuntimeFailure(
                classification="execution",
                message="design provider unavailable",
            ),
        ),
    )
    result = failed.progress.result
    assert result is not None
    assert len(result.branches) == 2
    assert all(branch.retired_reason == "runtime-failure" for branch in result.branches)

    with pytest.raises(ValueError, match="complete exact frontier"):
        replace(result, branches=result.branches[:-1])

    altered_branch = replace(result.branches[1], retired_reason="no-action")
    with pytest.raises(ValueError, match="complete exact frontier"):
        replace(result, branches=(result.branches[0], altered_branch))

    missing_roster = deepcopy(result.to_dict())
    missing_roster["data"]["branches"].pop()
    with pytest.raises(ValueError, match="complete exact frontier"):
        record_from_dict(missing_roster)

    altered_roster = deepcopy(result.to_dict())
    altered_roster["data"]["branches"][1] = altered_branch.to_dict()
    with pytest.raises(ValueError, match="complete exact frontier"):
        record_from_dict(altered_roster)


def test_runtime_failure_rejects_a_complete_but_nonpolicy_action_frontier() -> None:
    request = _request()
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    branches = started.progress.branches
    substituted_frontier = InvestigationFrontier.for_branch(
        investigation=request,
        branches=branches,
        selected_branch_id=branches[1].branch_id,
    )
    substituted_action = _make_investigation_design_reasoning_action(substituted_frontier)
    failure_result = make_reasoning_failure(
        action=substituted_action,
        failure=RuntimeFailure(
            classification="execution",
            message="substituted branch failed",
        ),
    )
    policy = InvestigationPolicy()
    settled = policy.settle(request, branches, reason="runtime-failure")

    with pytest.raises(ValueError, match="not policy-derived"):
        policy.build_result(
            investigation=request,
            branches=settled,
            failure_result=failure_result,
        )
