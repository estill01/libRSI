"""Exact Implementer action codecs for candidate-only preparation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..identity import thaw
from ..records import TargetSnapshot, record_from_dict
from ..runtime import Action, ActionResult, RunState, RuntimeFailure
from ..targets import TargetPolicy
from .records import (
    IMPLEMENT_INTERVENTION_ACTION_KIND,
    ImplementationHandoff,
    ImplementationResult,
    InterventionImplementationRequest,
)


def make_implementation_action(request: InterventionImplementationRequest) -> Action:
    if not isinstance(request, InterventionImplementationRequest):
        raise TypeError("implementation actions require an InterventionImplementationRequest")
    return request.canonical_action()


def implementation_request_from_action(action: Action) -> InterventionImplementationRequest:
    if not isinstance(action, Action):
        raise TypeError("implementation action decoding requires an Action")
    if action.kind != IMPLEMENT_INTERVENTION_ACTION_KIND:
        raise ValueError("action is not an intervention implementation")
    if frozenset(action.payload) != {"request"}:
        raise ValueError("implementation action must contain only its exact request")
    payload = action.payload["request"]
    if not isinstance(payload, Mapping):
        raise TypeError("implementation request payload must be a mapping")
    request = record_from_dict(thaw(payload))
    if not isinstance(request, InterventionImplementationRequest):
        raise TypeError(
            "implementation payload must decode to an InterventionImplementationRequest"
        )
    expected = make_implementation_action(request)
    if action != expected:
        raise ValueError("implementation action is not canonically request-derived")
    return request


def make_implementation_result(
    *,
    action: Action,
    result: ImplementationResult,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    request = implementation_request_from_action(action)
    if not isinstance(result, ImplementationResult):
        raise TypeError("implementation action results require an ImplementationResult")
    decoded = record_from_dict(result.to_dict())
    if not isinstance(decoded, ImplementationResult) or decoded != result:
        raise ValueError("implementation result must be a canonical validated record")
    if result.request != request:
        raise ValueError("implementation result does not answer the exact dispatched request")
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(result.ref, result.candidate.ref),
        payload={"result": result.to_dict()},
        resource_usage=resource_usage or {},
    )


def make_implementation_failure(
    *,
    action: Action,
    failure: RuntimeFailure,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    implementation_request_from_action(action)
    if not isinstance(failure, RuntimeFailure):
        raise TypeError("implementation failures require a RuntimeFailure")
    return ActionResult(
        action=action,
        disposition="failed",
        failure=failure,
        resource_usage=resource_usage or {},
    )


def implementation_result_from_action_result(
    action_result: ActionResult,
) -> ImplementationResult:
    if not isinstance(action_result, ActionResult):
        raise TypeError("implementation result decoding requires an ActionResult")
    request = implementation_request_from_action(action_result.action)
    if action_result.disposition != "succeeded":
        raise ValueError("failed implementation actions do not contain a candidate result")
    if frozenset(action_result.payload) != {"result"}:
        raise ValueError("implementation result payload must contain only its exact result")
    payload: Any = action_result.payload["result"]
    if not isinstance(payload, Mapping):
        raise TypeError("implementation result payload must be a mapping")
    result = record_from_dict(thaw(payload))
    if not isinstance(result, ImplementationResult):
        raise TypeError("implementation payload must decode to an ImplementationResult")
    if result.request != request:
        raise ValueError("implementation result does not answer the exact dispatched request")
    if action_result.output_refs != (result.ref, result.candidate.ref):
        raise ValueError("implementation outputs must cite the exact result and candidate")
    return result


def make_implementation_handoff(
    request: InterventionImplementationRequest,
) -> ImplementationHandoff:
    action = make_implementation_action(request)
    return ImplementationHandoff(
        request=request,
        action=action,
        lineage=(
            request.ref,
            action.ref,
            request.intervention.ref,
            request.intervention.baseline.ref,
        ),
    )


class ImplementationResultValidator:
    """Nonreplaceable candidate/currentness validation before runtime mutation."""

    action_kind = IMPLEMENT_INTERVENTION_ACTION_KIND

    def require_current_frontier(
        self,
        state: RunState,
        action: Action,
        current_snapshot: TargetSnapshot | None,
    ) -> None:
        """Fail closed on stale or unobserved targets before an Implementer runs."""

        if not isinstance(state, RunState):
            raise TypeError("implementation currentness requires a RunState")
        if not isinstance(action, Action):
            raise TypeError("implementation currentness requires an Action")
        if not isinstance(current_snapshot, TargetSnapshot):
            raise ValueError("implementation dispatch requires an explicit current snapshot")
        request = implementation_request_from_action(action)
        if state.run != request.intervention.canonical_run():
            raise ValueError("implementation request is stale or mismatched for the run")
        if action not in state.pending_actions:
            raise ValueError("implementation action is not the exact pending frontier")
        TargetPolicy().require_current(request.intervention.baseline, current_snapshot)

    def validate(self, state: RunState, result: ActionResult) -> None:
        if not isinstance(state, RunState):
            raise TypeError("implementation validation requires a RunState")
        if not isinstance(result, ActionResult):
            raise TypeError("implementation validation requires an ActionResult")
        request = implementation_request_from_action(result.action)
        if state.run != request.intervention.canonical_run():
            raise ValueError("implementation request is stale or mismatched for the run")
        if result.action not in state.pending_actions and result not in state.results:
            raise ValueError("implementation result is not for a pending action")
        if result.disposition == "succeeded":
            implementation_result_from_action_result(result)
            return
        if result.output_refs or result.payload:
            raise ValueError("failed implementation results cannot contain candidate outputs")
        if not isinstance(result.failure, RuntimeFailure):
            raise ValueError("failed implementation results require a RuntimeFailure")
