from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Action,
    ActionResult,
    Event,
    Goal,
    Outcome,
    RecordRef,
    RSITransitionError,
    Run,
    RunBudget,
    RuntimeEngine,
    RuntimeFailure,
    RuntimeUpdate,
    TargetRef,
    TargetSnapshot,
    Transition,
)


def _run(*, budget: RunBudget | None = None, run_id: str = "run-1") -> Run:
    intent = Goal(statement="Validate the process")
    target = TargetRef(target_id="process", kind="simulation")
    return Run(
        run_id=run_id,
        intent=intent.ref,
        target_snapshot=TargetSnapshot(target=target, state={"value": 1}),
        budget=RunBudget() if budget is None else budget,
    )


def _action(run: Run, action_id: str = "inspect") -> Action:
    return Action(
        run=run.ref,
        action_id=action_id,
        kind="inspect",
        budget_reservation={"seconds": 1},
    )


def _applied(update: RuntimeUpdate):
    assert update.transition is not None
    assert update.duplicate is False
    return update.transition


def test_start_request_success_step_and_complete_are_pure_exact_transitions() -> None:
    run = _run()
    started = RuntimeEngine.start(run)
    start_transition = _applied(started)
    assert started.state.status == "active"
    assert start_transition.prior_state is None

    action = _action(run)
    requested = RuntimeEngine.request(started.state, action)
    request_transition = _applied(requested)
    assert RuntimeEngine.step(requested.state).actions == (action,)
    assert requested.state.status == "waiting"
    assert request_transition.event.previous_event == start_transition.event.ref

    result = ActionResult(
        action=action,
        disposition="succeeded",
        resource_usage={"seconds": 0.5},
    )
    submitted = RuntimeEngine.submit(requested.state, result)
    _applied(submitted)
    assert submitted.state.status == "active"
    assert submitted.state.pending_actions == ()
    assert submitted.state.results == (result,)
    assert submitted.state.resource_usage == {"seconds": 0.5}

    outcome = Outcome(
        intent=run.intent,
        status="validated",
        target_snapshot=run.target_snapshot,
    )
    completed = RuntimeEngine.complete(submitted.state, outcome)
    _applied(completed)
    step = RuntimeEngine.step(completed.state)
    assert step.terminal is True
    assert step.actions == ()
    assert step.outcome == outcome


def test_retry_is_emitted_not_executed_and_duplicate_submission_is_a_noop() -> None:
    run = _run(budget=RunBudget(max_actions=3, max_failures=3, max_retries=2))
    state = RuntimeEngine.request(RuntimeEngine.start(run).state, _action(run)).state
    failure = RuntimeFailure(
        classification="transient",
        message="temporary",
        retryable=True,
    )
    failed_result = ActionResult(
        action=state.pending_actions[0],
        disposition="failed",
        failure=failure,
    )
    failed = RuntimeEngine.submit(state, failed_result)
    transition = _applied(failed)
    retry = failed.state.pending_actions[0]

    assert transition.event.kind == "action_failed"
    assert transition.event.emitted_actions == (retry,)
    assert retry.action_id == "inspect"
    assert retry.attempt == 2
    assert failed.state.retry_count == 1
    assert RuntimeEngine.step(failed.state).actions == (retry,)

    duplicate = RuntimeEngine.submit(failed.state, failed_result)
    assert duplicate.duplicate is True
    assert duplicate.transition is None
    assert duplicate.state == failed.state

    divergent = replace(failed_result, payload={"different": True})
    with pytest.raises(RSITransitionError, match="divergent result"):
        RuntimeEngine.submit(failed.state, divergent)


def test_exact_result_submission_remains_idempotent_after_terminal_state() -> None:
    failed_run = _run(run_id="terminal-failed")
    waiting = RuntimeEngine.request(
        RuntimeEngine.start(failed_run).state,
        _action(failed_run),
    ).state
    failure = RuntimeFailure(classification="execution", message="terminal failure")
    failed_result = ActionResult(
        action=waiting.pending_actions[0],
        disposition="failed",
        failure=failure,
    )
    failed = RuntimeEngine.submit(waiting, failed_result)
    duplicate = RuntimeEngine.submit(failed.state, failed_result)
    assert duplicate == RuntimeUpdate(state=failed.state, transition=None, duplicate=True)

    cancelled_run = _run(run_id="terminal-cancelled")
    waiting = RuntimeEngine.request(
        RuntimeEngine.start(cancelled_run).state,
        _action(cancelled_run),
    ).state
    cancelled_failure = RuntimeFailure(classification="cancelled", message="cancelled")
    cancelled_result = ActionResult(
        action=waiting.pending_actions[0],
        disposition="cancelled",
        failure=cancelled_failure,
    )
    cancelled = RuntimeEngine.submit(waiting, cancelled_result)
    assert RuntimeEngine.submit(cancelled.state, cancelled_result).duplicate is True

    completed_run = _run(run_id="terminal-completed")
    waiting = RuntimeEngine.request(
        RuntimeEngine.start(completed_run).state,
        _action(completed_run),
    ).state
    succeeded_result = ActionResult(
        action=waiting.pending_actions[0],
        disposition="succeeded",
    )
    succeeded = RuntimeEngine.submit(waiting, succeeded_result)
    completed = RuntimeEngine.complete(
        succeeded.state,
        Outcome(
            intent=completed_run.intent,
            status="completed",
            target_snapshot=completed_run.target_snapshot,
        ),
    )
    assert RuntimeEngine.submit(completed.state, succeeded_result).duplicate is True

    unseen = ActionResult(action=_action(completed_run, "unseen"), disposition="succeeded")
    with pytest.raises(RSITransitionError, match="terminal runtime state"):
        RuntimeEngine.submit(completed.state, unseen)


def test_nonretryable_failure_and_cancellation_are_explicit_terminal_outcomes() -> None:
    run = _run()
    waiting = RuntimeEngine.request(RuntimeEngine.start(run).state, _action(run)).state
    failure = RuntimeFailure(
        classification="execution",
        message="experiment failed",
    )
    failed = RuntimeEngine.submit(
        waiting,
        ActionResult(action=waiting.pending_actions[0], disposition="failed", failure=failure),
    )
    assert failed.state.status == "failed"
    assert failed.state.outcome is not None
    assert failed.state.outcome.status == "failed"
    assert failed.state.pending_actions == ()

    other_run = _run(run_id="run-2")
    waiting = RuntimeEngine.request(
        RuntimeEngine.start(other_run).state,
        _action(other_run),
    ).state
    cancelled_failure = RuntimeFailure(
        classification="cancelled",
        message="operator cancelled",
    )
    cancelled = RuntimeEngine.submit(
        waiting,
        ActionResult(
            action=waiting.pending_actions[0],
            disposition="cancelled",
            failure=cancelled_failure,
        ),
    )
    assert cancelled.state.status == "cancelled"
    assert cancelled.state.outcome is not None
    assert cancelled.state.outcome.status == "cancelled"


def test_action_failure_and_retry_budgets_cannot_be_bypassed() -> None:
    action_limited = _run(budget=RunBudget(max_actions=0))
    with pytest.raises(RSITransitionError, match="action budget"):
        RuntimeEngine.request(RuntimeEngine.start(action_limited).state, _action(action_limited))

    retry_limited = _run(budget=RunBudget(max_actions=2, max_failures=2, max_retries=0))
    waiting = RuntimeEngine.request(
        RuntimeEngine.start(retry_limited).state,
        _action(retry_limited),
    ).state
    transient = RuntimeFailure(
        classification="transient",
        message="retry requested",
        retryable=True,
    )
    exhausted = RuntimeEngine.submit(
        waiting,
        ActionResult(
            action=waiting.pending_actions[0],
            disposition="failed",
            failure=transient,
        ),
    )
    assert exhausted.state.status == "failed"
    assert exhausted.state.failures[-1].classification == "budget-exhausted"

    failure_limited = _run(budget=RunBudget(max_actions=2, max_failures=0, max_retries=2))
    waiting = RuntimeEngine.request(
        RuntimeEngine.start(failure_limited).state,
        _action(failure_limited),
    ).state
    exhausted = RuntimeEngine.submit(
        waiting,
        ActionResult(
            action=waiting.pending_actions[0],
            disposition="failed",
            failure=transient,
        ),
    )
    assert exhausted.state.status == "failed"
    assert exhausted.state.failures[-1].classification == "budget-exhausted"


def test_resource_reservations_and_usage_are_bounded() -> None:
    run = _run(budget=RunBudget(resource_limits={"seconds": 1.0}))
    waiting = RuntimeEngine.request(RuntimeEngine.start(run).state, _action(run)).state

    with pytest.raises(RSITransitionError, match="resource budget"):
        RuntimeEngine.request(waiting, _action(run, "second"))
    with pytest.raises(RSITransitionError, match="resource budget"):
        RuntimeEngine.submit(
            waiting,
            ActionResult(
                action=waiting.pending_actions[0],
                disposition="succeeded",
                resource_usage={"seconds": 1.1},
            ),
        )
    assert waiting.pending_actions
    assert waiting.results == ()

    retry_run = _run(
        run_id="resource-retry",
        budget=RunBudget(
            max_actions=2,
            max_failures=2,
            max_retries=1,
            resource_limits={"seconds": 1.0},
        ),
    )
    retry_action = Action(
        run=retry_run.ref,
        action_id="bounded",
        kind="inspect",
        budget_reservation={"seconds": 0.75},
    )
    waiting = RuntimeEngine.request(RuntimeEngine.start(retry_run).state, retry_action).state
    exhausted = RuntimeEngine.submit(
        waiting,
        ActionResult(
            action=retry_action,
            disposition="failed",
            resource_usage={"seconds": 0.5},
            failure=RuntimeFailure(
                classification="transient",
                message="retry would exceed reservation",
                retryable=True,
            ),
        ),
    )
    assert exhausted.state.status == "failed"
    assert exhausted.state.failures[-1].classification == "budget-exhausted"
    assert exhausted.state.failures[-1].message == "runtime resource budget prevents retry"


def test_success_cannot_overcommit_usage_plus_other_pending_reservations() -> None:
    run = _run(
        run_id="multi-pending-budget",
        budget=RunBudget(resource_limits={"seconds": 10.0}),
    )
    started = RuntimeEngine.start(run)
    first_action = Action(
        run=run.ref,
        action_id="first",
        kind="inspect",
        budget_reservation={"seconds": 5.0},
    )
    first_requested = RuntimeEngine.request(started.state, first_action)
    second_action = Action(
        run=run.ref,
        action_id="second",
        kind="inspect",
        budget_reservation={"seconds": 5.0},
    )
    second_requested = RuntimeEngine.request(first_requested.state, second_action)

    with pytest.raises(RSITransitionError, match="resource budget"):
        RuntimeEngine.submit(
            second_requested.state,
            ActionResult(
                action=first_action,
                disposition="succeeded",
                resource_usage={"seconds": 8.0},
            ),
        )
    assert second_requested.state.resource_usage == {}
    assert second_requested.state.pending_actions == (first_action, second_action)

    accepted = RuntimeEngine.submit(
        second_requested.state,
        ActionResult(
            action=first_action,
            disposition="succeeded",
            resource_usage={"seconds": 5.0},
        ),
    )
    assert accepted.state.resource_usage == {"seconds": 5.0}
    assert accepted.state.pending_actions == (second_action,)
    transitions = tuple(
        update.transition for update in (started, first_requested, second_requested, accepted)
    )
    assert all(isinstance(item, Transition) for item in transitions)
    events = tuple(item.event for item in transitions if item is not None)
    assert RuntimeEngine.replay(run, events) == accepted.state


def test_wrong_stale_terminal_and_prose_transitions_fail_closed() -> None:
    run = _run()
    other = _run(run_id="run-other")
    started = RuntimeEngine.start(run).state
    waiting = RuntimeEngine.request(started, _action(run)).state

    with pytest.raises(RSITransitionError, match="different run"):
        RuntimeEngine.request(waiting, _action(other))
    with pytest.raises(RSITransitionError, match="stale or does not match"):
        RuntimeEngine.submit(
            waiting,
            ActionResult(action=_action(run, "other"), disposition="succeeded"),
        )
    with pytest.raises(RSITransitionError, match="while actions are pending"):
        RuntimeEngine.complete(waiting, Outcome(intent=run.intent, status="complete"))
    with pytest.raises(TypeError, match="RunState"):
        RuntimeEngine.step("complete the run")  # type: ignore[arg-type]

    failure = RuntimeFailure(classification="internal", message="terminal")
    terminal = RuntimeEngine.fail(waiting, failure).state
    with pytest.raises(RSITransitionError, match="terminal runtime state"):
        RuntimeEngine.request(terminal, _action(run, "late"))


def test_terminal_outcomes_require_the_exact_run_target_snapshot() -> None:
    run = _run(run_id="target-bound")
    started = RuntimeEngine.start(run).state
    wrong_target = TargetRef(target_id="other", kind="simulation")
    wrong_snapshot = TargetSnapshot(target=wrong_target, state={"value": 2})
    wrong_outcome = Outcome(
        intent=run.intent,
        status="completed",
        target_snapshot=wrong_snapshot,
    )
    with pytest.raises(RSITransitionError, match="target snapshot"):
        RuntimeEngine.complete(started, wrong_outcome)

    failure = RuntimeFailure(classification="execution", message="failed")
    with pytest.raises(RSITransitionError, match="target snapshot"):
        RuntimeEngine.fail(
            started,
            failure,
            Outcome(intent=run.intent, status="failed"),
        )

    cancelled = RuntimeFailure(classification="cancelled", message="cancelled")
    with pytest.raises(RSITransitionError, match="target snapshot"):
        RuntimeEngine.cancel(started, cancelled, wrong_outcome)

    unbound = Run(run_id="target-unbound", intent=run.intent)
    with pytest.raises(RSITransitionError, match="target snapshot"):
        RuntimeEngine.complete(
            RuntimeEngine.start(unbound).state,
            Outcome(
                intent=unbound.intent,
                status="completed",
                target_snapshot=run.target_snapshot,
            ),
        )


def test_replay_matches_every_transition_and_rejects_gaps_reordering_and_drift() -> None:
    run = _run()
    started = RuntimeEngine.start(run)
    requested = RuntimeEngine.request(started.state, _action(run))
    submitted = RuntimeEngine.submit(
        requested.state,
        ActionResult(action=requested.state.pending_actions[0], disposition="succeeded"),
    )
    outcome = Outcome(
        intent=run.intent,
        status="validated",
        target_snapshot=run.target_snapshot,
    )
    completed = RuntimeEngine.complete(submitted.state, outcome)
    events = tuple(_applied(update).event for update in (started, requested, submitted, completed))

    assert RuntimeEngine.replay(run, events) == completed.state
    with pytest.raises(RSITransitionError):
        RuntimeEngine.replay(run, (events[0], events[2], events[3]))
    with pytest.raises(RSITransitionError):
        RuntimeEngine.replay(run, (events[0], events[2], events[1], events[3]))

    drifted = Event(
        run=events[2].run,
        sequence=events[2].sequence,
        previous_event=RecordRef("event", "d" * 64),
        kind=events[2].kind,
        result=events[2].result,
    )
    with pytest.raises(RSITransitionError, match="gap, reordering, or drift"):
        RuntimeEngine.replay(run, (events[0], events[1], drifted))
