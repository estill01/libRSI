"""Restartable intervention-to-candidate preparation over the canonical runtime."""

from __future__ import annotations

from dataclasses import dataclass

from ..capabilities import Implementer
from ..records import EvidenceRef, Outcome, TargetSnapshot
from ..runtime import Action, ActionResult, RunState, RuntimeEngine, Transition
from .actions import (
    ImplementationResultValidator,
    implementation_result_from_action_result,
    make_implementation_action,
    make_implementation_handoff,
)
from .policy import InterventionPolicy
from .records import (
    ImplementationHandoff,
    ImplementationResult,
    InterventionImplementationRequest,
    InterventionSpec,
)


def _canonical_request(intervention: InterventionSpec) -> InterventionImplementationRequest:
    return InterventionImplementationRequest.for_intervention(
        intervention,
        candidate_id=f"{intervention.intervention_id}:candidate",
    )


def _implementation_outcome(result: ImplementationResult) -> Outcome:
    intervention = result.request.intervention
    evidence_refs = tuple(EvidenceRef.from_evidence(item) for item in intervention.evidence)
    compatibility_intervention = intervention.to_intervention()
    return Outcome(
        intent=intervention.ref,
        status="candidate-prepared",
        target_snapshot=result.authoritative_snapshot,
        evidence_refs=evidence_refs,
        intervention_refs=(compatibility_intervention.ref,),
        artifacts=result.candidate.artifacts,
        next_actions=("validate the prospective candidate before any application",),
        lineage=(
            result.ref,
            result.candidate.ref,
            intervention.ref,
            result.authoritative_snapshot.ref,
            *evidence_refs,
        ),
    )


def _require_canonical_runtime_state(
    intervention: InterventionSpec,
    state: RunState,
) -> tuple[
    InterventionImplementationRequest,
    Action,
    ImplementationResult | None,
]:
    request = _canonical_request(intervention)
    action = make_implementation_action(request)
    started = RuntimeEngine.start(intervention.canonical_run()).state
    if state.status == "active" and not state.actions:
        if state != started:
            raise ValueError("intervention state does not match the canonical runtime transition")
        return request, action, None

    canonical_waiting = RuntimeEngine.request(started, action).state
    if not state.results:
        if state != canonical_waiting:
            raise ValueError("intervention state does not match the canonical runtime transition")
        return request, action, None

    if len(state.results) != 1:
        raise ValueError("intervention runtime must contain one exact implementation result")
    result_envelope = state.results[0]
    ImplementationResultValidator().validate(canonical_waiting, result_envelope)
    submitted = RuntimeEngine.submit(canonical_waiting, result_envelope).state
    implementation_result: ImplementationResult | None = None
    expected_state = submitted
    if result_envelope.disposition == "succeeded":
        implementation_result = implementation_result_from_action_result(result_envelope)
        if state.status == "completed":
            expected_state = RuntimeEngine.complete(
                submitted,
                _implementation_outcome(implementation_result),
            ).state
    if state != expected_state:
        raise ValueError("intervention state does not match the canonical runtime transition")
    return request, action, implementation_result


@dataclass(frozen=True)
class InterventionProgress:
    """Candidate-preparation projection; RunState owns lifecycle mutation."""

    intervention: InterventionSpec
    current_snapshot: TargetSnapshot
    state: RunState
    handoff: ImplementationHandoff | None = None
    result: ImplementationResult | None = None
    failure_result: ActionResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intervention, InterventionSpec):
            raise TypeError("intervention progress requires an InterventionSpec")
        if not isinstance(self.current_snapshot, TargetSnapshot):
            raise TypeError("intervention progress requires a current TargetSnapshot")
        InterventionPolicy.require_current(self.intervention, self.current_snapshot)
        if not isinstance(self.state, RunState):
            raise TypeError("intervention progress requires a RunState")
        if self.state.run != self.intervention.canonical_run():
            raise ValueError("intervention progress runtime does not match its specification")

        request, action, runtime_result = _require_canonical_runtime_state(
            self.intervention,
            self.state,
        )
        if self.state.status == "waiting":
            expected_handoff = make_implementation_handoff(request)
            if self.handoff != expected_handoff:
                raise ValueError("waiting intervention progress lost its exact handoff frontier")
            if self.result is not None or self.failure_result is not None:
                raise ValueError("waiting intervention progress cannot contain a result")
        elif self.handoff is not None:
            raise ValueError("only waiting intervention progress may expose a handoff")

        if self.state.status == "completed":
            if not isinstance(self.result, ImplementationResult):
                raise ValueError(
                    "completed intervention progress requires an implementation result"
                )
            if self.failure_result is not None:
                raise ValueError("completed intervention progress cannot contain a failure result")
            if self.result.request != request:
                raise ValueError("implementation result belongs to another intervention frontier")
            if self.result != runtime_result:
                raise ValueError("completed intervention progress result has drifted")
        elif self.result is not None:
            raise ValueError("implementation results require completed runtime state")

        if self.state.status in {"failed", "cancelled"}:
            settled_result = self.state.results[0]
            if not isinstance(self.failure_result, ActionResult) or (
                self.failure_result != settled_result
            ):
                raise ValueError("terminal intervention failure requires its exact ActionResult")
        elif self.failure_result is not None:
            raise ValueError("failure results require failed or cancelled runtime state")
        if self.state.status not in {"waiting", "completed", "failed", "cancelled"}:
            raise ValueError("intervention progress requires a waiting or terminal runtime state")


@dataclass(frozen=True)
class InterventionUpdate:
    progress: InterventionProgress
    transitions: tuple[Transition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.progress, InterventionProgress):
            raise TypeError("intervention updates require InterventionProgress")
        transitions = tuple(self.transitions)
        if any(not isinstance(item, Transition) for item in transitions):
            raise TypeError("intervention updates require Transition values")
        object.__setattr__(self, "transitions", transitions)


class InterventionWorkflow:
    """Prepare a prospective candidate without authoritative target application."""

    def __init__(self) -> None:
        self._policy = InterventionPolicy()

    @staticmethod
    def _request(intervention: InterventionSpec) -> InterventionImplementationRequest:
        return _canonical_request(intervention)

    @staticmethod
    def _outcome(result: ImplementationResult) -> Outcome:
        return _implementation_outcome(result)

    def _require_current(
        self,
        intervention: InterventionSpec,
        current_snapshot: TargetSnapshot,
    ) -> None:
        self._policy.require_current(intervention, current_snapshot)

    def start(
        self,
        intervention: InterventionSpec,
        *,
        current_snapshot: TargetSnapshot,
    ) -> InterventionUpdate:
        if not isinstance(intervention, InterventionSpec):
            raise TypeError("intervention start requires an InterventionSpec")
        self._require_current(intervention, current_snapshot)
        started = RuntimeEngine.start(intervention.canonical_run())
        if started.transition is None:  # pragma: no cover - runtime invariant
            raise RuntimeError("intervention start lost its transition")
        resumed = self.resume(
            intervention,
            started.state,
            current_snapshot=current_snapshot,
        )
        return InterventionUpdate(
            progress=resumed.progress,
            transitions=(started.transition, *resumed.transitions),
        )

    def resume(
        self,
        intervention: InterventionSpec,
        state: RunState,
        *,
        current_snapshot: TargetSnapshot,
    ) -> InterventionUpdate:
        if not isinstance(intervention, InterventionSpec):
            raise TypeError("intervention resume requires an InterventionSpec")
        if not isinstance(state, RunState):
            raise TypeError("intervention resume requires a RunState")
        self._require_current(intervention, current_snapshot)
        if state.run != intervention.canonical_run():
            raise ValueError("persisted intervention run envelope has drifted")
        request, action, runtime_result = _require_canonical_runtime_state(
            intervention,
            state,
        )

        if state.status == "waiting":
            return InterventionUpdate(
                progress=InterventionProgress(
                    intervention=intervention,
                    current_snapshot=current_snapshot,
                    state=state,
                    handoff=make_implementation_handoff(request),
                ),
                transitions=(),
            )

        if state.status in {"failed", "cancelled"}:
            failure_result = state.results[0]
            return InterventionUpdate(
                progress=InterventionProgress(
                    intervention=intervention,
                    current_snapshot=current_snapshot,
                    state=state,
                    failure_result=failure_result,
                ),
                transitions=(),
            )

        if state.status == "completed":
            if runtime_result is None:  # pragma: no cover - canonical replay invariant
                raise RuntimeError("completed intervention lost its implementation result")
            return InterventionUpdate(
                progress=InterventionProgress(
                    intervention=intervention,
                    current_snapshot=current_snapshot,
                    state=state,
                    result=runtime_result,
                ),
                transitions=(),
            )

        if not state.actions:
            requested = RuntimeEngine.request(state, action)
            if requested.transition is None:  # pragma: no cover - runtime invariant
                raise RuntimeError("intervention action request lost its transition")
            return InterventionUpdate(
                progress=InterventionProgress(
                    intervention=intervention,
                    current_snapshot=current_snapshot,
                    state=requested.state,
                    handoff=make_implementation_handoff(request),
                ),
                transitions=(requested.transition,),
            )
        if runtime_result is None:  # pragma: no cover - canonical replay invariant
            raise RuntimeError("active intervention lost its successful implementation")
        completed = RuntimeEngine.complete(state, self._outcome(runtime_result))
        if completed.transition is None:  # pragma: no cover - runtime invariant
            raise RuntimeError("intervention completion lost its transition")
        return InterventionUpdate(
            progress=InterventionProgress(
                intervention=intervention,
                current_snapshot=current_snapshot,
                state=completed.state,
                result=runtime_result,
            ),
            transitions=(completed.transition,),
        )

    def _require_canonical(self, progress: InterventionProgress) -> None:
        if not isinstance(progress, InterventionProgress):
            raise TypeError("intervention progress must be InterventionProgress")
        resumed = self.resume(
            progress.intervention,
            progress.state,
            current_snapshot=progress.current_snapshot,
        )
        if resumed.transitions or resumed.progress != progress:
            raise ValueError("intervention progress is not the canonical persisted frontier")

    def submit(
        self,
        progress: InterventionProgress,
        action_result: ActionResult,
        *,
        current_snapshot: TargetSnapshot,
    ) -> InterventionUpdate:
        if not isinstance(progress, InterventionProgress):
            raise TypeError("intervention submission requires InterventionProgress")
        self._require_current(progress.intervention, current_snapshot)
        if current_snapshot != progress.current_snapshot:
            raise ValueError("intervention submission currentness differs from its progress")
        self._require_canonical(progress)
        if progress.handoff is None or len(progress.state.pending_actions) != 1:
            raise ValueError("intervention submission requires one exact pending handoff")
        if (
            not isinstance(action_result, ActionResult)
            or action_result.action != progress.handoff.action
        ):
            raise ValueError("implementation result does not match the exact pending action")
        ImplementationResultValidator().validate(progress.state, action_result)
        submitted = RuntimeEngine.submit(progress.state, action_result)
        if submitted.transition is None:
            raise ValueError("intervention workflow does not accept duplicate submissions")
        resumed = self.resume(
            progress.intervention,
            submitted.state,
            current_snapshot=current_snapshot,
        )
        return InterventionUpdate(
            progress=resumed.progress,
            transitions=(submitted.transition, *resumed.transitions),
        )

    def run_managed(
        self,
        progress: InterventionProgress,
        *,
        implementer: Implementer,
        current_snapshot: TargetSnapshot,
    ) -> InterventionUpdate:
        if not isinstance(implementer, Implementer):
            raise TypeError("managed intervention preparation requires an Implementer")
        self._require_current(progress.intervention, current_snapshot)
        if current_snapshot != progress.current_snapshot:
            raise ValueError("managed intervention currentness differs from its progress")
        self._require_canonical(progress)
        if progress.handoff is None:
            return InterventionUpdate(progress=progress, transitions=())
        result = implementer.implement(progress.handoff.action)
        return self.submit(
            progress,
            result,
            current_snapshot=current_snapshot,
        )


def prepare_intervention(
    intervention: InterventionSpec,
    *,
    current_snapshot: TargetSnapshot,
) -> InterventionProgress:
    """Return a complete candidate-only handoff without requiring an Implementer."""

    return (
        InterventionWorkflow()
        .start(
            intervention,
            current_snapshot=current_snapshot,
        )
        .progress
    )
