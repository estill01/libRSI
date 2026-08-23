"""Exact capability action codecs for application, verification, and rollback."""

from __future__ import annotations

from collections.abc import Mapping

from ..comparison import CandidateTrialBatch, ComparativeSelectionPolicy
from ..identity import thaw
from ..records import TargetSnapshot, record_from_dict
from ..runtime import Action, ActionResult, RunState, RuntimeFailure
from .records import (
    APPLICATION_ACTION_KINDS,
    APPLY_CANDIDATE_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
    ApplicationCommand,
    ApplicationReceipt,
    ApplicationRequest,
    ApplicationVerification,
    RollbackReceipt,
)


def make_apply_action(request: ApplicationRequest) -> Action:
    if type(request) is not ApplicationRequest or not request.apply:
        raise ValueError("apply actions require an enabled ApplicationRequest")
    command = ApplicationCommand.from_request(request)
    return Action(
        run=request.canonical_run().ref,
        action_id=f"{request.application_id}:apply",
        kind=APPLY_CANDIDATE_ACTION_KIND,
        input_refs=(
            request.ref,
            request.improvement.ref,
            request.handoff.ref,
            command.contract.ref,
            command.risk_policy.ref,
            command.candidate.ref,
            request.current_snapshot.ref,
            *((command.governance_authority,) if command.governance_authority is not None else ()),
        ),
        payload={"command": command.to_dict()},
        lineage=(
            request.ref,
            request.handoff.ref,
            command.contract.ref,
            command.risk_policy.ref,
            command.candidate.ref,
            *((command.governance_authority,) if command.governance_authority is not None else ()),
        ),
    )


def application_command_from_action(action: Action) -> ApplicationCommand:
    if type(action) is not Action:
        raise TypeError("application action decoding requires an Action")
    if action.kind != APPLY_CANDIDATE_ACTION_KIND:
        raise ValueError("action is not an apply-candidate action")
    if frozenset(action.payload) != {"command"}:
        raise ValueError("apply action must contain only its exact command")
    payload = action.payload["command"]
    if not isinstance(payload, Mapping):
        raise TypeError("application command payload must be a mapping")
    command = record_from_dict(thaw(payload))
    if type(command) is not ApplicationCommand:
        raise TypeError("apply payload must decode to an ApplicationCommand")
    expected = Action(
        run=action.run,
        action_id=f"{command.application_id}:apply",
        kind=APPLY_CANDIDATE_ACTION_KIND,
        input_refs=(
            command.request,
            command.improvement,
            command.handoff,
            command.contract.ref,
            command.risk_policy.ref,
            command.candidate.ref,
            command.prior_snapshot.ref,
            *((command.governance_authority,) if command.governance_authority is not None else ()),
        ),
        payload={"command": command.to_dict()},
        lineage=(
            command.request,
            command.handoff,
            command.contract.ref,
            command.risk_policy.ref,
            command.candidate.ref,
            *((command.governance_authority,) if command.governance_authority is not None else ()),
        ),
    )
    if action != expected:
        raise ValueError("apply action is not canonically command-derived")
    return command


def make_application_success(
    *,
    action: Action,
    produced_snapshot: TargetSnapshot,
) -> ActionResult:
    command = application_command_from_action(action)
    receipt = ApplicationReceipt(
        request=command.request,
        action=action,
        candidate=command.candidate,
        prior_snapshot=command.prior_snapshot,
        produced_snapshot=produced_snapshot,
        lineage=(
            command.request,
            action.ref,
            command.candidate.ref,
            command.prior_snapshot.ref,
            produced_snapshot.ref,
        ),
    )
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(receipt.ref, produced_snapshot.ref),
        payload={"receipt": receipt.to_dict()},
    )


def application_receipt_from_result(result: ActionResult) -> ApplicationReceipt:
    if type(result) is not ActionResult:
        raise TypeError("application receipt decoding requires an ActionResult")
    command = application_command_from_action(result.action)
    if result.disposition != "succeeded":
        raise ValueError("failed application actions do not contain a receipt")
    if frozenset(result.payload) != {"receipt"}:
        raise ValueError("application result must contain only its exact receipt")
    payload = result.payload["receipt"]
    if not isinstance(payload, Mapping):
        raise TypeError("application receipt payload must be a mapping")
    receipt = record_from_dict(thaw(payload))
    if type(receipt) is not ApplicationReceipt or receipt.request != command.request:
        raise ValueError("application receipt does not answer the exact request")
    if result.output_refs != (receipt.ref, receipt.produced_snapshot.ref):
        raise ValueError("application outputs must cite the exact receipt and produced state")
    return receipt


def make_verify_action(
    application: ApplicationReceipt,
) -> Action:
    if type(application) is not ApplicationReceipt:
        raise TypeError("verification actions require an ApplicationReceipt")
    command = application_command_from_action(application.action)
    return Action(
        run=application.action.run,
        action_id=f"{command.application_id}:verify",
        kind=VERIFY_APPLICATION_ACTION_KIND,
        input_refs=(
            application.request,
            application.ref,
            application.produced_snapshot.ref,
            command.improvement,
        ),
        payload={"application": application.to_dict()},
        lineage=(application.request, application.ref, application.produced_snapshot.ref),
    )


def verification_input_from_action(
    action: Action,
) -> ApplicationReceipt:
    if type(action) is not Action:
        raise TypeError("verification action decoding requires an Action")
    if action.kind != VERIFY_APPLICATION_ACTION_KIND:
        raise ValueError("action is not an application verification")
    if frozenset(action.payload) != {"application"}:
        raise ValueError("verification action must contain only its exact receipt")
    payload = action.payload["application"]
    if not isinstance(payload, Mapping):
        raise TypeError("verification receipt payload must be a mapping")
    application = record_from_dict(thaw(payload))
    if type(application) is not ApplicationReceipt:
        raise TypeError("verification payload contains the wrong record type")
    if action != make_verify_action(application):
        raise ValueError("verification action is not canonically receipt-derived")
    return application


def make_verification_result(
    *,
    action: Action,
    observed_snapshot: TargetSnapshot,
    batch: CandidateTrialBatch | None = None,
    operational_failure: RuntimeFailure | None = None,
) -> ActionResult:
    application = verification_input_from_action(action)
    command = application_command_from_action(application.action)
    if operational_failure is not None:
        if batch is not None:
            raise ValueError("unavailable verification cannot contain a trial batch")
        assessment = None
        disposition = "unavailable"
        reason = operational_failure.message
    else:
        if type(batch) is not CandidateTrialBatch:
            raise ValueError("conclusive verification requires a CandidateTrialBatch")
        assessment = ComparativeSelectionPolicy.assess(
            batch,
            risk_policy=command.risk_policy,
        )
        disposition = "verified" if assessment.disposition == "accepted" else "rejected"
        reason = "; ".join(assessment.reasons)
    verification = ApplicationVerification(
        request=application.request,
        application=application,
        action=action,
        observed_snapshot=observed_snapshot,
        disposition=disposition,
        reason=reason,
        assessment=assessment,
        operational_failure=operational_failure,
        lineage=(
            application.request,
            application.ref,
            action.ref,
            observed_snapshot.ref,
            *((assessment.ref,) if assessment is not None else ()),
            *((operational_failure.ref,) if operational_failure is not None else ()),
        ),
    )
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(verification.ref, observed_snapshot.ref),
        payload={"verification": verification.to_dict()},
    )


def verification_from_result(result: ActionResult) -> ApplicationVerification:
    if type(result) is not ActionResult:
        raise TypeError("verification decoding requires an ActionResult")
    application = verification_input_from_action(result.action)
    if result.disposition != "succeeded":
        raise ValueError("failed verifier envelopes cannot determine application validity")
    if frozenset(result.payload) != {"verification"}:
        raise ValueError("verification result must contain only its exact report")
    payload = result.payload["verification"]
    if not isinstance(payload, Mapping):
        raise TypeError("verification result payload must be a mapping")
    verification = record_from_dict(thaw(payload))
    if (
        type(verification) is not ApplicationVerification
        or verification.request != application.request
        or verification.application != application
    ):
        raise ValueError("verification report does not answer the exact application")
    if result.output_refs != (verification.ref, verification.observed_snapshot.ref):
        raise ValueError("verification outputs must cite the exact report and observed state")
    return verification


def make_rollback_action(
    application: ApplicationReceipt,
    verification: ApplicationVerification,
) -> Action:
    if type(application) is not ApplicationReceipt:
        raise TypeError("rollback actions require an ApplicationReceipt")
    if (
        type(verification) is not ApplicationVerification
        or verification.application != application
        or verification.disposition == "verified"
    ):
        raise ValueError("rollback actions require an exact nonverified report")
    command = application_command_from_action(application.action)
    return Action(
        run=application.action.run,
        action_id=f"{command.application_id}:rollback",
        kind=ROLLBACK_APPLICATION_ACTION_KIND,
        input_refs=(
            application.request,
            application.ref,
            verification.ref,
            application.prior_snapshot.ref,
        ),
        payload={"verification": verification.to_dict()},
        lineage=(application.request, application.ref, verification.ref),
    )


def rollback_input_from_action(
    action: Action,
) -> tuple[ApplicationReceipt, ApplicationVerification]:
    if type(action) is not Action:
        raise TypeError("rollback action decoding requires an Action")
    if action.kind != ROLLBACK_APPLICATION_ACTION_KIND:
        raise ValueError("action is not an application rollback")
    if frozenset(action.payload) != {"verification"}:
        raise ValueError("rollback action must contain only its exact verification report")
    payload = action.payload["verification"]
    if not isinstance(payload, Mapping):
        raise TypeError("rollback verification payload must be a mapping")
    verification = record_from_dict(thaw(payload))
    if (
        type(verification) is not ApplicationVerification
        or type(verification.application) is not ApplicationReceipt
    ):
        raise TypeError("rollback payload contains the wrong record type")
    application = verification.application
    if action != make_rollback_action(application, verification):
        raise ValueError("rollback action is not canonically verification-derived")
    return application, verification


def make_rollback_success(
    *,
    action: Action,
    restored_snapshot: TargetSnapshot,
) -> ActionResult:
    application, verification = rollback_input_from_action(action)
    receipt = RollbackReceipt(
        request=application.request,
        application=application,
        verification=verification,
        action=action,
        restored_snapshot=restored_snapshot,
        lineage=(
            application.request,
            application.ref,
            verification.ref,
            action.ref,
            restored_snapshot.ref,
        ),
    )
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(receipt.ref, restored_snapshot.ref),
        payload={"rollback": receipt.to_dict()},
    )


def rollback_receipt_from_result(result: ActionResult) -> RollbackReceipt:
    if type(result) is not ActionResult:
        raise TypeError("rollback decoding requires an ActionResult")
    application, verification = rollback_input_from_action(result.action)
    if result.disposition != "succeeded":
        raise ValueError("failed rollback actions do not contain a restoration receipt")
    if frozenset(result.payload) != {"rollback"}:
        raise ValueError("rollback result must contain only its exact receipt")
    payload = result.payload["rollback"]
    if not isinstance(payload, Mapping):
        raise TypeError("rollback result payload must be a mapping")
    receipt = record_from_dict(thaw(payload))
    if (
        type(receipt) is not RollbackReceipt
        or receipt.request != application.request
        or receipt.application != application
        or receipt.verification != verification
    ):
        raise ValueError("rollback receipt does not answer the exact request")
    if result.output_refs != (receipt.ref, receipt.restored_snapshot.ref):
        raise ValueError("rollback outputs must cite the exact receipt and restored state")
    return receipt


def make_application_failure(
    *,
    action: Action,
    failure: RuntimeFailure,
) -> ActionResult:
    if type(action) is not Action or action.kind not in APPLICATION_ACTION_KINDS:
        raise ValueError("application failures require an application lifecycle action")
    if action.kind == APPLY_CANDIDATE_ACTION_KIND:
        application_command_from_action(action)
    elif action.kind == VERIFY_APPLICATION_ACTION_KIND:
        verification_input_from_action(action)
    else:
        rollback_input_from_action(action)
    if type(failure) is not RuntimeFailure:
        raise TypeError("application failures require a RuntimeFailure")
    return ActionResult(action=action, disposition="failed", failure=failure)


class ApplicationActionResultValidator:
    """Validate every lifecycle action result before canonical runtime mutation."""

    action_kind = APPLY_CANDIDATE_ACTION_KIND

    def validate(self, state: RunState, result: ActionResult) -> None:
        if type(state) is not RunState:
            raise TypeError("application validation requires a RunState")
        if type(result) is not ActionResult:
            raise TypeError("application validation requires an ActionResult")
        if result.action not in state.pending_actions and result not in state.results:
            raise ValueError("application result is not for an exact pending action")
        if result.action.kind == APPLY_CANDIDATE_ACTION_KIND:
            command = application_command_from_action(result.action)
            if result.disposition == "succeeded":
                application_receipt_from_result(result)
        elif result.action.kind == VERIFY_APPLICATION_ACTION_KIND:
            application = verification_input_from_action(result.action)
            command = application_command_from_action(application.action)
            if result.disposition != "succeeded":
                raise ValueError(
                    "verifier infrastructure failures require a typed unavailable report"
                )
            verification_from_result(result)
        elif result.action.kind == ROLLBACK_APPLICATION_ACTION_KIND:
            application, _ = rollback_input_from_action(result.action)
            command = application_command_from_action(application.action)
            if result.disposition == "succeeded":
                rollback_receipt_from_result(result)
        else:
            raise ValueError("result is not an application lifecycle action")
        if state.run.ref != result.action.run or state.run.intent != command.request:
            raise ValueError("application action belongs to another canonical run")
        if result.disposition != "succeeded" and (
            result.output_refs or result.payload or type(result.failure) is not RuntimeFailure
        ):
            raise ValueError("failed application actions cannot contain semantic outputs")
