"""Restartable complete improvement workflow over the canonical runtime."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..records import EvidenceRef, Outcome, TargetSnapshot
from ..runtime import ActionResult, Run, RunState, RuntimeEngine, Transition
from .actions import ImprovementCycleProvider, validate_cycle_action_result
from .policy import ImprovementPolicy, improvement_stop_reason
from .records import (
    ApplicationHandoff,
    ImprovementIteration,
    ImprovementRequest,
    ImprovementResult,
)
from .replay import (
    improvement_experiment_count,
    next_improvement_action,
    replay_improvement_state,
)


def improvement_outcome(result: ImprovementResult) -> Outcome:
    """Derive the canonical terminal Outcome owned by improvement semantics."""

    if not isinstance(result, ImprovementResult):
        raise TypeError("improvement outcome requires an ImprovementResult")
    evidence = {
        item.root: EvidenceRef.from_evidence(item)
        for iteration in result.iterations
        for item in iteration.proposal.investigation.evidence
    }
    return Outcome(
        intent=result.request.ref,
        status=result.disposition,
        target_snapshot=result.request.baseline,
        conclusions=(result.stop_reason,),
        evidence_refs=tuple(evidence[key] for key in sorted(evidence)),
        unresolved=() if result.disposition == "improved" else ("no candidate accepted",),
        next_actions=(
            ("submit the explicit application handoff to an authorized Applier",)
            if result.handoff is not None
            else ("revise the goal, evidence, or search budget before another run",)
        ),
        lineage=(result.ref, *result.lineage),
    )


@dataclass(frozen=True)
class ImprovementProgress:
    request: ImprovementRequest
    current_snapshot: TargetSnapshot
    state: RunState
    iterations: tuple[ImprovementIteration, ...] = ()
    result: ImprovementResult | None = None

    @property
    def terminal(self) -> bool:
        return self.state.status in {"completed", "failed", "cancelled"}

    def __post_init__(self) -> None:
        if self.current_snapshot != self.request.baseline:
            raise ValueError("improvement progress is stale for the authoritative target")


@dataclass(frozen=True)
class ImprovementUpdate:
    progress: ImprovementProgress
    transitions: tuple[Transition, ...]


class ImprovementWorkflow:
    """Compose hypothesis investigation and comparative testing without applying changes."""

    def __init__(self) -> None:
        self._policy = ImprovementPolicy()

    @staticmethod
    def _run(request: ImprovementRequest) -> Run:
        return request.canonical_run()

    @staticmethod
    def _result(
        request: ImprovementRequest,
        state: RunState,
        iterations: tuple[ImprovementIteration, ...],
        *,
        stop_reason: str,
    ) -> ImprovementResult:
        terminal = iterations[-1]
        improved = terminal.selection.disposition != "none-accepted"
        handoff = None
        if improved:
            handoff = ApplicationHandoff(
                request=request,
                selection=terminal.selection,
                current_snapshot=request.baseline,
                governance_requirement=request.governance_requirement,
                lineage=(
                    request.ref,
                    terminal.selection.ref,
                    request.baseline.ref,
                    *(
                        (request.governance_requirement.ref,)
                        if request.governance_requirement is not None
                        else ()
                    ),
                    *terminal.selection.selected,
                ),
            )
        return ImprovementResult(
            request=request,
            disposition="improved" if improved else "no-useful-improvement",
            iterations=iterations,
            settled_state=state,
            handoff=handoff,
            stop_reason=stop_reason,
            budget_usage={
                "iterations": len(iterations),
                "experiments": improvement_experiment_count(iterations),
                "retries": state.retry_count,
                "resource_units": state.resource_usage.get("units", 0.0),
            },
            lineage=(
                request.ref,
                state.ref,
                *(item.ref for item in iterations),
                *((handoff.ref,) if handoff is not None else ()),
            ),
        )

    @staticmethod
    def _outcome(result: ImprovementResult) -> Outcome:
        return improvement_outcome(result)

    @staticmethod
    def _require_current(request: ImprovementRequest, current_snapshot: TargetSnapshot) -> None:
        if type(current_snapshot) is not TargetSnapshot or current_snapshot != request.baseline:
            raise ValueError("improvement requires the exact current target snapshot")

    def start(
        self, request: ImprovementRequest, *, current_snapshot: TargetSnapshot
    ) -> ImprovementUpdate:
        self._policy.validate_request(request)
        self._require_current(request, current_snapshot)
        started = RuntimeEngine.start(self._run(request))
        assert started.transition is not None
        resumed = self.resume(
            request,
            started.state,
            current_snapshot=current_snapshot,
        )
        return ImprovementUpdate(
            resumed.progress,
            (started.transition, *resumed.transitions),
        )

    def resume(
        self,
        request: ImprovementRequest,
        state: RunState,
        *,
        current_snapshot: TargetSnapshot,
    ) -> ImprovementUpdate:
        """Reconcile and continue from any exact persisted runtime transition."""

        self._policy.validate_request(request)
        self._require_current(request, current_snapshot)
        if not isinstance(state, RunState) or state.run != self._run(request):
            raise ValueError("persisted improvement run envelope has drifted")
        settled_state, iterations = replay_improvement_state(request, state)
        if state.status == "waiting":
            if len(state.pending_actions) != 1:
                raise ValueError("waiting improvement state requires one pending action")
            return ImprovementUpdate(
                ImprovementProgress(request, current_snapshot, state, iterations),
                (),
            )
        if state.status in {"failed", "cancelled"}:
            return ImprovementUpdate(
                ImprovementProgress(request, current_snapshot, state, iterations),
                (),
            )
        if state.status == "completed":
            if state.outcome is None or not state.outcome.conclusions or not iterations:
                raise ValueError("completed improvement state lost its exact outcome")
            result = self._result(
                request,
                settled_state,
                iterations,
                stop_reason=state.outcome.conclusions[0],
            )
            if state.outcome != self._outcome(result):
                raise ValueError("completed improvement outcome has drifted")
            return ImprovementUpdate(
                ImprovementProgress(request, current_snapshot, state, iterations, result),
                (),
            )

        if state.status != "active" or state.pending_actions:
            raise ValueError("persisted improvement state has an unsupported live frontier")
        stop_reason = improvement_stop_reason(
            request,
            iterations,
            resource_units=state.resource_usage.get("units", 0.0),
        )
        if stop_reason is None:
            action = next_improvement_action(request, state, iterations)
            requested = RuntimeEngine.request(state, action)
            assert requested.transition is not None
            return ImprovementUpdate(
                ImprovementProgress(request, current_snapshot, requested.state, iterations),
                (requested.transition,),
            )
        complete_result = self._result(
            request,
            settled_state,
            iterations,
            stop_reason=stop_reason,
        )
        completed = RuntimeEngine.complete(state, self._outcome(complete_result))
        assert completed.transition is not None
        return ImprovementUpdate(
            ImprovementProgress(
                request,
                current_snapshot,
                completed.state,
                iterations,
                complete_result,
            ),
            (completed.transition,),
        )

    def _require_canonical(self, progress: ImprovementProgress) -> None:
        resumed = self.resume(
            progress.request,
            progress.state,
            current_snapshot=progress.current_snapshot,
        )
        if resumed.transitions or resumed.progress != progress:
            raise ValueError("improvement progress is not the canonical persisted frontier")

    def submit(
        self,
        progress: ImprovementProgress,
        result: ActionResult,
        *,
        current_snapshot: TargetSnapshot,
    ) -> ImprovementUpdate:
        if not isinstance(progress, ImprovementProgress):
            raise TypeError("improvement submission requires ImprovementProgress")
        self._require_current(progress.request, current_snapshot)
        if current_snapshot != progress.current_snapshot:
            raise ValueError("improvement currentness differs from its persisted frontier")
        self._require_canonical(progress)
        if progress.terminal or len(progress.state.pending_actions) != 1:
            raise ValueError("improvement submission requires one live pending action")
        if result.action != progress.state.pending_actions[0]:
            raise ValueError("improvement result does not match the pending action")
        validate_cycle_action_result(result)
        submitted = RuntimeEngine.submit(progress.state, result)
        assert submitted.transition is not None
        resumed = self.resume(
            progress.request,
            submitted.state,
            current_snapshot=current_snapshot,
        )
        return ImprovementUpdate(
            resumed.progress,
            (submitted.transition, *resumed.transitions),
        )

    def run_managed(
        self,
        progress: ImprovementProgress,
        *,
        provider: ImprovementCycleProvider,
        current_snapshot: TargetSnapshot,
    ) -> ImprovementUpdate:
        resumed = self.resume(
            progress.request,
            progress.state,
            current_snapshot=current_snapshot,
        )
        if not resumed.transitions and resumed.progress != progress:
            raise ValueError("managed improvement progress is not canonical")
        transitions: list[Transition] = list(resumed.transitions)
        current = resumed.progress
        while not current.terminal:
            self._require_canonical(current)
            action = current.state.pending_actions[0]
            claim = provider.resource_claim(action)
            if (
                isinstance(claim, bool)
                or not isinstance(claim, (int, float))
                or not math.isfinite(float(claim))
                or float(claim) != action.budget_reservation.get("units", 0.0)
            ):
                raise ValueError("provider resource claim must equal the persisted per-attempt cap")
            result = provider.improve_cycle(action)
            if result.resource_usage.get("units", 0.0) > float(claim):
                raise ValueError("provider exceeded its declared resource claim")
            update = self.submit(
                current,
                result,
                current_snapshot=current_snapshot,
            )
            transitions.extend(update.transitions)
            current = update.progress
        return ImprovementUpdate(current, tuple(transitions))


def improve(
    request: ImprovementRequest,
    *,
    provider: ImprovementCycleProvider,
    current_snapshot: TargetSnapshot,
) -> ImprovementResult:
    """Run the complete bounded lifecycle without manual policy sequencing."""

    workflow = ImprovementWorkflow()
    completed = workflow.run_managed(
        workflow.start(request, current_snapshot=current_snapshot).progress,
        provider=provider,
        current_snapshot=current_snapshot,
    )
    if completed.progress.result is None:
        raise RuntimeError("improvement run ended without an ImprovementResult")
    return completed.progress.result
