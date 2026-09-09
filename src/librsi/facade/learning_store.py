"""Consumer-owned persistence for serialized adaptive strategy operation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from ..records import Observation, SemanticRecord, TargetRef, TargetSnapshot
from ..runtime import RuntimeStore


@runtime_checkable
class LearningStore(Protocol):
    """Bindings for one profile, independent of its storage backend.

    The host serializes all profile use, including effects and recovery. A shared
    backend must fence that ownership; implementing this protocol alone does not
    provide distributed coordination. Reads return current canonical records and
    successful writes are durable before the next workflow action can execute.
    Runtime history remains owned by the existing replay-checked RuntimeStore.
    The caller owns connections and their lifetime; the loop does not close them.
    """

    @property
    def runtime(self) -> RuntimeStore:
        """The same durable runtime history after reopening this profile."""
        ...

    @property
    def target(self) -> TargetRef:
        """Stable profile identity shared by all strategy snapshots."""
        ...

    @property
    def active(self) -> TargetSnapshot:
        """Current strategy, bound to this profile's stable target identity."""
        ...

    @property
    def pending_pass(self) -> str | None:
        """The unfinished pass, if any, with its exact input binding retained."""
        ...

    @property
    def pass_ids(self) -> tuple[str, ...]:
        """All recorded pass identities, including completed and failed passes."""
        ...

    def snapshot(self, configuration: Mapping[str, Any]) -> TargetSnapshot:
        """Canonicalize a nonempty configuration for this profile without applying it."""
        ...

    def feedback(self, task_id: str | None = None) -> tuple[Observation, ...]:
        """Return exact task/profile-bound feedback in its stable recorded order."""
        ...

    def record_feedback(self, observation: Observation) -> Observation:
        """Record current-strategy feedback; identical repeats reuse the record.

        Reject conflicting task identities, missing producing-strategy lineage,
        stale strategies, and new feedback while a learning pass is pending.
        """
        ...

    def pass_input(self, pass_id: str) -> Observation | None:
        """Return the exact immutable profile-bound input, or None if absent."""
        ...

    def begin_pass(self, inputs: Observation) -> None:
        """Persist inputs and pending identity together against the current strategy.

        Reuse identical inputs; reject conflicting identities, stale baselines,
        or another pending pass.
        """
        ...

    def cached(self, pass_id: str, key: str) -> SemanticRecord | None:
        """Load and validate a completed record; return None only when absent."""
        ...

    def remember(self, pass_id: str, key: str, record: SemanticRecord) -> None:
        """Persist completed work for the pending pass; exact repeats are no-ops.

        Reject replacement of an existing record and new writes to a nonpending pass.
        """
        ...

    def finish_pass(self, pass_id: str, result: SemanticRecord) -> None:
        """Persist the native terminal result before clearing the pending identity.

        This operation is recoverable and idempotent; storage does not derive or
        grant acceptance independently of the canonical workflows.
        """
        ...

    def apply_snapshot(
        self,
        *,
        expected: TargetSnapshot,
        replacement: TargetSnapshot,
        effect_root: str,
    ) -> TargetSnapshot:
        """Atomically compare-and-swap strategy and exact canonical action identity.

        Require a pending pass and same-profile snapshots. Reject a stale expected
        snapshot. An identical effect may return its replacement after recovery,
        but must reject a recorded effect whose actual strategy has diverged.
        The workflow supplies authority; this method must not manufacture it.
        """
        ...
