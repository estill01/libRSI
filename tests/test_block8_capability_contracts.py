from __future__ import annotations

import pytest

from librsi import (
    Action,
    ActionResult,
    Applier,
    CapabilityRegistry,
    CapabilityResolution,
    CapabilityRoute,
    DispatchBatch,
    DispatchPlan,
    Experimenter,
    Goal,
    Implementer,
    Inspector,
    Reasoner,
    Retriever,
    Reviewer,
    RSICapabilityError,
    Run,
    RuntimeEngine,
    Verifier,
)


def _waiting_state(kinds: tuple[str, ...]):
    run = Run(run_id="capability-contract", intent=Goal(statement="Route work").ref)
    state = RuntimeEngine.start(run).state
    actions: list[Action] = []
    for index, kind in enumerate(kinds):
        action = Action(
            run=run.ref,
            action_id=f"action-{index}",
            kind=kind,
        )
        actions.append(action)
        state = RuntimeEngine.request(state, action).state
    return state, tuple(actions)


class _AllCapabilities:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Action]] = []

    def _result(self, family: str, action: Action) -> ActionResult:
        self.calls.append((family, action))
        return ActionResult(action=action, disposition="succeeded", payload={"family": family})

    def inspect(self, action: Action) -> ActionResult:
        return self._result("inspector", action)

    def retrieve(self, action: Action) -> ActionResult:
        return self._result("retriever", action)

    def reason(self, action: Action) -> ActionResult:
        return self._result("reasoner", action)

    def experiment(self, action: Action) -> ActionResult:
        return self._result("experimenter", action)

    def implement(self, action: Action) -> ActionResult:
        return self._result("implementer", action)

    def review(self, action: Action) -> ActionResult:
        return self._result("reviewer", action)

    def apply(self, action: Action) -> ActionResult:
        return self._result("applier", action)

    def verify(self, action: Action) -> ActionResult:
        return self._result("verifier", action)


class _InspectorOnly:
    def inspect(self, action: Action) -> ActionResult:
        return ActionResult(action=action, disposition="succeeded")


def test_one_object_can_satisfy_every_granular_protocol() -> None:
    implementation = _AllCapabilities()
    assert isinstance(implementation, Inspector)
    assert isinstance(implementation, Retriever)
    assert isinstance(implementation, Reasoner)
    assert isinstance(implementation, Experimenter)
    assert isinstance(implementation, Implementer)
    assert isinstance(implementation, Reviewer)
    assert isinstance(implementation, Applier)
    assert isinstance(implementation, Verifier)

    state, actions = _waiting_state(("inspect", "retrieve", "reason"))
    registry = CapabilityRegistry(
        routes=(
            CapabilityRoute("inspect", "inspector", "automatic"),
            CapabilityRoute("retrieve", "retriever", "automatic"),
            CapabilityRoute("reason", "reasoner", "automatic"),
        ),
        implementations=(implementation, implementation),
    )
    resolutions = registry.plan(state).resolutions
    results = tuple(registry.execute(item) for item in resolutions)
    assert tuple(item.action for item in results) == actions
    assert [item[0] for item in implementation.calls] == [
        "inspector",
        "retriever",
        "reasoner",
    ]


def test_resolution_partitions_automatic_external_human_and_unavailable() -> None:
    implementation = _InspectorOnly()
    state, actions = _waiting_state(
        ("auto", "external", "human", "disabled", "missing-route", "missing-provider")
    )
    registry = CapabilityRegistry(
        routes=(
            CapabilityRoute("auto", "inspector", "automatic"),
            CapabilityRoute("external", "retriever", "external"),
            CapabilityRoute("human", "reasoner", "human-reserved"),
            CapabilityRoute("disabled", "experimenter", "unavailable"),
            CapabilityRoute("missing-provider", "verifier", "automatic"),
        ),
        implementations=(implementation,),
    )
    plan = registry.plan(state)

    assert plan.automatic_actions == (actions[0],)
    assert plan.external_actions == (actions[1],)
    assert plan.human_reserved_actions == (actions[2],)
    assert plan.unavailable_actions == (actions[3], actions[4], actions[5])
    assert plan.resolutions[3].reason == "capability is configured unavailable"
    assert plan.resolutions[4].route is None
    assert plan.resolutions[5].posture == "unavailable"


def test_registry_rejects_ambiguous_routes_providers_and_nonautomatic_execution() -> None:
    state, actions = _waiting_state(("inspect",))
    route = CapabilityRoute("inspect", "inspector", "automatic")
    with pytest.raises(ValueError, match="routes must be unique"):
        CapabilityRegistry(routes=(route, route))

    first = _AllCapabilities()
    second = _AllCapabilities()
    with pytest.raises(ValueError, match="ambiguous implementations"):
        CapabilityRegistry(routes=(route,), implementations=(first, second))

    external = CapabilityRegistry(
        routes=(CapabilityRoute("inspect", "inspector", "external"),),
        implementations=(first,),
    ).resolve(actions[0])
    with pytest.raises(RSICapabilityError, match="only resolved automatic"):
        CapabilityRegistry(implementations=(first,)).execute(external)

    assert state.pending_actions == actions


@pytest.mark.parametrize(
    "arguments",
    [
        ("", "inspector", "automatic"),
        ("inspect", "optimizer", "automatic"),
        ("inspect", "inspector", "managed"),
    ],
)
def test_capability_routes_reject_unknown_or_implicit_authority(
    arguments: tuple[str, str, str],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        CapabilityRoute(*arguments)


def test_resolution_requires_exact_action_kind_and_structured_unavailable_reason() -> None:
    state, actions = _waiting_state(("inspect",))
    with pytest.raises(ValueError, match="exact action kind"):
        CapabilityResolution(
            action=actions[0],
            route=CapabilityRoute("other", "inspector", "external"),
            posture="external",
        )
    with pytest.raises(ValueError, match="require a reason"):
        CapabilityResolution(
            action=actions[0],
            route=None,
            posture="unavailable",
        )
    assert state.pending_actions == actions


def test_dispatch_views_and_registry_inputs_fail_closed() -> None:
    state, actions = _waiting_state(("inspect",))
    route = CapabilityRoute("inspect", "inspector", "external")
    resolution = CapabilityResolution(
        action=actions[0],
        route=route,
        posture="external",
    )
    plan = DispatchPlan(state=state, resolutions=(resolution,))

    with pytest.raises(TypeError, match="must be text"):
        CapabilityRoute(7, "inspector", "external")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires an Action"):
        CapabilityResolution(
            action="inspect",  # type: ignore[arg-type]
            route=route,
            posture="external",
        )
    with pytest.raises(TypeError, match="route must be"):
        CapabilityResolution(
            action=actions[0],
            route="external",  # type: ignore[arg-type]
            posture="external",
        )
    with pytest.raises(ValueError, match="diverges from its route"):
        CapabilityResolution(action=actions[0], route=route, posture="automatic")
    with pytest.raises(TypeError, match="RunState"):
        DispatchPlan(state="waiting", resolutions=())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="CapabilityResolution"):
        DispatchPlan(state=state, resolutions=("external",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="every pending action"):
        DispatchPlan(state=state, resolutions=())
    with pytest.raises(ValueError, match="unsupported capability posture"):
        plan.actions_for("managed")

    result = ActionResult(action=actions[0], disposition="succeeded")
    with pytest.raises(ValueError, match="correlate exactly"):
        DispatchBatch(
            prior_state=state,
            state=state,
            transitions=(),
            results=(result,),
            plan=plan,
        )

    with pytest.raises(TypeError, match="routes must be a sequence"):
        CapabilityRegistry(routes="inspect")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="CapabilityRoute"):
        CapabilityRegistry(routes=("inspect",))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="implementations must be a sequence"):
        CapabilityRegistry(implementations="provider")  # type: ignore[arg-type]
    registry = CapabilityRegistry(routes=(route,))
    assert registry.routes == (route,)
    with pytest.raises(TypeError, match="requires an Action"):
        registry.resolve("inspect")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires a RunState"):
        registry.plan("waiting")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires a CapabilityResolution"):
        registry.execute("external")  # type: ignore[arg-type]
