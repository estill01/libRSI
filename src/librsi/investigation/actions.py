"""Runtime codecs and pre-transition validation for investigation experiments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..identity import thaw
from ..reasoning import (
    ReasoningRequest,
    ReasoningResultValidator,
)
from ..reasoning.actions import (
    reasoning_request_from_action,
    reasoning_result_from_action_result,
)
from ..records import record_from_dict
from ..runtime import Action, ActionResult, Run, RunState, RuntimeFailure
from .policy import (
    INVESTIGATION_EVIDENCE_RELATIONSHIPS,
    INVESTIGATION_OBSERVATION_METHOD_ORDER,
    InvestigationPolicy,
)
from .records import (
    InvestigationBranch,
    InvestigationEvidenceBatch,
    InvestigationExperimentRequest,
    InvestigationFrontier,
    InvestigationRequest,
)

INVESTIGATION_EXPERIMENT_ACTION_KIND = "investigation-experiment"
INVESTIGATION_REASONING_ACTION_KIND = "investigation-reason"


def investigation_hypothesis_reasoning_action(
    investigation: InvestigationRequest,
) -> Action:
    if not isinstance(investigation, InvestigationRequest):
        raise TypeError("investigation reasoning requires an InvestigationRequest")
    frontier = InvestigationFrontier.for_hypothesis_generation(investigation)
    input_refs = (
        frontier.ref,
        investigation.ref,
        investigation.question.ref,
        *(() if investigation.target_snapshot is None else (investigation.target_snapshot.ref,)),
    )
    request = ReasoningRequest(
        request_id=f"{investigation.investigation_id}:hypotheses",
        kind="hypothesis-generation",
        instruction=(
            "Propose competing falsifiable hypotheses for the exact question; "
            "do not propose interventions or treat a proposal as evidence."
        ),
        input_refs=input_refs,
        target_snapshot=investigation.target_snapshot,
        context={
            "workflow": "investigation",
            "phase": "hypothesis-generation",
            "frontier": frontier.to_dict(),
            "maximum_hypotheses": investigation.max_hypotheses,
            "minimum_hypotheses": 2,
            "portfolio_mode": investigation.portfolio_mode,
        },
        lineage=input_refs,
    )
    return _investigation_reasoning_action(
        run=investigation.canonical_run(),
        action_id="investigation-hypotheses",
        request=request,
    )


def investigation_design_reasoning_action(
    frontier: InvestigationFrontier,
) -> Action:
    action = _make_investigation_design_reasoning_action(frontier)
    expected = derive_investigation_action(
        frontier.investigation,
        frontier.branches,
    )
    if action != expected:
        raise ValueError("investigation design is not the canonical policy frontier")
    return action


def _make_investigation_design_reasoning_action(
    frontier: InvestigationFrontier,
) -> Action:
    if not isinstance(frontier, InvestigationFrontier):
        raise TypeError("investigation design requires an InvestigationFrontier")
    investigation = frontier.investigation
    branch = frontier.selected_branch
    if branch is None:
        raise ValueError("investigation design requires an exact selected branch")
    iteration = len(branch.experiments) + 1
    previous = () if not branch.experiments else (branch.experiments[-1].ref,)
    evidence_refs = tuple(item.evidence_ref for item in branch.evidence)
    input_refs = (
        frontier.ref,
        investigation.ref,
        investigation.question.ref,
        *(item.ref for item in frontier.branches),
        branch.hypothesis.ref,
        *(() if investigation.target_snapshot is None else (investigation.target_snapshot.ref,)),
        *previous,
        *evidence_refs,
    )
    required_objective = f"Falsify the exact hypothesis: {branch.hypothesis.statement}"
    request = ReasoningRequest(
        request_id=(f"{investigation.investigation_id}:{branch.branch_id}:design:{iteration}"),
        kind="experiment-design",
        instruction=(
            "Select one observation-only redesign for this exact hypothesis from the "
            "closed investigation schema; do not propose a target change or intervention."
            if branch.experiments
            else "Select one observation-only falsification experiment for this exact "
            "hypothesis from the closed investigation schema."
        ),
        input_refs=input_refs,
        target_snapshot=investigation.target_snapshot,
        context={
            "workflow": "investigation",
            "phase": "experiment-design",
            "frontier": frontier.to_dict(),
            "branch_id": branch.branch_id,
            "design_iteration": iteration,
            "prior_experiment_root": (
                None if not branch.experiments else branch.experiments[-1].root
            ),
            "evidence_roots": tuple(item.root for item in evidence_refs),
            "required_objective": required_objective,
            "allowed_design_methods": INVESTIGATION_OBSERVATION_METHOD_ORDER,
            "required_criteria": {
                "accepted_relationships": INVESTIGATION_EVIDENCE_RELATIONSHIPS,
                "minimum_evidence_items": 1,
            },
        },
        lineage=input_refs,
    )
    return _investigation_reasoning_action(
        run=investigation.canonical_run(),
        action_id=f"investigation-design-{branch.branch_id}-{iteration}",
        request=request,
    )


def _investigation_reasoning_action(
    *,
    run: Run,
    action_id: str,
    request: ReasoningRequest,
) -> Action:
    if request.target_snapshot != run.target_snapshot:
        raise ValueError("investigation reasoning currentness has drifted")
    return Action(
        run=run.ref,
        action_id=action_id,
        kind=INVESTIGATION_REASONING_ACTION_KIND,
        input_refs=(request.ref, *request.input_refs),
        payload={"request": request.to_dict()},
    )


def _investigation_reasoning_context(
    action: Action,
) -> tuple[
    InvestigationRequest,
    InvestigationFrontier,
    InvestigationBranch | None,
    ReasoningRequest,
]:
    if not isinstance(action, Action) or action.kind != INVESTIGATION_REASONING_ACTION_KIND:
        raise ValueError("action is not investigation reasoning")
    request = reasoning_request_from_action(action)
    context = request.context
    frontier_payload = context.get("frontier")
    if not isinstance(frontier_payload, Mapping):
        raise TypeError("investigation reasoning lost its exact frontier")
    frontier = record_from_dict(thaw(frontier_payload))
    if not isinstance(frontier, InvestigationFrontier):
        raise TypeError("investigation reasoning frontier payload has drifted")
    investigation = frontier.investigation
    phase = context.get("phase")
    if context.get("workflow") != "investigation":
        raise ValueError("investigation reasoning workflow marker has drifted")
    if phase == "hypothesis-generation":
        if frontier.branches or frontier.selected_branch is not None:
            raise ValueError("hypothesis generation requires the empty branch frontier")
        branch: InvestigationBranch | None = None
    elif phase == "experiment-design":
        branch = frontier.selected_branch
        if branch is None:
            raise ValueError("investigation design lost its exact selected branch")
    else:
        raise ValueError("investigation reasoning phase is unsupported")
    expected = derive_investigation_action(investigation, frontier.branches)
    if action != expected or request != reasoning_request_from_action(expected):
        raise ValueError("investigation reasoning action is not policy-derived")
    return investigation, frontier, branch, request


class InvestigationReasoningResultValidator:
    """Nonreplaceable workflow validation before reasoning mutates runtime."""

    action_kind = INVESTIGATION_REASONING_ACTION_KIND

    def validate(self, state: RunState, result: ActionResult) -> None:
        if not isinstance(state, RunState):
            raise TypeError("investigation reasoning validation requires a RunState")
        if not isinstance(result, ActionResult):
            raise TypeError("investigation reasoning validation requires an ActionResult")
        investigation, _, branch, request = _investigation_reasoning_context(result.action)
        if state.run != investigation.canonical_run():
            raise ValueError("investigation reasoning request is stale or mismatched")
        if result.action not in state.pending_actions and result not in state.results:
            raise ValueError("investigation reasoning result is not for a pending action")
        ReasoningResultValidator().validate(state, result)
        if result.disposition != "succeeded":
            if not isinstance(result.failure, RuntimeFailure):
                raise ValueError("failed investigation reasoning requires a RuntimeFailure")
            return
        proposal = reasoning_result_from_action_result(result)
        policy = InvestigationPolicy()
        if request.kind == "hypothesis-generation":
            if branch is not None:
                raise ValueError("hypothesis generation cannot carry a branch")
            policy.hypotheses_from_result(
                investigation=investigation,
                result=proposal,
            )
            return
        if branch is None:
            raise ValueError("investigation design requires its exact branch")
        policy.build_experiment(
            investigation=investigation,
            branch=branch,
            result=proposal,
        )


def make_investigation_experiment_action(
    *,
    run: Run,
    request: InvestigationExperimentRequest,
) -> Action:
    action = _make_investigation_experiment_action(run=run, request=request)
    expected = derive_investigation_action(
        request.investigation,
        request.frontier.branches,
    )
    if action != expected:
        raise ValueError("investigation experiment is not the canonical policy frontier")
    return action


def _make_investigation_experiment_action(
    *,
    run: Run,
    request: InvestigationExperimentRequest,
) -> Action:
    if not isinstance(run, Run):
        raise TypeError("investigation experiment actions require a Run")
    if not isinstance(request, InvestigationExperimentRequest):
        raise TypeError(
            "investigation experiment actions require an InvestigationExperimentRequest"
        )
    if run != request.investigation.canonical_run():
        raise ValueError("investigation experiment request does not match the canonical run")
    return Action(
        run=run.ref,
        action_id=(f"investigation-experiment-{request.branch.branch_id}-{request.sequence}"),
        kind=INVESTIGATION_EXPERIMENT_ACTION_KIND,
        input_refs=(
            request.ref,
            request.frontier.ref,
            *request.frontier.lineage,
            request.branch.hypothesis.ref,
            request.experiment.ref,
        ),
        payload={"request": request.to_dict()},
    )


def derive_investigation_action(
    investigation: InvestigationRequest,
    branches: Sequence[InvestigationBranch],
) -> Action | None:
    """Derive the one canonical action from a complete ordered branch roster."""

    if not isinstance(investigation, InvestigationRequest):
        raise TypeError("investigation action derivation requires an InvestigationRequest")
    items = tuple(branches)
    if any(not isinstance(item, InvestigationBranch) for item in items):
        raise TypeError("investigation action derivation requires InvestigationBranch records")
    if not items:
        return investigation_hypothesis_reasoning_action(investigation)

    policy = InvestigationPolicy()
    branch = policy.prioritized_branch(investigation, items)
    if branch is None:
        return None
    frontier = InvestigationFrontier.for_branch(
        investigation=investigation,
        branches=items,
        selected_branch_id=branch.branch_id,
    )
    total_experiments = sum(len(item.experiments) for item in items)
    if branch.experiments and not policy.experiment_has_evidence(branch):
        request = InvestigationExperimentRequest.for_frontier(
            frontier=frontier,
            sequence=total_experiments,
        )
        return _make_investigation_experiment_action(
            run=investigation.canonical_run(),
            request=request,
        )
    if policy.can_design(
        investigation,
        branch,
        total_experiments=total_experiments,
    ):
        return _make_investigation_design_reasoning_action(frontier)
    return None


def investigation_experiment_request_from_action(
    action: Action,
) -> InvestigationExperimentRequest:
    if not isinstance(action, Action):
        raise TypeError("investigation experiment decoding requires an Action")
    if action.kind != INVESTIGATION_EXPERIMENT_ACTION_KIND:
        raise ValueError("action is not an investigation experiment")
    if frozenset(action.payload) != {"request"}:
        raise ValueError("investigation experiment action must contain only its request")
    payload = action.payload["request"]
    if not isinstance(payload, Mapping):
        raise TypeError("investigation experiment request payload must be a mapping")
    request = record_from_dict(thaw(payload))
    if not isinstance(request, InvestigationExperimentRequest):
        raise TypeError(
            "investigation experiment payload must decode to an InvestigationExperimentRequest"
        )
    expected_refs = (
        request.ref,
        request.frontier.ref,
        *request.frontier.lineage,
        request.branch.hypothesis.ref,
        request.experiment.ref,
    )
    if action.input_refs != expected_refs:
        raise ValueError("investigation experiment action lineage has drifted")
    expected_id = f"investigation-experiment-{request.branch.branch_id}-{request.sequence}"
    if action.action_id != expected_id:
        raise ValueError("investigation experiment action id has drifted")
    expected = derive_investigation_action(request.investigation, request.frontier.branches)
    if action != expected:
        raise ValueError("investigation experiment action is not policy-derived")
    return request


def make_investigation_experiment_result(
    *,
    action: Action,
    batch: InvestigationEvidenceBatch,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    request = investigation_experiment_request_from_action(action)
    if not isinstance(batch, InvestigationEvidenceBatch):
        raise TypeError("investigation experiment results require an evidence batch")
    if batch.request != request:
        raise ValueError("investigation evidence does not answer the exact dispatched request")
    return ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(batch.ref,),
        payload={"batch": batch.to_dict()},
        resource_usage=resource_usage or {},
    )


def make_investigation_experiment_failure(
    *,
    action: Action,
    failure: RuntimeFailure,
    resource_usage: Mapping[str, float] | None = None,
) -> ActionResult:
    investigation_experiment_request_from_action(action)
    if not isinstance(failure, RuntimeFailure):
        raise TypeError("investigation experiment failures require a RuntimeFailure")
    return ActionResult(
        action=action,
        disposition="failed",
        failure=failure,
        resource_usage=resource_usage or {},
    )


def investigation_batch_from_action_result(
    action_result: ActionResult,
) -> InvestigationEvidenceBatch:
    if not isinstance(action_result, ActionResult):
        raise TypeError("investigation batch decoding requires an ActionResult")
    request = investigation_experiment_request_from_action(action_result.action)
    if action_result.disposition != "succeeded":
        raise ValueError("failed investigation experiments do not contain evidence batches")
    if frozenset(action_result.payload) != {"batch"}:
        raise ValueError("investigation result payload must contain only its evidence batch")
    payload: Any = action_result.payload["batch"]
    if not isinstance(payload, Mapping):
        raise TypeError("investigation evidence batch payload must be a mapping")
    batch = record_from_dict(thaw(payload))
    if not isinstance(batch, InvestigationEvidenceBatch):
        raise TypeError("investigation payload must decode to an InvestigationEvidenceBatch")
    if batch.request != request:
        raise ValueError("investigation evidence does not answer the exact dispatched request")
    if action_result.output_refs != (batch.ref,):
        raise ValueError("investigation outputs may cite only the exact evidence batch")
    return batch


def validate_investigation_experiment_result_shape(
    result: ActionResult,
) -> InvestigationExperimentRequest:
    """Validate one experiment result without requiring runtime membership."""

    if not isinstance(result, ActionResult):
        raise TypeError("investigation result validation requires an ActionResult")
    request = investigation_experiment_request_from_action(result.action)
    if result.disposition == "succeeded":
        investigation_batch_from_action_result(result)
    elif result.payload or result.output_refs:
        raise ValueError("failed investigation results cannot contain batch outputs")
    if result.disposition != "succeeded" and not isinstance(result.failure, RuntimeFailure):
        raise ValueError("failed investigation results require a RuntimeFailure")
    return request


class InvestigationExperimentResultValidator:
    """Nonreplaceable validation before an investigation result mutates runtime."""

    action_kind = INVESTIGATION_EXPERIMENT_ACTION_KIND

    def validate(self, state: RunState, result: ActionResult) -> None:
        if not isinstance(state, RunState):
            raise TypeError("investigation result validation requires a RunState")
        request = validate_investigation_experiment_result_shape(result)
        if state.run != request.investigation.canonical_run():
            raise ValueError("investigation experiment request is stale or mismatched")
