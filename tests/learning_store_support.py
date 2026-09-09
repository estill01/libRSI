"""A consumer adapter exposing only the public persistence contract.

The local backend supplies durable test data, but the adapter is not its subclass
and exposes none of its directory, artifact, or private binding implementation.
This exercises substitution, not qualification of a distributed database backend.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from librsi import (
    LearningStore,
    LocalLearningStore,
    Observation,
    SemanticRecord,
    TargetRef,
    TargetSnapshot,
)
from librsi.runtime import RuntimeStore


class ConsumerLearningStore:
    def __init__(
        self,
        directory: str | Path,
        *,
        profile_id: str,
        initial_configuration: Mapping[str, Any] | None = None,
    ) -> None:
        self._backend = LocalLearningStore(
            directory, profile_id=profile_id, initial_configuration=initial_configuration
        )
        self.runtime: RuntimeStore = self._backend.runtime

    def __enter__(self) -> ConsumerLearningStore:
        return self

    def __exit__(self, *args: object) -> None:
        self._backend.close()

    @property
    def active(self) -> TargetSnapshot:
        return self._backend.active

    @property
    def target(self) -> TargetRef:
        return self._backend.target

    @property
    def pending_pass(self) -> str | None:
        return self._backend.pending_pass

    @property
    def pass_ids(self) -> tuple[str, ...]:
        return self._backend.pass_ids

    def snapshot(self, configuration: Mapping[str, Any]) -> TargetSnapshot:
        return self._backend.snapshot(configuration)

    def feedback(self, task_id: str | None = None) -> tuple[Observation, ...]:
        return self._backend.feedback(task_id)

    def record_feedback(self, observation: Observation) -> Observation:
        return self._backend.record_feedback(observation)

    def pass_input(self, pass_id: str) -> Observation | None:
        return self._backend.pass_input(pass_id)

    def begin_pass(self, inputs: Observation) -> None:
        self._backend.begin_pass(inputs)

    def cached(self, pass_id: str, key: str) -> SemanticRecord | None:
        return self._backend.cached(pass_id, key)

    def remember(self, pass_id: str, key: str, record: SemanticRecord) -> None:
        self._backend.remember(pass_id, key, record)

    def finish_pass(self, pass_id: str, result: SemanticRecord) -> None:
        self._backend.finish_pass(pass_id, result)

    def apply_snapshot(
        self,
        *,
        expected: TargetSnapshot,
        replacement: TargetSnapshot,
        effect_root: str,
    ) -> TargetSnapshot:
        return self._backend.apply_snapshot(
            expected=expected, replacement=replacement, effect_root=effect_root
        )


def as_learning_store(store: ConsumerLearningStore) -> LearningStore:
    """Static as well as runtime compatibility; no nominal inheritance or cast."""
    return store
