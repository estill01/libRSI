"""Nonreplaceable policy for improvement-cycle validation and learning."""

from __future__ import annotations

from collections.abc import Sequence

from ..comparison import ComparativeSelectionPolicy
from ..intent import OperationalizationPolicy
from ..records import RecordRef
from .directives import next_search_directive
from .records import (
    ImprovementCycleProposal,
    ImprovementIteration,
    ImprovementRequest,
)


def validate_cycle_admissibility(proposal: ImprovementCycleProposal) -> None:
    """Validate invariants that do not depend on earlier iterations."""

    if type(proposal) is not ImprovementCycleProposal:
        raise TypeError("cycle admissibility requires an ImprovementCycleProposal")
    request = proposal.request.improvement
    ImprovementPolicy.validate_request(request)
    investigation = proposal.investigation.investigation
    if investigation.question != request.question:
        raise ValueError("cycle investigation answers another question")
    if investigation.target_snapshot != request.baseline:
        raise ValueError("cycle investigation is stale or target-mismatched")
    if (
        proposal.request.directive.iteration == 1
        and investigation.initial_hypotheses != request.initial_hypotheses
    ):
        raise ValueError("first cycle must investigate the declared competing hypotheses")
    if (
        proposal.request.directive.iteration == 1
        and proposal.request.remaining_resource_units != request.budget.max_resource_units
    ):
        raise ValueError("first cycle must expose the complete resource allowance")
    if (
        proposal.request.directive.iteration == 1
        and proposal.request.resource_units_per_attempt
        != request.budget.max_resource_units / (request.budget.max_retries + 1)
    ):
        raise ValueError("first cycle per-attempt resources must preserve every retry")
    supported = tuple(
        branch for branch in proposal.investigation.branches if branch.status == "supported"
    )
    supported_hypotheses = {branch.hypothesis.ref for branch in supported}
    supporting_evidence = {
        item.ref
        for branch in supported
        for item in branch.evidence
        if item.evidence_type == "support"
    }
    for batch in proposal.batches:
        if batch.contract != request.contract:
            raise ValueError("cycle candidate comparison uses another evaluation contract")
        intervention = batch.candidate.request.intervention
        if intervention.baseline != request.baseline:
            raise ValueError("cycle candidate was prepared from a stale baseline")
        if not set(intervention.supporting_refs).issubset(supported_hypotheses):
            raise ValueError("candidate intervention must cite only supported hypotheses")
        if not intervention.evidence or not {item.ref for item in intervention.evidence}.issubset(
            supporting_evidence
        ):
            raise ValueError("candidate intervention requires exact supporting evidence")


def improvement_history(
    previous: ImprovementIteration | None,
) -> tuple[ImprovementIteration, ...]:
    """Recover the complete root-to-frontier chain embedded in an iteration."""

    if previous is None:
        return ()
    if type(previous) is not ImprovementIteration:
        raise TypeError("improvement history requires ImprovementIteration records")
    reversed_history: list[ImprovementIteration] = []
    seen: set[int] = set()
    current: ImprovementIteration | None = previous
    while current is not None:
        if type(current) is not ImprovementIteration:
            raise TypeError("improvement history requires ImprovementIteration records")
        identity = id(current)
        if identity in seen:
            raise ValueError("improvement history contains a predecessor cycle")
        seen.add(identity)
        reversed_history.append(current)
        current = current.previous_iteration
    return tuple(reversed(reversed_history))


def validate_cycle_sequence(
    proposal: ImprovementCycleProposal,
    previous: ImprovementIteration | None,
) -> tuple[RecordRef, ...]:
    """Validate every chain-dependent rule and return evidence-derived rejections."""

    validate_cycle_admissibility(proposal)
    history = improvement_history(previous)
    request = proposal.request.improvement
    if any(item.proposal.request.improvement != request for item in history):
        raise ValueError("improvement history belongs to another request")
    experiments_used = sum(item.proposal.experiment_count for item in history)
    expected_remaining = request.budget.max_experiments - experiments_used
    if proposal.request.remaining_experiments != expected_remaining:
        raise ValueError("cycle experiment allowance is not the exact remaining budget")
    if proposal.request.directive != next_search_directive(previous):
        raise ValueError("cycle search directive is not the exact policy-derived frontier")

    investigation = proposal.investigation.investigation
    if investigation.question != request.question:
        raise ValueError("cycle investigation answers another question")
    if investigation.target_snapshot != request.baseline:
        raise ValueError("cycle investigation is stale or target-mismatched")
    if not history and investigation.initial_hypotheses != request.initial_hypotheses:
        raise ValueError("first cycle must investigate the declared competing hypotheses")
    rejected = tuple(
        branch.hypothesis.ref
        for branch in proposal.investigation.branches
        if branch.status == "rejected"
    )
    if history:
        prior_hypotheses = {
            branch.hypothesis.ref for branch in history[-1].proposal.investigation.branches
        }
        current_hypotheses = {branch.hypothesis.ref for branch in proposal.investigation.branches}
        if history[-1].selection.disposition == "none-accepted" and (
            current_hypotheses == prior_hypotheses
        ):
            raise ValueError("failed cycles must not blindly retry the same hypothesis set")
        historically_rejected = {
            hypothesis for iteration in history for hypothesis in iteration.rejected_hypotheses
        }
        if historically_rejected & current_hypotheses:
            raise ValueError("falsified hypotheses must be replaced, not relabeled")
    return rejected


def improvement_stop_reason(
    request: ImprovementRequest,
    iterations: Sequence[ImprovementIteration],
    *,
    resource_units: float = 0.0,
) -> str | None:
    """Return the unique workflow-precedence stop projection."""

    items = tuple(iterations)
    if not items:
        return None
    if items[-1].next_direction == "stop":
        return "accepted candidate selected"
    if len(items) >= request.budget.max_iterations:
        return "iteration budget exhausted"
    experiments = sum(item.proposal.experiment_count for item in items)
    if experiments >= request.budget.max_experiments:
        return "experiment budget exhausted"
    if resource_units >= request.budget.max_resource_units:
        return "resource budget exhausted"
    if len(items) >= request.budget.diminishing_return_patience:
        return "diminishing returns"
    return None


class ImprovementPolicy:
    """Owns currentness, composition, selection, and search-direction decisions."""

    @staticmethod
    def validate_request(request: ImprovementRequest) -> None:
        if type(request) is not ImprovementRequest:
            raise TypeError("improvement policy requires an ImprovementRequest")
        OperationalizationPolicy.validate_contract(
            request.operationalization.request,
            request.contract,
        )
        if request.operationalization.request.current_snapshot != request.baseline:
            raise ValueError("improvement baseline is no longer the operationalized snapshot")

    @classmethod
    def evaluate(
        cls,
        proposal: ImprovementCycleProposal,
        *,
        previous: Sequence[ImprovementIteration] = (),
    ) -> ImprovementIteration:
        if type(proposal) is not ImprovementCycleProposal:
            raise TypeError("improvement evaluation requires an ImprovementCycleProposal")
        history = tuple(previous)
        if any(type(item) is not ImprovementIteration for item in history):
            raise TypeError("improvement history requires ImprovementIteration records")
        prior = history[-1] if history else None
        if history != improvement_history(prior):
            raise ValueError("improvement history is not a continuous iteration chain")
        request = proposal.request.improvement
        rejected = validate_cycle_sequence(proposal, prior)
        selection = ComparativeSelectionPolicy.select(
            selection_id=f"{request.request_id}:selection:{proposal.request.directive.iteration}",
            contract=request.contract,
            batches=proposal.batches,
            risk_policy=request.risk_policy,
        )
        if selection.disposition != "none-accepted":
            direction = "stop"
        elif any(
            any(
                criterion.criterion_kind == "objective" and criterion.disposition == "passed"
                for criterion in assessment.criteria
            )
            for assessment in selection.assessments
        ):
            direction = "narrow"
        else:
            direction = "broaden"
        return ImprovementIteration(
            proposal=proposal,
            selection=selection,
            next_direction=direction,
            previous_iteration=prior,
            rejected_hypotheses=rejected,
            lineage=(
                proposal.ref,
                selection.ref,
                *((prior.ref,) if prior is not None else ()),
                *rejected,
            ),
        )
