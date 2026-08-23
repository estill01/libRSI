"""Action codecs and host protocol for improvement cycles."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from ..identity import thaw
from ..records import record_from_dict
from ..runtime import Action, ActionResult, RuntimeFailure
from .records import IMPROVEMENT_ACTION_KIND, ImprovementCycleProposal, ImprovementCycleRequest


@runtime_checkable
class ImprovementCycleProvider(Protocol):
    """Host capability that investigates, prepares, and experiments for one cycle."""

    def resource_claim(self, action: Action) -> float: ...

    def improve_cycle(self, action: Action) -> ActionResult: ...


def cycle_request_from_action(action: Action) -> ImprovementCycleRequest:
    if not isinstance(action, Action) or action.kind != IMPROVEMENT_ACTION_KIND:
        raise ValueError("improvement cycle requires its reserved action kind")
    payload = action.payload.get("request")
    if frozenset(action.payload) != {"request"} or not isinstance(payload, Mapping):
        raise ValueError("improvement cycle action lost its request")
    record = record_from_dict(thaw(payload))
    if type(record) is not ImprovementCycleRequest:
        raise TypeError("improvement cycle action contains another record type")
    if action.input_refs != (record.ref, record.improvement.ref, record.directive.ref):
        raise ValueError("improvement cycle action inputs do not match its request")
    if (
        action.run != record.improvement.canonical_run().ref
        or action.action_id != f"{record.improvement.request_id}:cycle:{record.directive.iteration}"
        or action.budget_reservation != {"units": record.resource_units_per_attempt}
    ):
        raise ValueError("improvement cycle action is not the canonical resource frontier")
    if action.attempt == 1 and action.lineage != (
        record.improvement.ref,
        record.directive.ref,
    ):
        raise ValueError("initial improvement cycle action has noncanonical lineage")
    if action.attempt > 1 and (
        len(action.lineage) != 2
        or action.lineage[0].record_type != "action"
        or action.lineage[1].record_type != "action_result"
    ):
        raise ValueError("retried improvement cycle action lost runtime lineage")
    return record


def proposal_from_action_result(result: ActionResult) -> ImprovementCycleProposal:
    if not isinstance(result, ActionResult) or result.disposition != "succeeded":
        raise ValueError("improvement proposal requires a successful action result")
    request = cycle_request_from_action(result.action)
    payload = result.payload.get("proposal")
    if frozenset(result.payload) != {"proposal"} or not isinstance(payload, Mapping):
        raise ValueError("improvement action result lost its proposal")
    record = record_from_dict(thaw(payload))
    if type(record) is not ImprovementCycleProposal:
        raise TypeError("improvement action result contains another record type")
    if record.request != request or result.output_refs != (record.ref,):
        raise ValueError("improvement proposal does not answer the exact action")
    if (
        set(result.resource_usage) - {"units"}
        or result.resource_usage.get("units", 0.0) > request.resource_units_per_attempt
    ):
        raise ValueError("improvement result exceeds its authorized cycle resources")
    return record


def make_cycle_result(
    *, action: Action, proposal: ImprovementCycleProposal, resource_units: float = 0.0
) -> ActionResult:
    request = cycle_request_from_action(action)
    if proposal.request != request:
        raise ValueError("improvement proposal answers another cycle request")
    decoded = record_from_dict(proposal.to_dict())
    if decoded != proposal:
        raise ValueError("improvement proposal is not canonical")
    if (
        isinstance(resource_units, bool)
        or not isinstance(resource_units, (int, float))
        or float(resource_units) > request.resource_units_per_attempt
    ):
        raise ValueError("cycle resource usage exceeds its pre-authorized allowance")
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(proposal.ref,),
        payload={"proposal": proposal.to_dict()},
        resource_usage={"units": resource_units},
        lineage=(action.ref, proposal.ref),
    )


def make_cycle_failure(
    *,
    action: Action,
    message: str,
    retryable: bool = True,
    resource_units: float = 0.0,
) -> ActionResult:
    request = cycle_request_from_action(action)
    if (
        isinstance(resource_units, bool)
        or not isinstance(resource_units, (int, float))
        or float(resource_units) > request.resource_units_per_attempt
    ):
        raise ValueError("cycle failure resources exceed the pre-authorized allowance")
    failure = RuntimeFailure(
        classification="transient" if retryable else "execution",
        message=message,
        retryable=retryable,
        lineage=(action.ref,),
    )
    return ActionResult(
        action=action,
        disposition="failed",
        resource_usage={"units": resource_units},
        failure=failure,
        lineage=(action.ref, failure.ref),
    )


def validate_cycle_action_result(result: ActionResult) -> None:
    """Validate every disposition before any improvement runtime transition."""

    if not isinstance(result, ActionResult):
        raise TypeError("cycle result validation requires an ActionResult")
    request = cycle_request_from_action(result.action)
    if (
        set(result.resource_usage) - {"units"}
        or result.resource_usage.get("units", 0.0) > request.resource_units_per_attempt
    ):
        raise ValueError("cycle result resources exceed the authorized per-attempt cap")
    if result.disposition == "succeeded":
        proposal_from_action_result(result)
    elif result.output_refs or result.payload:
        raise ValueError("failed or cancelled cycle results cannot smuggle outputs or payloads")
