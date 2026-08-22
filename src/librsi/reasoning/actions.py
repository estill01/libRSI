"""Exact conversion between structured reasoning and runtime actions/results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..identity import thaw
from ..records import record_from_dict
from ..runtime import Action, ActionResult, Run, RuntimeFailure
from .records import ReasoningRequest, ReasoningResult

REASONING_ACTION_KIND = "reason"


def make_reasoning_action(
    *,
    run: Run,
    action_id: str,
    request: ReasoningRequest,
    attempt: int = 1,
    budget_reservation: Mapping[str, float] | None = None,
) -> Action:
    """Bind a reasoning request to one exact run and current target snapshot."""

    if not isinstance(run, Run):
        raise TypeError("reasoning actions require a Run")
    if not isinstance(request, ReasoningRequest):
        raise TypeError("reasoning actions require a ReasoningRequest")
    if request.target_snapshot != run.target_snapshot:
        raise ValueError("reasoning request target snapshot is stale or mismatched for the run")
    return Action(
        run=run.ref,
        action_id=action_id,
        kind=REASONING_ACTION_KIND,
        attempt=attempt,
        input_refs=(request.ref, *request.input_refs),
        payload={"request": request.to_dict()},
        budget_reservation=budget_reservation or {},
    )


def reasoning_request_from_action(action: Action) -> ReasoningRequest:
    """Decode and integrity-check the exact request carried by a reasoning Action."""

    if not isinstance(action, Action):
        raise TypeError("reasoning action decoding requires an Action")
    if action.kind != REASONING_ACTION_KIND:
        raise ValueError("action is not a structured reasoning action")
    if frozenset(action.payload) != {"request"}:
        raise ValueError("reasoning action payload must contain only its exact request")
    payload = action.payload["request"]
    if not isinstance(payload, Mapping):
        raise TypeError("reasoning action request payload must be a mapping")
    request = record_from_dict(thaw(payload))
    if not isinstance(request, ReasoningRequest):
        raise TypeError("reasoning action payload must decode to a ReasoningRequest")
    if action.input_refs != (request.ref, *request.input_refs):
        raise ValueError("reasoning action inputs do not match the exact request lineage")
    return request


def make_reasoning_action_result(
    *,
    action: Action,
    result: ReasoningResult,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    """Encode one validated proposal as a correlated successful ActionResult."""

    request = reasoning_request_from_action(action)
    if not isinstance(result, ReasoningResult):
        raise TypeError("reasoning action results require a ReasoningResult")
    if result.request.ref != request.ref or result.request != request:
        raise ValueError("reasoning result does not answer the exact dispatched request")
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(result.ref,),
        payload={"result": result.to_dict()},
        resource_usage=resource_usage or {},
    )


def make_reasoning_failure(
    *,
    action: Action,
    failure: RuntimeFailure,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    """Represent an execution failure without inventing an epistemic proposal."""

    reasoning_request_from_action(action)
    if not isinstance(failure, RuntimeFailure):
        raise TypeError("reasoning failures require a RuntimeFailure")
    return ActionResult(
        action=action,
        disposition="failed",
        resource_usage=resource_usage or {},
        failure=failure,
    )


def reasoning_result_from_action_result(action_result: ActionResult) -> ReasoningResult:
    """Decode a successful proposal and reject promotion or schema substitution."""

    if not isinstance(action_result, ActionResult):
        raise TypeError("reasoning result decoding requires an ActionResult")
    request = reasoning_request_from_action(action_result.action)
    if action_result.disposition != "succeeded":
        raise ValueError("failed reasoning actions do not contain proposals")
    if frozenset(action_result.payload) != {"result"}:
        raise ValueError("reasoning result payload must contain only its proposal")
    payload: Any = action_result.payload["result"]
    if not isinstance(payload, Mapping):
        raise TypeError("reasoning result payload must be a mapping")
    result = record_from_dict(thaw(payload))
    if not isinstance(result, ReasoningResult):
        raise TypeError("reasoning result payload must decode to a ReasoningResult")
    if result.request.ref != request.ref or result.request != request:
        raise ValueError("reasoning result does not answer the exact dispatched request")
    if action_result.output_refs != (result.ref,):
        raise ValueError("reasoning outputs may reference only the exact proposal record")
    return result
