from __future__ import annotations

from librsi import (
    Action,
    ActionResult,
    CandidateSnapshot,
    CandidateTrialBatch,
    Evidence,
    Hypothesis,
    ImprovementCycleProposal,
    ImprovementRequest,
    InterventionImplementationRequest,
    InterventionSpec,
    OperationalizationPolicy,
    OperationalizationRequest,
    Question,
    cycle_request_from_action,
    investigate,
    investigation_experiment_request_from_action,
    make_cycle_result,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action_result,
    reasoning_request_from_action,
)
from tests.block14_support import ComparisonContext, candidate_for, comparison_context, trial_batch


class CycleReasoner:
    def reason(self, action: Action) -> ActionResult:
        request = reasoning_request_from_action(action)
        content = make_investigation_observation_content(request, measurements=("response",))
        from librsi import ReasoningResult

        return make_reasoning_action_result(
            action=action,
            result=ReasoningResult.propose(request=request, content=content),
        )


class CycleExperimenter:
    def experiment(self, action: Action) -> ActionResult:
        request = investigation_experiment_request_from_action(action)
        relationship = "counterexample" if request.branch.branch_id.endswith("1") else "support"
        evidence = tuple(
            Evidence(
                evidence_type=relationship,
                data={"replicate": index},
                subject_refs=(request.branch.hypothesis.ref,),
                source_refs=(request.experiment.ref,),
                target_snapshot=request.investigation.target_snapshot,
                weight=1.0,
            )
            for index in (1, 2)
        )
        from librsi import InvestigationEvidenceBatch

        return make_investigation_experiment_result(
            action=action,
            batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
        )


def hypotheses(question: Question, suffix: str = "initial") -> tuple[Hypothesis, Hypothesis]:
    return tuple(
        Hypothesis(
            statement=f"{label} mechanism explains the target ({suffix})",
            target=question.target,
            causal_model={"mechanism": label},
            predictions=({"signal": label},),
            source_refs=(question.ref,),
            lineage=(question.ref,),
        )
        for label in ("primary", "alternative")
    )  # type: ignore[return-value]


def improvement_request(
    context: ComparisonContext | None = None,
    *,
    governance_requirement=None,
    patience: int = 2,
    max_iterations: int = 3,
    max_experiments: int = 9,
    max_resource_units: float = 10,
    max_retries: int = 1,
) -> ImprovementRequest:
    from librsi import ImprovementBudget, RiskPolicy

    context = comparison_context() if context is None else context
    operationalization_request = OperationalizationRequest.create(
        request_id="improvement-operationalization",
        goal=context.contract.goal,
        current_snapshot=context.baseline_snapshot,
    )
    operationalization = OperationalizationPolicy().accept_typed(
        operationalization_request,
        context.contract,
    )
    question = Question(
        prompt="Which causal mechanism can improve the exact objective?",
        target=context.target,
        lineage=(context.baseline_snapshot.ref,),
    )
    seeds = hypotheses(question)
    return ImprovementRequest.create(
        request_id="bounded-improvement",
        operationalization=operationalization,
        question=question,
        initial_hypotheses=seeds,
        risk_policy=RiskPolicy(policy_id="loop-risk", confidence_multiplier=1.0),
        governance_requirement=governance_requirement,
        budget=ImprovementBudget(
            max_iterations=max_iterations,
            max_experiments=max_experiments,
            max_retries=max_retries,
            max_resource_units=max_resource_units,
            diminishing_return_patience=patience,
        ),
    )


def cycle_proposal(
    action: Action,
    *,
    context: ComparisonContext,
    accepted: bool,
    guardrail_failure: bool = False,
    hypothesis_seeds: tuple[Hypothesis, Hypothesis] | None = None,
) -> ImprovementCycleProposal:
    cycle = cycle_request_from_action(action)
    seeds = (
        hypothesis_seeds
        if hypothesis_seeds is not None
        else cycle.improvement.initial_hypotheses
        if cycle.directive.iteration == 1
        else hypotheses(cycle.improvement.question, f"replacement-{cycle.directive.iteration}")
    )
    investigation = investigate(
        question=cycle.improvement.question,
        target_snapshot=cycle.improvement.baseline,
        investigation_id=f"cycle-{cycle.directive.iteration}",
        initial_hypotheses=seeds,
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
        reasoner=CycleReasoner(),
        experimenter=CycleExperimenter(),
    )
    supported = next(branch for branch in investigation.branches if branch.status == "supported")
    intervention = InterventionSpec.create(
        intervention_id=f"cycle-{cycle.directive.iteration}-intervention",
        baseline=context.baseline_snapshot,
        kind="bounded.parameter-change",
        specification={"iteration": cycle.directive.iteration},
        rationale=("Test the supported causal mechanism",),
        supporting_refs=(supported.hypothesis.ref,),
        evidence=supported.evidence,
        expected_effects={"objective": "improve"},
        risks=("Guardrail regression",),
        constraints=(context.constraint,),
        validation_plan={"comparison": "controlled"},
        rollback_expectations={"restore": context.baseline_snapshot.revision},
    )
    candidate_id = f"cycle-{cycle.directive.iteration}"
    candidate = CandidateSnapshot.prepared(
        request=InterventionImplementationRequest.for_intervention(
            intervention, candidate_id=candidate_id
        ),
        snapshot=candidate_for(context, candidate_id).snapshot,
    )
    rows = (
        ((76.0, 16.0, 5.0),) * 3
        if guardrail_failure
        else ((76.0, 16.0, 2.0),) * 3
        if accepted
        else ((72.0, 18.0, 2.0),) * 3
    )
    batch: CandidateTrialBatch = trial_batch(context, candidate, candidate_rows=rows)
    return ImprovementCycleProposal.create(
        request=cycle,
        investigation=investigation,
        batches=(batch,),
    )


class DeterministicCycleProvider:
    def __init__(self, context: ComparisonContext, outcomes: tuple[bool, ...]) -> None:
        self.context = context
        self.outcomes = outcomes
        self.actions: list[Action] = []

    def resource_claim(self, action: Action) -> float:
        cycle_request_from_action(action)
        return action.budget_reservation["units"]

    def improve_cycle(self, action: Action) -> ActionResult:
        self.actions.append(action)
        proposal = cycle_proposal(
            action,
            context=self.context,
            accepted=self.outcomes[len(self.actions) - 1],
        )
        return make_cycle_result(action=action, proposal=proposal, resource_units=1)
