"""Structural lifecycle projection over caller-owned libRSI operations."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from embedded_service_contract import (  # type: ignore[import-untyped]
    Cancelled,
    CancelResult,
    EventRecord,
    Failed,
    HostContract,
    HostShape,
    InvalidCursorError,
    RunRef,
    RunState,
    RunStatus,
    Succeeded,
    UnknownRunError,
)

from .shared_handoff import load_shared_utilities

ObservationState = Literal["running", "succeeded", "failed"]
LifecycleExecutor = Callable[[object], "LifecycleObservation"]

_INSTANCES = itertools.count(1)


@dataclass(frozen=True, slots=True)
class LifecycleObservation:
    """Explicit caller mapping; the structural package infers no product semantics."""

    state: ObservationState
    value: object
    event: object

    def __post_init__(self) -> None:
        if self.state not in ("running", "succeeded", "failed"):
            raise ValueError("unsupported lifecycle observation state")

    @classmethod
    def running(cls, *, value: object, event: object) -> LifecycleObservation:
        return cls("running", value, event)

    @classmethod
    def succeeded(cls, *, value: object, event: object) -> LifecycleObservation:
        return cls("succeeded", value, event)

    @classmethod
    def failed(cls, *, error: object, event: object) -> LifecycleObservation:
        return cls("failed", error, event)


@dataclass(slots=True)
class _ProjectedRun:
    state: RunState
    value: object
    events: list[EventRecord[Any]]


class LifecycleProjection:
    """Adapt explicit observations to the accepted structure-only host protocol."""

    def __init__(self, *, shape: HostShape, lineage: str, execute: LifecycleExecutor) -> None:
        load_shared_utilities()
        if type(shape) is not HostShape:
            raise TypeError("lifecycle projection requires an exact HostShape")
        if type(lineage) is not str or not lineage:
            raise ValueError("lifecycle projection requires a lineage")
        if not callable(execute):
            raise TypeError("lifecycle projection requires a callable executor")
        self._contract = HostContract(
            shape=shape,
            process_owner_count=0 if shape is HostShape.EMBEDDED else 1,
        )
        self._lineage = lineage
        self._execute = execute
        self._instance = next(_INSTANCES)
        self._sequence = 0
        self._runs: dict[RunRef, _ProjectedRun] = {}

    @property
    def contract(self) -> HostContract:
        return self._contract

    def _require(self, ref: RunRef) -> _ProjectedRun:
        if type(ref) is not RunRef or ref not in self._runs:
            raise UnknownRunError("run reference is not owned by this lifecycle projection")
        return self._runs[ref]

    def start(self, request: object) -> RunRef:
        observation = self._execute(request)
        if type(observation) is not LifecycleObservation:
            raise TypeError("lifecycle executor must return an exact LifecycleObservation")
        self._sequence += 1
        ref = RunRef(
            f"librsi-{self._contract.shape.value}-{self._lineage}-{self._instance}-{self._sequence}"
        )
        state = RunState(observation.state)
        event = EventRecord(ref=ref, sequence=1, value=observation.event)
        self._runs[ref] = _ProjectedRun(state=state, value=observation.value, events=[event])
        return ref

    def status(self, ref: RunRef) -> RunStatus:
        run = self._require(ref)
        return RunStatus(ref=ref, state=run.state, last_event_sequence=len(run.events))

    def events(self, ref: RunRef, *, after_sequence: int = 0) -> tuple[EventRecord[Any], ...]:
        run = self._require(ref)
        if type(after_sequence) is not int or after_sequence < 0:
            raise InvalidCursorError("event cursor must be a non-negative integer")
        return tuple(run.events[after_sequence:])

    def cancel(self, ref: RunRef) -> CancelResult:
        run = self._require(ref)
        if run.state is not RunState.RUNNING:
            return CancelResult(ref=ref, state=run.state, changed=False)
        run.state = RunState.CANCELLED
        run.events.append(
            EventRecord(
                ref=ref,
                sequence=len(run.events) + 1,
                value={"operation": "cancel", "semantic_authority": "caller"},
            )
        )
        return CancelResult(ref=ref, state=run.state, changed=True)

    def outcome(self, ref: RunRef) -> Succeeded[Any] | Failed[Any] | Cancelled | None:
        run = self._require(ref)
        if run.state is RunState.RUNNING:
            return None
        if run.state is RunState.SUCCEEDED:
            return Succeeded(ref=ref, value=run.value)
        if run.state is RunState.FAILED:
            return Failed(ref=ref, error=run.value)
        return Cancelled(ref=ref)


def require_single_process_owner(contracts: Sequence[HostContract]) -> None:
    """Reject a composed topology unless exactly one service process owns execution."""

    if isinstance(contracts, (str, bytes, bytearray)) or not isinstance(contracts, Sequence):
        raise TypeError("host composition requires a sequence of HostContract values")
    items = tuple(contracts)
    if not items or any(type(item) is not HostContract for item in items):
        raise TypeError("host composition requires exact HostContract values")
    if sum(item.process_owner_count for item in items) != 1:
        raise ValueError("host composition requires exactly one process owner")
