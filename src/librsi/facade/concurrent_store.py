"""Opt-in persistence contract for serving while a learning pass is running."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from ..records import Metric, Observation, TargetSnapshot
from .learning_records import LearningCase, TaskMeasurement
from .learning_store import LearningStore


@runtime_checkable
class ConcurrentLearningStore(LearningStore, Protocol):
    """One learning owner with independently executing, snapshot-pinned tasks.

    This is an explicit extension, not a concurrency guarantee for LearningStore.
    All profile operations must be linearizable and completed writes durable.
    Model execution happens outside the store's short state transactions. The
    learning owner excludes other learning/history operations across the whole
    workflow, without excluding task admission or completion.

    ``active`` retains the native application's current pointer, including an
    applied candidate awaiting verification. ``serving_snapshot`` remains the
    last qualified configuration until the native terminal result is committed.
    Initial configuration is the host-supplied starting serving revision.
    """

    @property
    def serving_snapshot(self) -> TargetSnapshot:
        """Resolve a coherent qualified snapshot even during application/recovery."""
        ...

    def learning_owner(self) -> AbstractContextManager[None]:
        """Fence a complete learning/history call; reject an overlapping owner.

        Release ownership on every exit, including interruption. A pending pass
        remains durable after an interruption; this lock is not its completion.
        """
        ...

    def admit_task(self, case: LearningCase, *, adapter_id: str, metric: Metric) -> Observation:
        """Persist an immutable learning.task-admission before external execution.

        Bind task_id, exact case, adapter/scoring identities and serving snapshot.
        Reuse an identical admission, retaining its original snapshot after a
        promotion or restart. Reject input/scoring conflicts under the same ID.
        """
        ...

    def complete_task(self, admission: Observation, measurement: TaskMeasurement) -> Observation:
        """Record learning.feedback against the exact durable task admission.

        An admitted old snapshot remains valid after promotion. Keep its actual
        producing revision and source lineage. Identical completion is idempotent;
        conflicting completion rejects. New feedback cannot change a pending
        pass's frozen inputs. This does not promise exactly-once external calls.
        The inherited record_feedback method keeps its stricter legacy contract.
        """
        ...
