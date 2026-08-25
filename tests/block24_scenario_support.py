from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from librsi import (
    Action,
    ActionResult,
    CandidateSnapshot,
    CapabilityRegistry,
    Evidence,
    Hypothesis,
    ImprovementCycleProposal,
    ImprovementRequest,
    InterventionImplementationRequest,
    InterventionSpec,
    ManagedBounds,
    ReasoningRequest,
    ReasoningResult,
    TargetSnapshot,
    cycle_request_from_action,
    investigate,
    investigation_experiment_request_from_action,
    make_cycle_result,
    make_investigation_experiment_result,
    record_from_dict,
)
from librsi.investigation import InvestigationEvidenceBatch
from librsi.protocol import TargetAdmission
from librsi.providers import CodexAppServerBackend, CodexProcessPolicy
from librsi.service import LibRSIService
from tests.block14_support import ComparisonContext, comparison_context, trial_batch
from tests.block15_support import CycleReasoner, hypotheses
from tests.block20_support import workflow_cases
from tests.block21_support import ManagedImprovementProvider, automatic_admission


class SystemExperimenter:
    """Return discriminating support in one lane and honest nulls in the other."""

    def experiment(self, action: Action) -> ActionResult:
        request = investigation_experiment_request_from_action(action)
        mechanism = request.branch.hypothesis.causal_model["mechanism"]
        relationship = "support" if mechanism == "primary" else "null"
        evidence = tuple(
            Evidence(
                evidence_type=relationship,
                data={"measurement": "controlled-response", "replicate": index},
                subject_refs=(request.branch.hypothesis.ref,),
                source_refs=(request.experiment.ref,),
                target_snapshot=request.investigation.target_snapshot,
                weight=1.0 if relationship == "support" else 0.0,
            )
            for index in (1, 2)
        )
        return make_investigation_experiment_result(
            action=action,
            batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
        )


def _candidate_batch(
    action: Action,
    *,
    context: ComparisonContext,
    investigation,
    candidate_id: str,
    candidate_rows: tuple[tuple[float, float, float], ...],
):
    cycle = cycle_request_from_action(action)
    supported = next(branch for branch in investigation.branches if branch.status == "supported")
    intervention = InterventionSpec.create(
        intervention_id=f"system-{cycle.directive.iteration}-{candidate_id}",
        baseline=context.baseline_snapshot,
        kind="bounded.parameter-change",
        specification={"candidate": candidate_id, "iteration": cycle.directive.iteration},
        rationale=("Compare the intervention under the supported mechanism",),
        supporting_refs=(supported.hypothesis.ref,),
        evidence=supported.evidence,
        expected_effects={"objective": "improve"},
        risks=("Guardrail regression",),
        constraints=(context.constraint,),
        validation_plan={"comparison": "controlled"},
        rollback_expectations={"restore": context.baseline_snapshot.revision},
    )
    candidate = CandidateSnapshot.prepared(
        request=InterventionImplementationRequest.for_intervention(
            intervention,
            candidate_id=f"{candidate_id}-{cycle.directive.iteration}",
        ),
        snapshot=TargetSnapshot(
            target=context.target,
            revision=f"candidate-{candidate_id}-{cycle.directive.iteration}",
            state={"candidate": candidate_id, "iteration": cycle.directive.iteration},
        ),
    )
    return trial_batch(
        context,
        candidate,
        candidate_rows=candidate_rows,
        experiment_suffix=f"-{cycle.directive.iteration}",
    )


def system_cycle_proposal(
    action: Action,
    *,
    context: ComparisonContext,
) -> ImprovementCycleProposal:
    cycle = cycle_request_from_action(action)
    seeds = (
        cycle.improvement.initial_hypotheses
        if cycle.directive.iteration == 1
        else hypotheses(cycle.improvement.question, f"replacement-{cycle.directive.iteration}")
    )
    investigation = investigate(
        question=cycle.improvement.question,
        target_snapshot=cycle.improvement.baseline,
        investigation_id=f"system-cycle-{cycle.directive.iteration}",
        initial_hypotheses=seeds,
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
        reasoner=CycleReasoner(),
        experimenter=SystemExperimenter(),
    )
    rows = (
        (
            ((72.0, 18.0, 2.0),) * 3,
            ((71.0, 19.0, 2.0),) * 3,
        )
        if cycle.directive.iteration == 1
        else (
            ((76.0, 16.0, 2.0),) * 3,
            ((74.0, 17.0, 2.0),) * 3,
        )
    )
    leading = _candidate_batch(
        action,
        context=context,
        investigation=investigation,
        candidate_id="leading",
        candidate_rows=rows[0],
    )
    alternative = _candidate_batch(
        action,
        context=context,
        investigation=investigation,
        candidate_id="alternative",
        candidate_rows=rows[1],
    )
    return ImprovementCycleProposal.create(
        request=cycle,
        investigation=investigation,
        batches=(leading, alternative),
    )


class SystemCycleProvider:
    def __init__(self, context: ComparisonContext) -> None:
        self.context = context
        self.actions: list[Action] = []

    def improve_cycle(self, action: Action) -> ActionResult:
        self.actions.append(action)
        return make_cycle_result(
            action=action,
            proposal=system_cycle_proposal(action, context=self.context),
            resource_units=1,
        )


@dataclass(frozen=True, slots=True)
class SystemScenarioResult:
    projection: dict[str, object]
    provider: SystemCycleProvider
    execution_stop_reason: str
    request: ImprovementRequest


@dataclass(frozen=True, slots=True)
class SystemScenarioInput:
    request: ImprovementRequest
    admission: TargetAdmission
    proposal: ReasoningResult
    executor: InjectedCodexFake


def run_system_improvement(
    root: Path,
    *,
    managed: bool,
    scenario: SystemScenarioInput,
) -> SystemScenarioResult:
    context = comparison_context()
    admission = automatic_admission(scenario.admission) if managed else scenario.admission
    provider = SystemCycleProvider(context)
    registry = (
        CapabilityRegistry(
            routes=tuple(binding.route() for binding in admission.capabilities),
            implementations=(ManagedImprovementProvider(provider),),
        )
        if managed
        else None
    )
    service = LibRSIService.local(root, registry=registry)
    run_id = scenario.request.canonical_run().run_id
    try:
        service.submit_target(admission)
        service.improve(scenario.request, admission_id=admission.admission_id)
        if managed:
            execution = service.run_managed(run_id, ManagedBounds(max_actions=4))
            stop_reason = execution.stop_reason
        else:
            while not service.get_status(run_id)["data"]["terminal"]:
                pending = service.next_actions(run_id)
                action = record_from_dict(pending["data"]["action"])
                assert type(action) is Action
                service.submit_result(
                    run_id,
                    provider.improve_cycle(action),
                    authority="external",
                )
            stop_reason = "outcome"
        projection = service.get_outcome(run_id)["data"]["projection"]
        assert type(projection) is dict
        return SystemScenarioResult(projection, provider, stop_reason, scenario.request)
    finally:
        service.close()


class InjectedCodexFake:
    """Injected proposal provider that owns no process and records its exact input."""

    def __init__(self) -> None:
        self.policy = CodexProcessPolicy(owner="embedding-host")
        self.process_owner_count = 0
        self.requests: list[ReasoningRequest] = []

    def complete(self, request: ReasoningRequest) -> str:
        self.requests.append(request)
        assert request.kind == "hypothesis-generation"
        return json.dumps(
            {
                "content": {
                    "hypotheses": [
                        {
                            "statement": "Primary mechanism changes controlled response",
                            "causal_model": {"mechanism": "primary"},
                            "predictions": [{"signal": "primary"}],
                            "confidence": 0.5,
                        },
                        {
                            "statement": "Alternative mechanism changes controlled response",
                            "causal_model": {"mechanism": "alternative"},
                            "predictions": [{"signal": "alternative"}],
                            "confidence": 0.5,
                        },
                    ]
                },
                "narration": "Two competing proposals; neither is evidence.",
            }
        )


def system_scenario_input() -> SystemScenarioInput:
    """Build one request whose initial hypotheses derive from the Codex proposal."""

    case = next(item for item in workflow_cases() if item.command == "improve")
    request = case.request
    assert type(request) is ImprovementRequest
    reasoning = ReasoningRequest(
        request_id="system-codex-hypotheses",
        kind="hypothesis-generation",
        instruction="Propose two materially competing causal mechanisms",
        input_refs=(request.question.ref, request.baseline.ref),
        target_snapshot=request.baseline,
        context={"objective": request.contract.goal.statement},
        lineage=(request.question.ref, request.baseline.ref),
    )
    executor = InjectedCodexFake()
    proposal = CodexAppServerBackend(executor).respond(reasoning)
    rows = proposal.content["hypotheses"]
    if not isinstance(rows, tuple) or len(rows) != 2:
        raise RuntimeError("system Codex proposal must contain two hypotheses")
    derived = tuple(
        Hypothesis(
            statement=row["statement"],
            target=request.question.target,
            causal_model=row["causal_model"],
            predictions=tuple(row["predictions"]),
            source_refs=(request.question.ref, proposal.ref),
            confidence=row["confidence"],
            lineage=(proposal.ref, proposal.request.ref, *proposal.request.input_refs),
        )
        for row in rows
    )
    causal_request = ImprovementRequest.create(
        request_id=request.request_id,
        operationalization=request.operationalization,
        question=request.question,
        initial_hypotheses=derived,
        risk_policy=request.risk_policy,
        governance_requirement=request.governance_requirement,
        budget=request.budget,
    )
    return SystemScenarioInput(causal_request, case.admission, proposal, executor)
