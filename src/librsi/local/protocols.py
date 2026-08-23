"""Replaceable contracts used by the standard-library local composition."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..records import ArtifactRef, TargetRef, TargetSnapshot
from ..runtime import Transition


@runtime_checkable
class ArtifactStore(Protocol):
    """Persist and retrieve exact artifact bytes."""

    def put(
        self,
        artifact_id: str,
        content: bytes,
        *,
        media_type: str | None = None,
    ) -> ArtifactRef: ...

    def get(self, artifact: ArtifactRef) -> bytes: ...


@runtime_checkable
class TransitionSink(Protocol):
    """Observe canonical transitions without gaining lifecycle authority."""

    def emit(self, transition: Transition) -> None: ...


@runtime_checkable
class WorkspaceInspector(Protocol):
    """Create an explicit local target and inspect its current snapshot."""

    def target(self, *, target_id: str | None = None, kind: str = "filesystem") -> TargetRef: ...

    def snapshot(self, target: TargetRef) -> TargetSnapshot: ...


def emit_transitions(sink: TransitionSink, transitions: Sequence[Transition]) -> None:
    """Emit one exact transition sequence through a replaceable observer."""

    if not isinstance(sink, TransitionSink):
        raise TypeError("transition emission requires a TransitionSink")
    if isinstance(transitions, (str, bytes, bytearray)) or not isinstance(transitions, Sequence):
        raise TypeError("transition emission requires a sequence")
    for transition in transitions:
        if not isinstance(transition, Transition):
            raise TypeError("transition emission requires Transition values")
        sink.emit(transition)
