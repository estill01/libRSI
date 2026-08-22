"""Exact codecs for validation evidence-gap runtime actions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..identity import thaw
from ..records import record_from_dict
from ..runtime import Action, ActionResult, Run, RunState, RuntimeFailure
from .records import ValidationEvidenceBatch, ValidationEvidenceRequest

VALIDATION_EVIDENCE_ACTION_KIND = "validation-evidence"


def make_validation_evidence_action(*, run: Run, request: ValidationEvidenceRequest) -> Action:
    if not isinstance(run, Run):
        raise TypeError("validation evidence actions require a Run")
    if not isinstance(request, ValidationEvidenceRequest):
        raise TypeError("validation evidence actions require a ValidationEvidenceRequest")
    validation = request.validation
    if run.intent != validation.claim.ref or run.target_snapshot != validation.target_snapshot:
        raise ValueError("validation evidence request does not match the exact run")
    return Action(
        run=run.ref,
        action_id=f"validation-evidence-{request.sequence}",
        kind=VALIDATION_EVIDENCE_ACTION_KIND,
        input_refs=(request.ref, *request.lineage),
        payload={"request": request.to_dict()},
    )


def validation_evidence_request_from_action(action: Action) -> ValidationEvidenceRequest:
    if not isinstance(action, Action):
        raise TypeError("validation action decoding requires an Action")
    if action.kind != VALIDATION_EVIDENCE_ACTION_KIND:
        raise ValueError("action is not a validation evidence action")
    if frozenset(action.payload) != {"request"}:
        raise ValueError("validation action payload must contain only its exact request")
    payload = action.payload["request"]
    if not isinstance(payload, Mapping):
        raise TypeError("validation action request payload must be a mapping")
    request = record_from_dict(thaw(payload))
    if not isinstance(request, ValidationEvidenceRequest):
        raise TypeError("validation action payload must decode to a ValidationEvidenceRequest")
    if action.input_refs != (request.ref, *request.lineage):
        raise ValueError("validation action inputs do not match the exact request lineage")
    return request


def make_validation_evidence_result(
    *,
    action: Action,
    batch: ValidationEvidenceBatch,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    request = validation_evidence_request_from_action(action)
    if not isinstance(batch, ValidationEvidenceBatch):
        raise TypeError("validation action results require a ValidationEvidenceBatch")
    if batch.request.ref != request.ref or batch.request != request:
        raise ValueError("validation evidence does not answer the exact dispatched request")
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(batch.ref,),
        payload={"batch": batch.to_dict()},
        resource_usage=resource_usage or {},
    )


def make_validation_evidence_failure(
    *,
    action: Action,
    failure: RuntimeFailure,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    validation_evidence_request_from_action(action)
    if not isinstance(failure, RuntimeFailure):
        raise TypeError("validation evidence failures require a RuntimeFailure")
    return ActionResult(
        action=action,
        disposition="failed",
        resource_usage=resource_usage or {},
        failure=failure,
    )


def validation_batch_from_action_result(
    action_result: ActionResult,
) -> ValidationEvidenceBatch:
    if not isinstance(action_result, ActionResult):
        raise TypeError("validation result decoding requires an ActionResult")
    request = validation_evidence_request_from_action(action_result.action)
    if action_result.disposition != "succeeded":
        raise ValueError("failed validation evidence actions do not contain a batch")
    if frozenset(action_result.payload) != {"batch"}:
        raise ValueError("validation result payload must contain only its evidence batch")
    payload: Any = action_result.payload["batch"]
    if not isinstance(payload, Mapping):
        raise TypeError("validation evidence batch payload must be a mapping")
    batch = record_from_dict(thaw(payload))
    if not isinstance(batch, ValidationEvidenceBatch):
        raise TypeError("validation result payload must decode to a ValidationEvidenceBatch")
    if batch.request.ref != request.ref or batch.request != request:
        raise ValueError("validation evidence does not answer the exact dispatched request")
    if action_result.output_refs != (batch.ref,):
        raise ValueError("validation outputs may reference only the exact evidence batch")
    return batch


class ValidationEvidenceResultValidator:
    """Non-authoritative schema/currentness validation before runtime mutation."""

    action_kind = VALIDATION_EVIDENCE_ACTION_KIND

    def validate(self, state: RunState, result: ActionResult) -> None:
        if not isinstance(state, RunState):
            raise TypeError("validation evidence validation requires a RunState")
        if not isinstance(result, ActionResult):
            raise TypeError("validation evidence validation requires an ActionResult")
        request = validation_evidence_request_from_action(result.action)
        validation = request.validation
        if (
            state.run.intent != validation.claim.ref
            or state.run.target_snapshot != validation.target_snapshot
        ):
            raise ValueError("validation evidence request is stale or mismatched for the run")
        if result.disposition == "succeeded":
            validation_batch_from_action_result(result)
        elif result.output_refs or result.payload:
            raise ValueError("failed validation evidence results cannot contain batch outputs")
