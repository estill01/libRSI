from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from librsi import (
    Action,
    ActionResult,
    Claim,
    Evidence,
    RSITransitionError,
    RuntimeEngine,
    RuntimeFailure,
    SQLiteRuntimeStore,
    TargetPolicy,
    TargetRef,
    ValidationEvidenceBatch,
    ValidationEvidenceRequest,
    ValidationRequest,
    ValidationWorkflow,
    make_validation_evidence_action,
    make_validation_evidence_failure,
    make_validation_evidence_result,
    persist_transitions,
    validation_evidence_request_from_action,
)


def _process_context():
    policy = TargetPolicy()
    controller = TargetRef(target_id="controller", kind="configuration")
    vessel = TargetRef(target_id="vessel", kind="physical-system")
    process = policy.compose(
        target_id="heat-treatment-process",
        kind="synthetic-process",
        components=(
            policy.component(component_id="controller", target=controller),
            policy.component(component_id="vessel", target=vessel),
        ),
        locator={"site": "test-cell"},
    )
    snapshot = policy.snapshot(
        process,
        revision="cycle-8",
        state={"mode": "closed-loop"},
        components=(
            policy.snapshot(controller, state={"gain": 0.4}),
            policy.snapshot(vessel, state={"volume": 100.0}),
        ),
    )
    claim = Claim(
        statement="The heat-treatment cycle remains within its temperature bound",
        kind="invariant",
        target=process,
    )
    return snapshot, claim


class _ProcessExperimenter:
    def __init__(self, claim: Claim) -> None:
        self.claim = claim
        self.actions: list[Action] = []

    def experiment(self, action: Action) -> ActionResult:
        self.actions.append(action)
        request = validation_evidence_request_from_action(action)
        snapshot = request.validation.target_snapshot
        assert snapshot is not None
        evidence = tuple(
            Evidence(
                evidence_type="support",
                data={"cycle": cycle, "maximum_celsius": 43.0 + cycle / 10},
                subject_refs=(self.claim.ref,),
                source_refs=(request.ref,),
                target_snapshot=snapshot,
                weight=1.0,
            )
            for cycle in (1, 2)
        )
        batch = ValidationEvidenceBatch.collected(request=request, evidence=evidence)
        return make_validation_evidence_result(action=action, batch=batch)


def test_nonsoftware_validation_is_generic_and_requires_no_goal_or_intervention() -> None:
    snapshot, claim = _process_context()
    request = ValidationRequest.for_claim(
        validation_id="physical-process-validation",
        claim=claim,
        target_snapshot=snapshot,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    experimenter = _ProcessExperimenter(claim)
    completed = workflow.run_managed(started.progress, experimenter)

    assert completed.progress.result is not None
    assert completed.progress.result.disposition == "supported"
    assert completed.progress.state.run.intent.record_type == "claim"
    assert completed.progress.state.run.target_snapshot == snapshot
    assert completed.progress.state.outcome is not None
    assert completed.progress.state.outcome.intervention_refs == ()
    action = experimenter.actions[0]
    assert "repository" not in str(action.payload).lower()
    assert "git" not in str(action.payload).lower()


def test_pending_and_completed_validation_runs_persist_and_resume_exactly(
    tmp_path: Path,
) -> None:
    snapshot, claim = _process_context()
    request = ValidationRequest.for_claim(
        validation_id="persisted-validation",
        claim=claim,
        target_snapshot=snapshot,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    result = _ProcessExperimenter(claim).experiment(action)
    completed = workflow.submit(started.progress, result)

    with SQLiteRuntimeStore(tmp_path / "runtime.sqlite") as store:
        assert store.append(started.transitions[0]) == started.transitions[0].next_state
        active_start = store.resume(request.validation_id)
        assert active_start == started.transitions[0].next_state
        resumed_start = workflow.resume(request, active_start)
        assert resumed_start.progress == started.progress
        assert resumed_start.transitions == (started.transitions[1],)
        assert persist_transitions(store, resumed_start.transitions) == started.progress.state
        pending_state = store.resume(request.validation_id)
        assert pending_state == started.progress.state
        resumed_pending = workflow.resume(request, pending_state)
        assert resumed_pending.progress == started.progress
        assert resumed_pending.transitions == ()
        assert store.append(completed.transitions[0]) == completed.transitions[0].next_state
        active_result = store.resume(request.validation_id)
        assert active_result == completed.transitions[0].next_state
        resumed_result = workflow.resume(request, active_result)
        assert resumed_result.progress == completed.progress
        assert resumed_result.transitions == (completed.transitions[1],)
        assert persist_transitions(store, resumed_result.transitions) == completed.progress.state
        completed_state = store.resume(request.validation_id)
        assert completed_state == completed.progress.state
        resumed_completed = workflow.resume(request, completed_state)
        assert resumed_completed.progress == completed.progress
        assert resumed_completed.transitions == ()
        events = store.events(request.validation_id)

    assert tuple(event.kind for event in events) == (
        "run_started",
        "action_requested",
        "action_succeeded",
        "run_completed",
    )


def test_multi_frontier_resume_reconstructs_gathered_evidence_exactly() -> None:
    snapshot, claim = _process_context()
    request = ValidationRequest.for_claim(
        validation_id="resume-two-frontiers",
        claim=claim,
        target_snapshot=snapshot,
        max_evidence_actions=2,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    gap = validation_evidence_request_from_action(action)
    evidence = Evidence(
        evidence_type="support",
        data={"cycle": 1, "maximum_celsius": 43.1},
        subject_refs=(claim.ref,),
        source_refs=(gap.ref,),
        target_snapshot=snapshot,
        weight=1.0,
    )
    advanced = workflow.submit(
        started.progress,
        make_validation_evidence_result(
            action=action,
            batch=ValidationEvidenceBatch.collected(request=gap, evidence=(evidence,)),
        ),
    )

    assert advanced.progress.result is None
    resumed = workflow.resume(request, advanced.progress.state)
    assert resumed.progress == advanced.progress
    assert resumed.transitions == ()


def test_resume_rejects_request_drift_and_narrative_outcome_drift() -> None:
    snapshot, claim = _process_context()
    request = ValidationRequest.for_claim(
        validation_id="resume-integrity",
        claim=claim,
        target_snapshot=snapshot,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    other = ValidationRequest.for_claim(
        validation_id="other-validation",
        claim=claim,
        target_snapshot=snapshot,
    )
    other_gap = ValidationEvidenceRequest.for_gaps(
        validation=other,
        sequence=1,
        known_evidence_refs=(),
        gaps=("obtain current evidence",),
    )
    drifted_action = make_validation_evidence_action(
        run=started.progress.state.run,
        request=other_gap,
    )
    drifted_state = replace(
        started.progress.state,
        actions=(drifted_action,),
        pending_actions=(drifted_action,),
    )
    with pytest.raises(ValueError, match="drifted from its request"):
        workflow.resume(request, drifted_state)

    completed = workflow.submit(
        started.progress,
        _ProcessExperimenter(claim).experiment(started.progress.state.pending_actions[0]),
    )
    assert completed.progress.state.outcome is not None
    narrative_outcome = replace(
        completed.progress.state.outcome,
        conclusions=("A narrative asserted success",),
    )
    with pytest.raises(ValueError, match="outcome has drifted"):
        workflow.resume(
            request,
            replace(completed.progress.state, outcome=narrative_outcome),
        )


def test_resume_rejects_substituted_gap_and_terminal_unresolved_policy() -> None:
    snapshot, claim = _process_context()
    request = ValidationRequest.for_claim(
        validation_id="resume-policy-integrity",
        claim=claim,
        target_snapshot=snapshot,
    )
    workflow = ValidationWorkflow()
    active = RuntimeEngine.start(request.canonical_run()).state
    substituted_gap = ValidationEvidenceRequest.for_gaps(
        validation=request,
        sequence=1,
        known_evidence_refs=(),
        gaps=("generate and apply an intervention",),
    )
    substituted_action = make_validation_evidence_action(
        run=active.run,
        request=substituted_gap,
    )
    with pytest.raises(ValueError, match="not policy-derived"):
        workflow.resume(request, RuntimeEngine.request(active, substituted_action).state)

    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    gap = validation_evidence_request_from_action(action)
    one_sample = Evidence(
        evidence_type="support",
        data={"cycle": 1},
        subject_refs=(claim.ref,),
        source_refs=(gap.ref,),
        target_snapshot=snapshot,
        weight=1.0,
    )
    completed = workflow.submit(
        started.progress,
        make_validation_evidence_result(
            action=action,
            batch=ValidationEvidenceBatch.collected(
                request=gap,
                evidence=(one_sample,),
            ),
        ),
    )
    assert completed.progress.result is not None
    assert completed.progress.result.disposition == "inconclusive"
    assert completed.progress.state.outcome is not None
    substituted_outcome = replace(
        completed.progress.state.outcome,
        unresolved=("generate and apply an intervention",),
        next_actions=("generate and apply an intervention",),
    )
    with pytest.raises(ValueError, match="outcome has drifted"):
        workflow.resume(
            request,
            replace(completed.progress.state, outcome=substituted_outcome),
        )


def test_retry_budget_failure_resumes_with_authoritative_terminal_reason() -> None:
    snapshot, claim = _process_context()
    request = ValidationRequest.for_claim(
        validation_id="retry-budget",
        claim=claim,
        target_snapshot=snapshot,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    completed = workflow.submit(
        started.progress,
        make_validation_evidence_failure(
            action=action,
            failure=RuntimeFailure(
                classification="transient",
                message="instrument temporarily unavailable",
                retryable=True,
            ),
        ),
    )

    assert completed.progress.result is not None
    assert completed.progress.result.unresolved == ("runtime retry budget is exhausted",)
    resumed = workflow.resume(request, completed.progress.state)
    assert resumed.progress == completed.progress
    assert resumed.transitions == ()


def test_duplicate_submission_and_duplicate_action_ids_fail_closed() -> None:
    snapshot, claim = _process_context()
    request = ValidationRequest.for_claim(
        validation_id="duplicates",
        claim=claim,
        target_snapshot=snapshot,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    result = _ProcessExperimenter(claim).experiment(action)
    completed = workflow.submit(started.progress, result)

    with pytest.raises(ValueError, match="one pending"):
        workflow.submit(completed.progress, result)

    duplicate = Action(
        run=started.progress.state.run.ref,
        action_id=action.action_id,
        kind=action.kind,
    )
    with pytest.raises(RSITransitionError, match="already been issued"):
        RuntimeEngine.request(started.progress.state, duplicate)


def test_infrastructure_failure_is_inconclusive_not_counterevidence() -> None:
    snapshot, claim = _process_context()
    request = ValidationRequest.for_claim(
        validation_id="infrastructure-failure",
        claim=claim,
        target_snapshot=snapshot,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    failure = RuntimeFailure(
        classification="execution",
        message="instrument unavailable",
        retryable=False,
    )
    completed = workflow.submit(
        started.progress,
        make_validation_evidence_failure(action=action, failure=failure),
    )

    assert completed.progress.result is not None
    assert completed.progress.result.disposition == "inconclusive"
    assert completed.progress.belief.evidence_refs == ()
    assert completed.progress.state.status == "failed"
    assert completed.progress.result.unresolved == ("instrument unavailable",)
