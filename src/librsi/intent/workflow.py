"""Restartable typed and proposal-backed goal operationalization workflow."""

from __future__ import annotations

from dataclasses import dataclass

from ..records import Outcome, TargetSnapshot
from ..runtime import Action, ActionResult, RunState, RuntimeEngine, Transition
from ..targets import TargetPolicy
from .actions import (
    OperationalizationResultValidator,
    make_operationalization_action,
    operationalization_proposal_from_result,
)
from .policy import OperationalizationPolicy
from .records import (
    EvaluationContract,
    OperationalizationHandoff,
    OperationalizationRequest,
    OperationalizationResult,
)


def _outcome(result: OperationalizationResult) -> Outcome:
    return Outcome(
        intent=result.request.goal.ref,
        status=result.disposition,
        target_snapshot=result.request.current_snapshot,
        next_actions=result.missing_facts,
        lineage=(
            result.ref,
            result.request.ref,
            result.request.goal.ref,
            result.request.current_snapshot.ref,
            *((result.contract.ref,) if result.contract is not None else ()),
        ),
    )


def _require_current(
    request: OperationalizationRequest,
    current_snapshot: TargetSnapshot,
) -> None:
    if type(current_snapshot) is not TargetSnapshot:
        raise TypeError("operationalization requires an exact current TargetSnapshot")
    TargetPolicy().require_current(request.current_snapshot, current_snapshot)


def _require_canonical_runtime_state(
    request: OperationalizationRequest,
    state: RunState,
) -> tuple[Action, OperationalizationResult | None]:
    action = make_operationalization_action(request)
    started = RuntimeEngine.start(request.canonical_run()).state
    if state.status == "active" and not state.actions:
        if state != started:
            raise ValueError("operationalization state does not match canonical runtime replay")
        return action, None

    waiting = RuntimeEngine.request(started, action).state
    if not state.results:
        if state != waiting:
            raise ValueError("operationalization state does not match canonical runtime replay")
        return action, None

    if len(state.results) != 1:
        raise ValueError("operationalization runtime must contain one exact proposal result")
    envelope = state.results[0]
    OperationalizationResultValidator().validate(waiting, envelope)
    submitted = RuntimeEngine.submit(waiting, envelope).state
    semantic_result: OperationalizationResult | None = None
    expected_state = submitted
    if envelope.disposition == "succeeded":
        proposal = operationalization_proposal_from_result(envelope)
        semantic_result = OperationalizationPolicy().accept_proposal(request, proposal)
        if state.status == "completed":
            expected_state = RuntimeEngine.complete(submitted, _outcome(semantic_result)).state
    if state != expected_state:
        raise ValueError("operationalization state does not match canonical runtime replay")
    return action, semantic_result


@dataclass(frozen=True)
class OperationalizationProgress:
    """Projection of the exact canonical operationalization runtime frontier."""

    request: OperationalizationRequest
    current_snapshot: TargetSnapshot
    state: RunState
    handoff: OperationalizationHandoff | None = None
    result: OperationalizationResult | None = None
    failure_result: ActionResult | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not OperationalizationRequest:
            raise TypeError("operationalization progress requires an exact request")
        _require_current(self.request, self.current_snapshot)
        if not isinstance(self.state, RunState):
            raise TypeError("operationalization progress requires a RunState")
        if self.state.run != self.request.canonical_run():
            raise ValueError("operationalization progress runtime does not match its request")
        action, runtime_result = _require_canonical_runtime_state(self.request, self.state)

        if self.state.status == "waiting":
            expected_handoff = OperationalizationHandoff(
                request=self.request,
                action=action,
                lineage=(self.request.ref, action.ref),
            )
            if self.handoff != expected_handoff:
                raise ValueError("waiting operationalization lost its exact handoff")
            if self.result is not None or self.failure_result is not None:
                raise ValueError("waiting operationalization cannot contain a result")
        elif self.handoff is not None:
            raise ValueError("only waiting operationalization may expose a handoff")

        if self.state.status == "completed":
            if type(self.result) is not OperationalizationResult:
                raise ValueError("completed operationalization requires its exact result")
            if self.result != runtime_result:
                raise ValueError("completed operationalization result has drifted")
            if self.failure_result is not None:
                raise ValueError("completed operationalization cannot contain a failure")
        elif self.result is not None:
            raise ValueError("operationalization results require completed runtime state")

        if self.state.status in {"failed", "cancelled"}:
            settled_result = self.state.results[0]
            if self.failure_result != settled_result:
                raise ValueError("terminal operationalization requires its exact failure result")
        elif self.failure_result is not None:
            raise ValueError("failure results require failed or cancelled runtime state")
        if self.state.status not in {"waiting", "completed", "failed", "cancelled"}:
            raise ValueError("operationalization progress requires a waiting or terminal state")


@dataclass(frozen=True)
class OperationalizationUpdate:
    progress: OperationalizationProgress
    transitions: tuple[Transition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.progress, OperationalizationProgress):
            raise TypeError("operationalization updates require OperationalizationProgress")
        transitions = tuple(self.transitions)
        if any(not isinstance(item, Transition) for item in transitions):
            raise TypeError("operationalization updates require Transition values")
        object.__setattr__(self, "transitions", transitions)


class OperationalizationWorkflow:
    """Canonical runtime owner; proposal backends never control lifecycle state."""

    __slots__ = ()

    def operationalize_typed(
        self,
        request: OperationalizationRequest,
        contract: EvaluationContract,
        *,
        current_snapshot: TargetSnapshot,
    ) -> OperationalizationResult:
        _require_current(request, current_snapshot)
        return OperationalizationPolicy().accept_typed(request, contract)

    def start(
        self,
        request: OperationalizationRequest,
        *,
        current_snapshot: TargetSnapshot,
    ) -> OperationalizationUpdate:
        if type(request) is not OperationalizationRequest:
            raise TypeError("operationalization start requires an exact request")
        _require_current(request, current_snapshot)
        started = RuntimeEngine.start(request.canonical_run())
        if started.transition is None:  # pragma: no cover - runtime invariant
            raise RuntimeError("operationalization start lost its transition")
        resumed = self.resume(request, started.state, current_snapshot=current_snapshot)
        return OperationalizationUpdate(
            progress=resumed.progress,
            transitions=(started.transition, *resumed.transitions),
        )

    def resume(
        self,
        request: OperationalizationRequest,
        state: RunState,
        *,
        current_snapshot: TargetSnapshot,
    ) -> OperationalizationUpdate:
        if type(request) is not OperationalizationRequest:
            raise TypeError("operationalization resume requires an exact request")
        if not isinstance(state, RunState):
            raise TypeError("operationalization resume requires a RunState")
        _require_current(request, current_snapshot)
        if state.run != request.canonical_run():
            raise ValueError("persisted operationalization run envelope has drifted")
        action, semantic_result = _require_canonical_runtime_state(request, state)

        if state.status == "waiting":
            return OperationalizationUpdate(
                progress=OperationalizationProgress(
                    request=request,
                    current_snapshot=current_snapshot,
                    state=state,
                    handoff=OperationalizationHandoff(
                        request=request,
                        action=action,
                        lineage=(request.ref, action.ref),
                    ),
                ),
                transitions=(),
            )
        if state.status in {"failed", "cancelled"}:
            return OperationalizationUpdate(
                progress=OperationalizationProgress(
                    request=request,
                    current_snapshot=current_snapshot,
                    state=state,
                    failure_result=state.results[0],
                ),
                transitions=(),
            )
        if state.status == "completed":
            if semantic_result is None:  # pragma: no cover - canonical replay invariant
                raise RuntimeError("completed operationalization lost its result")
            return OperationalizationUpdate(
                progress=OperationalizationProgress(
                    request=request,
                    current_snapshot=current_snapshot,
                    state=state,
                    result=semantic_result,
                ),
                transitions=(),
            )
        if not state.actions:
            requested = RuntimeEngine.request(state, action)
            if requested.transition is None:  # pragma: no cover - runtime invariant
                raise RuntimeError("operationalization request lost its transition")
            return OperationalizationUpdate(
                progress=OperationalizationProgress(
                    request=request,
                    current_snapshot=current_snapshot,
                    state=requested.state,
                    handoff=OperationalizationHandoff(
                        request=request,
                        action=action,
                        lineage=(request.ref, action.ref),
                    ),
                ),
                transitions=(requested.transition,),
            )
        if semantic_result is None:  # pragma: no cover - canonical replay invariant
            raise RuntimeError("active operationalization lost its proposal result")
        completed = RuntimeEngine.complete(state, _outcome(semantic_result))
        if completed.transition is None:  # pragma: no cover - runtime invariant
            raise RuntimeError("operationalization completion lost its transition")
        return OperationalizationUpdate(
            progress=OperationalizationProgress(
                request=request,
                current_snapshot=current_snapshot,
                state=completed.state,
                result=semantic_result,
            ),
            transitions=(completed.transition,),
        )

    def _require_canonical(self, progress: OperationalizationProgress) -> None:
        if not isinstance(progress, OperationalizationProgress):
            raise TypeError("operationalization progress must be OperationalizationProgress")
        resumed = self.resume(
            progress.request,
            progress.state,
            current_snapshot=progress.current_snapshot,
        )
        if resumed.transitions or resumed.progress != progress:
            raise ValueError("operationalization progress is not the canonical persisted frontier")

    def submit(
        self,
        progress: OperationalizationProgress,
        action_result: ActionResult,
        *,
        current_snapshot: TargetSnapshot,
    ) -> OperationalizationUpdate:
        if not isinstance(progress, OperationalizationProgress):
            raise TypeError("operationalization submission requires OperationalizationProgress")
        if action_result in progress.state.results:
            OperationalizationResultValidator().validate(progress.state, action_result)
            self._require_canonical(progress)
            return OperationalizationUpdate(progress=progress, transitions=())
        _require_current(progress.request, current_snapshot)
        if current_snapshot != progress.current_snapshot:
            raise ValueError("operationalization submission currentness differs from progress")
        self._require_canonical(progress)
        if progress.handoff is None:
            raise ValueError("operationalization has no pending proposal handoff")
        validator = OperationalizationResultValidator()
        validator.require_current_frontier(progress.state, action_result.action, current_snapshot)
        validator.validate(progress.state, action_result)
        submitted = RuntimeEngine.submit(progress.state, action_result)
        if submitted.transition is None:  # pragma: no cover - runtime invariant
            raise RuntimeError("operationalization submission lost its transition")
        resumed = self.resume(
            progress.request,
            submitted.state,
            current_snapshot=current_snapshot,
        )
        return OperationalizationUpdate(
            progress=resumed.progress,
            transitions=(submitted.transition, *resumed.transitions),
        )
