"""Measured positive, negative, shadow and verification controls for AdaptiveLoop."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from benchmark_document_search import MeasuredReviewer
from join_order import JoinProblem, workload

from librsi import (
    AdaptiveLoop,
    LearningCase,
    LearningPolicy,
    LocalLearningStore,
    Metric,
    ReasoningResult,
    TaskMeasurement,
)


class ControlAdapter:
    adapter_id = "join-cost-native-adoption-control-v1"

    def validate_configuration(self, configuration):
        if set(configuration) != {"policy"} or configuration["policy"] not in {
            "original",
            "optimal",
            "training_only",
            "before_verification",
            "original_copy",
        }:
            raise ValueError("unknown control policy")

    def evaluate(self, configuration, case):
        p = JoinProblem(case.payload["query"])
        mode, phase = configuration["policy"], case.payload["phase"]
        use_optimum = (
            mode == "optimal"
            or (mode == "training_only" and phase == "train")
            or (mode == "before_verification" and phase != "verification")
        )
        cost = p.optimal_cost if use_optimum else p.starting_cost
        quality = p.optimal_cost / cost
        return TaskMeasurement(
            {"cost": cost, "quality": quality}, quality - p.optimal_cost / p.starting_cost
        )


class ControlProposer:
    def __init__(self, policy):
        self.policy = policy

    def respond(self, request):
        return ReasoningResult.propose(
            request=request,
            content={
                "hypotheses": [
                    {
                        "statement": "Test the measured join-cost control",
                        "causal_model": {"configuration": {"policy": policy}},
                        "predictions": [{"join_quality": "increase"}],
                        "confidence": 0.5,
                    }
                    for policy in (self.policy, "original_copy")
                ]
            },
        )


def run(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, before, candidate, expected_adoption in [
        ("positive", "original", "optimal", True),
        ("negative", "optimal", "original", False),
        ("shadow_regression", "original", "training_only", False),
        ("verification_regression", "original", "before_verification", False),
    ]:
        phases = {
            phase: [
                LearningCase(
                    f"{phase}-{i}", {"phase": phase, "query": workload(777000 + offset + i, i)}
                )
                for i in range(4)
            ]
            for phase, offset in [("train", 0), ("shadow", 100), ("verification", 200)]
        }
        with LocalLearningStore(
            output / name, profile_id=name, initial_configuration={"policy": before}
        ) as store:
            loop = AdaptiveLoop(
                store,
                adapter=ControlAdapter(),
                proposer=ControlProposer(candidate),
                proposer_id="deterministic-control",
                reviewer=MeasuredReviewer(),
                reviewer_id="search-measured-review-v1",
                policy=LearningPolicy(
                    objective="Increase paired join-plan quality",
                    metric=Metric(metric_id="join_quality", direction="increase"),
                    minimum_effect=0.01,
                    max_feedback=4,
                    max_cases=4,
                    max_candidates=2,
                    history_limit=0,
                ),
            )
            for case in phases["train"]:
                loop.run_task(case)
            result = loop.learn(
                "control",
                shadow_cases=phases["shadow"],
                verification_cases=phases["verification"],
                activate=True,
            )
            assert result is not None
            assert result.adopted == expected_adoption, (name, result.disposition)
            expected = {"policy": candidate if expected_adoption else before}
            assert dict(store.active.state) == expected
            after = loop.run_task(
                LearningCase("after", {"phase": "after", "query": workload(777400, 0)})
            )
            assert after.target_snapshot is not None
            assert after.target_snapshot.root == store.active.root
            active_root = store.active.root
            (output / f"{name}-native.json.gz").write_bytes(
                gzip.compress(json.dumps(result.native.to_dict(), sort_keys=True).encode(), mtime=0)
            )
            row = {
                "name": name,
                "adopted": result.adopted,
                "disposition": result.disposition,
                "active": expected,
                "active_root": active_root,
                "native_root": result.native.root,
                "after_value": after.value["value"],
            }
        with LocalLearningStore(output / name, profile_id=name) as store:
            assert store.active.root == active_root
        results.append(row)
        print(json.dumps(row), flush=True)
    (output / "report.json").write_text(
        json.dumps({"model": "none; measured deterministic controls", "results": results}, indent=2)
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
