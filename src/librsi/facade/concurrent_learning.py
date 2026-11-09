"""Concurrent ordinary tasks with one bounded native learning workflow."""

from __future__ import annotations

from collections.abc import Sequence

from ..capabilities import Reviewer
from ..reasoning import ReasoningBackend
from ..records import Observation
from .concurrent_store import ConcurrentLearningStore
from .learning import AdaptiveLoop
from .learning_history import LearningAttempt
from .learning_records import LearningAdapter, LearningCase, LearningPolicy, TaskMeasurement
from .learning_results import LearningResult


class ConcurrentAdaptiveLoop(AdaptiveLoop):
    """Serve pinned revisions while one learning pass runs in another host thread.

    The host owns scheduling, thread lifetime and external call limits. Adapters
    must isolate each configuration and support concurrent evaluations. A separate
    ``task_adapter`` can own serving resources, but must implement the same
    versioned execution/scoring semantics as the learning adapter. No background
    thread is started by this facade.
    """

    def __init__(
        self,
        store: ConcurrentLearningStore,
        *,
        adapter: LearningAdapter,
        proposer: ReasoningBackend,
        proposer_id: str,
        reviewer: Reviewer,
        reviewer_id: str,
        policy: LearningPolicy,
        task_adapter: LearningAdapter | None = None,
    ) -> None:
        if not isinstance(store, ConcurrentLearningStore):
            raise TypeError("concurrent adaptive operation requires a ConcurrentLearningStore")
        super().__init__(
            store,
            adapter=adapter,
            proposer=proposer,
            proposer_id=proposer_id,
            reviewer=reviewer,
            reviewer_id=reviewer_id,
            policy=policy,
        )
        serving_adapter = adapter if task_adapter is None else task_adapter
        if not isinstance(serving_adapter, LearningAdapter):
            raise TypeError("task adapter must implement LearningAdapter")
        if serving_adapter.adapter_id != adapter.adapter_id:
            raise ValueError("task and learning adapters must have the same adapter_id")
        serving_adapter.validate_configuration(store.serving_snapshot.state)
        self.concurrent_store = store
        self.task_adapter = serving_adapter

    def run_task(self, case: LearningCase) -> Observation:
        """Execute outside store locks, then retain the admitted producing revision.

        Reusing an already completed task returns its exact feedback. Concurrent
        duplicate calls or a crash before completion can repeat external work;
        adapters must supply any required external idempotency.
        """
        if not isinstance(case, LearningCase):
            raise TypeError("ordinary tasks require LearningCase")
        admission = self.concurrent_store.admit_task(
            case, adapter_id=self.adapter.adapter_id, metric=self.policy.metric
        )
        existing = self.concurrent_store.feedback(case.case_id)
        if existing:
            return existing[0]
        snapshot = admission.target_snapshot
        if snapshot is None or snapshot.target != self.store.target:
            raise ValueError("task admission must retain its producing strategy")
        measured = self.task_adapter.evaluate(snapshot.state, case)
        if not isinstance(measured, TaskMeasurement):
            raise TypeError("learning adapter must return TaskMeasurement")
        return self.concurrent_store.complete_task(admission, measured)

    def learn(
        self,
        pass_id: str,
        *,
        shadow_cases: Sequence[LearningCase],
        verification_cases: Sequence[LearningCase] | None = None,
        activate: bool = False,
        follow_up_to: str | None = None,
    ) -> LearningResult | None:
        """Run/resume one learner without holding the task store's state lock."""
        with self.concurrent_store.learning_owner():
            return super().learn(
                pass_id,
                shadow_cases=shadow_cases,
                verification_cases=verification_cases,
                activate=activate,
                follow_up_to=follow_up_to,
            )

    def history(self, *, limit: int = 2) -> tuple[LearningAttempt, ...]:
        """Read native runtime history only when no learning owner is executing."""
        with self.concurrent_store.learning_owner():
            return super().history(limit=limit)
