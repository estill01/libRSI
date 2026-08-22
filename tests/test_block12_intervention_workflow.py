from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    ActionResult,
    InterventionProgress,
    InterventionWorkflow,
    RuntimeEngine,
    RuntimeFailure,
    make_implementation_failure,
    prepare_intervention,
    record_from_dict,
    serialize_record,
)
from tests.block12_support import FermenterImplementer, intervention_context


def test_absent_implementer_returns_complete_restartable_handoff() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    started = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    )

    assert started.progress.state.status == "waiting"
    assert started.progress.handoff is not None
    assert started.progress.handoff.request.intervention == context.intervention
    assert started.progress.handoff.authority == "candidate-only"
    assert len(started.transitions) == 2
    restored = record_from_dict(started.progress.state.to_dict())
    resumed = workflow.resume(
        context.intervention,
        restored,
        current_snapshot=context.baseline,
    )
    assert resumed.progress == started.progress
    assert resumed.transitions == ()
    assert (
        prepare_intervention(
            context.intervention,
            current_snapshot=context.baseline,
        )
        == started.progress
    )


def test_managed_and_external_preparation_complete_with_baseline_authority() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    managed_implementer = FermenterImplementer()
    managed = workflow.run_managed(
        waiting,
        implementer=managed_implementer,
        current_snapshot=context.baseline,
    )

    external_implementer = FermenterImplementer()
    external_envelope = external_implementer.implement(waiting.state.pending_actions[0])
    external = workflow.submit(
        waiting,
        external_envelope,
        current_snapshot=context.baseline,
    )

    assert managed.progress == external.progress
    assert managed.transitions == external.transitions
    assert managed_implementer.calls == [waiting.state.pending_actions[0]]
    assert managed.progress.state.status == "completed"
    assert managed.progress.result is not None
    assert managed.progress.result.candidate.snapshot == context.prospective
    assert managed.progress.result.authoritative_snapshot == context.baseline
    assert managed.progress.state.outcome is not None
    assert managed.progress.state.outcome.target_snapshot == context.baseline
    assert managed.progress.state.outcome.status == "candidate-prepared"
    assert managed.progress.state.outcome.next_actions == (
        "validate the prospective candidate before any application",
    )
    restored = record_from_dict(managed.progress.state.to_dict())
    resumed = workflow.resume(
        context.intervention,
        restored,
        current_snapshot=context.baseline,
    )
    assert serialize_record(resumed.progress.state) == serialize_record(managed.progress.state)
    assert resumed.transitions == ()


def test_stale_current_snapshot_fails_before_managed_provider_call() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    stale = replace(context.baseline, revision="batch-18")
    implementer = FermenterImplementer()

    with pytest.raises(ValueError, match="target snapshot is stale"):
        workflow.run_managed(
            waiting,
            implementer=implementer,
            current_snapshot=stale,
        )
    assert implementer.calls == []
    assert waiting.state.results == ()


def test_failed_implementation_terminates_without_candidate_or_application() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    action = waiting.state.pending_actions[0]
    failure = RuntimeFailure(
        classification="execution",
        message="Implementer refused the bounded request",
        retryable=False,
    )
    failed = workflow.submit(
        waiting,
        make_implementation_failure(action=action, failure=failure),
        current_snapshot=context.baseline,
    )

    assert failed.progress.state.status == "failed"
    assert failed.progress.failure_result is not None
    assert failed.progress.result is None
    assert failed.progress.state.outcome is not None
    assert failed.progress.state.outcome.target_snapshot == context.baseline
    assert failed.progress.state.outcome.unresolved == (failure.message,)


def test_forged_progress_and_persisted_frontier_drift_fail_closed() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    forged = object.__new__(InterventionProgress)
    object.__setattr__(forged, "intervention", waiting.intervention)
    object.__setattr__(forged, "current_snapshot", waiting.current_snapshot)
    object.__setattr__(forged, "state", waiting.state)
    object.__setattr__(forged, "handoff", None)
    object.__setattr__(forged, "result", None)
    object.__setattr__(forged, "failure_result", None)
    implementer = FermenterImplementer()

    with pytest.raises(ValueError, match="not the canonical persisted frontier"):
        workflow.run_managed(
            forged,
            implementer=implementer,
            current_snapshot=context.baseline,
        )
    assert implementer.calls == []
    drifted_action = replace(waiting.state.actions[0], action_id="forged-action")
    drifted_state = replace(
        waiting.state,
        actions=(drifted_action,),
        pending_actions=(drifted_action,),
    )
    with pytest.raises(ValueError, match="canonical runtime transition"):
        workflow.resume(
            context.intervention,
            drifted_state,
            current_snapshot=context.baseline,
        )
    with pytest.raises(ValueError, match="runtime actions must belong"):
        InterventionProgress(
            intervention=context.intervention,
            current_snapshot=context.baseline,
            state=replace(
                waiting.state,
                run=replace(waiting.state.run, run_id="other-run"),
            ),
        )


def test_terminal_settlement_binds_result_failure_status_and_outcome() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    original_failure = RuntimeFailure(
        classification="execution",
        message="original implementation failure",
    )
    failed = workflow.submit(
        waiting,
        make_implementation_failure(
            action=waiting.state.pending_actions[0],
            failure=original_failure,
        ),
        current_snapshot=context.baseline,
    ).progress
    assert failed.state.outcome is not None
    assert failed.failure_result is not None
    substituted_failure = RuntimeFailure(
        classification="execution",
        message="substituted implementation failure",
    )
    substituted_outcome = replace(
        failed.state.outcome,
        unresolved=(substituted_failure.message,),
        lineage=(failed.failure_result.ref, substituted_failure.ref),
    )
    substituted_state = replace(
        failed.state,
        failures=(substituted_failure,),
        outcome=substituted_outcome,
    )

    with pytest.raises(ValueError, match="canonical runtime transition"):
        InterventionProgress(
            intervention=context.intervention,
            current_snapshot=context.baseline,
            state=substituted_state,
            failure_result=failed.failure_result,
        )
    with pytest.raises(ValueError, match="canonical runtime transition"):
        workflow.resume(
            context.intervention,
            substituted_state,
            current_snapshot=context.baseline,
        )

    cancelled_outcome = replace(failed.state.outcome, status="cancelled")
    cancelled_state = replace(
        failed.state,
        status="cancelled",
        outcome=cancelled_outcome,
    )
    with pytest.raises(ValueError, match="canonical runtime transition"):
        workflow.resume(
            context.intervention,
            cancelled_state,
            current_snapshot=context.baseline,
        )


def test_exact_cancelled_result_produces_a_canonical_cancelled_settlement() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    cancellation = RuntimeFailure(
        classification="cancelled",
        message="Host cancelled candidate preparation",
    )
    cancelled = workflow.submit(
        waiting,
        ActionResult(
            action=waiting.state.pending_actions[0],
            disposition="cancelled",
            failure=cancellation,
        ),
        current_snapshot=context.baseline,
    ).progress

    assert cancelled.state.status == "cancelled"
    assert cancelled.failure_result is not None
    assert cancelled.failure_result.failure == cancellation
    assert cancelled.state.failures == (cancellation,)
    resumed = workflow.resume(
        context.intervention,
        cancelled.state,
        current_snapshot=context.baseline,
    )
    assert resumed.progress == cancelled
    assert resumed.transitions == ()


def test_retry_budget_failure_is_preserved_by_canonical_terminal_replay() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    retryable = RuntimeFailure(
        classification="execution",
        message="A transient-looking implementation failure",
        retryable=True,
    )
    failed = workflow.submit(
        waiting,
        make_implementation_failure(
            action=waiting.state.pending_actions[0],
            failure=retryable,
        ),
        current_snapshot=context.baseline,
    ).progress

    assert failed.state.status == "failed"
    assert failed.state.failures[0] == retryable
    assert failed.state.failures[1].classification == "budget-exhausted"
    assert failed.state.failures[1].message == "runtime retry budget is exhausted"
    resumed = workflow.resume(
        context.intervention,
        failed.state,
        current_snapshot=context.baseline,
    )
    assert resumed.progress == failed


def test_terminal_progress_replays_intervention_validation_before_acceptance() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    failure = RuntimeFailure(
        classification="execution",
        message="Malformed implementation failure",
    )
    malformed = ActionResult(
        action=waiting.state.pending_actions[0],
        disposition="failed",
        output_refs=(context.prospective.ref,),
        payload={"applied": True},
        failure=failure,
    )
    runtime_state = RuntimeEngine.submit(waiting.state, malformed).state

    with pytest.raises(ValueError, match="cannot contain candidate outputs"):
        InterventionProgress(
            intervention=context.intervention,
            current_snapshot=context.baseline,
            state=runtime_state,
            failure_result=malformed,
        )
    with pytest.raises(ValueError, match="cannot contain candidate outputs"):
        workflow.resume(
            context.intervention,
            runtime_state,
            current_snapshot=context.baseline,
        )


def test_every_waiting_and_completed_projection_requires_canonical_runtime_replay() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    phantom = RuntimeFailure(
        classification="internal",
        message="phantom failure outside the runtime history",
    )
    forged_waiting_state = replace(waiting.state, failures=(phantom,))

    with pytest.raises(ValueError, match="canonical runtime transition"):
        InterventionProgress(
            intervention=context.intervention,
            current_snapshot=context.baseline,
            state=forged_waiting_state,
            handoff=waiting.handoff,
        )
    with pytest.raises(ValueError, match="canonical runtime transition"):
        workflow.resume(
            context.intervention,
            forged_waiting_state,
            current_snapshot=context.baseline,
        )

    completed = workflow.run_managed(
        waiting,
        implementer=FermenterImplementer(),
        current_snapshot=context.baseline,
    ).progress
    forged_completed_state = replace(completed.state, failures=(phantom,))
    with pytest.raises(ValueError, match="canonical runtime transition"):
        InterventionProgress(
            intervention=context.intervention,
            current_snapshot=context.baseline,
            state=forged_completed_state,
            result=completed.result,
        )
    with pytest.raises(ValueError, match="canonical runtime transition"):
        workflow.resume(
            context.intervention,
            forged_completed_state,
            current_snapshot=context.baseline,
        )
