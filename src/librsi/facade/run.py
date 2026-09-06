"""Stateful Python convenience around the canonical immutable workflow frontiers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeAlias

from ..capabilities import CapabilityRegistry, DispatchPlan
from ..errors import RSICapabilityError
from ..improvement import (
    ImprovementCycleProvider,
    ImprovementProgress,
    ImprovementResult,
    ImprovementUpdate,
    ImprovementWorkflow,
)
from ..investigation import (
    InvestigationProgress,
    InvestigationResult,
    InvestigationUpdate,
    InvestigationWorkflow,
)
from ..knowledge import KnowledgeStore
from ..records import TargetSnapshot
from ..rsi import RSIProgress, RSIResult, RSIUpdate, RSIWorkflow
from ..runtime import TERMINAL_RUN_STATUSES, Action, ActionResult, RunState, Transition
from ..validation import (
    ValidationProgress,
    ValidationResult,
    ValidationUpdate,
    ValidationWorkflow,
)

FacadeProgress: TypeAlias = (
    ValidationProgress | InvestigationProgress | ImprovementProgress | RSIProgress
)
FacadeResult: TypeAlias = ValidationResult | InvestigationResult | ImprovementResult | RSIResult
FacadeUpdate: TypeAlias = ValidationUpdate | InvestigationUpdate | ImprovementUpdate | RSIUpdate
FacadeWorkflow: TypeAlias = (
    ValidationWorkflow | InvestigationWorkflow | ImprovementWorkflow | RSIWorkflow
)
TransitionRecorder: TypeAlias = Callable[[Sequence[Transition]], None]


class LibRSIRun:
    """Mutable ergonomic handle whose semantic state remains canonical and immutable."""

    def __init__(
        self,
        *,
        workflow: FacadeWorkflow,
        progress: FacadeProgress,
        registry: CapabilityRegistry,
        record_transitions: TransitionRecorder,
        knowledge_store: KnowledgeStore | None = None,
        current_snapshot: TargetSnapshot | None = None,
        improvement_provider: ImprovementCycleProvider | None = None,
    ) -> None:
        if not isinstance(
            workflow,
            (ValidationWorkflow, InvestigationWorkflow, ImprovementWorkflow, RSIWorkflow),
        ):
            raise TypeError("facade run requires a canonical workflow")
        if not isinstance(
            progress,
            (ValidationProgress, InvestigationProgress, ImprovementProgress, RSIProgress),
        ):
            raise TypeError("facade run requires canonical progress")
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("facade run requires a CapabilityRegistry")
        if not callable(record_transitions):
            raise TypeError("facade run requires a transition recorder")
        if current_snapshot is not None and not isinstance(current_snapshot, TargetSnapshot):
            raise TypeError("facade current snapshot must be a TargetSnapshot")
        if knowledge_store is not None and not isinstance(knowledge_store, KnowledgeStore):
            raise TypeError("facade knowledge store must implement KnowledgeStore")
        if improvement_provider is not None and not isinstance(
            improvement_provider, ImprovementCycleProvider
        ):
            raise TypeError("facade improvement provider is invalid")
        self._workflow = workflow
        self._progress = progress
        self._registry = registry
        self._record_transitions = record_transitions
        self._knowledge_store = knowledge_store
        self._current_snapshot = current_snapshot
        self._improvement_provider = improvement_provider
        self._transitions: list[Transition] = []

    @property
    def progress(self) -> FacadeProgress:
        return self._progress

    @property
    def state(self) -> RunState:
        return self._progress.state

    @property
    def result(self) -> FacadeResult | None:
        return self._progress.result

    @property
    def terminal(self) -> bool:
        return self.state.status in TERMINAL_RUN_STATUSES

    @property
    def actions(self) -> tuple[Action, ...]:
        return self.state.pending_actions

    @property
    def transitions(self) -> tuple[Transition, ...]:
        return tuple(self._transitions)

    @property
    def current_snapshot(self) -> TargetSnapshot | None:
        return self._current_snapshot

    @property
    def plan(self) -> DispatchPlan:
        return self._registry.plan(self.state)

    def next(self) -> Action | None:
        """Return the one canonical pending action, or ``None`` when terminal."""

        if self.terminal:
            return None
        if len(self.actions) != 1:
            raise ValueError("facade stepping requires exactly one pending action")
        return self.actions[0]

    def _accept(self, update: FacadeUpdate) -> None:
        self._record_transitions(update.transitions)
        self._transitions.extend(update.transitions)
        self._progress = update.progress
        result = update.progress.result
        authoritative = getattr(result, "authoritative_snapshot", None)
        if isinstance(authoritative, TargetSnapshot):
            self._current_snapshot = authoritative

    def submit(
        self,
        result: ActionResult,
        *,
        authority: str = "external",
        current_snapshot: TargetSnapshot | None = None,
    ) -> LibRSIRun:
        """Submit one host result through the exact underlying workflow."""

        if not isinstance(result, ActionResult):
            raise TypeError("facade submission requires an ActionResult")
        if result.action != self.next():
            raise ValueError("facade result does not match the exact pending action")
        if current_snapshot is not None and not isinstance(current_snapshot, TargetSnapshot):
            raise TypeError("facade submission snapshot must be a TargetSnapshot")
        observed = self._current_snapshot if current_snapshot is None else current_snapshot
        progress = self._progress
        if isinstance(progress, ValidationProgress):
            assert isinstance(self._workflow, ValidationWorkflow)
            update: FacadeUpdate = self._workflow.submit(
                progress,
                result,
                knowledge_store=self._knowledge_store,
            )
        elif isinstance(progress, InvestigationProgress):
            assert isinstance(self._workflow, InvestigationWorkflow)
            update = self._workflow.submit(
                progress,
                result,
                knowledge_store=self._knowledge_store,
            )
        elif isinstance(progress, ImprovementProgress):
            assert isinstance(self._workflow, ImprovementWorkflow)
            if observed is None:
                raise ValueError("improvement submission requires a current snapshot")
            update = self._workflow.submit(progress, result, current_snapshot=observed)
        else:
            assert isinstance(progress, RSIProgress) and isinstance(self._workflow, RSIWorkflow)
            if self._current_snapshot is None or observed is None:
                raise ValueError("RSI submission requires prior and current snapshots")
            update = self._workflow.submit(
                progress,
                result,
                prior_snapshot=self._current_snapshot,
                current_snapshot=observed,
                authority=authority,
            )
        self._current_snapshot = observed
        self._accept(update)
        return self

    def run(self) -> LibRSIRun:
        """Execute configured automatic work and stop at an explicit handoff."""

        if self.terminal:
            return self
        if isinstance(self._progress, ImprovementProgress):
            if self._improvement_provider is None:
                raise RSICapabilityError("managed improvement requires an ImprovementCycleProvider")
            if self._current_snapshot is None:
                raise ValueError("managed improvement requires a current snapshot")
            assert isinstance(self._workflow, ImprovementWorkflow)
            self._workflow.run_managed(
                self._progress,
                provider=self._improvement_provider,
                current_snapshot=self._current_snapshot,
                on_update=self._accept,
            )
            return self
        if isinstance(self._progress, RSIProgress):
            if self._current_snapshot is None:
                raise ValueError("managed RSI requires a current snapshot")
            assert isinstance(self._workflow, RSIWorkflow)
            rsi_update = self._workflow.run_managed(
                self._progress,
                current_snapshot=self._current_snapshot,
            )
            self._accept(rsi_update)
            return self
        while not self.terminal:
            action = self.next()
            assert action is not None
            resolution = self._registry.resolve(action)
            if resolution.posture != "automatic":
                break
            self.submit(self._registry.execute(resolution), authority="automatic")
        return self
