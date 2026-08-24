"""Bounded managed dispatch over the shared external-agent controller."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from ..application import (
    APPLY_CANDIDATE_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
    application_receipt_from_result,
    rollback_receipt_from_result,
)
from ..capabilities import CapabilityRegistry
from ..protocol import CapabilityBinding, ExternalAgentController
from ..records import TargetSnapshot, record_from_dict
from ..runtime import Action, ActionResult
from .records import ManagedBounds, ManagedExecution, ServiceLimits

_CURRENTNESS_ACTIONS = frozenset(
    {
        APPLY_CANDIDATE_ACTION_KIND,
        VERIFY_APPLICATION_ACTION_KIND,
        ROLLBACK_APPLICATION_ACTION_KIND,
    }
)


def _data(document: Mapping[str, Any]) -> Mapping[str, Any]:
    data = document.get("data")
    if not isinstance(data, Mapping):
        raise RuntimeError("service controller response lost its structured data")
    return cast(Mapping[str, Any], data)


def _observed_snapshot(
    result: ActionResult,
    prior: TargetSnapshot,
) -> TargetSnapshot:
    if result.disposition != "succeeded":
        return prior
    if result.action.kind == APPLY_CANDIDATE_ACTION_KIND:
        return application_receipt_from_result(result).produced_snapshot
    if result.action.kind == ROLLBACK_APPLICATION_ACTION_KIND:
        return rollback_receipt_from_result(result).restored_snapshot
    return prior


class ManagedServiceRunner:
    """One bounded loop that never owns workflow or lifecycle state."""

    def __init__(
        self,
        controller: ExternalAgentController,
        registry: CapabilityRegistry,
        limits: ServiceLimits,
        current_snapshot_resolver: Callable[[TargetSnapshot], TargetSnapshot] | None = None,
    ) -> None:
        if type(controller) is not ExternalAgentController:
            raise TypeError("managed service requires an ExternalAgentController")
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("managed service requires a CapabilityRegistry")
        if type(limits) is not ServiceLimits:
            raise TypeError("managed service requires ServiceLimits")
        if current_snapshot_resolver is not None and not callable(current_snapshot_resolver):
            raise TypeError("managed service current snapshot resolver must be callable")
        self._controller = controller
        self._registry = registry
        self._limits = limits
        self._current_snapshot_resolver = current_snapshot_resolver

    def _report(
        self,
        run_id: str,
        *,
        reason: str,
        executed: list[str],
    ) -> ManagedExecution:
        return self._report_from(
            self._controller.status(run_id),
            run_id=run_id,
            reason=reason,
            executed=executed,
        )

    @staticmethod
    def _report_from(
        document: Mapping[str, Any],
        *,
        run_id: str,
        reason: str,
        executed: list[str],
    ) -> ManagedExecution:
        data = _data(document)
        state_root = document.get("state_root")
        terminal = data.get("terminal")
        status = data.get("status")
        if type(state_root) is not str:
            raise RuntimeError("managed status lost its canonical state root")
        if type(terminal) is not bool or type(status) is not str or not status:
            raise RuntimeError("managed status lost its canonical lifecycle fields")
        return ManagedExecution(
            run_id=run_id,
            stop_reason=reason,
            executed_action_roots=tuple(executed),
            terminal=terminal,
            status=status,
            state_root=state_root,
        )

    def run(self, run_id: str, bounds: ManagedBounds) -> ManagedExecution:
        if type(run_id) is not str or not run_id.strip():
            raise ValueError("managed execution requires a run id")
        if type(bounds) is not ManagedBounds:
            raise TypeError("managed execution requires explicit ManagedBounds")
        if bounds.max_actions > self._limits.max_managed_actions:
            raise ValueError("managed invocation exceeds the configured action bound")
        executed: list[str] = []
        latest_status: Mapping[str, Any] | None = None
        for _ in range(bounds.max_actions):
            status = self._controller.status(run_id)
            latest_status = status
            if bool(_data(status).get("terminal")):
                return self._report_from(
                    status,
                    run_id=run_id,
                    reason="outcome",
                    executed=executed,
                )
            pending = self._controller.next(run_id)
            data = _data(pending)
            action = record_from_dict(cast(Mapping[str, Any], data.get("action")))
            binding = record_from_dict(cast(Mapping[str, Any], data.get("capability")))
            snapshot = record_from_dict(cast(Mapping[str, Any], data.get("target_snapshot")))
            if (
                type(action) is not Action
                or type(binding) is not CapabilityBinding
                or type(snapshot) is not TargetSnapshot
            ):
                raise RuntimeError("managed frontier is not canonical")
            if binding.posture != "automatic":
                reason = (
                    "capability-unavailable"
                    if binding.posture == "unavailable"
                    else "authority-gate"
                )
                return self._report_from(
                    status,
                    run_id=run_id,
                    reason=reason,
                    executed=executed,
                )
            resolution = self._registry.resolve(action)
            if resolution.route != binding.route() or resolution.posture != "automatic":
                return self._report_from(
                    status,
                    run_id=run_id,
                    reason="capability-unavailable",
                    executed=executed,
                )
            if resolution.family == "applier" and not bounds.allow_application:
                return self._report_from(
                    status,
                    run_id=run_id,
                    reason="application-authority",
                    executed=executed,
                )
            if action.kind in _CURRENTNESS_ACTIONS:
                if self._current_snapshot_resolver is None:
                    return self._report_from(
                        status,
                        run_id=run_id,
                        reason="currentness-unavailable",
                        executed=executed,
                    )
                current = self._current_snapshot_resolver(snapshot)
                if type(current) is not TargetSnapshot or current.target != snapshot.target:
                    raise ValueError(
                        "managed current snapshot resolver returned an invalid target snapshot"
                    )
                if current != snapshot:
                    return self._report_from(
                        status,
                        run_id=run_id,
                        reason="currentness-gate",
                        executed=executed,
                    )
            result = self._registry.execute(resolution)
            observed = _observed_snapshot(result, snapshot)
            submitted = self._controller.submit(
                run_id,
                result,
                authority="automatic",
                current_snapshot=observed,
            )
            latest_status = submitted
            executed.append(action.root)
            if bool(_data(submitted).get("terminal")):
                return self._report_from(
                    submitted,
                    run_id=run_id,
                    reason="outcome",
                    executed=executed,
                )
        assert latest_status is not None
        return self._report_from(
            latest_status,
            run_id=run_id,
            reason="action-bound",
            executed=executed,
        )
