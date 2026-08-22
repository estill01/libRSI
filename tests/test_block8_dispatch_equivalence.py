from __future__ import annotations

import pytest

from librsi import (
    Action,
    ActionResult,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilityRoute,
    Goal,
    RSICapabilityError,
    Run,
    RuntimeEngine,
    RuntimeFailure,
    serialize_record,
)


def _waiting(*kinds: str):
    run = Run(run_id="dispatch-equivalence", intent=Goal(statement="Dispatch exactly").ref)
    state = RuntimeEngine.start(run).state
    actions: list[Action] = []
    for index, kind in enumerate(kinds):
        action = Action(run=run.ref, action_id=f"action-{index}", kind=kind)
        actions.append(action)
        state = RuntimeEngine.request(state, action).state
    return state, tuple(actions)


class _DeterministicInspector:
    def __init__(self) -> None:
        self.calls: list[Action] = []

    def inspect(self, action: Action) -> ActionResult:
        self.calls.append(action)
        return ActionResult(
            action=action,
            disposition="succeeded",
            payload={"action_id": action.action_id},
        )


def test_managed_and_external_result_paths_produce_identical_state_and_event() -> None:
    waiting, actions = _waiting("inspect")
    implementation = _DeterministicInspector()
    managed = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("inspect", "inspector", "automatic"),),
            implementations=(implementation,),
        )
    )
    direct_result = implementation.inspect(actions[0])
    with pytest.raises(RSICapabilityError, match="resolved posture"):
        managed.submit(waiting, direct_result)
    with pytest.raises(TypeError, match="requires an ActionResult"):
        managed.submit(waiting, {"status": "succeeded"})  # type: ignore[arg-type]
    managed_batch = managed.advance(waiting)

    external = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("inspect", "inspector", "external"),),
        )
    )
    external_plan = external.next(waiting)
    assert external_plan.external_actions == actions
    external_update = external.submit(waiting, implementation.inspect(actions[0]))
    assert external_update.transition is not None

    assert serialize_record(managed_batch.state) == serialize_record(external_update.state)
    assert managed_batch.transitions == (external_update.transition,)
    assert managed_batch.results == (external_update.transition.event.result,)

    with pytest.raises(TypeError, match="requires a CapabilityRegistry"):
        CapabilityDispatcher("automatic")  # type: ignore[arg-type]


def test_hybrid_and_fully_automatic_frontiers_are_semantically_equivalent() -> None:
    waiting, actions = _waiting("automatic-inspect", "external-inspect")
    fully_managed_implementation = _DeterministicInspector()
    fully_managed = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(
                CapabilityRoute("automatic-inspect", "inspector", "automatic"),
                CapabilityRoute("external-inspect", "inspector", "automatic"),
            ),
            implementations=(fully_managed_implementation,),
        )
    ).advance(waiting)

    hybrid_implementation = _DeterministicInspector()
    hybrid_dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(
                CapabilityRoute("automatic-inspect", "inspector", "automatic"),
                CapabilityRoute("external-inspect", "inspector", "external"),
            ),
            implementations=(hybrid_implementation,),
        )
    )
    hybrid = hybrid_dispatcher.advance(waiting)
    assert hybrid.results[0].action == actions[0]
    assert hybrid.plan.external_actions == (actions[1],)
    external_result = hybrid_implementation.inspect(actions[1])
    external_update = hybrid_dispatcher.submit(hybrid.state, external_result)

    assert serialize_record(external_update.state) == serialize_record(fully_managed.state)
    assert tuple(item.action for item in fully_managed.results) == actions
    assert fully_managed.plan.resolutions == ()


def test_human_reserved_and_unavailable_actions_are_never_autoexecuted() -> None:
    waiting, actions = _waiting("human", "disabled", "missing")
    implementation = _DeterministicInspector()
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(
                CapabilityRoute("human", "inspector", "human-reserved"),
                CapabilityRoute("disabled", "inspector", "unavailable"),
            ),
            implementations=(implementation,),
        )
    )
    batch = dispatcher.advance(waiting)

    assert batch.state == waiting
    assert batch.transitions == ()
    assert batch.results == ()
    assert batch.plan.human_reserved_actions == (actions[0],)
    assert batch.plan.unavailable_actions == (actions[1], actions[2])
    assert implementation.calls == []

    human_result = implementation.inspect(actions[0])
    with pytest.raises(RSICapabilityError, match="resolved posture"):
        dispatcher.submit(waiting, human_result)
    human_update = dispatcher.submit(
        waiting,
        human_result,
        authority="human-reserved",
    )
    assert human_update.transition is not None

    unavailable_result = implementation.inspect(actions[1])
    with pytest.raises(RSICapabilityError, match="unavailable"):
        dispatcher.submit(waiting, unavailable_result)
    with pytest.raises(RSICapabilityError, match="authority is unsupported"):
        dispatcher.submit(waiting, human_result, authority="automatic")


class _WrongSchema:
    def inspect(self, action: Action) -> object:
        return {"action": action.root, "status": "succeeded"}


class _WrongAction:
    def __init__(self, run: Run) -> None:
        self._run = run

    def inspect(self, action: Action) -> ActionResult:
        return ActionResult(
            action=Action(run=self._run.ref, action_id="wrong", kind=action.kind),
            disposition="succeeded",
        )


class _Raises:
    def inspect(self, action: Action) -> ActionResult:
        raise RuntimeError("host failure")


@pytest.mark.parametrize("implementation", [_WrongSchema(), _Raises()])
def test_invalid_or_raised_automatic_results_fail_without_runtime_mutation(
    implementation: object,
) -> None:
    waiting, _ = _waiting("inspect")
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("inspect", "inspector", "automatic"),),
            implementations=(implementation,),
        )
    )
    with pytest.raises(RSICapabilityError):
        dispatcher.advance(waiting)
    assert waiting.results == ()
    assert waiting.pending_actions


def test_result_for_a_different_action_is_rejected_before_submission() -> None:
    waiting, _ = _waiting("inspect")
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("inspect", "inspector", "automatic"),),
            implementations=(_WrongAction(waiting.run),),
        )
    )
    with pytest.raises(RSICapabilityError, match="exact dispatched action"):
        dispatcher.advance(waiting)
    assert waiting.results == ()


class _TerminalInspector:
    def __init__(self) -> None:
        self.calls: list[Action] = []

    def inspect(self, action: Action) -> ActionResult:
        self.calls.append(action)
        if action.action_id == "action-0":
            return ActionResult(
                action=action,
                disposition="failed",
                failure=RuntimeFailure(
                    classification="execution",
                    message="terminal capability result",
                ),
            )
        return ActionResult(action=action, disposition="succeeded")


def test_terminal_result_stops_frontier_without_dispatching_cancelled_pending_work() -> None:
    waiting, actions = _waiting("inspect", "inspect")
    implementation = _TerminalInspector()
    batch = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("inspect", "inspector", "automatic"),),
            implementations=(implementation,),
        )
    ).advance(waiting)

    assert batch.state.status == "failed"
    assert batch.state.pending_actions == ()
    assert tuple(item.action for item in batch.results) == (actions[0],)
    assert implementation.calls == [actions[0]]
