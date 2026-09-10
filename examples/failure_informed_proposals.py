"""Improve a proposal generator using its actual failed experiments.

Run with an installed libRSI wheel, without providers, credentials or network:
    python -I examples/failure_informed_proposals.py --data-dir ./proposal-demo

The synthetic program language is y = slope*x + intercept. The adaptive target
is the generator of repair proposals, not the program being repaired. This is
a measured framework demonstration, not a claim about LLM or production quality.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from librsi import (
    Action,
    ActionResult,
    AdaptiveLoop,
    CandidateReview,
    LearningCase,
    LearningPolicy,
    LocalLearningStore,
    Metric,
    ReasoningRequest,
    ReasoningResult,
    RSIResult,
    TaskMeasurement,
    make_review_result,
    review_command_from_action,
)
from librsi.identity import canonical_json

BASE_GENERATOR = {"family": "offset", "estimator": "first"}
BUDGET = 2
TOLERANCE = 1e-9


def number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("program numbers must be finite")
    return float(value)


def execute(program: Mapping[str, Any], x: float) -> float:
    if not isinstance(program, Mapping) or set(program) != {"slope", "intercept"}:
        raise ValueError("program requires slope and intercept")
    return number(number(program["slope"]) * number(x) + number(program["intercept"]))


def generate(configuration: Mapping[str, Any], inputs: Mapping[str, Any]) -> list[dict[str, float]]:
    """The actual inner generator receives no scoring probes or expected answers."""
    if set(inputs) != {"baseline_program", "observations", "budget"} or inputs["budget"] != BUDGET:
        raise ValueError("generator input boundary changed")
    observations = inputs["observations"]
    if configuration["family"] == "offset":
        residuals = [
            row["y"] - execute(inputs["baseline_program"], row["x"]) for row in observations
        ]
        choice = configuration["estimator"]
        offset = (
            residuals[0]
            if choice == "first"
            else residuals[-1]
            if choice == "last"
            else sum(residuals) / len(residuals)
        )
        slope = number(inputs["baseline_program"]["slope"])
        intercept = number(inputs["baseline_program"]["intercept"]) + offset
    else:
        if configuration["estimator"] == "pair":
            first, last = observations[0], observations[-1]
            slope = (last["y"] - first["y"]) / (last["x"] - first["x"])
            intercept = first["y"] - slope * first["x"]
        else:
            xs, ys = [row["x"] for row in observations], [row["y"] for row in observations]
            mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
            slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sum(
                (x - mean_x) ** 2 for x in xs
            )
            intercept = mean_y - slope * mean_x
    return [{"slope": slope, "intercept": intercept + delta} for delta in (0, 1)]


def score(proposals: Sequence[Any], case: LearningCase) -> tuple[float, dict[str, Any]]:
    """Execute complete proposals; distinct useful outputs earn one credit each."""
    payload = case.payload
    if payload["budget"] != BUDGET or payload["tolerance"] != TOLERANCE:
        raise ValueError("frozen scoring contract changed")
    probes = payload["probes"]
    baseline_outputs = [execute(payload["baseline_program"], row["x"]) for row in probes]
    baseline_correct = sum(
        abs(value - row["y"]) <= TOLERANCE
        for value, row in zip(baseline_outputs, probes, strict=True)
    )
    evaluated: list[dict[str, Any]] = []
    seen: list[list[float]] = []
    useful = 0
    for program in proposals[:BUDGET]:
        try:
            outputs = [execute(program, row["x"]) for row in probes]
            correct = sum(
                abs(value - row["y"]) <= TOLERANCE
                for value, row in zip(outputs, probes, strict=True)
            )
            duplicate = any(
                all(abs(a - b) <= TOLERANCE for a, b in zip(outputs, prior, strict=True))
                for prior in seen
            )
            credit = len(proposals) == BUDGET and not duplicate and correct > baseline_correct
            useful += credit
            seen.append(outputs)
            evaluated.append(
                {
                    "program": program,
                    "outputs": outputs,
                    "correct": correct,
                    "status": "duplicate" if duplicate else "valid",
                    "useful": credit,
                }
            )
        except (ValueError, TypeError, KeyError, OverflowError):
            evaluated.append(
                {"invalid_program": repr(program), "status": "invalid", "useful": False}
            )
    return useful / BUDGET, {
        "baseline_outputs": baseline_outputs,
        "baseline_correct": baseline_correct,
        "evaluated": evaluated,
        "useful_count": useful,
        "budget": BUDGET,
        "budget_valid": len(proposals) == BUDGET,
        "tolerance": TOLERANCE,
    }


class ProposalAdapter:
    adapter_id = "affine-repair-proposal-quality-v1"

    def validate_configuration(self, configuration: Mapping[str, Any]) -> None:
        choices = {"offset": {"first", "mean", "last"}, "affine": {"pair", "regression"}}
        if set(configuration) != {"family", "estimator"} or configuration[
            "estimator"
        ] not in choices.get(configuration["family"], set()):
            raise ValueError("unsupported proposal-generator configuration")

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        self.validate_configuration(configuration)
        inputs = {key: case.payload[key] for key in ("baseline_program", "observations", "budget")}
        proposals = generate(configuration, inputs)
        value, output = score(proposals, case)
        return TaskMeasurement({"generator_input": inputs, **output}, value)


def diagnose(history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Require measured failure and a violated assumption, not just a prior pass."""
    cases, estimators = set(), set()
    for attempt in history:
        for trial in attempt["trials"]:
            if (
                trial["status"] != "measured"
                or trial["value"] != 0
                or trial["configuration"]["family"] != "offset"
            ):
                continue
            output = trial["output"]
            if (
                not output["budget_valid"]
                or len(output["evaluated"]) != BUDGET
                or any(row["status"] != "valid" or row["useful"] for row in output["evaluated"])
            ):
                continue
            inputs = output["generator_input"]
            residuals = [
                row["y"] - execute(inputs["baseline_program"], row["x"])
                for row in inputs["observations"]
            ]
            if max(residuals) - min(residuals) > TOLERANCE:
                cases.add(trial["case_id"])
                if trial["configuration"] != attempt["baseline_configuration"]:
                    estimators.add(trial["configuration"]["estimator"])
    return {
        "varying_residual_cases": sorted(cases),
        "failed_alternatives": sorted(estimators),
        "test_affine": len(cases) >= 2 and len(estimators) >= 2,
    }


class FailureInformedProposer:
    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        diagnosis = diagnose(request.context.get("history", ()))
        if request.kind == "reflection":
            return ReasoningResult.propose(
                request=request,
                content={
                    "summary": "Test whether the constant-offset assumption caused the failed repairs.",
                    "observations": [json.dumps(diagnosis, sort_keys=True)],
                    "open_questions": [
                        "Does fitting slope as well as intercept yield useful proposals on fresh problems?"
                    ],
                },
            )
        reflection = request.context.get("reflection")
        supported = (
            diagnosis["test_affine"]
            and reflection is not None
            and json.loads(reflection["observations"][0]) == diagnosis
        )
        alternatives = ("pair", "regression") if supported else ("mean", "last")
        return ReasoningResult.propose(
            request=request,
            content={
                "hypotheses": [
                    {
                        "statement": f"Generate repair proposals with {'affine' if supported else 'offset'} {estimator} fitting",
                        "causal_model": {
                            "configuration": {
                                "family": "affine" if supported else "offset",
                                "estimator": estimator,
                            }
                        },
                        "predictions": [{"useful_proposal_fraction": "increase"}],
                        "confidence": 0.6,
                    }
                    for estimator in alternatives
                ]
            },
        )


class IndependentReviewer:
    def review(self, action: Action) -> ActionResult:
        command = review_command_from_action(action)
        passed = command.evaluation.disposition == "passed"
        return make_review_result(
            action=action,
            review=CandidateReview(
                review_id=f"{action.action_id}:review",
                reviewer_id="repair-reviewer-v1",
                candidate=command.candidate,
                experiment=command.experiment,
                evaluation=command.evaluation,
                disposition="accepted" if passed else "rejected",
                findings=(
                    "Fresh measured useful-proposal criterion passes"
                    if passed
                    else "Criterion failed",
                ),
                lineage=(command.candidate.ref, command.experiment.ref, command.evaluation.ref),
            ),
        )


def make_case(name: str, slope: int, intercept: int) -> LearningCase:
    return LearningCase(
        name,
        {
            "baseline_program": {"slope": 1, "intercept": 0},
            "observations": [{"x": x, "y": slope * x + intercept} for x in (1, 3, 5)],
            "probes": [{"x": x, "y": slope * x + intercept} for x in (11, 13)],
            "budget": BUDGET,
            "tolerance": TOLERANCE,
        },
    )


def make_loop(store: LocalLearningStore) -> AdaptiveLoop:
    return AdaptiveLoop(
        store,
        adapter=ProposalAdapter(),
        proposer=FailureInformedProposer(),
        proposer_id="repair-meta-proposer-v1",
        reviewer=IndependentReviewer(),
        reviewer_id="repair-reviewer-v1",
        policy=LearningPolicy(
            objective="Increase fraction of distinct useful repair proposals",
            metric=Metric(metric_id="useful-proposals", direction="increase", unit="fraction"),
            minimum_effect=0.25,
            max_feedback=2,
            max_cases=2,
            history_limit=1,
            reflect_on_failure=True,
        ),
    )


def counterfactual(request: ReasoningRequest) -> ReasoningResult:
    """A valid ordinary proposal context with the historical failure signal removed."""
    context = dict(request.context)
    context.update(history=[], follow_up_to=None)
    context.pop("reflection", None)
    feedback_roots = {row["feedback"] for row in context["feedback"]}
    assert request.target_snapshot is not None
    refs = tuple(
        ref
        for ref in request.input_refs
        if ref == request.target_snapshot.ref or ref.root in feedback_roots
    )
    ablated = replace(
        request,
        request_id="failure-signal-ablation",
        context=context,
        input_refs=refs,
        lineage=refs,
    )
    return FailureInformedProposer().respond(ablated)


def run_demo(directory: Path) -> dict[str, Any]:
    started, cpu = perf_counter(), process_time()
    training = (make_case("training-a", 2, 3), make_case("training-b", 3, -2))
    first_shadow = (make_case("first-shadow-a", 4, 1), make_case("first-shadow-b", -2, 7))
    fresh_shadow = (make_case("fresh-shadow-a", 5, -4), make_case("fresh-shadow-b", -3, 8))
    with LocalLearningStore(
        directory, profile_id="repair-generator", initial_configuration=BASE_GENERATOR
    ) as store:
        engine = make_loop(store)
        ordinary = [engine.run_task(case) for case in training]
        first = engine.learn("offset-estimators", shadow_cases=first_shadow)
        if first is None or first.disposition != "no-supported-revision":
            raise RuntimeError(
                "initial offset alternatives did not produce the required negative result"
            )
    with LocalLearningStore(directory, profile_id="repair-generator") as store:
        engine = make_loop(store)
        learned = engine.learn(
            "diagnose-model",
            follow_up_to="offset-estimators",
            shadow_cases=fresh_shadow,
            activate=True,
        )
        if learned is None or not learned.adopted or not isinstance(learned.native, RSIResult):
            raise RuntimeError("native owners did not verify a better generator")
        attempts = engine.history(limit=2)
        proposal = attempts[-1].proposal
        assert proposal is not None
        ablation = counterfactual(proposal.request)
        ablation_trials = [
            ProposalAdapter().evaluate(item["causal_model"]["configuration"], case)
            for item in ablation.content["hypotheses"]
            for case in fresh_shadow
        ]
        if any(row.value != 0 for row in ablation_trials):
            raise RuntimeError("failure-signal ablation did not preserve the negative control")
        forward = learned.native.governance.forward_shadow
        assert forward is not None
        heldout = {
            role: [
                row.measurements[0].value for row in forward.batch.results if row.trial.role == role
            ]
            for role in ("baseline", "candidate")
        }
        evidence = {
            "first": first.native.to_dict(),
            "learned": learned.native.to_dict(),
            "feedback": [row.to_dict() for row in ordinary],
            "history": [row.feedback.to_dict() for row in attempts],
            "reflection": attempts[-1].reflection.to_dict() if attempts[-1].reflection else None,
            "ablation": ablation.to_dict(),
            "ablation_trials": [
                {"output": row.output, "value": row.value} for row in ablation_trials
            ],
        }
        operation_scopes = [
            {
                "action": row.action.action_id,
                "kind": row.action.kind,
                "usage": row.resource_usage,
                "timing": row.metadata.get("learning_operation"),
            }
            for attempt in attempts
            for row in attempt.operations
        ]
    # Reopen once more and consume the adopted generator on a new ordinary input.
    with LocalLearningStore(directory, profile_id="repair-generator") as store:
        next_task = make_loop(store).run_task(make_case("ordinary-next", 7, -6))
        if (
            next_task.target_snapshot != learned.strategy_after
            or next_task.value["value"] <= ordinary[0].value["value"]
        ):
            raise RuntimeError("new ordinary work did not benefit from the adopted generator")
        evidence["next_task"] = next_task.to_dict()
        report = {
            "initial_disposition": first.disposition,
            "learned_disposition": learned.disposition,
            "first_result_root": first.native.root,
            "learned_result_root": learned.native.root,
            "configuration": store.active.state,
            "active_root": store.active.root,
            "initial_rates": [row.value["value"] for row in ordinary],
            "heldout_rates": heldout,
            "ablation_rates": [row.value for row in ablation_trials],
            "next_rate": next_task.value["value"],
            "next_task_root": next_task.root,
            "next_strategy_root": next_task.target_snapshot.root,
            "operations": operation_scopes,
            "wall_seconds": perf_counter() - started,
            "process_cpu_seconds": process_time() - cpu,
            "cost_scope": "whole invocation including native admission/history, control and ordinary work; excludes final JSON serialization; not additive with nested operations",
            "provider_usage": None,
            "child_cpu_seconds": None,
        }
    directory.joinpath("evidence.json").write_text(canonical_json(evidence) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    print(canonical_json(run_demo(parser.parse_args().data_dir)))
