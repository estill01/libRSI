"""Backend-neutral persistence contract for authoritative runtime history."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from .records import Event, RunState, Transition


@runtime_checkable
class RuntimeStore(Protocol):
    """Replaceable append-only storage for replayable semantic runs."""

    def append(self, transition: Transition) -> RunState: ...

    def load(self, run_id: str) -> RunState | None: ...

    def events(self, run_id: str) -> tuple[Event, ...]: ...

    def transitions(self, run_id: str) -> tuple[Transition, ...]: ...

    def resume(self, run_id: str) -> RunState | None: ...

    def close(self) -> None: ...


def persist_transitions(
    store: RuntimeStore,
    transitions: Sequence[Transition],
) -> RunState | None:
    """Append a bounded trace through only the replaceable store contract."""

    if not isinstance(store, RuntimeStore):
        raise TypeError("runtime persistence requires a RuntimeStore")
    if isinstance(transitions, (str, bytes, bytearray)) or not isinstance(transitions, Sequence):
        raise TypeError("runtime transitions must be a sequence")
    state: RunState | None = None
    for transition in transitions:
        if not isinstance(transition, Transition):
            raise TypeError("runtime transitions must contain Transition values")
        state = store.append(transition)
    return state
