"""Canonical records for the durable semantic runtime."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..identity import FrozenMap
from ..records import (
    Outcome,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    register_record_type,
)

RUN_STATUSES = frozenset({"active", "waiting", "completed", "failed", "cancelled"})
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})
ACTION_RESULT_DISPOSITIONS = frozenset({"succeeded", "failed", "cancelled"})
RUNTIME_FAILURE_CLASSES = frozenset(
    {
        "transient",
        "invalid-result",
        "execution",
        "budget-exhausted",
        "cancelled",
        "internal",
    }
)
RUNTIME_EVENT_KINDS = frozenset(
    {
        "run_started",
        "action_requested",
        "action_succeeded",
        "action_failed",
        "action_cancelled",
        "run_completed",
        "run_failed",
        "run_cancelled",
    }
)


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _nonnegative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _positive_int(value: int, label: str) -> int:
    value = _nonnegative_int(value, label)
    if value == 0:
        raise ValueError(f"{label} must be positive")
    return value


def _refs(value: Sequence[RecordRef], label: str) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of RecordRef values")
    result = tuple(value)
    if any(not isinstance(item, RecordRef) for item in result):
        raise TypeError(f"{label} must contain RecordRef values")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must be unique")
    return result


def _amounts(value: Mapping[str, float], label: str) -> FrozenMap:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    normalized: dict[str, float] = {}
    for key, amount in value.items():
        name = _require_text(key, f"{label} key")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError(f"{label} values must be numbers")
        number = float(amount)
        if not math.isfinite(number) or number < 0.0:
            raise ValueError(f"{label} values must be finite and nonnegative")
        normalized[name] = number
    return FrozenMap(normalized)


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RunBudget(SemanticRecord):
    """Explicit limits that bound one semantic run."""

    RECORD_TYPE: ClassVar[str] = "run_budget"

    max_actions: int = 100
    max_failures: int = 10
    max_retries: int = 3
    resource_limits: Mapping[str, float] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "max_actions", _nonnegative_int(self.max_actions, "maximum actions")
        )
        object.__setattr__(
            self,
            "max_failures",
            _nonnegative_int(self.max_failures, "maximum failures"),
        )
        object.__setattr__(
            self, "max_retries", _nonnegative_int(self.max_retries, "maximum retries")
        )
        object.__setattr__(
            self,
            "resource_limits",
            _amounts(self.resource_limits, "resource limits"),
        )
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class Run(SemanticRecord):
    """Immutable identity and authority envelope for one execution."""

    RECORD_TYPE: ClassVar[str] = "run"

    run_id: str
    intent: RecordRef
    target_snapshot: TargetSnapshot | None = None
    budget: RunBudget = field(default_factory=RunBudget)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run id"))
        if not isinstance(self.intent, RecordRef):
            raise TypeError("run intent must be a RecordRef")
        if self.target_snapshot is not None and not isinstance(
            self.target_snapshot, TargetSnapshot
        ):
            raise TypeError("run target snapshot must be a TargetSnapshot")
        if not isinstance(self.budget, RunBudget):
            raise TypeError("run budget must be a RunBudget")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RuntimeFailure(SemanticRecord):
    """Structured failure whose classification can drive runtime policy."""

    RECORD_TYPE: ClassVar[str] = "runtime_failure"

    classification: str
    message: str
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        classification = _require_text(self.classification, "failure classification")
        if classification not in RUNTIME_FAILURE_CLASSES:
            raise ValueError(f"unsupported runtime failure classification: {classification}")
        object.__setattr__(self, "classification", classification)
        object.__setattr__(self, "message", _require_text(self.message, "failure message"))
        if type(self.retryable) is not bool:
            raise TypeError("failure retryable must be a boolean")
        if not isinstance(self.details, Mapping):
            raise TypeError("failure details must be a mapping")
        object.__setattr__(self, "details", FrozenMap(self.details))
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class Action(SemanticRecord):
    """One exact host-executable request emitted by the semantic runtime."""

    RECORD_TYPE: ClassVar[str] = "action"

    run: RecordRef
    action_id: str
    kind: str
    attempt: int = 1
    input_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    payload: Mapping[str, Any] = field(default_factory=FrozenMap)
    budget_reservation: Mapping[str, float] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        if not isinstance(self.run, RecordRef) or self.run.record_type != "run":
            raise TypeError("action run must reference a Run")
        object.__setattr__(self, "action_id", _require_text(self.action_id, "action id"))
        object.__setattr__(self, "kind", _require_text(self.kind, "action kind"))
        object.__setattr__(self, "attempt", _positive_int(self.attempt, "action attempt"))
        object.__setattr__(self, "input_refs", _refs(self.input_refs, "action inputs"))
        if not isinstance(self.payload, Mapping):
            raise TypeError("action payload must be a mapping")
        object.__setattr__(self, "payload", FrozenMap(self.payload))
        object.__setattr__(
            self,
            "budget_reservation",
            _amounts(self.budget_reservation, "action budget reservation"),
        )
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ActionResult(SemanticRecord):
    """Exactly correlated result for one Action."""

    RECORD_TYPE: ClassVar[str] = "action_result"

    action: Action
    disposition: str
    output_refs: tuple[RecordRef, ...] = field(default_factory=tuple)
    payload: Mapping[str, Any] = field(default_factory=FrozenMap)
    resource_usage: Mapping[str, float] = field(default_factory=FrozenMap)
    failure: RuntimeFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, Action):
            raise TypeError("action result must contain its exact Action")
        disposition = _require_text(self.disposition, "action result disposition")
        if disposition not in ACTION_RESULT_DISPOSITIONS:
            raise ValueError(f"unsupported action result disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "output_refs", _refs(self.output_refs, "action result outputs"))
        if not isinstance(self.payload, Mapping):
            raise TypeError("action result payload must be a mapping")
        object.__setattr__(self, "payload", FrozenMap(self.payload))
        object.__setattr__(
            self,
            "resource_usage",
            _amounts(self.resource_usage, "action result resource usage"),
        )
        if disposition == "succeeded" and self.failure is not None:
            raise ValueError("successful action results cannot contain a failure")
        if disposition != "succeeded" and not isinstance(self.failure, RuntimeFailure):
            raise ValueError("failed or cancelled action results require a failure")
        if (
            disposition == "cancelled"
            and self.failure is not None
            and self.failure.classification != "cancelled"
        ):
            raise ValueError("cancelled action results require a cancelled failure class")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class Event(SemanticRecord):
    """One append-only authoritative runtime transition event."""

    RECORD_TYPE: ClassVar[str] = "event"

    run: RecordRef
    sequence: int
    kind: str
    previous_event: RecordRef | None = None
    action: Action | None = None
    result: ActionResult | None = None
    outcome: Outcome | None = None
    failure: RuntimeFailure | None = None
    emitted_actions: tuple[Action, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.run, RecordRef) or self.run.record_type != "run":
            raise TypeError("event run must reference a Run")
        sequence = _nonnegative_int(self.sequence, "event sequence")
        object.__setattr__(self, "sequence", sequence)
        if sequence == 0 and self.previous_event is not None:
            raise ValueError("initial runtime event cannot have a predecessor")
        if sequence > 0 and (
            not isinstance(self.previous_event, RecordRef)
            or self.previous_event.record_type != "event"
        ):
            raise ValueError("noninitial runtime events require an exact predecessor")
        kind = _require_text(self.kind, "event kind")
        if kind not in RUNTIME_EVENT_KINDS:
            raise ValueError(f"unsupported runtime event kind: {kind}")
        object.__setattr__(self, "kind", kind)
        emitted = tuple(self.emitted_actions)
        if any(not isinstance(item, Action) for item in emitted):
            raise TypeError("emitted actions must contain Action values")
        if any(item.run != self.run for item in emitted):
            raise ValueError("emitted actions must belong to the event run")
        if len({item.ref for item in emitted}) != len(emitted):
            raise ValueError("emitted actions must be unique")
        object.__setattr__(self, "emitted_actions", emitted)
        self._validate_shape()
        super().__post_init__()

    def _validate_shape(self) -> None:
        if self.action is not None and (
            not isinstance(self.action, Action) or self.action.run != self.run
        ):
            raise ValueError("event action must belong to the event run")
        if self.result is not None and not isinstance(self.result, ActionResult):
            raise TypeError("event result must be an ActionResult")
        if self.result is not None and self.result.action.run != self.run:
            raise ValueError("event result action must belong to the event run")
        if self.outcome is not None and not isinstance(self.outcome, Outcome):
            raise TypeError("event outcome must be an Outcome")
        if self.failure is not None and not isinstance(self.failure, RuntimeFailure):
            raise TypeError("event failure must be a RuntimeFailure")

        present = tuple(
            item is not None for item in (self.action, self.result, self.outcome, self.failure)
        )
        fixed_shapes = {
            "run_started": ((False, False, False, False), 0),
            "action_requested": ((True, False, False, False), 1),
            "action_succeeded": ((False, True, False, False), 0),
            "action_cancelled": ((False, True, True, True), 0),
            "run_completed": ((False, False, True, False), 0),
            "run_failed": ((False, False, True, True), 0),
            "run_cancelled": ((False, False, True, True), 0),
        }
        if self.kind in fixed_shapes:
            expected_present, expected_emitted = fixed_shapes[self.kind]
            if present != expected_present or len(self.emitted_actions) != expected_emitted:
                raise ValueError(f"runtime event payload does not match kind {self.kind!r}")
        elif self.kind == "action_failed":
            retry_shape = present == (False, True, False, False) and len(self.emitted_actions) == 1
            terminal_shape = present == (False, True, True, True) and not self.emitted_actions
            if not retry_shape and not terminal_shape:
                raise ValueError("action-failed event must retry once or terminate explicitly")
            if retry_shape:
                retry = self.emitted_actions[0]
                if self.result is None:  # pragma: no cover - retry_shape invariant
                    raise RuntimeError("action-failed retry lost its result")
                original = self.result.action
                if (
                    retry.action_id != original.action_id
                    or retry.kind != original.kind
                    or retry.attempt != original.attempt + 1
                    or retry.input_refs != original.input_refs
                    or retry.payload != original.payload
                    or retry.budget_reservation != original.budget_reservation
                    or original.ref not in retry.lineage
                    or self.result.ref not in retry.lineage
                ):
                    raise ValueError("action-failed retry must preserve and cite its exact action")
        if self.kind == "action_requested" and self.emitted_actions != (self.action,):
            raise ValueError("action-requested event must emit its exact action")
        if self.result is not None:
            expected_disposition = {
                "action_succeeded": "succeeded",
                "action_failed": "failed",
                "action_cancelled": "cancelled",
            }.get(self.kind)
            if expected_disposition is not None and self.result.disposition != expected_disposition:
                raise ValueError(f"{self.kind.replace('_', '-')} event requires a matching result")
        if (
            self.kind == "action_cancelled"
            and self.result is not None
            and self.failure != self.result.failure
        ):
            raise ValueError("action-cancelled event must retain its exact result failure")


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RunState(SemanticRecord):
    """Materialized canonical state derived from one exact event prefix."""

    RECORD_TYPE: ClassVar[str] = "run_state"

    run: Run
    status: str
    sequence: int
    last_event: RecordRef
    actions: tuple[Action, ...] = field(default_factory=tuple)
    pending_actions: tuple[Action, ...] = field(default_factory=tuple)
    results: tuple[ActionResult, ...] = field(default_factory=tuple)
    failures: tuple[RuntimeFailure, ...] = field(default_factory=tuple)
    action_count: int = 0
    retry_count: int = 0
    resource_usage: Mapping[str, float] = field(default_factory=FrozenMap)
    outcome: Outcome | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run, Run):
            raise TypeError("runtime state requires a Run")
        status = _require_text(self.status, "run status")
        if status not in RUN_STATUSES:
            raise ValueError(f"unsupported run status: {status}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "sequence", _nonnegative_int(self.sequence, "state sequence"))
        if not isinstance(self.last_event, RecordRef) or self.last_event.record_type != "event":
            raise TypeError("runtime state last_event must reference an Event")
        actions = tuple(self.actions)
        pending = tuple(self.pending_actions)
        results = tuple(self.results)
        failures = tuple(self.failures)
        if any(not isinstance(item, Action) or item.run != self.run.ref for item in actions):
            raise ValueError("runtime actions must belong to the exact run")
        if len({item.ref for item in actions}) != len(actions):
            raise ValueError("runtime actions must be unique")
        action_attempts: dict[str, list[int]] = {}
        for action in actions:
            action_attempts.setdefault(action.action_id, []).append(action.attempt)
        if any(
            sorted(attempts) != list(range(1, len(attempts) + 1))
            for attempts in action_attempts.values()
        ):
            raise ValueError("runtime action attempts must be contiguous from one")
        if any(not isinstance(item, Action) or item.run != self.run.ref for item in pending):
            raise ValueError("pending actions must belong to the exact run")
        if len({item.ref for item in pending}) != len(pending):
            raise ValueError("pending actions must be unique")
        action_refs = {item.ref for item in actions}
        if any(item.ref not in action_refs for item in pending):
            raise ValueError("pending actions must be issued runtime actions")
        if any(
            not isinstance(item, ActionResult) or item.action.run != self.run.ref
            for item in results
        ):
            raise ValueError("runtime results must belong to the exact run")
        if len({item.ref for item in results}) != len(results):
            raise ValueError("runtime results must be unique")
        if len({item.action.ref for item in results}) != len(results):
            raise ValueError("runtime results must correlate once to each exact action")
        if any(item.action.ref not in action_refs for item in results):
            raise ValueError("runtime results must correlate to issued runtime actions")
        if {item.ref for item in pending} & {item.action.ref for item in results}:
            raise ValueError("an action cannot be both pending and completed")
        accounted = {item.ref for item in pending} | {item.action.ref for item in results}
        if status not in TERMINAL_RUN_STATUSES and accounted != action_refs:
            raise ValueError("nonterminal runtime state must account for every issued action")
        if any(not isinstance(item, RuntimeFailure) for item in failures):
            raise TypeError("runtime failures must contain RuntimeFailure values")
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "pending_actions", pending)
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "failures", failures)
        action_count = _nonnegative_int(self.action_count, "state action count")
        if action_count != len(actions):
            raise ValueError("state action count must account for issued actions")
        object.__setattr__(self, "action_count", action_count)
        retry_count = _nonnegative_int(self.retry_count, "state retry count")
        if retry_count != sum(item.attempt > 1 for item in actions):
            raise ValueError("state retry count must account for every retried action")
        object.__setattr__(self, "retry_count", retry_count)
        object.__setattr__(
            self, "resource_usage", _amounts(self.resource_usage, "state resource usage")
        )
        if status in TERMINAL_RUN_STATUSES:
            if pending or not isinstance(self.outcome, Outcome):
                raise ValueError(
                    "terminal runtime states require an outcome and no pending actions"
                )
        elif self.outcome is not None:
            raise ValueError("nonterminal runtime states cannot contain an outcome")
        if status == "waiting" and not pending:
            raise ValueError("waiting runtime states require pending actions")
        if status == "active" and pending:
            raise ValueError("active runtime states cannot contain pending actions")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class Transition(SemanticRecord):
    """One valid state transition bound to its authoritative event."""

    RECORD_TYPE: ClassVar[str] = "transition"

    prior_state: RecordRef | None
    event: Event
    next_state: RunState

    def __post_init__(self) -> None:
        if self.prior_state is not None and (
            not isinstance(self.prior_state, RecordRef)
            or self.prior_state.record_type != "run_state"
        ):
            raise TypeError("transition prior state must reference a RunState")
        if not isinstance(self.event, Event) or not isinstance(self.next_state, RunState):
            raise TypeError("transition requires an Event and RunState")
        if self.event.run != self.next_state.run.ref:
            raise ValueError("transition event and state must belong to the same run")
        if self.next_state.sequence != self.event.sequence:
            raise ValueError("transition event and state sequence must match")
        if self.next_state.last_event != self.event.ref:
            raise ValueError("transition state must cite its exact event")
        if self.event.sequence == 0 and self.prior_state is not None:
            raise ValueError("initial transition cannot have a prior state")
        if self.event.sequence > 0 and self.prior_state is None:
            raise ValueError("noninitial transitions require a prior state")
        super().__post_init__()
