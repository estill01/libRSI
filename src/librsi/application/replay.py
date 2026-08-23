"""Single canonical replay and result-projection authority for application."""

from __future__ import annotations

from dataclasses import dataclass

from ..records import Outcome, TargetSnapshot
from ..runtime import Action, RunState, RuntimeEngine, RuntimeFailure
from .actions import (
    ApplicationActionResultValidator,
    application_receipt_from_result,
    make_apply_action,
    make_rollback_action,
    make_verify_action,
    rollback_receipt_from_result,
    verification_from_result,
)
from .records import (
    APPLY_CANDIDATE_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
    ApplicationReceipt,
    ApplicationRequest,
    ApplicationVerification,
    RollbackReceipt,
)


@dataclass(frozen=True)
class ApplicationProjection:
    """Records derived from one exact runtime prefix."""

    application: ApplicationReceipt | None = None
    verification: ApplicationVerification | None = None
    rollback: RollbackReceipt | None = None


def next_application_action(
    request: ApplicationRequest,
    projection: ApplicationProjection,
) -> Action | None:
    """Return the sole action eligible at the derived application frontier."""

    if not request.apply:
        return None
    if projection.application is None:
        return make_apply_action(request)
    if projection.verification is None:
        return make_verify_action(projection.application)
    if projection.verification.disposition != "verified" and projection.rollback is None:
        return make_rollback_action(
            projection.application,
            projection.verification,
        )
    return None


def application_outcome(
    request: ApplicationRequest,
    projection: ApplicationProjection,
) -> Outcome:
    """Build the exact successful terminal outcome for a complete projection."""

    unresolved: tuple[str, ...]
    if not request.apply:
        status = "application-disabled"
        conclusions = ("selected improvement retained without authoritative application",)
        unresolved = ("application requires an explicitly enabled request",)
        target_snapshot = request.current_snapshot
    elif projection.verification is not None and projection.verification.disposition == "verified":
        status = "verified"
        conclusions = ("actual applied target state verified",)
        unresolved = ()
        if projection.application is None:  # pragma: no cover - projection invariant
            raise RuntimeError("verified outcome lost its application receipt")
        target_snapshot = projection.application.produced_snapshot
    elif projection.rollback is not None:
        status = "rolled-back"
        conclusions = ("nonverified application restored to the exact prior target state",)
        unresolved = (projection.verification.reason,) if projection.verification else ()
        target_snapshot = projection.rollback.restored_snapshot
    else:
        raise ValueError("incomplete application projection cannot produce a terminal outcome")
    lineage = (
        request.ref,
        request.handoff.ref,
        *((projection.application.ref,) if projection.application is not None else ()),
        *((projection.verification.ref,) if projection.verification is not None else ()),
        *((projection.rollback.ref,) if projection.rollback is not None else ()),
    )
    return Outcome(
        intent=request.ref,
        status=status,
        target_snapshot=target_snapshot,
        conclusions=conclusions,
        unresolved=unresolved,
        lineage=lineage,
    )


def replay_application_state(
    request: ApplicationRequest,
    state: RunState,
) -> tuple[RunState, ApplicationProjection]:
    """Validate and replay every lifecycle action, result, and terminal posture."""

    if type(request) is not ApplicationRequest:
        raise TypeError("application replay requires an ApplicationRequest")
    if type(state) is not RunState or state.run != request.canonical_run():
        raise ValueError("persisted application run envelope has drifted")
    replay = RuntimeEngine.start(request.canonical_run()).state
    projection = ApplicationProjection()
    result_index = 0
    validator = ApplicationActionResultValidator()
    for action in state.actions:
        if action.attempt != 1:
            raise ValueError("application lifecycle actions cannot retry or duplicate effects")
        expected = next_application_action(request, projection)
        if action not in replay.actions:
            if action != expected:
                raise ValueError("application action is not the exact lifecycle-derived frontier")
            replay = RuntimeEngine.request(replay, action).state
        if result_index < len(state.results) and state.results[result_index].action == action:
            result = state.results[result_index]
            validator.validate(replay, result)
            replay = RuntimeEngine.submit(replay, result).state
            if result.disposition == "succeeded":
                if action.kind == APPLY_CANDIDATE_ACTION_KIND:
                    projection = ApplicationProjection(
                        application=application_receipt_from_result(result)
                    )
                elif action.kind == VERIFY_APPLICATION_ACTION_KIND:
                    projection = ApplicationProjection(
                        application=projection.application,
                        verification=verification_from_result(result),
                    )
                elif action.kind == ROLLBACK_APPLICATION_ACTION_KIND:
                    projection = ApplicationProjection(
                        application=projection.application,
                        verification=projection.verification,
                        rollback=rollback_receipt_from_result(result),
                    )
            result_index += 1
    if result_index != len(state.results):
        raise ValueError("application result history is reordered or disconnected")
    settled = replay
    if state.status == "completed":
        expected_outcome = application_outcome(request, projection)
        replay = RuntimeEngine.complete(settled, expected_outcome).state
    if replay != state:
        raise ValueError("persisted application state does not replay exactly")
    return settled, projection


def application_projection(
    request: ApplicationRequest,
    state: RunState,
    projection: ApplicationProjection,
) -> tuple[
    str,
    ApplicationReceipt | None,
    ApplicationVerification | None,
    RollbackReceipt | None,
    tuple[RuntimeFailure, ...],
    TargetSnapshot | None,
]:
    """Return the sole result fields permitted by a settled terminal frontier."""

    if state.status in {"active", "completed"}:
        if next_application_action(request, projection) is not None:
            raise ValueError("application result projection is not terminal")
        if not request.apply:
            disposition = "application-disabled"
            authoritative = request.current_snapshot
        elif (
            projection.verification is not None
            and projection.verification.disposition == "verified"
        ):
            disposition = "verified"
            if projection.application is None:  # pragma: no cover - projection invariant
                raise RuntimeError("verified projection lost its application receipt")
            authoritative = projection.application.produced_snapshot
        elif projection.rollback is not None:
            disposition = "rolled-back"
            authoritative = projection.rollback.restored_snapshot
        else:
            raise ValueError("completed application state lacks a complete projection")
    elif state.status == "failed":
        if projection.application is None:
            disposition = "application-failed"
            authoritative = request.current_snapshot
        elif projection.verification is not None:
            disposition = "rollback-failed"
            authoritative = None
        else:
            raise ValueError("verification infrastructure failure cannot become terminal state")
    else:
        raise ValueError("application results require a terminal settled state")
    failures = tuple(
        item
        for item in (
            *(
                (projection.verification.operational_failure,)
                if projection.verification and projection.verification.operational_failure
                else ()
            ),
            *state.failures,
        )
    )
    return (
        disposition,
        projection.application,
        projection.verification,
        projection.rollback,
        failures,
        authoritative,
    )
