"""Restartable capability-mediated application, verification, and rollback."""

from __future__ import annotations

from dataclasses import dataclass

from ..capabilities import CapabilityRegistry, DispatchPlan
from ..errors import RSICapabilityError
from ..governance import ApplicationGovernanceAuthority
from ..improvement import ImprovementResult
from ..records import TargetSnapshot
from ..runtime import ActionResult, RunState, RuntimeEngine, Transition
from .actions import (
    ApplicationActionResultValidator,
    application_receipt_from_result,
    rollback_receipt_from_result,
)
from .policy import ApplicationPolicy
from .records import (
    APPLY_CANDIDATE_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
    ApplicationRequest,
    ApplicationResult,
)
from .replay import (
    ApplicationProjection,
    application_outcome,
    next_application_action,
    replay_application_state,
)

_EXPECTED_FAMILIES = {
    APPLY_CANDIDATE_ACTION_KIND: "applier",
    VERIFY_APPLICATION_ACTION_KIND: "verifier",
    ROLLBACK_APPLICATION_ACTION_KIND: "applier",
}


@dataclass(frozen=True)
class ApplicationProgress:
    request: ApplicationRequest
    state: RunState
    projection: ApplicationProjection = ApplicationProjection()
    result: ApplicationResult | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not ApplicationRequest or type(self.state) is not RunState:
            raise TypeError("application progress requires an exact request and RunState")
        settled, expected = replay_application_state(self.request, self.state)
        if self.projection != expected:
            raise ValueError("application progress projection is not runtime-derived")
        if self.state.status in {"completed", "failed"}:
            if type(self.result) is not ApplicationResult or self.result.request != self.request:
                raise ValueError("terminal application progress requires its exact result")
            if self.result.settled_state != settled:
                raise ValueError("application progress result belongs to another exact state")
        elif self.result is not None:
            raise ValueError("nonterminal application progress cannot contain a result")

    @property
    def terminal(self) -> bool:
        return self.state.status in {"completed", "failed", "cancelled"}

    @property
    def handoff(self):
        return self.request.handoff


@dataclass(frozen=True)
class ApplicationUpdate:
    progress: ApplicationProgress
    transitions: tuple[Transition, ...]
    plan: DispatchPlan

    def __post_init__(self) -> None:
        if type(self.progress) is not ApplicationProgress:
            raise TypeError("application updates require ApplicationProgress")
        transitions = tuple(self.transitions)
        if any(type(item) is not Transition for item in transitions):
            raise TypeError("application updates require Transition records")
        object.__setattr__(self, "transitions", transitions)
        if type(self.plan) is not DispatchPlan or self.plan.state != self.progress.state:
            raise ValueError("application update plan must describe its exact progress state")


class ApplicationWorkflow:
    """Own lifecycle transitions while host capabilities own every external effect."""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = CapabilityRegistry() if registry is None else registry
        if type(self._registry) is not CapabilityRegistry:
            raise TypeError("application workflow requires a CapabilityRegistry")
        for route in self._registry.routes:
            expected = _EXPECTED_FAMILIES.get(route.action_kind)
            if expected is not None and route.family != expected:
                raise RSICapabilityError(
                    f"{route.action_kind} actions require an exact {expected} route"
                )
        self._policy = ApplicationPolicy()
        self._validator = ApplicationActionResultValidator()

    def _update(
        self,
        request: ApplicationRequest,
        state: RunState,
        projection: ApplicationProjection,
        transitions: tuple[Transition, ...],
        result: ApplicationResult | None = None,
    ) -> ApplicationUpdate:
        progress = ApplicationProgress(request, state, projection, result)
        return ApplicationUpdate(progress, transitions, self._registry.plan(state))

    def start(
        self,
        request: ApplicationRequest,
        *,
        current_snapshot: TargetSnapshot,
    ) -> ApplicationUpdate:
        self._policy.validate_request(request)
        self._policy.require_current(request, ApplicationProjection(), current_snapshot)
        started = RuntimeEngine.start(request.canonical_run())
        assert started.transition is not None
        resumed = self.resume(
            request,
            started.state,
            current_snapshot=current_snapshot,
        )
        return ApplicationUpdate(
            resumed.progress,
            (started.transition, *resumed.transitions),
            resumed.plan,
        )

    def resume(
        self,
        request: ApplicationRequest,
        state: RunState,
        *,
        current_snapshot: TargetSnapshot,
    ) -> ApplicationUpdate:
        """Reconcile and continue from any exact persisted lifecycle frontier."""

        self._policy.validate_request(request)
        settled, projection = replay_application_state(request, state)
        rollback_failed = (
            state.status == "failed"
            and projection.application is not None
            and projection.verification is not None
            and projection.rollback is None
        )
        self._policy.require_current(
            request,
            projection,
            current_snapshot,
            rollback_failed=rollback_failed,
        )
        if state.status == "waiting":
            if len(state.pending_actions) != 1:
                raise ValueError("waiting application state requires one pending action")
            return self._update(request, state, projection, ())
        if state.status == "cancelled":
            raise ValueError("application lifecycle does not support cancellation")
        if state.status == "failed":
            return self._update(
                request,
                state,
                projection,
                (),
                self._policy.result(request, state),
            )
        if state.status == "completed":
            expected_outcome = application_outcome(request, projection)
            if state.outcome != expected_outcome:
                raise ValueError("completed application outcome has drifted")
            return self._update(
                request,
                state,
                projection,
                (),
                self._policy.result(request, settled),
            )
        if state.status != "active" or state.pending_actions:
            raise ValueError("persisted application state has an unsupported live frontier")
        action = next_application_action(request, projection)
        if action is not None:
            requested = RuntimeEngine.request(state, action)
            assert requested.transition is not None
            return self._update(
                request,
                requested.state,
                projection,
                (requested.transition,),
            )
        result = self._policy.result(request, settled)
        completed = RuntimeEngine.complete(state, application_outcome(request, projection))
        assert completed.transition is not None
        return self._update(
            request,
            completed.state,
            projection,
            (completed.transition,),
            result,
        )

    def _require_canonical(
        self,
        progress: ApplicationProgress,
        current_snapshot: TargetSnapshot,
    ) -> None:
        resumed = self.resume(
            progress.request,
            progress.state,
            current_snapshot=current_snapshot,
        )
        if resumed.transitions or resumed.progress != progress:
            raise ValueError("application progress is not the canonical persisted frontier")

    def submit(
        self,
        progress: ApplicationProgress,
        result: ActionResult,
        *,
        prior_snapshot: TargetSnapshot,
        current_snapshot: TargetSnapshot,
        authority: str,
    ) -> ApplicationUpdate:
        if type(progress) is not ApplicationProgress:
            raise TypeError("application submission requires ApplicationProgress")
        self._require_canonical(progress, prior_snapshot)
        if progress.terminal or len(progress.state.pending_actions) != 1:
            raise ValueError("application submission requires one live pending action")
        action = progress.state.pending_actions[0]
        if type(result) is not ActionResult or result.action != action:
            raise ValueError("application result does not match the exact pending action")
        resolution = self._registry.resolve(action)
        expected_family = _EXPECTED_FAMILIES[action.kind]
        if resolution.family != expected_family:
            raise RSICapabilityError(
                f"{action.kind} actions require an exact {expected_family} route"
            )
        if resolution.posture == "unavailable":
            raise RSICapabilityError("unavailable application capabilities cannot submit results")
        if authority not in {"automatic", "external", "human-reserved"}:
            raise RSICapabilityError("unsupported application submission authority")
        if resolution.posture != authority:
            raise RSICapabilityError(
                "application result authority does not match the resolved posture"
            )
        self._validator.validate(progress.state, result)
        submitted = RuntimeEngine.submit(progress.state, result)
        assert submitted.transition is not None
        resumed = self.resume(
            progress.request,
            submitted.state,
            current_snapshot=current_snapshot,
        )
        return ApplicationUpdate(
            resumed.progress,
            (submitted.transition, *resumed.transitions),
            resumed.plan,
        )

    def run_managed(
        self,
        progress: ApplicationProgress,
        *,
        current_snapshot: TargetSnapshot,
    ) -> ApplicationUpdate:
        """Execute only automatic routes and stop cleanly at every explicit handoff."""

        resumed = self.resume(
            progress.request,
            progress.state,
            current_snapshot=current_snapshot,
        )
        if not resumed.transitions and resumed.progress != progress:
            raise ValueError("managed application progress is not canonical")
        transitions = list(resumed.transitions)
        current = resumed.progress
        observed = current_snapshot
        while not current.terminal:
            self._require_canonical(current, observed)
            resolution = self._registry.resolve(current.state.pending_actions[0])
            if resolution.posture != "automatic":
                return ApplicationUpdate(
                    current,
                    tuple(transitions),
                    self._registry.plan(current.state),
                )
            expected_family = _EXPECTED_FAMILIES[resolution.action.kind]
            if resolution.family != expected_family:
                raise RSICapabilityError(
                    f"{resolution.action.kind} actions require an exact {expected_family} route"
                )
            result = self._registry.execute(resolution)
            self._validator.validate(current.state, result)
            prior = observed
            if result.disposition == "succeeded":
                if result.action.kind == APPLY_CANDIDATE_ACTION_KIND:
                    observed = application_receipt_from_result(result).produced_snapshot
                elif result.action.kind == ROLLBACK_APPLICATION_ACTION_KIND:
                    observed = rollback_receipt_from_result(result).restored_snapshot
            update = self.submit(
                current,
                result,
                prior_snapshot=prior,
                current_snapshot=observed,
                authority="automatic",
            )
            transitions.extend(update.transitions)
            current = update.progress
        return ApplicationUpdate(
            current,
            tuple(transitions),
            self._registry.plan(current.state),
        )


def apply_improvement(
    improvement: ImprovementResult,
    *,
    current_snapshot: TargetSnapshot,
    apply: bool = False,
    registry: CapabilityRegistry | None = None,
    application_id: str = "application",
    governance_authority: ApplicationGovernanceAuthority | None = None,
) -> ApplicationResult | ApplicationUpdate:
    """Apply when explicitly enabled, otherwise return the consumable disabled result."""

    request = ApplicationRequest.create(
        application_id=application_id,
        improvement=improvement,
        current_snapshot=current_snapshot,
        apply=apply,
        governance_authority=governance_authority,
    )
    workflow = ApplicationWorkflow(registry)
    update = workflow.run_managed(
        workflow.start(request, current_snapshot=current_snapshot).progress,
        current_snapshot=current_snapshot,
    )
    return update.progress.result if update.progress.result is not None else update
