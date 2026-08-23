"""Exact action codecs for self-change evaluation and independent review."""

from __future__ import annotations

from collections.abc import Mapping

from ..comparison import CandidateReview, CandidateTrialBatch, ComparativeSelectionPolicy
from ..identity import thaw
from ..records import record_from_dict
from ..runtime import Action, ActionResult, RunState, RuntimeFailure
from .records import (
    RSIRequest,
    SelfChangeEvaluation,
    SelfChangeEvaluationCommand,
    SelfChangeReview,
    SelfChangeReviewCommand,
)

HISTORICAL_EVALUATION_ACTION_KIND = "evaluate-self-change-history"
FORWARD_SHADOW_ACTION_KIND = "evaluate-self-change-shadow"
INDEPENDENT_REVIEW_ACTION_KIND = "review-self-change"
SELF_CHANGE_ACTION_KINDS = frozenset(
    {
        HISTORICAL_EVALUATION_ACTION_KIND,
        FORWARD_SHADOW_ACTION_KIND,
        INDEPENDENT_REVIEW_ACTION_KIND,
    }
)

_STAGE_KINDS = {
    "historical": HISTORICAL_EVALUATION_ACTION_KIND,
    "forward-shadow": FORWARD_SHADOW_ACTION_KIND,
}


def _evaluation_action(command: SelfChangeEvaluationCommand, *, run_ref) -> Action:
    return Action(
        run=run_ref,
        action_id=f"{command.request.root}:{command.stage}",
        kind=_STAGE_KINDS[command.stage],
        input_refs=(command.ref, *command.lineage),
        payload={"command": command.to_dict()},
        lineage=(command.request, command.ref, *command.lineage[1:]),
    )


def make_evaluation_action(
    request: RSIRequest,
    *,
    stage: str,
    historical: SelfChangeEvaluation | None = None,
) -> Action:
    if type(request) is not RSIRequest:
        raise TypeError("self-change evaluation actions require an RSIRequest")
    predecessor = None
    if stage == "forward-shadow":
        if (
            type(historical) is not SelfChangeEvaluation
            or historical.request != request.ref
            or historical.stage != "historical"
            or historical.disposition != "passed"
        ):
            raise ValueError("forward-shadow evaluation requires passed historical evidence")
        predecessor = historical.ref
    elif historical is not None:
        raise ValueError("historical evaluation cannot cite a predecessor")
    command = SelfChangeEvaluationCommand(
        request=request.ref,
        stage=stage,
        contract=request.improvement.request.contract,
        risk_policy=request.governance.risk_policy,
        candidate=request.candidate,
        baseline=request.declaration.target_snapshot,
        predecessor=predecessor,
        lineage=(
            request.ref,
            request.improvement.request.contract.ref,
            request.governance.risk_policy.ref,
            request.candidate.ref,
            request.declaration.target_snapshot.ref,
            *((predecessor,) if predecessor is not None else ()),
        ),
    )
    return _evaluation_action(command, run_ref=request.canonical_run().ref)


def evaluation_command_from_action(action: Action) -> SelfChangeEvaluationCommand:
    if type(action) is not Action:
        raise TypeError("self-change action decoding requires an Action")
    if action.kind not in _STAGE_KINDS.values():
        raise ValueError("action is not a self-change evaluation")
    if frozenset(action.payload) != {"command"}:
        raise ValueError("self-change evaluation action must contain only its command")
    payload = action.payload["command"]
    if not isinstance(payload, Mapping):
        raise TypeError("self-change evaluation command must be a mapping")
    command = record_from_dict(thaw(payload))
    if type(command) is not SelfChangeEvaluationCommand:
        raise TypeError("self-change evaluation payload has the wrong record type")
    if action != _evaluation_action(command, run_ref=action.run):
        raise ValueError("self-change evaluation action is not command-derived")
    return command


def make_evaluation_result(
    *,
    action: Action,
    batch: CandidateTrialBatch,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    command = evaluation_command_from_action(action)
    if type(batch) is not CandidateTrialBatch:
        raise TypeError("self-change evaluation results require a CandidateTrialBatch")
    if (
        batch.contract != command.contract
        or batch.candidate != command.candidate
        or batch.experiment.baseline_snapshot != command.baseline
        or batch.experiment.candidate_snapshot != command.candidate.snapshot
    ):
        raise ValueError("self-change trial batch does not answer the exact command")
    assessment = ComparativeSelectionPolicy.assess(batch, risk_policy=command.risk_policy)
    disposition = {
        "accepted": "passed",
        "rejected": "rejected",
        "inconclusive": "inconclusive",
    }[assessment.disposition]
    evaluation = SelfChangeEvaluation(
        request=command.request,
        stage=command.stage,
        action=action,
        batch=batch,
        assessment=assessment,
        disposition=disposition,
        reason="; ".join(assessment.reasons),
        lineage=(command.request, action.ref, batch.ref, assessment.ref),
    )
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(evaluation.ref, batch.ref, assessment.ref),
        payload={"evaluation": evaluation.to_dict()},
        resource_usage={} if resource_usage is None else resource_usage,
    )


def evaluation_from_result(result: ActionResult) -> SelfChangeEvaluation:
    if type(result) is not ActionResult:
        raise TypeError("self-change evaluation decoding requires an ActionResult")
    command = evaluation_command_from_action(result.action)
    if result.disposition != "succeeded":
        raise ValueError("failed self-change evaluation actions contain no epistemic gate")
    if frozenset(result.payload) != {"evaluation"}:
        raise ValueError("self-change evaluation result must contain only its evaluation")
    payload = result.payload["evaluation"]
    if not isinstance(payload, Mapping):
        raise TypeError("self-change evaluation result payload must be a mapping")
    evaluation = record_from_dict(thaw(payload))
    if (
        type(evaluation) is not SelfChangeEvaluation
        or evaluation.request != command.request
        or evaluation.stage != command.stage
    ):
        raise ValueError("self-change evaluation does not answer the exact action")
    if result.output_refs != (
        evaluation.ref,
        evaluation.batch.ref,
        evaluation.assessment.ref,
    ):
        raise ValueError("self-change evaluation outputs are not exact")
    return evaluation


def _review_action(command: SelfChangeReviewCommand, *, run_ref) -> Action:
    return Action(
        run=run_ref,
        action_id=f"{command.request.root}:independent-review",
        kind=INDEPENDENT_REVIEW_ACTION_KIND,
        input_refs=(command.ref, *command.lineage),
        payload={"command": command.to_dict()},
        lineage=(command.request, command.forward_evaluation, command.ref),
    )


def make_review_action(request: RSIRequest, forward: SelfChangeEvaluation) -> Action:
    if type(request) is not RSIRequest:
        raise TypeError("self-change review actions require an RSIRequest")
    if (
        type(forward) is not SelfChangeEvaluation
        or forward.request != request.ref
        or forward.stage != "forward-shadow"
        or forward.disposition != "passed"
    ):
        raise ValueError("self-change review requires passed forward-shadow evidence")
    command = SelfChangeReviewCommand(
        request=request.ref,
        forward_evaluation=forward.ref,
        candidate=request.candidate,
        experiment=forward.batch.experiment,
        evaluation=forward.batch.evaluation,
        candidate_author_id=request.declaration.candidate_author_id,
        lineage=(
            request.ref,
            forward.ref,
            request.candidate.ref,
            forward.batch.experiment.ref,
            forward.batch.evaluation.ref,
        ),
    )
    return _review_action(command, run_ref=request.canonical_run().ref)


def review_command_from_action(action: Action) -> SelfChangeReviewCommand:
    if type(action) is not Action:
        raise TypeError("self-change review decoding requires an Action")
    if action.kind != INDEPENDENT_REVIEW_ACTION_KIND:
        raise ValueError("action is not a self-change independent review")
    if frozenset(action.payload) != {"command"}:
        raise ValueError("self-change review action must contain only its command")
    payload = action.payload["command"]
    if not isinstance(payload, Mapping):
        raise TypeError("self-change review command must be a mapping")
    command = record_from_dict(thaw(payload))
    if type(command) is not SelfChangeReviewCommand:
        raise TypeError("self-change review payload has the wrong record type")
    if action != _review_action(command, run_ref=action.run):
        raise ValueError("self-change review action is not command-derived")
    return command


def make_review_result(
    *,
    action: Action,
    review: CandidateReview,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    command = review_command_from_action(action)
    if (
        type(review) is not CandidateReview
        or review.candidate != command.candidate
        or review.experiment != command.experiment
        or review.evaluation != command.evaluation
    ):
        raise ValueError("independent review does not answer the exact command")
    report = SelfChangeReview(
        request=command.request,
        forward_evaluation=command.forward_evaluation,
        action=action,
        review=review,
        disposition=review.disposition,
        reason="; ".join(review.findings),
        lineage=(command.request, command.forward_evaluation, action.ref, review.ref),
    )
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(report.ref, review.ref),
        payload={"review": report.to_dict()},
        resource_usage={} if resource_usage is None else resource_usage,
    )


def review_from_result(result: ActionResult) -> SelfChangeReview:
    if type(result) is not ActionResult:
        raise TypeError("self-change review decoding requires an ActionResult")
    command = review_command_from_action(result.action)
    if result.disposition != "succeeded":
        raise ValueError("failed self-change review actions contain no governance decision")
    if frozenset(result.payload) != {"review"}:
        raise ValueError("self-change review result must contain only its exact review")
    payload = result.payload["review"]
    if not isinstance(payload, Mapping):
        raise TypeError("self-change review result payload must be a mapping")
    report = record_from_dict(thaw(payload))
    if (
        type(report) is not SelfChangeReview
        or report.request != command.request
        or report.forward_evaluation != command.forward_evaluation
    ):
        raise ValueError("self-change review does not answer the exact action")
    if result.output_refs != (report.ref, report.review.ref):
        raise ValueError("self-change review outputs are not exact")
    return report


def make_self_change_failure(*, action: Action, failure: RuntimeFailure) -> ActionResult:
    if action.kind in _STAGE_KINDS.values():
        evaluation_command_from_action(action)
    elif action.kind == INDEPENDENT_REVIEW_ACTION_KIND:
        review_command_from_action(action)
    else:
        raise ValueError("action is not a self-change governance action")
    if type(failure) is not RuntimeFailure:
        raise TypeError("self-change failures require a RuntimeFailure")
    return ActionResult(action=action, disposition="failed", failure=failure)


class SelfChangeActionResultValidator:
    """Validate every self-change capability result before runtime mutation."""

    def validate(self, state: RunState, result: ActionResult) -> None:
        if type(state) is not RunState or type(result) is not ActionResult:
            raise TypeError("self-change result validation requires exact runtime records")
        if result.action not in state.pending_actions or result.action.run != state.run.ref:
            raise ValueError("self-change result does not answer a pending action")
        if result.action.kind not in SELF_CHANGE_ACTION_KINDS:
            raise ValueError("result is not a self-change governance action")
        if result.disposition == "succeeded":
            if result.action.kind == INDEPENDENT_REVIEW_ACTION_KIND:
                review_from_result(result)
            else:
                evaluation_from_result(result)
        elif result.output_refs or result.payload:
            raise ValueError("failed self-change actions cannot contain semantic gate outputs")
