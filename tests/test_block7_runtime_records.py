from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Action,
    ActionResult,
    Event,
    Goal,
    KnowledgeWrite,
    Outcome,
    RecordRef,
    Run,
    RunBudget,
    RunState,
    RuntimeFailure,
    TargetRef,
    TargetSnapshot,
    Transition,
    deserialize_record,
    serialize_record,
)


def _run(*, budget: RunBudget | None = None) -> Run:
    intent = Goal(statement="Validate the thermal simulation")
    target = TargetRef(target_id="thermal", kind="simulation")
    snapshot = TargetSnapshot(target=target, revision="v1", state={"gain": 0.4})
    return Run(
        run_id="run-1",
        intent=intent.ref,
        target_snapshot=snapshot,
        budget=RunBudget() if budget is None else budget,
    )


def _action(run: Run, *, attempt: int = 1) -> Action:
    return Action(
        run=run.ref,
        action_id="inspect",
        kind="inspect",
        attempt=attempt,
        payload={"region": "bounded"},
        budget_reservation={"seconds": 1},
    )


def test_runtime_records_round_trip_as_canonical_registered_types() -> None:
    run = _run()
    action = _action(run)
    failure = RuntimeFailure(
        classification="transient",
        message="temporary sensor miss",
        retryable=True,
    )
    result = ActionResult(
        action=action,
        disposition="failed",
        failure=failure,
        resource_usage={"seconds": 0.5},
    )
    event = Event(
        run=run.ref,
        sequence=1,
        previous_event=RecordRef("event", "a" * 64),
        kind="action_failed",
        result=result,
        emitted_actions=(
            Action(
                run=run.ref,
                action_id="inspect",
                kind="inspect",
                attempt=2,
                payload=action.payload,
                budget_reservation=action.budget_reservation,
                lineage=(action.ref, result.ref),
            ),
        ),
    )

    for record in (run.budget, run, action, failure, result, event):
        assert deserialize_record(serialize_record(record)) == record
        with pytest.raises(ValueError, match="not knowledge state"):
            KnowledgeWrite(record)


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        ({"max_actions": -1}, ValueError),
        ({"max_failures": True}, TypeError),
        ({"max_retries": -1}, ValueError),
        ({"resource_limits": {"seconds": -0.1}}, ValueError),
        ({"resource_limits": {"seconds": float("inf")}}, ValueError),
        ({"resource_limits": {"seconds": True}}, TypeError),
    ],
)
def test_run_budget_rejects_ambiguous_or_unbounded_values(
    arguments: dict[str, object],
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        RunBudget(**arguments)  # type: ignore[arg-type]


def test_run_action_result_and_failure_validation_fail_closed() -> None:
    run = _run()
    action = _action(run)
    failure = RuntimeFailure(
        classification="execution",
        message="failed",
    )

    with pytest.raises(TypeError, match="intent"):
        Run(run_id="bad", intent=run)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="reference a Run"):
        Action(
            run=run.intent,
            action_id="bad",
            kind="inspect",
        )
    with pytest.raises(ValueError, match="attempt must be positive"):
        _action(run, attempt=0)
    with pytest.raises(ValueError, match="unsupported runtime failure"):
        RuntimeFailure(classification="narrative", message="not authority")
    with pytest.raises(TypeError, match="retryable"):
        RuntimeFailure(
            classification="transient",
            message="bad bool",
            retryable=1,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="cannot contain a failure"):
        ActionResult(action=action, disposition="succeeded", failure=failure)
    with pytest.raises(ValueError, match="require a failure"):
        ActionResult(action=action, disposition="failed")
    with pytest.raises(ValueError, match="cancelled failure class"):
        ActionResult(
            action=action,
            disposition="cancelled",
            failure=failure,
        )
    with pytest.raises(ValueError, match="finite and nonnegative"):
        ActionResult(
            action=action,
            disposition="failed",
            failure=failure,
            resource_usage={"seconds": -1},
        )


def test_event_payload_and_chain_shape_are_exact() -> None:
    run = _run()
    action = _action(run)
    previous = RecordRef("event", "b" * 64)

    with pytest.raises(ValueError, match="initial.*predecessor"):
        Event(
            run=run.ref,
            sequence=0,
            previous_event=previous,
            kind="run_started",
        )
    with pytest.raises(ValueError, match="require an exact predecessor"):
        Event(run=run.ref, sequence=1, kind="action_requested", action=action)
    with pytest.raises(ValueError, match="payload does not match"):
        Event(
            run=run.ref,
            sequence=1,
            previous_event=previous,
            kind="action_requested",
            action=action,
        )
    with pytest.raises(ValueError, match="exact action"):
        Event(
            run=run.ref,
            sequence=1,
            previous_event=previous,
            kind="action_requested",
            action=action,
            emitted_actions=(Action(run=run.ref, action_id="other", kind="inspect"),),
        )


def test_run_state_and_transition_reject_incomplete_materializations() -> None:
    run = _run()
    start = Event(run=run.ref, sequence=0, kind="run_started")
    action = _action(run)
    request = Event(
        run=run.ref,
        sequence=1,
        previous_event=start.ref,
        kind="action_requested",
        action=action,
        emitted_actions=(action,),
    )
    waiting = RunState(
        run=run,
        status="waiting",
        sequence=1,
        last_event=request.ref,
        actions=(action,),
        pending_actions=(action,),
        action_count=1,
    )
    transition = Transition(
        prior_state=RecordRef("run_state", "c" * 64),
        event=request,
        next_state=waiting,
    )
    assert deserialize_record(serialize_record(transition)) == transition

    with pytest.raises(ValueError, match="action count"):
        RunState(
            run=run,
            status="waiting",
            sequence=1,
            last_event=request.ref,
            actions=(action,),
            pending_actions=(action,),
            action_count=0,
        )
    with pytest.raises(ValueError, match="terminal runtime states"):
        RunState(
            run=run,
            status="completed",
            sequence=1,
            last_event=request.ref,
            actions=(action,),
            pending_actions=(action,),
            action_count=1,
        )
    with pytest.raises(ValueError, match="sequence must match"):
        Transition(
            prior_state=waiting.ref,
            event=request,
            next_state=replace(waiting, sequence=2),
        )


def test_terminal_state_requires_explicit_canonical_outcome() -> None:
    run = _run()
    event = Event(run=run.ref, sequence=0, kind="run_started")
    outcome = Outcome(
        intent=run.intent,
        status="completed",
        target_snapshot=run.target_snapshot,
    )
    terminal_event = Event(
        run=run.ref,
        sequence=1,
        previous_event=event.ref,
        kind="run_completed",
        outcome=outcome,
    )
    state = RunState(
        run=run,
        status="completed",
        sequence=1,
        last_event=terminal_event.ref,
        outcome=outcome,
    )
    assert state.outcome == outcome
