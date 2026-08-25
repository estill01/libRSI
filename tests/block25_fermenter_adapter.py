from __future__ import annotations

from librsi import (
    Action,
    ActionResult,
    CandidateSnapshot,
    Claim,
    Evidence,
    Hypothesis,
    ImprovementBudget,
    ImprovementCycleProposal,
    ImprovementRequest,
    InterventionImplementationRequest,
    InterventionSpec,
    InvestigationEvidenceBatch,
    OperationalizationPolicy,
    OperationalizationRequest,
    Question,
    ReasoningResult,
    TargetSnapshot,
    ValidationEvidenceBatch,
    cycle_request_from_action,
    investigate,
    investigation_experiment_request_from_action,
    make_cycle_result,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action_result,
    make_validation_evidence_result,
    reasoning_request_from_action,
    validation_evidence_request_from_action,
)
from tests.block14_support import ComparisonContext, comparison_context, trial_batch


def fermenter_question(context: ComparisonContext, *, purpose: str) -> Question:
    return Question(
        prompt=(
            "Which physical transfer mechanism limits fermentation yield while the "
            f"contamination guardrail remains satisfied ({purpose})?"
        ),
        target=context.target,
        lineage=(context.baseline_snapshot.ref,),
    )


def fermenter_hypotheses(question: Question) -> tuple[Hypothesis, Hypothesis]:
    return (
        Hypothesis(
            statement="Oxygen transfer is the limiting physical mechanism",
            target=question.target,
            causal_model={"mechanism": "oxygen-transfer"},
            predictions=({"dissolved_oxygen_response": "limiting"},),
            source_refs=(question.ref,),
            lineage=(question.ref,),
        ),
        Hypothesis(
            statement="Thermal transfer is the limiting physical mechanism",
            target=question.target,
            causal_model={"mechanism": "thermal-transfer"},
            predictions=({"thermal_response": "limiting"},),
            source_refs=(question.ref,),
            lineage=(question.ref,),
        ),
    )


def fermenter_improvement_request(context: ComparisonContext) -> ImprovementRequest:
    operationalization_request = OperationalizationRequest.create(
        request_id="fermenter-cross-domain-operationalization",
        goal=context.contract.goal,
        current_snapshot=context.baseline_snapshot,
    )
    operationalization = OperationalizationPolicy().accept_typed(
        operationalization_request,
        context.contract,
    )
    question = fermenter_question(context, purpose="improvement")
    hypotheses = fermenter_hypotheses(question)
    return ImprovementRequest.create(
        request_id="fermenter-cross-domain-improvement",
        operationalization=operationalization,
        question=question,
        initial_hypotheses=hypotheses,
        risk_policy=context.risk_policy,
        budget=ImprovementBudget(
            max_iterations=1,
            max_experiments=3,
            max_retries=0,
            max_resource_units=2,
            diminishing_return_patience=1,
        ),
    )


class FermenterAdapter:
    """Deterministic physical-process effects behind libRSI capability ports."""

    def __init__(self, context: ComparisonContext | None = None) -> None:
        self.context = comparison_context() if context is None else context
        self.actions: list[Action] = []

    def reason(self, action: Action) -> ActionResult:
        self.actions.append(action)
        request = reasoning_request_from_action(action)
        if request.kind != "experiment-design":
            raise ValueError("the fermenter adapter accepts only bounded experiment design")
        content = make_investigation_observation_content(
            request,
            measurements=("dissolved-oxygen-response", "thermal-response"),
        )
        return make_reasoning_action_result(
            action=action,
            result=ReasoningResult.propose(request=request, content=content),
        )

    def experiment(self, action: Action) -> ActionResult:
        self.actions.append(action)
        if action.kind == "validation-evidence":
            return self._validation_evidence(action)
        if action.kind == "investigation-experiment":
            return self._investigation_evidence(action)
        raise ValueError("the fermenter adapter received an unsupported experiment action")

    def _validation_evidence(self, action: Action) -> ActionResult:
        request = validation_evidence_request_from_action(action)
        snapshot = request.validation.target_snapshot
        if snapshot != self.context.baseline_snapshot:
            raise ValueError("validation is not bound to the exact fermenter baseline")
        evidence = tuple(
            Evidence(
                evidence_type="support",
                data={
                    "batch": batch,
                    "yield_pct": 72.0,
                    "contamination_ppm": 2.0,
                },
                subject_refs=(request.validation.claim.ref,),
                source_refs=(request.ref,),
                target_snapshot=snapshot,
                weight=1.0,
            )
            for batch in (1, 2)
        )
        return make_validation_evidence_result(
            action=action,
            batch=ValidationEvidenceBatch.collected(request=request, evidence=evidence),
        )

    def _investigation_evidence(self, action: Action) -> ActionResult:
        request = investigation_experiment_request_from_action(action)
        if request.investigation.target_snapshot != self.context.baseline_snapshot:
            raise ValueError("investigation is not bound to the exact fermenter baseline")
        mechanism = request.branch.hypothesis.causal_model["mechanism"]
        relationship = "support" if mechanism == "thermal-transfer" else "counterexample"
        evidence = tuple(
            Evidence(
                evidence_type=relationship,
                data={"replicate": replicate, "mechanism": mechanism},
                subject_refs=(request.branch.hypothesis.ref,),
                source_refs=(request.experiment.ref,),
                target_snapshot=self.context.baseline_snapshot,
                weight=1.0,
            )
            for replicate in (1, 2)
        )
        return make_investigation_experiment_result(
            action=action,
            batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
        )

    def resource_claim(self, action: Action) -> float:
        cycle_request_from_action(action)
        return action.budget_reservation["units"]

    def improve_cycle(self, action: Action) -> ActionResult:
        self.actions.append(action)
        cycle = cycle_request_from_action(action)
        investigation = investigate(
            question=cycle.improvement.question,
            target_snapshot=cycle.improvement.baseline,
            investigation_id=f"{cycle.improvement.request_id}:investigation:1",
            initial_hypotheses=cycle.improvement.initial_hypotheses,
            max_hypotheses=2,
            max_experiments=2,
            max_redesigns_per_hypothesis=0,
            reasoner=self,
            experimenter=self,
        )
        supported = next(
            branch for branch in investigation.branches if branch.status == "supported"
        )
        intervention = InterventionSpec.create(
            intervention_id="fermenter-bounded-thermal-setpoint",
            baseline=self.context.baseline_snapshot,
            kind="physical-process.parameter-change",
            specification={"parameter": "temperature_c", "from": 31.0, "to": 32.0},
            rationale=("Test the supported thermal-transfer mechanism",),
            supporting_refs=(supported.hypothesis.ref,),
            evidence=supported.evidence,
            expected_effects={"yield_pct": "increase", "energy_kwh": "decrease"},
            risks=("Contamination may increase",),
            constraints=(self.context.constraint,),
            validation_plan={"controlled_batches": 3},
            rollback_expectations={"restore_temperature_c": 31.0},
        )
        candidate = CandidateSnapshot.prepared(
            request=InterventionImplementationRequest.for_intervention(
                intervention,
                candidate_id="fermenter-thermal-candidate",
            ),
            snapshot=TargetSnapshot(
                target=self.context.target,
                revision="fermenter-thermal-candidate-v1",
                state={
                    "temperature_c": 32.0,
                    "yield_pct": 76.0,
                    "energy_kwh": 16.0,
                    "contamination_ppm": 2.0,
                },
            ),
        )
        batch = trial_batch(self.context, candidate)
        proposal = ImprovementCycleProposal.create(
            request=cycle,
            investigation=investigation,
            batches=(batch,),
        )
        return make_cycle_result(action=action, proposal=proposal, resource_units=1)


def fermenter_validation_claim(context: ComparisonContext) -> Claim:
    return Claim(
        statement="The fermenter remains within its measured production envelope",
        kind="physical-process-bound",
        target=context.target,
        lineage=(context.baseline_snapshot.ref,),
    )
