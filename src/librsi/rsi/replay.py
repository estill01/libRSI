"""Canonical replay and result projection for self-change governance."""

from __future__ import annotations

from dataclasses import dataclass

from ..records import Outcome
from ..runtime import Action, RunState, RuntimeEngine, RuntimeFailure
from .actions import (
    FORWARD_SHADOW_ACTION_KIND,
    HISTORICAL_EVALUATION_ACTION_KIND,
    INDEPENDENT_REVIEW_ACTION_KIND,
    SelfChangeActionResultValidator,
    evaluation_from_result,
    make_evaluation_action,
    make_review_action,
    review_from_result,
)
from .records import RSIRequest, SelfChangeEvaluation, SelfChangeReview


@dataclass(frozen=True)
class SelfChangeProjection:
    """Governance records derived from one exact runtime prefix."""

    historical: SelfChangeEvaluation | None = None
    forward_shadow: SelfChangeEvaluation | None = None
    independent_review: SelfChangeReview | None = None


def next_governance_action(
    request: RSIRequest,
    projection: SelfChangeProjection,
) -> Action | None:
    if projection.historical is None:
        return make_evaluation_action(request, stage="historical")
    if projection.historical.disposition != "passed":
        return None
    if projection.forward_shadow is None:
        return make_evaluation_action(
            request,
            stage="forward-shadow",
            historical=projection.historical,
        )
    if projection.forward_shadow.disposition != "passed":
        return None
    if projection.independent_review is None:
        return make_review_action(request, projection.forward_shadow)
    return None


def governance_disposition(projection: SelfChangeProjection) -> str:
    if projection.historical is None:
        raise ValueError("self-change governance lacks historical evidence")
    if projection.historical.disposition != "passed":
        return "rejected"
    if projection.forward_shadow is None:
        raise ValueError("self-change governance lacks forward-shadow evidence")
    if projection.forward_shadow.disposition != "passed":
        return "rejected"
    if projection.independent_review is None:
        raise ValueError("self-change governance lacks independent review")
    return "accepted" if projection.independent_review.disposition == "accepted" else "rejected"


def governance_outcome(request: RSIRequest, projection: SelfChangeProjection) -> Outcome:
    disposition = governance_disposition(projection)
    accepted = disposition == "accepted"
    lineage = (
        request.ref,
        *((projection.historical.ref,) if projection.historical is not None else ()),
        *((projection.forward_shadow.ref,) if projection.forward_shadow is not None else ()),
        *(
            (projection.independent_review.ref,)
            if projection.independent_review is not None
            else ()
        ),
    )
    return Outcome(
        intent=request.ref,
        status=disposition,
        target_snapshot=request.declaration.target_snapshot,
        conclusions=("every self-change governance gate passed",) if accepted else (),
        unresolved=() if accepted else ("self-change activation was not authorized",),
        lineage=lineage,
    )


def replay_governance_state(
    request: RSIRequest,
    state: RunState,
) -> tuple[RunState, SelfChangeProjection]:
    if type(request) is not RSIRequest:
        raise TypeError("self-change replay requires an RSIRequest")
    if type(state) is not RunState or state.run != request.canonical_run():
        raise ValueError("persisted self-change governance run envelope has drifted")
    replay = RuntimeEngine.start(request.canonical_run()).state
    projection = SelfChangeProjection()
    result_index = 0
    validator = SelfChangeActionResultValidator()
    for action in state.actions:
        if action.attempt != 1:
            raise ValueError("self-change governance actions cannot retry")
        expected = next_governance_action(request, projection)
        if action not in replay.actions:
            if action != expected:
                raise ValueError("self-change action is not the exact governance frontier")
            replay = RuntimeEngine.request(replay, action).state
        if result_index < len(state.results) and state.results[result_index].action == action:
            result = state.results[result_index]
            validator.validate(replay, result)
            replay = RuntimeEngine.submit(replay, result).state
            if result.disposition == "succeeded":
                if action.kind == HISTORICAL_EVALUATION_ACTION_KIND:
                    projection = SelfChangeProjection(historical=evaluation_from_result(result))
                elif action.kind == FORWARD_SHADOW_ACTION_KIND:
                    forward = evaluation_from_result(result)
                    if (
                        projection.historical is None
                        or forward.ref == projection.historical.ref
                        or forward.batch.ref == projection.historical.batch.ref
                        or forward.batch.experiment.ref
                        == projection.historical.batch.experiment.ref
                    ):
                        raise ValueError(
                            "forward-shadow evidence must be distinct from historical replay"
                        )
                    projection = SelfChangeProjection(
                        historical=projection.historical,
                        forward_shadow=forward,
                    )
                elif action.kind == INDEPENDENT_REVIEW_ACTION_KIND:
                    projection = SelfChangeProjection(
                        historical=projection.historical,
                        forward_shadow=projection.forward_shadow,
                        independent_review=review_from_result(result),
                    )
            result_index += 1
    if result_index != len(state.results):
        raise ValueError("self-change result history is reordered or disconnected")
    settled = replay
    if state.status == "completed":
        replay = RuntimeEngine.complete(settled, governance_outcome(request, projection)).state
    if replay != state:
        raise ValueError("persisted self-change governance state does not replay exactly")
    return settled, projection


def governance_projection_fields(
    request: RSIRequest,
    state: RunState,
    projection: SelfChangeProjection,
) -> tuple[
    str,
    SelfChangeEvaluation | None,
    SelfChangeEvaluation | None,
    SelfChangeReview | None,
    tuple[RuntimeFailure, ...],
]:
    if state.status == "failed":
        disposition = "governance-failed"
    elif state.status == "active" and next_governance_action(request, projection) is None:
        disposition = governance_disposition(projection)
    else:
        raise ValueError("self-change governance result requires a terminal settled frontier")
    return (
        disposition,
        projection.historical,
        projection.forward_shadow,
        projection.independent_review,
        tuple(state.failures),
    )
