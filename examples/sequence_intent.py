"""Translate a broad scheduling goal into an LLM-proposed native contract."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark_document_search import write_json
from sequence_program import BASE_PROGRAM, BUDGET, PROGRAM_CONTRACT

from librsi import Goal, Metric, TargetRef, TargetSnapshot
from librsi.identity import digest
from librsi.intent import (
    Baseline,
    EvaluationContract,
    Objective,
    OperationalizationPolicy,
    OperationalizationProposal,
    OperationalizationRequest,
    StoppingRule,
)

BROAD_GOAL = "Reduce downtime from changeovers in our repeating production schedules, while keeping planning inexpensive and covering every job exactly once."


def validate_plan(plan):
    expected = {
        "objective",
        "metric",
        "minimum_effect",
        "null_hypothesis",
        "baseline",
        "hypotheses",
        "confirmation",
    }
    if not isinstance(plan, dict) or set(plan) != expected:
        raise ValueError("goal interpretation fields do not match the supported interface")
    if (
        plan["metric"] not in ("quality", "cost_reduction")
        or plan["baseline"] != "current_nearest_neighbor"
    ):
        raise ValueError("unsupported metric or stale baseline")
    effect = plan["minimum_effect"]
    if type(effect) not in (int, float) or not 0.01 <= effect <= 0.05:
        raise ValueError("minimum worthwhile effect must be 0.01..0.05")
    if plan["null_hypothesis"] != "mean_gain <= minimum_effect":
        raise ValueError("the comparison must include no worthwhile improvement")
    for key in ("objective", "confirmation"):
        if not isinstance(plan[key], str) or not plan[key].strip():
            raise ValueError("missing interpretation")
    hypotheses = plan["hypotheses"]
    if not isinstance(hypotheses, list) or len(hypotheses) != 2:
        raise ValueError("two competing hypotheses required")
    for hypothesis in hypotheses:
        if (
            not isinstance(hypothesis, dict)
            or set(hypothesis) != {"claim", "mechanism", "experiment"}
            or any(not isinstance(x, str) or not x.strip() for x in hypothesis.values())
        ):
            raise ValueError(
                "hypotheses need a claim, mechanism and executable experiment description"
            )
    if hypotheses[0] == hypotheses[1]:
        raise ValueError("hypotheses must compete")


def operationalize(sampler, output: Path, baseline_quality: float):
    target = TargetRef(target_id="production-sequence-program", kind="bounded-search-program")
    snapshot = TargetSnapshot(target=target, revision=digest(BASE_PROGRAM), state=BASE_PROGRAM)
    goal = Goal(statement=BROAD_GOAL, target=target)
    facts = {
        "current_engine": "Best nearest-neighbor cycle over every starting job; no additional local search.",
        "workloads": "Synthetic 14-job directed setup matrices; unrelated pilot workloads informed task choice.",
        "available_measurements": "quality = exact_optimal_cost / returned_cost; cost_reduction = 1 - returned_cost / current_engine_cost. Both are dimensionless and larger is better.",
        "host_constraints": f"Every job once, start at job 0 and return to it; fixed {BUDGET} candidate-cost evaluations, audited JSON search primitives only; no model tools or external effects.",
        "sampling": "32 independent program-proposal draws per policy; 128 independent final workloads across four families; separate generation, scoring, shadow, verification and final-generation workloads.",
        "analysis": "Freeze policies before final draws. Compare mean paired gains with a two-way bootstrap over independent model draws and shared workloads; report native decision separately. Include a call-budget-matched original-proposer control.",
    }
    request = OperationalizationRequest.create(
        request_id="broad-production-goal", goal=goal, current_snapshot=snapshot, known_facts=facts
    )
    prompt = (
        "Turn the caller's broad goal into a measurable research plan using the actual host capabilities. "
        "Choose the better available primary metric and a minimum worthwhile absolute improvement "
        "between 0.01 and 0.05. Propose TWO competing causal hypotheses and experiments that can "
        "be executed by assembling search programs. You are proposing the interpretation, not reporting results. "
        "Do not choose a winner or claim improvement. The host validates your proposal and executes it. "
        'Return ONE candidate, configuration {"plan":"JSON TEXT"}. JSON text must contain exactly: '
        "objective (text), metric (quality or cost_reduction), minimum_effect (number), "
        "null_hypothesis (exactly 'mean_gain <= minimum_effect'), baseline (exactly 'current_nearest_neighbor'), "
        "hypotheses (two objects each with claim, mechanism, experiment strings), confirmation (text).\n"
        "GOAL:\n"
        + BROAD_GOAL
        + "\nKNOWN FACTS:\n"
        + json.dumps(facts, sort_keys=True)
        + "\nEXECUTABLE SEARCH LANGUAGE:\n"
        + PROGRAM_CONTRACT
    )
    choice = sampler.call(prompt, field="plan", count=1, role="broad-goal-operationalization")[0]
    plan = json.loads(choice["configuration"]["plan"])
    validate_plan(plan)
    metric = Metric(metric_id=plan["metric"], direction="increase", unit="dimensionless")
    contract = EvaluationContract.create(
        contract_id="astra-proposed-production-objective",
        goal=goal,
        baseline=Baseline.create(
            snapshot=snapshot,
            measurements={plan["metric"]: baseline_quality if plan["metric"] == "quality" else 0.0},
        ),
        objectives=[
            Objective.create(
                objective_id="planning-utility",
                metric=metric,
                semantics="maximize",
                goal=goal,
                minimum_effect=plan["minimum_effect"],
            )
        ],
        stopping_rules=[
            StoppingRule(
                rule_id="fixed-experiment",
                kind="budget",
                condition="Stop after the fixed experiment and confirmation samples; never extend based on final results.",
            )
        ],
        metadata={
            "model_plan": plan,
            "host_enforced_constraints": facts["host_constraints"],
            "scope": "The host implements measurements, constrained execution and the registered statistical analysis.",
        },
    )
    proposal = OperationalizationProposal.propose_contract(request=request, contract=contract)
    accepted = OperationalizationPolicy().accept_proposal(request, proposal)
    write_json(
        output / "intent.json",
        {
            "broad_goal": BROAD_GOAL,
            "model_plan": plan,
            "request": request.to_dict(),
            "proposal": proposal.to_dict(),
            "accepted": accepted.to_dict(),
        },
    )
    return plan, accepted
