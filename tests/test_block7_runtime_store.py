from __future__ import annotations

from pathlib import Path

import pytest

from librsi import (
    Action,
    ActionResult,
    Event,
    Goal,
    Outcome,
    RSITransitionError,
    Run,
    RunBudget,
    RunState,
    RuntimeEngine,
    RuntimeFailure,
    RuntimeStore,
    SQLiteRuntimeStore,
    Transition,
    persist_transitions,
)


def _run(run_id: str = "run-store") -> Run:
    return Run(run_id=run_id, intent=Goal(statement="Persist an exact runtime").ref)


def _successful_trace(run: Run) -> tuple[Transition, ...]:
    started = RuntimeEngine.start(run)
    action = Action(run=run.ref, action_id="inspect", kind="inspect")
    requested = RuntimeEngine.request(started.state, action)
    submitted = RuntimeEngine.submit(
        requested.state,
        ActionResult(action=action, disposition="succeeded", payload={"value": 1}),
    )
    completed = RuntimeEngine.complete(
        submitted.state,
        Outcome(intent=run.intent, status="validated"),
    )
    transitions = tuple(update.transition for update in (started, requested, submitted, completed))
    assert all(isinstance(item, Transition) for item in transitions)
    return transitions  # type: ignore[return-value]


def test_sqlite_runtime_resumes_after_every_transition_and_reopen(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite"
    run = _run()
    expected_events: list[Event] = []
    expected_transitions: list[Transition] = []

    for transition in _successful_trace(run):
        with SQLiteRuntimeStore(database) as store:
            assert store.append(transition) == transition.next_state
        expected_events.append(transition.event)
        expected_transitions.append(transition)
        with SQLiteRuntimeStore(database) as reopened:
            assert reopened.schema_version == 1
            assert reopened.resume(run.run_id) == transition.next_state
            assert reopened.load(run.run_id) == transition.next_state
            assert reopened.events(run.run_id) == tuple(expected_events)
            assert reopened.transitions(run.run_id) == tuple(expected_transitions)


def test_exact_duplicate_transition_is_an_idempotent_noop(tmp_path: Path) -> None:
    run = _run()
    trace = _successful_trace(run)
    with SQLiteRuntimeStore(tmp_path / "duplicate.sqlite") as store:
        persist_transitions(store, trace)
        current = store.resume(run.run_id)
        assert store.append(trace[1]) == current
        assert store.append(trace[-1]) == current
        assert store.transitions(run.run_id) == trace


def test_retry_trace_persists_exact_actions_results_and_terminal_state() -> None:
    run = _run("run-retry")
    started = RuntimeEngine.start(run)
    requested = RuntimeEngine.request(
        started.state,
        Action(run=run.ref, action_id="measure", kind="measure"),
    )
    transient = RuntimeFailure(
        classification="transient",
        message="temporary miss",
        retryable=True,
    )
    failed = RuntimeEngine.submit(
        requested.state,
        ActionResult(
            action=requested.state.pending_actions[0],
            disposition="failed",
            failure=transient,
        ),
    )
    retry = failed.state.pending_actions[0]
    succeeded = RuntimeEngine.submit(
        failed.state,
        ActionResult(action=retry, disposition="succeeded"),
    )
    transitions = tuple(update.transition for update in (started, requested, failed, succeeded))
    assert all(isinstance(item, Transition) for item in transitions)

    with SQLiteRuntimeStore() as store:
        state = persist_transitions(
            store,
            transitions,  # type: ignore[arg-type]
        )
        assert state == succeeded.state
        assert state is not None
        assert state.actions == (requested.state.pending_actions[0], retry)
        assert state.results[-1].action == retry
        assert store.resume(run.run_id) == state


def test_multi_pending_budget_trace_replays_and_resumes_without_overcommit() -> None:
    run = Run(
        run_id="stored-multi-pending",
        intent=Goal(statement="Preserve pending reservations").ref,
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
    accepted = RuntimeEngine.submit(
        second_requested.state,
        ActionResult(
            action=first_action,
            disposition="succeeded",
            resource_usage={"seconds": 5.0},
        ),
    )
    transitions = tuple(
        update.transition for update in (started, first_requested, second_requested, accepted)
    )
    assert all(isinstance(item, Transition) for item in transitions)
    events = tuple(item.event for item in transitions if item is not None)
    assert RuntimeEngine.replay(run, events) == accepted.state

    with SQLiteRuntimeStore() as store:
        persisted = persist_transitions(store, transitions)  # type: ignore[arg-type]
        assert persisted == accepted.state
        assert store.resume(run.run_id) == accepted.state


def test_append_rejects_missing_prefix_skips_and_divergent_positions() -> None:
    run = _run()
    trace = _successful_trace(run)
    with SQLiteRuntimeStore() as store:
        with pytest.raises(RSITransitionError, match="begin at transition zero"):
            store.append(trace[1])
        store.append(trace[0])
        with pytest.raises(RSITransitionError, match="sequence is not append-only"):
            store.append(trace[2])

        alternative = RuntimeEngine.request(
            trace[0].next_state,
            Action(run=run.ref, action_id="alternative", kind="inspect"),
        ).transition
        assert alternative is not None
        store.append(trace[1])
        with pytest.raises(ValueError, match="divergent bytes or position"):
            store.append(alternative)


def test_store_isolates_runs_and_handles_missing_and_closed_state() -> None:
    first = _successful_trace(_run("first"))
    second = _successful_trace(_run("second"))
    store = SQLiteRuntimeStore()
    assert store.resume("missing") is None
    assert store.events("missing") == ()
    persist_transitions(store, first)
    persist_transitions(store, second)
    assert store.resume("first") == first[-1].next_state
    assert store.resume("second") == second[-1].next_state
    with pytest.raises(ValueError, match="run id is required"):
        store.resume("  ")
    store.close()
    with pytest.raises(RuntimeError, match="closed"):
        store.resume("first")


class _MemoryRuntimeStore:
    def __init__(self) -> None:
        self._items: list[Transition] = []

    def append(self, transition: Transition) -> RunState:
        self._items.append(transition)
        return transition.next_state

    def load(self, run_id: str) -> RunState | None:
        matches = [item.next_state for item in self._items if item.next_state.run.run_id == run_id]
        return None if not matches else matches[-1]

    def events(self, run_id: str) -> tuple[Event, ...]:
        return tuple(item.event for item in self._items if item.next_state.run.run_id == run_id)

    def transitions(self, run_id: str) -> tuple[Transition, ...]:
        return tuple(item for item in self._items if item.next_state.run.run_id == run_id)

    def resume(self, run_id: str) -> RunState | None:
        return self.load(run_id)

    def close(self) -> None:
        pass


def test_runtime_store_protocol_accepts_an_alternative_backend() -> None:
    run = _run("portable")
    store = _MemoryRuntimeStore()
    assert isinstance(store, RuntimeStore)
    assert persist_transitions(store, _successful_trace(run)) == store.resume(run.run_id)
