"""Restartable RSI governance composed with ordinary application semantics."""

from __future__ import annotations

from dataclasses import dataclass

from ..application import (
    APPLY_CANDIDATE_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    ApplicationProgress,
    ApplicationWorkflow,
    application_receipt_from_result,
    rollback_receipt_from_result,
)
from ..capabilities import CapabilityRegistry, DispatchPlan
from ..errors import RSICapabilityError
from ..records import TargetSnapshot
from ..runtime import ActionResult, RunState, RuntimeEngine, Transition
from .actions import (
    FORWARD_SHADOW_ACTION_KIND,
    HISTORICAL_EVALUATION_ACTION_KIND,
    INDEPENDENT_REVIEW_ACTION_KIND,
    SelfChangeActionResultValidator,
)
from .policy import SelfChangePolicy
from .records import (
    RSIRequest,
    RSIResult,
    SelfChangeApproval,
    SelfChangeGovernanceResult,
)
from .replay import (
    SelfChangeProjection,
    governance_outcome,
    next_governance_action,
    replay_governance_state,
)

_EXPECTED_GOVERNANCE_FAMILIES = {
    HISTORICAL_EVALUATION_ACTION_KIND: "experimenter",
    FORWARD_SHADOW_ACTION_KIND: "experimenter",
    INDEPENDENT_REVIEW_ACTION_KIND: "reviewer",
}


@dataclass(frozen=True)
class RSIProgress:
    """Exact composite frontier; each underlying RunState remains authoritative."""

    request: RSIRequest
    governance_state: RunState
    projection: SelfChangeProjection = SelfChangeProjection()
    governance_result: SelfChangeGovernanceResult | None = None
    approval: SelfChangeApproval | None = None
    application_progress: ApplicationProgress | None = None
    result: RSIResult | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not RSIRequest or type(self.governance_state) is not RunState:
            raise TypeError("RSI progress requires exact request and governance state")
        settled, projection = replay_governance_state(self.request, self.governance_state)
        if self.projection != projection:
            raise ValueError("RSI progress governance projection is not runtime-derived")
        if self.governance_result is not None:
            expected = SelfChangePolicy.governance_result(self.request, settled)
            if self.governance_result != expected:
                raise ValueError("RSI progress governance result is not exact")
        elif self.governance_state.status in {"completed", "failed"}:
            raise ValueError("terminal governance progress requires its exact result")
        if self.application_progress is not None:
            if self.governance_result is None or self.governance_result.disposition != "accepted":
                raise ValueError("RSI application requires accepted governance")
            expected_approval = SelfChangePolicy.approval(
                self.request,
                self.governance_result,
            )
            if self.approval != expected_approval:
                raise ValueError("RSI application progress lost its exact approval")
            expected_request = SelfChangePolicy.application_request(
                expected_approval,
                current_snapshot=self.request.declaration.target_snapshot,
            )
            if self.application_progress.request != expected_request:
                raise ValueError("RSI application progress belongs to another approval")
        elif self.approval is not None:
            raise ValueError("RSI approval requires application progress")
        if self.result is not None:
            if self.governance_result is None:
                raise ValueError("terminal RSI progress requires governance")
            application = (
                self.application_progress.result if self.application_progress is not None else None
            )
            expected_result = SelfChangePolicy.result(
                self.request,
                self.governance_result,
                approval=self.approval,
                application=application,
            )
            if self.result != expected_result:
                raise ValueError("RSI progress result is not the exact composite projection")
        elif self.application_progress is not None and self.application_progress.result is not None:
            raise ValueError("terminal RSI application progress requires RSIResult")
        elif self.governance_result is not None:
            if self.governance_result.disposition == "accepted" and self.request.activate:
                if self.application_progress is None:
                    raise ValueError("accepted RSI activation requires application progress")
            elif self.application_progress is None:
                raise ValueError("terminal RSI governance requires RSIResult")

    @property
    def state(self) -> RunState:
        return (
            self.application_progress.state
            if self.application_progress is not None
            else self.governance_state
        )

    @property
    def terminal(self) -> bool:
        return self.result is not None


@dataclass(frozen=True)
class RSIUpdate:
    progress: RSIProgress
    transitions: tuple[Transition, ...]
    plan: DispatchPlan

    def __post_init__(self) -> None:
        if type(self.progress) is not RSIProgress:
            raise TypeError("RSI updates require RSIProgress")
        transitions = tuple(self.transitions)
        if any(type(item) is not Transition for item in transitions):
            raise TypeError("RSI updates require Transition records")
        object.__setattr__(self, "transitions", transitions)
        if type(self.plan) is not DispatchPlan or self.plan.state != self.progress.state:
            raise ValueError("RSI dispatch plan must describe the exact live state")


class RSIWorkflow:
    """Own self-change gates while reusing ordinary application and host effects."""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = CapabilityRegistry() if registry is None else registry
        if type(self._registry) is not CapabilityRegistry:
            raise TypeError("RSI workflows require a CapabilityRegistry")
        for route in self._registry.routes:
            expected = _EXPECTED_GOVERNANCE_FAMILIES.get(route.action_kind)
            if expected is not None and route.family != expected:
                raise RSICapabilityError(
                    f"{route.action_kind} actions require an exact {expected} route"
                )
        self._validator = SelfChangeActionResultValidator()
        self._application = ApplicationWorkflow(self._registry)

    def _update(
        self,
        progress: RSIProgress,
        transitions: tuple[Transition, ...],
    ) -> RSIUpdate:
        return RSIUpdate(progress, transitions, self._registry.plan(progress.state))

    def _compose(
        self,
        *,
        request: RSIRequest,
        governance_state: RunState,
        projection: SelfChangeProjection,
        governance: SelfChangeGovernanceResult,
        current_snapshot: TargetSnapshot,
        transitions: tuple[Transition, ...],
        application_state: RunState | None = None,
    ) -> RSIUpdate:
        if governance.disposition != "accepted" or not request.activate:
            result = SelfChangePolicy.result(request, governance)
            return self._update(
                RSIProgress(
                    request=request,
                    governance_state=governance_state,
                    projection=projection,
                    governance_result=governance,
                    result=result,
                ),
                transitions,
            )
        approval = SelfChangePolicy.approval(request, governance)
        application_request = SelfChangePolicy.application_request(
            approval,
            current_snapshot=request.declaration.target_snapshot,
        )
        application_update = (
            self._application.start(application_request, current_snapshot=current_snapshot)
            if application_state is None
            else self._application.resume(
                application_request,
                application_state,
                current_snapshot=current_snapshot,
            )
        )
        application_progress = application_update.progress
        application_result = (
            SelfChangePolicy.result(
                request,
                governance,
                approval=approval,
                application=application_progress.result,
            )
            if application_progress.result is not None
            else None
        )
        return self._update(
            RSIProgress(
                request=request,
                governance_state=governance_state,
                projection=projection,
                governance_result=governance,
                approval=approval,
                application_progress=application_progress,
                result=application_result,
            ),
            (*transitions, *application_update.transitions),
        )

    def start(
        self,
        request: RSIRequest,
        *,
        current_snapshot: TargetSnapshot,
    ) -> RSIUpdate:
        SelfChangePolicy.validate_request(request)
        SelfChangePolicy.require_current(request, current_snapshot)
        started = RuntimeEngine.start(request.canonical_run())
        assert started.transition is not None
        resumed = self.resume(
            request,
            started.state,
            current_snapshot=current_snapshot,
        )
        return RSIUpdate(
            resumed.progress,
            (started.transition, *resumed.transitions),
            resumed.plan,
        )

    def resume(
        self,
        request: RSIRequest,
        governance_state: RunState,
        *,
        current_snapshot: TargetSnapshot,
        application_state: RunState | None = None,
    ) -> RSIUpdate:
        SelfChangePolicy.validate_request(request)
        settled, projection = replay_governance_state(request, governance_state)
        if application_state is None:
            SelfChangePolicy.require_current(request, current_snapshot)
        if governance_state.status == "waiting":
            if application_state is not None:
                raise ValueError("application state cannot precede completed governance")
            return self._update(
                RSIProgress(request, governance_state, projection),
                (),
            )
        if governance_state.status == "cancelled":
            raise ValueError("RSI governance does not support cancellation")
        if governance_state.status == "failed":
            if application_state is not None:
                raise ValueError("failed governance cannot have application state")
            governance = SelfChangePolicy.governance_result(request, settled)
            return self._compose(
                request=request,
                governance_state=governance_state,
                projection=projection,
                governance=governance,
                current_snapshot=current_snapshot,
                transitions=(),
            )
        if governance_state.status == "completed":
            if governance_state.outcome != governance_outcome(request, projection):
                raise ValueError("completed self-change governance outcome has drifted")
            governance = SelfChangePolicy.governance_result(request, settled)
            return self._compose(
                request=request,
                governance_state=governance_state,
                projection=projection,
                governance=governance,
                current_snapshot=current_snapshot,
                transitions=(),
                application_state=application_state,
            )
        if governance_state.status != "active" or governance_state.pending_actions:
            raise ValueError("persisted self-change state has an unsupported live frontier")
        if application_state is not None:
            raise ValueError("application state cannot precede completed governance")
        action = next_governance_action(request, projection)
        if action is not None:
            requested = RuntimeEngine.request(governance_state, action)
            assert requested.transition is not None
            return self._update(
                RSIProgress(request, requested.state, projection),
                (requested.transition,),
            )
        governance = SelfChangePolicy.governance_result(request, settled)
        completed = RuntimeEngine.complete(
            governance_state,
            governance_outcome(request, projection),
        )
        assert completed.transition is not None
        return self._compose(
            request=request,
            governance_state=completed.state,
            projection=projection,
            governance=governance,
            current_snapshot=current_snapshot,
            transitions=(completed.transition,),
        )

    def _require_canonical(
        self,
        progress: RSIProgress,
        current_snapshot: TargetSnapshot,
    ) -> None:
        resumed = self.resume(
            progress.request,
            progress.governance_state,
            current_snapshot=current_snapshot,
            application_state=(
                progress.application_progress.state
                if progress.application_progress is not None
                else None
            ),
        )
        if resumed.transitions or resumed.progress != progress:
            raise ValueError("RSI progress is not the canonical persisted frontier")

    def submit(
        self,
        progress: RSIProgress,
        result: ActionResult,
        *,
        prior_snapshot: TargetSnapshot,
        current_snapshot: TargetSnapshot,
        authority: str,
    ) -> RSIUpdate:
        if type(progress) is not RSIProgress or type(result) is not ActionResult:
            raise TypeError("RSI submission requires exact progress and ActionResult")
        self._require_canonical(progress, prior_snapshot)
        if progress.terminal or len(progress.state.pending_actions) != 1:
            raise ValueError("RSI submission requires one live pending action")
        action = progress.state.pending_actions[0]
        if result.action != action:
            raise ValueError("RSI result does not match the exact pending action")
        if progress.application_progress is not None:
            application_update = self._application.submit(
                progress.application_progress,
                result,
                prior_snapshot=prior_snapshot,
                current_snapshot=current_snapshot,
                authority=authority,
            )
            application_progress = application_update.progress
            assert progress.governance_result is not None and progress.approval is not None
            rsi_result = (
                SelfChangePolicy.result(
                    progress.request,
                    progress.governance_result,
                    approval=progress.approval,
                    application=application_progress.result,
                )
                if application_progress.result is not None
                else None
            )
            return self._update(
                RSIProgress(
                    request=progress.request,
                    governance_state=progress.governance_state,
                    projection=progress.projection,
                    governance_result=progress.governance_result,
                    approval=progress.approval,
                    application_progress=application_progress,
                    result=rsi_result,
                ),
                application_update.transitions,
            )
        SelfChangePolicy.require_current(progress.request, prior_snapshot)
        SelfChangePolicy.require_current(progress.request, current_snapshot)
        resolution = self._registry.resolve(action)
        expected_family = _EXPECTED_GOVERNANCE_FAMILIES[action.kind]
        if resolution.family != expected_family or resolution.posture == "unavailable":
            raise RSICapabilityError("self-change result lacks the exact configured authority")
        if authority not in {"automatic", "external", "human-reserved"}:
            raise RSICapabilityError("unsupported RSI submission authority")
        if resolution.posture != authority:
            raise RSICapabilityError("RSI result authority does not match the resolved posture")
        self._validator.validate(progress.governance_state, result)
        submitted = RuntimeEngine.submit(progress.governance_state, result)
        assert submitted.transition is not None
        resumed = self.resume(
            progress.request,
            submitted.state,
            current_snapshot=current_snapshot,
        )
        return RSIUpdate(
            resumed.progress,
            (submitted.transition, *resumed.transitions),
            resumed.plan,
        )

    def run_managed(
        self,
        progress: RSIProgress,
        *,
        current_snapshot: TargetSnapshot,
    ) -> RSIUpdate:
        resumed = self.resume(
            progress.request,
            progress.governance_state,
            current_snapshot=current_snapshot,
            application_state=(
                progress.application_progress.state
                if progress.application_progress is not None
                else None
            ),
        )
        if not resumed.transitions and resumed.progress != progress:
            raise ValueError("managed RSI progress is not canonical")
        transitions = list(resumed.transitions)
        current = resumed.progress
        observed = current_snapshot
        while not current.terminal:
            self._require_canonical(current, observed)
            resolution = self._registry.resolve(current.state.pending_actions[0])
            if resolution.posture != "automatic":
                return RSIUpdate(
                    current,
                    tuple(transitions),
                    self._registry.plan(current.state),
                )
            result = self._registry.execute(resolution)
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
        return RSIUpdate(
            current,
            tuple(transitions),
            self._registry.plan(current.state),
        )


def recurse(
    request: RSIRequest,
    *,
    current_snapshot: TargetSnapshot,
    registry: CapabilityRegistry | None = None,
) -> RSIResult | RSIUpdate:
    """Run configured automatic gates/effects and stop at explicit host handoffs."""

    workflow = RSIWorkflow(registry)
    update = workflow.start(request, current_snapshot=current_snapshot)
    update = workflow.run_managed(update.progress, current_snapshot=current_snapshot)
    return update.progress.result if update.progress.result is not None else update
