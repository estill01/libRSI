from __future__ import annotations

import pytest

from librsi import (
    Action,
    ActionResult,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilityRoute,
    InterventionWorkflow,
    RSICapabilityError,
)
from tests.block12_support import FermenterImplementer, intervention_context


def _waiting():
    context = intervention_context()
    progress = (
        InterventionWorkflow()
        .start(
            context.intervention,
            current_snapshot=context.baseline,
        )
        .progress
    )
    return context, progress


def test_automatic_and_external_dispatch_share_the_exact_runtime_transition() -> None:
    context, waiting = _waiting()
    managed_implementer = FermenterImplementer()
    automatic = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("implement-intervention", "implementer", "automatic"),),
            implementations=(managed_implementer,),
        )
    ).advance(waiting.state, current_snapshot=context.baseline)

    external_implementer = FermenterImplementer()
    external_result = external_implementer.implement(waiting.state.pending_actions[0])
    external = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("implement-intervention", "implementer", "external"),)
        )
    ).submit(
        waiting.state,
        external_result,
        current_snapshot=context.baseline,
    )

    assert automatic.results == (external_result,)
    assert automatic.transitions == (external.transition,)
    assert automatic.state == external.state
    assert managed_implementer.calls == [waiting.state.pending_actions[0]]
    reconciled = InterventionWorkflow().resume(
        context.intervention,
        automatic.state,
        current_snapshot=context.baseline,
    )
    assert reconciled.progress.state.status == "completed"
    assert reconciled.progress.state.outcome is not None
    assert reconciled.progress.state.outcome.target_snapshot == context.baseline


def test_unavailable_implementer_remains_an_explicit_handoff_frontier() -> None:
    _, waiting = _waiting()
    dispatcher = CapabilityDispatcher(CapabilityRegistry())

    plan = dispatcher.next(waiting.state)
    assert plan.unavailable_actions == waiting.state.pending_actions
    assert plan.resolutions[0].reason == "no capability route is configured"
    batch = dispatcher.advance(waiting.state)
    assert batch.state == waiting.state
    assert batch.results == ()


def test_wrong_implementer_route_and_malformed_results_fail_before_mutation() -> None:
    context, waiting = _waiting()
    with pytest.raises(RSICapabilityError, match="exact implementer route"):
        CapabilityDispatcher(
            CapabilityRegistry(
                routes=(CapabilityRoute("implement-intervention", "applier", "external"),)
            )
        )

    class _NarrativeImplementer:
        def implement(self, action: Action) -> ActionResult:
            return ActionResult(
                action=action,
                disposition="succeeded",
                payload={"narrative": "The change was applied successfully"},
            )

    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("implement-intervention", "implementer", "automatic"),),
            implementations=(_NarrativeImplementer(),),
        )
    )
    with pytest.raises(ValueError, match="only its exact result"):
        dispatcher.advance(waiting.state, current_snapshot=context.baseline)
    assert waiting.state.results == ()
    assert waiting.state.pending_actions != ()


def test_host_validator_cannot_bypass_builtin_candidate_authority() -> None:
    context, waiting = _waiting()

    class _NoOpValidator:
        action_kind = "implement-intervention"

        def validate(self, state, result) -> None:
            return None

    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("implement-intervention", "implementer", "external"),),
            result_validators=(_NoOpValidator(),),
        )
    )
    malformed = ActionResult(
        action=waiting.state.pending_actions[0],
        disposition="succeeded",
        payload={"applied": True},
    )

    with pytest.raises(ValueError, match="only its exact result"):
        dispatcher.submit(
            waiting.state,
            malformed,
            current_snapshot=context.baseline,
        )
    assert waiting.state.results == ()


def test_dispatch_requires_live_currentness_before_calling_an_implementer() -> None:
    context, waiting = _waiting()
    implementer = FermenterImplementer()
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("implement-intervention", "implementer", "automatic"),),
            implementations=(implementer,),
        )
    )

    with pytest.raises(ValueError, match="explicit current snapshot"):
        dispatcher.advance(waiting.state)
    assert implementer.calls == []

    stale = type(context.baseline)(
        target=context.target,
        revision="batch-18",
        state=context.baseline.state,
    )
    with pytest.raises(ValueError, match="target snapshot is stale"):
        dispatcher.advance(waiting.state, current_snapshot=stale)
    assert implementer.calls == []
    assert waiting.state.results == ()
