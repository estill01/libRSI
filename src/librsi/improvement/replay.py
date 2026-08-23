"""Single canonical replay authority for bounded improvement state."""

from __future__ import annotations

from ..runtime import Action, RunState, RuntimeEngine
from .actions import proposal_from_action_result, validate_cycle_action_result
from .directives import next_search_directive
from .policy import ImprovementPolicy, improvement_stop_reason
from .records import (
    IMPROVEMENT_ACTION_KIND,
    ImprovementCycleRequest,
    ImprovementIteration,
    ImprovementRequest,
)


def improvement_experiment_count(iterations: tuple[ImprovementIteration, ...]) -> int:
    return sum(item.proposal.experiment_count for item in iterations)


def next_improvement_action(
    request: ImprovementRequest,
    state: RunState,
    iterations: tuple[ImprovementIteration, ...],
) -> Action:
    """Derive the sole authorized next action from the exact persisted frontier."""

    number = len(iterations) + 1
    directive = next_search_directive(iterations[-1] if iterations else None)
    remaining_resources = request.budget.max_resource_units - state.resource_usage.get("units", 0.0)
    remaining_attempts = request.budget.max_retries - state.retry_count + 1
    cycle = ImprovementCycleRequest(
        improvement=request,
        directive=directive,
        remaining_experiments=(
            request.budget.max_experiments - improvement_experiment_count(iterations)
        ),
        remaining_resource_units=remaining_resources,
        resource_units_per_attempt=remaining_resources / remaining_attempts,
        lineage=(request.ref, directive.ref),
    )
    return Action(
        run=state.run.ref,
        action_id=f"{request.request_id}:cycle:{number}",
        kind=IMPROVEMENT_ACTION_KIND,
        input_refs=(cycle.ref, request.ref, directive.ref),
        payload={"request": cycle.to_dict()},
        budget_reservation={"units": cycle.resource_units_per_attempt},
        lineage=(request.ref, directive.ref),
    )


def replay_improvement_state(
    request: ImprovementRequest,
    state: RunState,
) -> tuple[RunState, tuple[ImprovementIteration, ...]]:
    """Validate and replay every improvement action, result, retry, and completion."""

    ImprovementPolicy.validate_request(request)
    if not isinstance(state, RunState) or state.run != request.canonical_run():
        raise ValueError("persisted improvement run envelope has drifted")
    replay = RuntimeEngine.start(request.canonical_run()).state
    iterations: tuple[ImprovementIteration, ...] = ()
    result_index = 0
    for action in state.actions:
        if action not in replay.actions:
            if action.attempt != 1:
                raise ValueError("improvement retry was not emitted by the runtime")
            if (
                improvement_stop_reason(
                    request,
                    iterations,
                    resource_units=replay.resource_usage.get("units", 0.0),
                )
                is not None
            ):
                raise ValueError("persisted improvement requested work after its policy stop")
            if action != next_improvement_action(request, replay, iterations):
                raise ValueError("improvement action is not the exact policy-derived frontier")
            replay = RuntimeEngine.request(replay, action).state
        if result_index < len(state.results) and state.results[result_index].action == action:
            envelope = state.results[result_index]
            validate_cycle_action_result(envelope)
            replay = RuntimeEngine.submit(replay, envelope).state
            if envelope.disposition == "succeeded":
                proposal = proposal_from_action_result(envelope)
                if proposal.request.directive.iteration != len(iterations) + 1:
                    raise ValueError("improvement iteration history has a gap or reordering")
                iterations = (
                    *iterations,
                    ImprovementPolicy.evaluate(proposal, previous=iterations),
                )
            result_index += 1
    if result_index != len(state.results):
        raise ValueError("improvement result history is reordered or disconnected")
    settled = replay
    if state.status == "completed":
        if state.outcome is None:
            raise ValueError("completed improvement state lost its outcome")
        replay = RuntimeEngine.complete(settled, state.outcome).state
    if replay != state:
        raise ValueError("persisted improvement state does not replay exactly")
    return settled, iterations
