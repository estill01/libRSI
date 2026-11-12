"""Isolate the adaptive investigation's treatment of ties; no model calls.

The diagnostic treatment changes only tie classification in this process. It is
not a production policy change and is never used by the registered Astra study.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
from pathlib import Path
from unittest.mock import patch

from benchmark_document_search import MeasuredReviewer
from check_meta_adoption import ControlProposer
from join_order import JoinProblem, workload

from librsi import (
    AdaptiveLoop,
    LearningCase,
    LearningPolicy,
    LocalLearningStore,
    Metric,
    TaskMeasurement,
)
from librsi.comparison.statistics import mean_interval
from librsi.facade import learning_host


class SparseAdapter:
    adapter_id = "sparse-measured-join-improvement-control-v1"

    @staticmethod
    def validate_configuration(config):
        if set(config) != {"policy"} or config["policy"] not in {
            "original",
            "original_copy",
            "original_copy_2",
            "sparse",
            "worse",
        }:
            raise ValueError("unknown control")

    def evaluate(self, config, case):
        p = JoinProblem(case.payload["query"])
        value = p.starting_cost
        if config["policy"] == "sparse" and case.payload["index"] % 4 == 0:
            value = p.optimal_cost
        if config["policy"] == "worse":
            value *= 2
        return TaskMeasurement(
            {"cost": value, "baseline_cost": p.starting_cost}, 1 - value / p.starting_cost
        )


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    results = []
    original_evidence = learning_host.Evidence

    def neutral_ties(**kwargs):
        data = kwargs["data"]
        if kwargs["evidence_type"] == "counterexample" and data["candidate"] == data["baseline"]:
            kwargs["evidence_type"] = "null"
            kwargs["weight"] = 0
        return original_evidence(**kwargs)

    for name, neutral, candidate in [
        ("current_sparse", False, "sparse"),
        ("neutral_ties_sparse", True, "sparse"),
        ("neutral_ties_worse", True, "worse"),
        ("neutral_ties_unchanged", True, "original"),
    ]:
        phases = {
            phase: [
                LearningCase(
                    f"{phase}-{i}", {"index": i, "query": workload(778000 + offset + i, i % 4)}
                )
                for i in range(16)
            ]
            for phase, offset in [("train", 0), ("shadow", 100), ("verification", 200)]
        }
        adapter = SparseAdapter()
        values = [adapter.evaluate({"policy": candidate}, c).value for c in phases["train"]]
        native_bound = mean_interval(values, confidence_multiplier=1.0)
        with patch.object(
            learning_host, "Evidence", neutral_ties if neutral else original_evidence
        ):
            with LocalLearningStore(
                output / name, profile_id=name, initial_configuration={"policy": "original"}
            ) as store:
                # For the unchanged diagnostic the proposal must still be a distinct configuration.
                proposal = "original_copy_2" if candidate == "original" else candidate
                proposer = ControlProposer(proposal)
                loop = AdaptiveLoop(
                    store,
                    adapter=adapter,
                    proposer=proposer,
                    proposer_id="deterministic-sparse-control",
                    reviewer=MeasuredReviewer(),
                    reviewer_id="search-measured-review-v1",
                    policy=LearningPolicy(
                        objective="Reduce mean measured join cost",
                        metric=Metric(metric_id="join_quality", direction="increase"),
                        minimum_effect=0.01,
                        max_feedback=16,
                        max_cases=16,
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
                assert result is not None and store.pending_pass is None
                row = {
                    "name": name,
                    "tie_treatment": "null" if neutral else "counterexample",
                    "adopted": result.adopted,
                    "disposition": result.disposition,
                    "active": dict(store.active.state),
                    "active_root": store.active.root,
                    "native_root": result.native.root,
                    "training_values": values,
                    "mean": statistics.mean(values),
                    "one_se_lower": native_bound.lower,
                    "wins": sum(v > 0 for v in values),
                    "ties": sum(v == 0 for v in values),
                    "losses": sum(v < 0 for v in values),
                }
                (output / f"{name}-native.json.gz").write_bytes(
                    gzip.compress(
                        json.dumps(result.native.to_dict(), sort_keys=True).encode(), mtime=0
                    )
                )
            with LocalLearningStore(output / name, profile_id=name) as store:
                assert store.active.root == row["active_root"]
        results.append(row)
        print(json.dumps(row), flush=True)
    report = {
        "model": "none; measured deterministic diagnostic",
        "results": results,
        "scope": "Only diagnostic process changes exact-zero counterexamples to neutral evidence. No library source or Astra study policy is changed.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
