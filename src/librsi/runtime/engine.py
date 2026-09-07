"""Pure deterministic transitions for the semantic runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..errors import RSITransitionError
from ..records import Outcome
from .records import (
    TERMINAL_RUN_STATUSES,
    Action,
    ActionResult,
    Event,
    Run,
    RunState,
    RuntimeFailure,
    Transition,
)


@dataclass(frozen=True)
class RuntimeUpdate:
    """Applied transition, or an exact duplicate submission no-op."""

    state: RunState
    transition: Transition | None
    duplicate: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.state, RunState):
            raise TypeError("runtime updates require a RunState")
        if self.transition is not None and not isinstance(self.transition, Transition):
            raise TypeError("runtime update transition must be a Transition")
        if type(self.duplicate) is not bool:
            raise TypeError("runtime update duplicate must be a boolean")
        if self.duplicate != (self.transition is None):
            raise ValueError("only exact duplicate updates may omit a transition")


@dataclass(frozen=True)
class RuntimeStep:
    """Control-plane-neutral view of the next externally visible runtime state."""

    state: RunState
    actions: tuple[Action, ...]
    outcome: Outcome | None

    @property
    def terminal(self) -> bool:
        return self.state.status in TERMINAL_RUN_STATUSES


def _sum_amounts(
    first: Mapping[str, float],
    second: Mapping[str, float],
) -> dict[str, float]:
    result = {str(key): float(value) for key, value in first.items()}
    for key, value in second.items():
        result[str(key)] = result.get(str(key), 0.0) + float(value)
    return result


class RuntimeEngine:
    """Authoritative pure state machine; it executes no capabilities or effects."""

    @staticmethod
    def _require_live(state: RunState) -> None:
        if not isinstance(state, RunState):
            raise TypeError("runtime transitions require a RunState")
        if state.status in TERMINAL_RUN_STATUSES:
            raise RSITransitionError("terminal runtime state cannot be mutated")

    @staticmethod
    def _event(
        state: RunState,
        kind: str,
        *,
        action: Action | None = None,
        result: ActionResult | None = None,
        outcome: Outcome | None = None,
        failure: RuntimeFailure | None = None,
        emitted_actions: tuple[Action, ...] = (),
    ) -> Event:
        return Event(
            run=state.run.ref,
            sequence=state.sequence + 1,
            previous_event=state.last_event,
            kind=kind,
            action=action,
            result=result,
            outcome=outcome,
            failure=failure,
            emitted_actions=emitted_actions,
        )

    @staticmethod
    def _state(
        prior: RunState,
        event: Event,
        *,
        status: str,
        actions: tuple[Action, ...] | None = None,
        pending_actions: tuple[Action, ...] | None = None,
        results: tuple[ActionResult, ...] | None = None,
        failures: tuple[RuntimeFailure, ...] | None = None,
        resource_usage: Mapping[str, float] | None = None,
        outcome: Outcome | None = None,
    ) -> RunState:
        all_actions = prior.actions if actions is None else actions
        return RunState(
            run=prior.run,
            status=status,
            sequence=event.sequence,
            last_event=event.ref,
            actions=all_actions,
            pending_actions=(prior.pending_actions if pending_actions is None else pending_actions),
            results=prior.results if results is None else results,
            failures=prior.failures if failures is None else failures,
            action_count=len(all_actions),
            retry_count=sum(item.attempt > 1 for item in all_actions),
            resource_usage=(prior.resource_usage if resource_usage is None else resource_usage),
            outcome=outcome,
        )

    @staticmethod
    def _transition(prior: RunState, event: Event, state: RunState) -> RuntimeUpdate:
        transition = Transition(prior_state=prior.ref, event=event, next_state=state)
        return RuntimeUpdate(state=state, transition=transition)

    @staticmethod
    def _outcome(
        run: Run,
        status: str,
        failure: RuntimeFailure,
        *,
        result: ActionResult | None = None,
    ) -> Outcome:
        lineage = (failure.ref,) if result is None else (result.ref, failure.ref)
        return Outcome(
            intent=run.intent,
            status=status,
            target_snapshot=run.target_snapshot,
            unresolved=(failure.message,),
            lineage=lineage,
        )

    @staticmethod
    def _budget_failure(message: str, details: Mapping[str, object]) -> RuntimeFailure:
        return RuntimeFailure(
            classification="budget-exhausted",
            message=message,
            retryable=False,
            details=details,
        )

    @staticmethod
    def _assert_resource_budget(run: Run, usage: Mapping[str, float]) -> None:
        exceeded = {
            key: {"used": amount, "limit": run.budget.resource_limits[key]}
            for key, amount in usage.items()
            if key in run.budget.resource_limits and amount > run.budget.resource_limits[key]
        }
        if exceeded:
            raise RSITransitionError(
                f"runtime resource budget would be exceeded: {sorted(exceeded)}"
            )

    @staticmethod
    def _require_matching_outcome(run: Run, outcome: Outcome, *, label: str) -> None:
        if not isinstance(outcome, Outcome):
            raise TypeError(f"runtime {label} requires an Outcome")
        target_matches = outcome.target_snapshot == run.target_snapshot
        authorized_transition = (
            run.target_transition_authority is not None
            and run.target_snapshot is not None
            and outcome.target_snapshot is not None
            and outcome.target_snapshot.target == run.target_snapshot.target
            and run.target_transition_authority in outcome.lineage
        )
        if outcome.intent != run.intent or not (target_matches or authorized_transition):
            raise RSITransitionError(
                f"{label} outcome does not match the run intent and target snapshot"
            )

    @classmethod
    def start(cls, run: Run) -> RuntimeUpdate:
        if not isinstance(run, Run):
            raise TypeError("runtime start requires a Run")
        event = Event(run=run.ref, sequence=0, kind="run_started")
        state = RunState(
            run=run,
            status="active",
            sequence=0,
            last_event=event.ref,
        )
        transition = Transition(prior_state=None, event=event, next_state=state)
        return RuntimeUpdate(state=state, transition=transition)

    @classmethod
    def request(cls, state: RunState, action: Action) -> RuntimeUpdate:
        cls._require_live(state)
        if not isinstance(action, Action):
            raise TypeError("runtime action request requires an Action")
        if action.run != state.run.ref:
            raise RSITransitionError("action belongs to a different run")
        if action.attempt != 1:
            raise RSITransitionError("new runtime actions must begin at attempt one")
        if any(item.action_id == action.action_id for item in state.actions):
            raise RSITransitionError("runtime action id has already been issued")
        if state.action_count >= state.run.budget.max_actions:
            raise RSITransitionError("runtime action budget is exhausted")

        reserved = dict(state.resource_usage)
        for pending in state.pending_actions:
            reserved = _sum_amounts(reserved, pending.budget_reservation)
        cls._assert_resource_budget(
            state.run,
            _sum_amounts(reserved, action.budget_reservation),
        )
        event = cls._event(
            state,
            "action_requested",
            action=action,
            emitted_actions=(action,),
        )
        next_state = cls._state(
            state,
            event,
            status="waiting",
            actions=(*state.actions, action),
            pending_actions=(*state.pending_actions, action),
        )
        return cls._transition(state, event, next_state)

    @classmethod
    def submit(cls, state: RunState, result: ActionResult) -> RuntimeUpdate:
        if not isinstance(state, RunState):
            raise TypeError("runtime transitions require a RunState")
        if not isinstance(result, ActionResult):
            raise TypeError("runtime submission requires an ActionResult")
        if result.action.run != state.run.ref:
            raise RSITransitionError("action result belongs to a different run")
        for existing in state.results:
            if existing.ref == result.ref:
                return RuntimeUpdate(state=state, transition=None, duplicate=True)
            if existing.action.ref == result.action.ref:
                raise RSITransitionError("a divergent result already completed this action")
        cls._require_live(state)

        action = next(
            (item for item in state.pending_actions if item.ref == result.action.ref),
            None,
        )
        if action is None:
            raise RSITransitionError("action result is stale or does not match a pending action")
        if action != result.action:
            raise RSITransitionError("action result does not contain the exact pending action")

        usage = _sum_amounts(state.resource_usage, result.resource_usage)
        cls._assert_resource_budget(state.run, usage)
        pending = tuple(item for item in state.pending_actions if item.ref != action.ref)
        results = (*state.results, result)
        failures = state.failures

        if result.disposition == "succeeded":
            authorized = dict(usage)
            for pending_action in pending:
                authorized = _sum_amounts(
                    authorized,
                    pending_action.budget_reservation,
                )
            cls._assert_resource_budget(state.run, authorized)
            event = cls._event(state, "action_succeeded", result=result)
            next_state = cls._state(
                state,
                event,
                status="waiting" if pending else "active",
                pending_actions=pending,
                results=results,
                resource_usage=usage,
            )
            return cls._transition(state, event, next_state)

        failure = result.failure
        if failure is None:  # pragma: no cover - ActionResult invariant
            raise RuntimeError("failed action result lost its failure")
        failures = (*failures, failure)
        if result.disposition == "cancelled":
            outcome = cls._outcome(state.run, "cancelled", failure, result=result)
            event = cls._event(
                state,
                "action_cancelled",
                result=result,
                outcome=outcome,
                failure=failure,
            )
            next_state = cls._state(
                state,
                event,
                status="cancelled",
                pending_actions=(),
                results=results,
                failures=failures,
                resource_usage=usage,
                outcome=outcome,
            )
            return cls._transition(state, event, next_state)

        budget_failure: RuntimeFailure | None = None
        if len(failures) > state.run.budget.max_failures:
            budget_failure = cls._budget_failure(
                "runtime failure budget is exhausted",
                {"failures": len(failures), "limit": state.run.budget.max_failures},
            )
        elif failure.retryable and state.retry_count >= state.run.budget.max_retries:
            budget_failure = cls._budget_failure(
                "runtime retry budget is exhausted",
                {"retries": state.retry_count, "limit": state.run.budget.max_retries},
            )
        elif failure.retryable and state.action_count >= state.run.budget.max_actions:
            budget_failure = cls._budget_failure(
                "runtime action budget prevents retry",
                {"actions": state.action_count, "limit": state.run.budget.max_actions},
            )

        retry: Action | None = None
        if failure.retryable and budget_failure is None:
            retry = Action(
                run=action.run,
                action_id=action.action_id,
                kind=action.kind,
                attempt=action.attempt + 1,
                input_refs=action.input_refs,
                payload=action.payload,
                budget_reservation=action.budget_reservation,
                lineage=(action.ref, result.ref),
                metadata=action.metadata,
            )
            reserved = dict(usage)
            for item in pending:
                reserved = _sum_amounts(reserved, item.budget_reservation)
            retry_reservation = _sum_amounts(reserved, retry.budget_reservation)
            try:
                cls._assert_resource_budget(state.run, retry_reservation)
            except RSITransitionError:
                budget_failure = cls._budget_failure(
                    "runtime resource budget prevents retry",
                    {
                        "reserved": retry_reservation,
                        "limits": state.run.budget.resource_limits,
                    },
                )

        if retry is not None and budget_failure is None:
            event = cls._event(
                state,
                "action_failed",
                result=result,
                emitted_actions=(retry,),
            )
            next_state = cls._state(
                state,
                event,
                status="waiting",
                actions=(*state.actions, retry),
                pending_actions=(*pending, retry),
                results=results,
                failures=failures,
                resource_usage=usage,
            )
            return cls._transition(state, event, next_state)

        terminal_failure = failure if budget_failure is None else budget_failure
        terminal_failures = failures if budget_failure is None else (*failures, budget_failure)
        outcome = cls._outcome(state.run, "failed", terminal_failure, result=result)
        event = cls._event(
            state,
            "action_failed",
            result=result,
            outcome=outcome,
            failure=terminal_failure,
        )
        next_state = cls._state(
            state,
            event,
            status="failed",
            pending_actions=(),
            results=results,
            failures=terminal_failures,
            resource_usage=usage,
            outcome=outcome,
        )
        return cls._transition(state, event, next_state)

    @classmethod
    def complete(cls, state: RunState, outcome: Outcome) -> RuntimeUpdate:
        cls._require_live(state)
        if state.pending_actions:
            raise RSITransitionError("run cannot complete while actions are pending")
        cls._require_matching_outcome(state.run, outcome, label="completion")
        event = cls._event(state, "run_completed", outcome=outcome)
        next_state = cls._state(state, event, status="completed", outcome=outcome)
        return cls._transition(state, event, next_state)

    @classmethod
    def fail(
        cls,
        state: RunState,
        failure: RuntimeFailure,
        outcome: Outcome | None = None,
    ) -> RuntimeUpdate:
        cls._require_live(state)
        if not isinstance(failure, RuntimeFailure):
            raise TypeError("runtime failure transition requires RuntimeFailure")
        outcome = cls._outcome(state.run, "failed", failure) if outcome is None else outcome
        cls._require_matching_outcome(state.run, outcome, label="failure")
        event = cls._event(
            state,
            "run_failed",
            outcome=outcome,
            failure=failure,
        )
        next_state = cls._state(
            state,
            event,
            status="failed",
            pending_actions=(),
            failures=(*state.failures, failure),
            outcome=outcome,
        )
        return cls._transition(state, event, next_state)

    @classmethod
    def cancel(
        cls,
        state: RunState,
        failure: RuntimeFailure,
        outcome: Outcome | None = None,
    ) -> RuntimeUpdate:
        cls._require_live(state)
        if not isinstance(failure, RuntimeFailure) or failure.classification != "cancelled":
            raise ValueError("runtime cancellation requires a cancelled failure")
        outcome = cls._outcome(state.run, "cancelled", failure) if outcome is None else outcome
        cls._require_matching_outcome(state.run, outcome, label="cancellation")
        event = cls._event(
            state,
            "run_cancelled",
            outcome=outcome,
            failure=failure,
        )
        next_state = cls._state(
            state,
            event,
            status="cancelled",
            pending_actions=(),
            failures=(*state.failures, failure),
            outcome=outcome,
        )
        return cls._transition(state, event, next_state)

    @staticmethod
    def step(state: RunState) -> RuntimeStep:
        if not isinstance(state, RunState):
            raise TypeError("runtime step requires a RunState")
        return RuntimeStep(
            state=state,
            actions=state.pending_actions,
            outcome=state.outcome,
        )

    @classmethod
    def replay_trace(cls, run: Run, events: Sequence[Event]) -> tuple[Transition, ...]:
        """Rebuild every authoritative transition from an exact event history."""

        if not isinstance(run, Run):
            raise TypeError("runtime replay requires a Run")
        if isinstance(events, (str, bytes, bytearray)) or not isinstance(events, Sequence):
            raise TypeError("runtime replay events must be a sequence")
        history = tuple(events)
        if not history:
            raise ValueError("runtime replay requires at least one event")
        if any(not isinstance(event, Event) for event in history):
            raise TypeError("runtime replay history must contain Event values")

        state: RunState | None = None
        trace: list[Transition] = []
        for event in history:
            transition = cls._replay_event(run, state, event)
            state = transition.next_state
            trace.append(transition)
        return tuple(trace)

    @classmethod
    def _replay_event(cls, run: Run, state: RunState | None, event: Event) -> Transition:
        """Extend a replay-verified prefix using the ordinary transition rules."""

        if event.run != run.ref:
            raise RSITransitionError("replay event belongs to a different run")
        if state is None:
            update = cls.start(run)
        elif event.kind == "action_requested":
            if event.action is None:  # pragma: no cover - Event invariant
                raise RuntimeError("action-requested replay event lost its action")
            update = cls.request(state, event.action)
        elif event.kind in {"action_succeeded", "action_failed", "action_cancelled"}:
            if event.result is None:  # pragma: no cover - Event invariant
                raise RuntimeError("action-result replay event lost its result")
            update = cls.submit(state, event.result)
        elif event.kind == "run_completed":
            if event.outcome is None:  # pragma: no cover - Event invariant
                raise RuntimeError("completion replay event lost its outcome")
            update = cls.complete(state, event.outcome)
        elif event.kind == "run_failed":
            if event.failure is None:  # pragma: no cover - Event invariant
                raise RuntimeError("failure replay event lost its failure")
            update = cls.fail(state, event.failure, event.outcome)
        elif event.kind == "run_cancelled":
            if event.failure is None:  # pragma: no cover - Event invariant
                raise RuntimeError("cancellation replay event lost its failure")
            update = cls.cancel(state, event.failure, event.outcome)
        else:
            raise RSITransitionError("run-started event may appear only first")
        if update.transition is None or update.transition.event != event:
            raise RSITransitionError("runtime event history has a gap, reordering, or drift")
        return update.transition

    @classmethod
    def replay(cls, run: Run, events: Sequence[Event]) -> RunState:
        """Rebuild the final materialized state from an exact event history."""

        return cls.replay_trace(run, events)[-1].next_state
