from __future__ import annotations

import pytest

from librsi import (
    Action,
    ActionResult,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilityRoute,
    Goal,
    KnowledgeWrite,
    Observation,
    Run,
    RuntimeEngine,
    TargetPolicy,
    TargetRef,
)


class _ProcessInspector:
    def __init__(self, observation: Observation) -> None:
        self.observation = observation
        self.calls: list[Action] = []

    def inspect(self, action: Action) -> ActionResult:
        self.calls.append(action)
        if action.input_refs != (self.observation.target_snapshot.ref,):
            raise ValueError("wrong process snapshot")
        return ActionResult(
            action=action,
            disposition="succeeded",
            output_refs=(self.observation.ref,),
            payload={"observation_kind": self.observation.kind},
        )


def test_inspector_capability_runs_against_the_nonsoftware_process_sentinel() -> None:
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
        revision="run-1",
        state={"mode": "closed-loop"},
        components=(
            policy.snapshot(controller, state={"gain": 0.4}),
            policy.snapshot(vessel, state={"volume": 100.0}),
        ),
    )
    observation = Observation(
        kind="temperature",
        value={"celsius": 42.0},
        target_snapshot=snapshot,
        source_refs=(snapshot.ref,),
    )
    implementation = _ProcessInspector(observation)
    run = Run(
        run_id="nonsoftware-capability",
        intent=Goal(statement="Inspect the heat-treatment process").ref,
        target_snapshot=snapshot,
    )
    started = RuntimeEngine.start(run).state
    action = Action(
        run=run.ref,
        action_id="inspect-process",
        kind="inspect-process",
        input_refs=(snapshot.ref,),
        payload={"measurement": "temperature"},
    )
    waiting = RuntimeEngine.request(started, action).state
    batch = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("inspect-process", "inspector", "automatic"),),
            implementations=(implementation,),
        )
    ).advance(waiting)

    assert batch.state.status == "active"
    assert batch.state.results[0].output_refs == (observation.ref,)
    assert batch.state.run.target_snapshot == snapshot
    assert implementation.calls == [action]
    assert "repository" not in action.payload
    assert "git" not in action.payload


class _FakeApplier:
    def __init__(self) -> None:
        self.calls: list[Action] = []

    def apply(self, action: Action) -> ActionResult:
        self.calls.append(action)
        return ActionResult(
            action=action,
            disposition="succeeded",
            payload={"proposal_applied": True},
        )


def test_capability_success_cannot_promote_knowledge_or_terminal_authority() -> None:
    run = Run(run_id="authority-boundary", intent=Goal(statement="Apply proposal").ref)
    action = Action(run=run.ref, action_id="apply", kind="apply-proposal")
    waiting = RuntimeEngine.request(RuntimeEngine.start(run).state, action).state
    implementation = _FakeApplier()
    batch = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("apply-proposal", "applier", "automatic"),),
            implementations=(implementation,),
        )
    ).advance(waiting)

    assert batch.state.status == "active"
    assert batch.state.outcome is None
    assert batch.state.results == batch.results
    assert implementation.calls == [action]
    with pytest.raises(ValueError, match="not knowledge state"):
        KnowledgeWrite(batch.results[0])


def test_human_reserved_applier_presence_never_grants_execution_authority() -> None:
    run = Run(run_id="human-authority", intent=Goal(statement="Reserve application").ref)
    action = Action(run=run.ref, action_id="apply", kind="apply-proposal")
    waiting = RuntimeEngine.request(RuntimeEngine.start(run).state, action).state
    implementation = _FakeApplier()
    batch = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("apply-proposal", "applier", "human-reserved"),),
            implementations=(implementation,),
        )
    ).advance(waiting)

    assert batch.state == waiting
    assert batch.plan.human_reserved_actions == (action,)
    assert implementation.calls == []
