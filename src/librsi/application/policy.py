"""Nonreplaceable authority, currentness, and terminal-result policy."""

from __future__ import annotations

from ..records import TargetSnapshot
from ..runtime import RunState
from .records import ApplicationRequest, ApplicationResult
from .replay import (
    ApplicationProjection,
    application_projection,
    replay_application_state,
)


class ApplicationPolicy:
    """Own application eligibility without owning host-side mutation."""

    @staticmethod
    def validate_request(request: ApplicationRequest) -> None:
        if type(request) is not ApplicationRequest:
            raise TypeError("application policy requires an ApplicationRequest")
        if request.improvement.request.baseline != request.current_snapshot:
            raise ValueError("application request does not retain the selected baseline")
        if request.improvement.handoff != request.handoff:
            raise ValueError("application request lost its exact improvement handoff")

    @staticmethod
    def require_current(
        request: ApplicationRequest,
        projection: ApplicationProjection,
        current_snapshot: TargetSnapshot,
        *,
        rollback_failed: bool = False,
    ) -> None:
        if type(current_snapshot) is not TargetSnapshot:
            raise ValueError("application lifecycle requires an explicit current snapshot")
        if current_snapshot.target != request.current_snapshot.target:
            raise ValueError("application currentness belongs to another target")
        if rollback_failed:
            return
        expected = (
            projection.rollback.restored_snapshot
            if projection.rollback is not None
            else projection.application.produced_snapshot
            if projection.application is not None
            else request.current_snapshot
        )
        if current_snapshot != expected:
            raise ValueError("application lifecycle current snapshot has drifted")

    @staticmethod
    def result(request: ApplicationRequest, state: RunState) -> ApplicationResult:
        settled, projection = replay_application_state(request, state)
        fields = application_projection(request, settled, projection)
        disposition, application, verification, rollback, failures, authoritative = fields
        return ApplicationResult(
            request=request,
            disposition=disposition,
            settled_state=settled,
            handoff=request.handoff,
            application=application,
            verification=verification,
            rollback=rollback,
            operational_failures=failures,
            authoritative_snapshot=authoritative,
            lineage=(
                request.ref,
                settled.ref,
                request.handoff.ref,
                *((application.ref,) if application is not None else ()),
                *((verification.ref,) if verification is not None else ()),
                *((rollback.ref,) if rollback is not None else ()),
                *(item.ref for item in failures),
                *((authoritative.ref,) if authoritative is not None else ()),
            ),
        )
