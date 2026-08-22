"""Exact action/result codecs for proposal-only goal operationalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..identity import thaw
from ..records import TargetSnapshot, record_from_dict
from ..runtime import Action, ActionResult, RunState, RuntimeFailure
from ..targets import TargetPolicy
from .policy import OperationalizationPolicy
from .records import (
    OPERATIONALIZE_GOAL_ACTION_KIND,
    OperationalizationProposal,
    OperationalizationRequest,
)


def make_operationalization_action(request: OperationalizationRequest) -> Action:
    if type(request) is not OperationalizationRequest:
        raise TypeError("operationalization actions require an OperationalizationRequest")
    return request.canonical_action()


def operationalization_request_from_action(action: Action) -> OperationalizationRequest:
    if not isinstance(action, Action):
        raise TypeError("operationalization action decoding requires an Action")
    payload = action.payload.get("request")
    if frozenset(action.payload) != {"request"} or not isinstance(payload, Mapping):
        raise ValueError("operationalization action must contain only its exact request")
    request = record_from_dict(thaw(payload))
    if not isinstance(request, OperationalizationRequest):
        raise TypeError("operationalization action must decode to an OperationalizationRequest")
    if action != request.canonical_action():
        raise ValueError("operationalization action is not canonically request-derived")
    return request


def make_operationalization_result(
    *,
    action: Action,
    proposal: OperationalizationProposal,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    request = operationalization_request_from_action(action)
    if type(proposal) is not OperationalizationProposal:
        raise TypeError("operationalization results require an OperationalizationProposal")
    decoded = record_from_dict(proposal.to_dict())
    if not isinstance(decoded, OperationalizationProposal) or decoded != proposal:
        raise ValueError("operationalization proposal must be canonical")
    if proposal.request != request:
        raise ValueError("operationalization proposal answers another request")
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(proposal.ref,),
        payload={"proposal": proposal.to_dict()},
        resource_usage={} if resource_usage is None else resource_usage,
    )


def make_operationalization_failure(
    *,
    action: Action,
    failure: RuntimeFailure,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    operationalization_request_from_action(action)
    if not isinstance(failure, RuntimeFailure):
        raise TypeError("operationalization failures require a RuntimeFailure")
    return ActionResult(
        action=action,
        disposition="failed",
        failure=failure,
        resource_usage={} if resource_usage is None else resource_usage,
    )


def operationalization_proposal_from_result(
    result: ActionResult,
) -> OperationalizationProposal:
    if not isinstance(result, ActionResult):
        raise TypeError("operationalization decoding requires an ActionResult")
    request = operationalization_request_from_action(result.action)
    if result.disposition != "succeeded":
        raise ValueError("failed operationalization actions do not contain proposals")
    payload: Any = result.payload.get("proposal")
    if frozenset(result.payload) != {"proposal"} or not isinstance(payload, Mapping):
        raise ValueError("operationalization result must contain only its exact proposal")
    proposal = record_from_dict(thaw(payload))
    if not isinstance(proposal, OperationalizationProposal):
        raise TypeError("operationalization result must decode to a proposal")
    if proposal.request != request:
        raise ValueError("operationalization proposal answers another request")
    if result.output_refs != (proposal.ref,):
        raise ValueError("operationalization output must cite only its exact proposal")
    return proposal


class OperationalizationResultValidator:
    """Nonreplaceable schema/currentness validation before runtime mutation."""

    action_kind = OPERATIONALIZE_GOAL_ACTION_KIND

    def require_current_frontier(
        self,
        state: RunState,
        action: Action,
        current_snapshot: TargetSnapshot | None,
    ) -> None:
        if not isinstance(state, RunState):
            raise TypeError("operationalization currentness requires a RunState")
        if not isinstance(action, Action):
            raise TypeError("operationalization currentness requires an Action")
        request = operationalization_request_from_action(action)
        if state.run != request.canonical_run():
            raise ValueError("operationalization request is stale or mismatched for the run")
        if action not in state.pending_actions and not any(
            item.action == action for item in state.results
        ):
            raise ValueError("operationalization action is not the exact pending frontier")
        if action not in state.pending_actions:
            return
        if type(current_snapshot) is not TargetSnapshot:
            raise ValueError("operationalization dispatch requires an explicit current snapshot")
        TargetPolicy().require_current(request.current_snapshot, current_snapshot)

    def validate(self, state: RunState, result: ActionResult) -> None:
        if not isinstance(state, RunState):
            raise TypeError("operationalization validation requires a RunState")
        if not isinstance(result, ActionResult):
            raise TypeError("operationalization validation requires an ActionResult")
        request = operationalization_request_from_action(result.action)
        if state.run != request.canonical_run():
            raise ValueError("operationalization request is stale or mismatched for the run")
        if result.action not in state.pending_actions and result not in state.results:
            raise ValueError("operationalization result is not for a pending action")
        if result.disposition == "succeeded":
            proposal = operationalization_proposal_from_result(result)
            OperationalizationPolicy().accept_proposal(request, proposal)
            return
        if result.output_refs or result.payload:
            raise ValueError("failed operationalization results cannot contain proposal outputs")
        if not isinstance(result.failure, RuntimeFailure):
            raise ValueError("failed operationalization results require a RuntimeFailure")
