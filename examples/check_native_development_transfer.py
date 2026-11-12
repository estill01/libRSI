"""Exploratory transfer of every frozen development policy; zero new model calls."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from benchmark_native_sequence import BASE_INSTRUCTIONS, fresh_problem
from sequence_program import execute
from setup_sequence import build_oracle

from librsi.identity import digest


def register(source):
    if (source / "frozen-final-systems.json").exists():
        raise ValueError("register this diagnostic before final systems and test evaluation")
    path = source / "development-transfer-plan.json"
    if path.exists():
        raise ValueError("diagnostic plan already exists")
    assert (source / "frozen-improver.json").exists()
    plan = {
        "registered_at": datetime.now(UTC).isoformat(),
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Exploratory, recorded after meta development and before final test evaluation. Does not replace the registered primary comparison.",
        "reason": "Both revisions lost on training, while revision 2 had mixed positive shadow and verification effects. Score ALL three existing development pools on the unseen test panel, including the revision that lost the training-only diagnostic selection.",
        "policies": ["original", "revision_1", "revision_2"],
        "native_runs_per_policy": 24,
        "test_workloads": 512,
        "extra_model_calls": 0,
        "extra_native_optimizations": 0,
        "bootstrap_resamples": 10000,
        "bootstrap_seeds": [2026111215, 2026111216],
        "interval": "97.5% crossed-bootstrap percentile intervals per contrast (Bonferroni for two exploratory comparisons)",
        "limitation": "Development programs used earlier native training cases and sequential model-generation batches. The primary final arms use fresh native cases and interleaved model requests.",
        "final_systems_frozen_at_registration": False,
    }
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps(plan), flush=True)


def contrast(a, b, seed):
    a, b = np.asarray(a), np.asarray(b)
    assert a.shape == b.shape == (24, 512)
    rng = np.random.default_rng(seed)
    families = [np.arange(i, 512, 4) for i in range(4)]
    draws = []
    for _ in range(10000):
        tasks = np.concatenate([rng.choice(ids, len(ids), replace=True) for ids in families])
        ai, bi = rng.integers(0, 24, 24), rng.integers(0, 24, 24)
        draws.append(float(b[bi][:, tasks].mean() - a[ai][:, tasks].mean()))
    return {
        "mean_effect": float(b.mean() - a.mean()),
        "bootstrap_97_5_percentile": np.quantile(draws, [0.0125, 0.9875]).tolist(),
        "model_draws_per_policy": 24,
        "workloads": 512,
    }


def run(source, data, work):
    plan = json.loads((source / "development-transfer-plan.json").read_text())
    assert plan["analysis_source_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    registered = datetime.fromisoformat(plan["registered_at"]).timestamp()
    assert registered < (source / "frozen-final-systems.json").stat().st_mtime
    work.mkdir(parents=True, exist_ok=False)
    report = json.loads(gzip.decompress((data / "confirmed-report.json.gz").read_bytes()))
    workloads = json.loads((data / "confirmation-workloads.json").read_text())
    oracle = build_oracle(work / "oracle")
    problems = [fresh_problem(row, oracle) for row in workloads]
    assert [p.starting_cost for p in problems] == report["test_baseline_costs"]
    assert [p.optimal_cost for p in problems] == report["test_optimal_costs"]
    configurations = [BASE_INSTRUCTIONS] + [c["configuration"] for c in report["meta"]["choices"]]
    cache, scores, labels = {}, {}, {}
    for name, config in zip(plan["policies"], configurations, strict=True):
        rows = report["development"][digest(config)]
        assert len(rows) == 24 and all(row["phase"] == "development" for row in rows)
        grid = []
        for row in rows:
            key = digest(row["configuration"])
            if key not in cache:
                cache[key] = [execute(row["configuration"], p)["cost_reduction"] for p in problems]
            grid.append(cache[key])
        scores[name], labels[name] = grid, [row["label"] for row in rows]
    comparisons = {
        name: contrast(scores["original"], scores[name], seed)
        for name, seed in zip(plan["policies"][1:], plan["bootstrap_seeds"], strict=True)
    }
    result = {
        "model": "gpt-6-astra",
        "reasoning_effort": "high",
        "model_roles": "scheduler proposals and meta-instruction proposals",
        "plan": plan,
        "native_run_labels": labels,
        "scores": scores,
        "means": {name: float(np.mean(grid)) for name, grid in scores.items()},
        "comparisons": comparisons,
        "extra_model_calls": 0,
        "extra_native_optimizations": 0,
        "registered_before_final_freeze": True,
        "final_systems_frozen_at": datetime.fromtimestamp(
            (source / "frozen-final-systems.json").stat().st_mtime, UTC
        ).isoformat(),
    }
    (data / "development-transfer.json.gz").write_bytes(
        gzip.compress(json.dumps(result, sort_keys=True).encode(), mtime=0)
    )
    (data / "development-transfer-plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n"
    )
    summary = {key: value for key, value in result.items() if key != "scores"}
    (data / "development-transfer-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({key: result[key] for key in ("means", "comparisons")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--data", type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    if args.register:
        register(args.source)
    elif args.data is not None and args.work is not None:
        run(args.source, args.data, args.work)
    else:
        parser.error("provide --register, or --data and --work")
