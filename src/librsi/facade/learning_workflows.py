"""Durable composition of native workflows for one frozen learning pass."""

from __future__ import annotations

from collections.abc import Callable

from ..application import (
    APPLY_CANDIDATE_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
)
from ..application.replay import replay_application_state
from ..capabilities import CapabilityRegistry, CapabilityRoute, Reviewer
from ..comparison import CandidateTrialBatch
from ..improvement import (
    ImprovementCycleProposal,
    ImprovementRequest,
    ImprovementResult,
    ImprovementWorkflow,
    cycle_request_from_action,
    make_cycle_result,
)
from ..investigation import (
    INVESTIGATION_EXPERIMENT_ACTION_KIND,
    InvestigationRequest,
    InvestigationResult,
    InvestigationWorkflow,
)
from ..local.learning import LocalLearningStore
from ..rsi import (
    FORWARD_SHADOW_ACTION_KIND,
    HISTORICAL_EVALUATION_ACTION_KIND,
    INDEPENDENT_REVIEW_ACTION_KIND,
    RSIRequest,
    RSIResult,
    RSIWorkflow,
    SelfChangePolicy,
    review_from_result,
)
from ..runtime import Action, ActionResult, RuntimeFailure, persist_transitions
from .learning_host import LearningHost


def recorded_action(
    store: LocalLearningStore,
    pass_id: str,
    action: Action,
    execute: Callable[[Action], ActionResult],
) -> ActionResult:
    key = f"action:{action.root}"
    cached = store.cached(pass_id, key)
    if cached is not None:
        if not isinstance(cached, ActionResult) or cached.action != action:
            raise ValueError("cached result does not answer the exact pending action")
        return cached
    try:
        result = execute(action)
        if not isinstance(result, ActionResult) or result.action != action:
            raise ValueError("provider did not answer the exact pending action")
    except Exception as error:
        result = ActionResult(
            action=action,
            disposition="failed",
            failure=RuntimeFailure(
                classification="execution",
                message=str(error) or type(error).__name__,
                retryable=False,
            ),
        )
    store.remember(pass_id, key, result)
    return result


def investigate(host: LearningHost, request: InvestigationRequest) -> InvestigationResult:
    store = host.store
    workflow = InvestigationWorkflow()
    state = store.runtime.resume(request.canonical_run().run_id)
    update = workflow.start(request) if state is None else workflow.resume(request, state)
    while True:
        persist_transitions(store.runtime, update.transitions)
        progress = update.progress
        if progress.result is not None:
            return progress.result
        action = progress.state.pending_actions[0]
        result = recorded_action(
            store,
            host.pass_id,
            action,
            host.experiment if action.kind == INVESTIGATION_EXPERIMENT_ACTION_KIND else host.reason,
        )
        update = workflow.submit(progress, result)


def improve(
    host: LearningHost,
    request: ImprovementRequest,
    investigation: InvestigationResult,
    batches: tuple[CandidateTrialBatch, ...],
) -> ImprovementResult:
    store = host.store
    workflow = ImprovementWorkflow()
    state = store.runtime.resume(request.canonical_run().run_id)
    update = (
        workflow.start(request, current_snapshot=host.baseline)
        if state is None
        else workflow.resume(request, state, current_snapshot=host.baseline)
    )
    while True:
        persist_transitions(store.runtime, update.transitions)
        if update.progress.result is not None:
            return update.progress.result
        action = update.progress.state.pending_actions[0]
        # All external measurements are already durably recorded under LearningPolicy's
        # finite allowances. This native cycle submission performs no external work.
        result = recorded_action(
            store,
            host.pass_id,
            action,
            lambda item: make_cycle_result(
                action=item,
                proposal=ImprovementCycleProposal.create(
                    request=cycle_request_from_action(item),
                    investigation=investigation,
                    batches=batches,
                ),
                resource_units=0,
            ),
        )
        update = workflow.submit(update.progress, result, current_snapshot=host.baseline)


def recurse(host: LearningHost, request: RSIRequest, reviewer: Reviewer) -> RSIResult:
    store = host.store
    routes = (
        (HISTORICAL_EVALUATION_ACTION_KIND, "experimenter"),
        (FORWARD_SHADOW_ACTION_KIND, "experimenter"),
        (INDEPENDENT_REVIEW_ACTION_KIND, "reviewer"),
        (APPLY_CANDIDATE_ACTION_KIND, "applier"),
        (ROLLBACK_APPLICATION_ACTION_KIND, "applier"),
        (VERIFY_APPLICATION_ACTION_KIND, "verifier"),
    )

    class BoundReviewer:
        def review(self, action: Action) -> ActionResult:
            result = reviewer.review(action)
            if result.disposition == "succeeded":
                report = review_from_result(result)
                if report.review.reviewer_id != host.inputs.value["configuration"]["reviewer_id"]:
                    raise ValueError("review does not match the configured independent reviewer")
            return result

    registry = CapabilityRegistry(
        routes=tuple(
            CapabilityRoute(action_kind=kind, family=family, posture="automatic")
            for kind, family in routes
        ),
        implementations=(host, BoundReviewer()),
    )
    workflow = RSIWorkflow(registry)
    state = store.runtime.resume(request.canonical_run().run_id)
    prior = host.baseline
    application_state = None
    if state is not None and state.status == "completed" and request.activate:
        governance = SelfChangePolicy.governance_result(request, state)
        if governance.disposition == "accepted":
            approval = SelfChangePolicy.approval(request, governance)
            application_request = SelfChangePolicy.application_request(
                approval,
                current_snapshot=host.baseline,
            )
            application_state = store.runtime.resume(application_request.canonical_run().run_id)
            if application_state is not None:
                _, projection = replay_application_state(application_request, application_state)
                prior = (
                    projection.rollback.restored_snapshot
                    if projection.rollback is not None
                    else projection.application.produced_snapshot
                    if projection.application is not None
                    else host.baseline
                )
    # Rehydrate the exact recorded frontier. An in-flight local CAS is reconciled
    # below with its receipt and the actual profile, through native submission.
    update = (
        workflow.start(request, current_snapshot=prior)
        if state is None
        else workflow.resume(
            request, state, current_snapshot=prior, application_state=application_state
        )
    )
    while True:
        persist_transitions(store.runtime, update.transitions)
        progress = update.progress
        if progress.result is not None:
            return progress.result
        action = progress.state.pending_actions[0]
        if store.active != prior and action.kind not in {
            APPLY_CANDIDATE_ACTION_KIND,
            ROLLBACK_APPLICATION_ACTION_KIND,
        }:
            raise ValueError("active strategy drifted from the native workflow frontier")
        result = recorded_action(
            store,
            host.pass_id,
            action,
            lambda item: registry.execute(registry.resolve(item)),
        )
        current = store.active
        update = workflow.submit(
            progress,
            result,
            prior_snapshot=prior,
            current_snapshot=current,
            authority="automatic",
        )
        prior = current
