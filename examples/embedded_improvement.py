"""Two measured cycles, interrupted and resumed from SQLite; no network or application.

Run after installing libRSI: python examples/embedded_improvement.py --data-dir ./demo
The host supplies the objective, hypotheses, measurements, and candidate preparation.
libRSI validates the records, compares candidates, bounds the loop, and selects a handoff.
"""

from __future__ import annotations

import argparse
import json
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal

from librsi import (
    Action,
    ActionResult,
    Baseline,
    CandidateSnapshot,
    CandidateTrialBatch,
    DecisionRule,
    EvaluationContract,
    Evidence,
    ExperimentEvaluator,
    Goal,
    Hypothesis,
    ImprovementBudget,
    ImprovementCycleProposal,
    ImprovementRequest,
    ImprovementUpdate,
    ImprovementWorkflow,
    InterventionImplementationRequest,
    InterventionSpec,
    InvestigationEvidenceBatch,
    LibRSI,
    Measurement,
    Metric,
    Objective,
    Observation,
    OperationalizationPolicy,
    OperationalizationRequest,
    Question,
    ReasoningResult,
    RiskPolicy,
    SQLiteRuntimeStore,
    StoppingRule,
    TargetRef,
    TargetSnapshot,
    cycle_request_from_action,
    investigate,
    investigation_experiment_request_from_action,
    make_cycle_result,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action_result,
    persist_transitions,
    reasoning_request_from_action,
)


def error(x: float) -> float:
    """The entire target: tune x to reduce its distance from 4."""
    return abs(4 - x)


def hypotheses(question: Question, delta: int) -> tuple[Hypothesis, ...]:
    return tuple(
        Hypothesis(
            statement=f"Changing x by {step} reduces error",
            target=question.target,
            causal_model={"delta": step},
            predictions=({"error": "decrease"},),
            source_refs=(question.ref,),
            lineage=(question.ref,),
        )
        for step in (delta, -delta)
    )


def improvement_request() -> ImprovementRequest:
    target = TargetRef(target_id="scalar-demo", kind="numeric-function")
    snapshot = TargetSnapshot(target=target, revision="x=0", state={"x": 0})
    goal = Goal(statement="Reduce distance from 4 by at least 2", target=target)
    metric = Metric(metric_id="error", direction="decrease", role="objective", unit="distance")
    contract = EvaluationContract.create(
        contract_id="distance-v1",
        goal=goal,
        baseline=Baseline.create(snapshot=snapshot, measurements={"error": error(0)}),
        objectives=(
            Objective.create(
                objective_id="reduce-error",
                metric=metric,
                semantics="minimize",
                goal=goal,
                minimum_effect=2,
            ),
        ),
        constraints=(),
        guardrails=(),
        stopping_rules=(
            StoppingRule(
                rule_id="sufficient",
                kind="criteria-sufficient",
                condition="Select when measured error decreases by at least 2",
            ),
        ),
    )
    question = Question(
        prompt="Which bounded change to x reduces error?",
        target=target,
        lineage=(snapshot.ref,),
    )
    return ImprovementRequest.create(
        request_id="embedded-improvement",
        operationalization=OperationalizationPolicy().accept_typed(
            OperationalizationRequest.create(
                request_id="distance-intent",
                goal=goal,
                current_snapshot=snapshot,
            ),
            contract,
        ),
        question=question,
        initial_hypotheses=hypotheses(question, 1),
        risk_policy=RiskPolicy(policy_id="demo-risk", confidence_multiplier=1),
        budget=ImprovementBudget(
            max_iterations=2,
            max_experiments=6,
            max_retries=0,
            max_resource_units=2,
            diminishing_return_patience=2,
        ),
    )


def compare(contract: EvaluationContract, candidate: CandidateSnapshot) -> CandidateTrialBatch:
    """Measure both exact snapshots; acceptance is derived by libRSI, never supplied."""
    metric = contract.objectives[0].metric
    evaluator = ExperimentEvaluator()
    experiment = evaluator.design(
        experiment_id=f"compare-{candidate.request.candidate_id}",
        subject=Hypothesis(
            statement=f"{candidate.request.candidate_id} meets the improvement criterion",
            target=candidate.snapshot.target,
            lineage=(candidate.ref, contract.ref),
        ),
        kind="controlled-numeric-trial",
        metrics=(metric,),
        decision_rules=(
            DecisionRule(
                metric=metric.ref,
                kind="baseline_delta",
                minimum_effect=2,
                required_valid_trials=2,
            ),
        ),
        baseline_snapshot=contract.baseline.snapshot,
        candidate_snapshot=candidate.snapshot,
        repetitions=2,
        seeds=(1, 2),
        validity_requirements={"require_all_metrics": True},
    )
    results = []
    roles: tuple[Literal["baseline", "candidate"], ...] = ("baseline", "candidate")
    for role in roles:
        snapshot = contract.baseline.snapshot if role == "baseline" else candidate.snapshot
        for index in range(2):
            trial = evaluator.prepare_trial(experiment, index=index, role=role)
            value = error(float(snapshot.state["x"]))
            observation = Observation(
                kind="numeric.error",
                value=value,
                target_snapshot=snapshot,
                source_refs=(trial.ref,),
            )
            measurement = Measurement(
                metric=metric.metric_id,
                metric_ref=metric.ref,
                value=value,
                unit=metric.unit,
                target_snapshot=snapshot,
                observation_refs=(observation.ref,),
            )
            results.append(
                evaluator.record_result(
                    experiment,
                    trial=trial,
                    disposition="valid",
                    observations=(observation,),
                    measurements=(measurement,),
                )
            )
    return CandidateTrialBatch.create(
        contract=contract,
        candidate=candidate,
        experiment=experiment,
        results=results,
    )


class DemoInterruption(RuntimeError):
    """An intentional interruption before cycle 2 performs any work."""


class NumericHost:
    """Deterministic host capabilities; replace these with your domain's actual work.

    Each completed cycle tests two directional hypotheses and compares one candidate.
    Resource units count completed cycles here; they are not currency or CPU seconds.
    """

    def __init__(self, *, interrupt: bool = False) -> None:
        self.interrupt = interrupt
        self.completed_cycles: list[int] = []

    def resource_claim(self, action: Action) -> float:
        return float(action.budget_reservation["units"])

    def reason(self, action: Action) -> ActionResult:
        request = reasoning_request_from_action(action)
        return make_reasoning_action_result(
            action=action,
            result=ReasoningResult.propose(
                request=request,
                content=make_investigation_observation_content(request, measurements=("error",)),
            ),
        )

    def experiment(self, action: Action) -> ActionResult:
        request = investigation_experiment_request_from_action(action)
        baseline = request.investigation.target_snapshot
        assert baseline is not None
        x = float(baseline.state["x"])
        changed = x + float(request.branch.hypothesis.causal_model["delta"])
        before, after = error(x), error(changed)
        relationship = "support" if after < before else "counterexample"
        evidence = tuple(
            Evidence(
                evidence_type=relationship,
                data={"replicate": index, "baseline_error": before, "changed_error": after},
                subject_refs=(request.branch.hypothesis.ref,),
                source_refs=(request.experiment.ref,),
                target_snapshot=baseline,
                weight=1,
            )
            for index in (1, 2)
        )
        return make_investigation_experiment_result(
            action=action,
            batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
        )

    def improve_cycle(self, action: Action) -> ActionResult:
        cycle = cycle_request_from_action(action)
        iteration = cycle.directive.iteration
        if self.interrupt and iteration == 2:
            raise DemoInterruption("cycle 1 saved; interrupting before cycle 2")
        request = cycle.improvement
        investigation = investigate(
            question=request.question,
            target_snapshot=request.baseline,
            investigation_id=f"numeric-cycle-{iteration}",
            initial_hypotheses=(
                request.initial_hypotheses if iteration == 1 else hypotheses(request.question, 3)
            ),
            max_hypotheses=2,
            max_experiments=2,
            max_redesigns_per_hypothesis=0,
            reasoner=self,
            experimenter=self,
        )
        supported = next(
            branch for branch in investigation.branches if branch.status == "supported"
        )
        x = float(request.baseline.state["x"]) + float(supported.hypothesis.causal_model["delta"])
        intervention = InterventionSpec.create(
            intervention_id=f"numeric-{iteration}",
            baseline=request.baseline,
            kind="parameter-change",
            specification={"x": x},
            rationale=("Measure the supported direction against the original baseline",),
            supporting_refs=(supported.hypothesis.ref,),
            evidence=supported.evidence,
            expected_effects={"error": "decrease"},
            risks=("Change may be too small",),
            constraints=(),
            validation_plan={"repetitions": 2},
            rollback_expectations={"restore": request.baseline.revision},
        )
        candidate = CandidateSnapshot.prepared(
            request=InterventionImplementationRequest.for_intervention(
                intervention,
                candidate_id=f"x={x:g}",
            ),
            snapshot=TargetSnapshot(
                target=request.baseline.target, revision=f"x={x:g}", state={"x": x}
            ),
        )
        batch = compare(request.contract, candidate)
        result = make_cycle_result(
            action=action,
            proposal=ImprovementCycleProposal.create(
                request=cycle,
                investigation=investigation,
                batches=(batch,),
            ),
            resource_units=1,
        )
        self.completed_cycles.append(iteration)
        return result


def run_example(data_dir: Path) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    database = data_dir / "runtime.sqlite"
    if database.exists():
        raise FileExistsError("Use a fresh --data-dir; this demo preserves existing run history")
    request = improvement_request()
    first_host = NumericHost(interrupt=True)
    with (
        SQLiteRuntimeStore(database) as store,
        LibRSI(
            runtime_store=store,
            improvement_provider=first_host,
        ) as library,
    ):
        handle = library.start(request)
        assert handle.next() is not None  # The public stepping frontier is also available.
        with suppress(DemoInterruption):
            handle.run()  # Each accepted step is persisted before the next host effect.
        saved = store.resume(handle.state.run.run_id)
        assert saved is not None and len(saved.results) == 1
        first_result_root = saved.results[0].root

    # Recreate the same request and host inputs. The facade has no resume convenience;
    # the public workflow/store API exposes the canonical persisted frontier directly.
    request = improvement_request()
    resumed_host = NumericHost()
    with SQLiteRuntimeStore(database) as store:
        state = store.resume(request.canonical_run().run_id)
        assert state is not None
        workflow = ImprovementWorkflow()
        resumed = workflow.resume(request, state, current_snapshot=request.baseline)
        persist_transitions(store, resumed.transitions)

        def save(update: ImprovementUpdate) -> None:
            persist_transitions(store, update.transitions)

        completed = workflow.run_managed(
            resumed.progress,
            provider=resumed_host,
            current_snapshot=request.baseline,
            on_update=save,
        )
        result = completed.progress.result
        assert result is not None and completed.progress.terminal
        assert result.disposition == "improved" and result.handoff is not None
        assert result.iterations[0].selection.disposition == "none-accepted"
        assert completed.progress.state.results[0].root == first_result_root
        assert store.resume(state.run.run_id) == completed.progress.state
    cycles = first_host.completed_cycles + resumed_host.completed_cycles
    assert cycles == [1, 2]  # Completed cycle 1 was not executed again.
    return {
        "status": completed.progress.state.status,
        "disposition": result.disposition,
        "stop_reason": result.stop_reason,
        "completed_cycles": cycles,
        "candidate_experiments": sum(len(item.proposal.batches) for item in result.iterations),
        "resumed_after_cycle": 1,
        "baseline_error": error(0),
        "candidate_errors": [
            error(float(batch.candidate.snapshot.state["x"]))
            for iteration in result.iterations
            for batch in iteration.proposal.batches
        ],
        "application_performed": False,
        "database": str(database.resolve()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("embedded-improvement-demo"))
    print(json.dumps(run_example(parser.parse_args().data_dir), indent=2))
