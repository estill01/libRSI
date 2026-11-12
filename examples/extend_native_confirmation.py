"""Prospectively expand a frozen native study's unseen workload panel.

Registration must precede the meta freeze and every final optimization. This
adds no model calls and never changes which system a native workflow retained.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from benchmark_document_search import write_json
from benchmark_native_sequence import fresh_problem
from sequence_program import execute
from setup_sequence import build_oracle, workload

from librsi.identity import digest

COUNT = 512
SEED = 2026111210


def register(source):
    if (source / "frozen-improver.json").exists() or (
        source / "frozen-final-systems.json"
    ).exists():
        raise ValueError("confirmation expansion must be registered before meta and final freeze")
    path = source / "confirmation-amendment.json"
    if path.exists():
        raise ValueError("confirmation amendment already exists")
    protocol = json.loads((source / "protocol.json").read_text())
    plan = {
        "registered_at": datetime.now(UTC).isoformat(),
        "original_test_workloads": 128,
        "test_workloads": COUNT,
        "seed": protocol["seed_bases"]["test"],
        "model_samples_per_arm": 32,
        "bootstrap_resamples": 10000,
        "bootstrap_seed": SEED,
        "primary_contrast": "after_meta minus ordinary, crossed-bootstrap 95% interval",
        "reason": "Increase workload precision without additional model calls or native optimization runs.",
        "native_runs_completed_at_registration": len(list((source / "runs").glob("*.json"))),
        "meta_policy_frozen_at_registration": False,
        "final_systems_frozen_at_registration": False,
        "rule": "Retain the original 128-workload result. Evaluate all frozen final systems on a 512-workload panel that contains those 128 plus 384 additional unseen workloads. No selection or stopping based on test outcomes.",
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    write_json(path, plan)
    print(json.dumps(plan), flush=True)


def contrast(grids, left, right):
    a, b = np.asarray(grids[left]), np.asarray(grids[right])
    assert a.shape == b.shape == (32, COUNT)
    rng = np.random.default_rng(SEED)
    family_indices = [np.arange(i, COUNT, 4) for i in range(4)]
    draws = []
    for _ in range(10000):
        tasks = np.concatenate([rng.choice(ids, len(ids), replace=True) for ids in family_indices])
        ai, bi = rng.integers(0, 32, 32), rng.integers(0, 32, 32)
        draws.append(float(b[bi][:, tasks].mean() - a[ai][:, tasks].mean()))
    return {
        "mean_effect": float(b.mean() - a.mean()),
        "bootstrap_95_percentile": np.quantile(draws, [0.025, 0.975]).tolist(),
        "method": "10000 crossed bootstrap draws: independent model draws by arm; shared workload draws stratified by four families",
        "model_samples_per_arm": 32,
        "independent_workloads": COUNT,
    }


def run(source, output):
    plan = json.loads((source / "confirmation-amendment.json").read_text())
    assert plan["analysis_source_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert plan["test_workloads"] == COUNT and plan["bootstrap_seed"] == SEED
    # The marker was written by register() before either freeze file existed.
    assert (
        datetime.fromisoformat(plan["registered_at"]).timestamp()
        < (source / "frozen-improver.json").stat().st_mtime
    )
    output.mkdir(parents=True, exist_ok=False)
    report = json.loads(gzip.decompress((source / "report.json.gz").read_bytes()))
    original = json.loads((source / "workloads.json").read_text())["test"]
    data = [workload(plan["seed"] + i, i % 4) for i in range(COUNT)]
    assert data[:128] == original
    oracle = build_oracle(output / "oracle")
    problems = [fresh_problem(row, oracle) for row in data]
    cache = {}

    def score(configuration):
        key = digest(configuration)
        if key not in cache:
            cache[key] = [execute(configuration, p)["cost_reduction"] for p in problems]
        return cache[key]

    grids = {
        arm: [
            score(row["configuration"])
            for row in report["runs"]
            if row["label"].startswith(arm + "-")
        ]
        for arm in report["scores"]
    }
    for arm, grid in grids.items():
        assert np.array_equal(np.asarray(grid)[:, :128], np.asarray(report["scores"][arm]))
    result = {
        **report,
        "confirmation": plan,
        "original_128_results": {
            key: report[key] for key in ("means", "scores", "primary_contrast")
        },
        "scores": grids,
        "means": {arm: float(np.mean(grid)) for arm, grid in grids.items()},
        "primary_contrast": contrast(grids, "ordinary", "after_meta"),
        "test_baseline_costs": [p.starting_cost for p in problems],
        "test_optimal_costs": [p.optimal_cost for p in problems],
    }
    if "forced_revision_diagnostic" in grids:
        result["exploratory_forced_contrast"] = contrast(
            grids, "ordinary", "forced_revision_diagnostic"
        )
    (output / "confirmed-report.json.gz").write_bytes(
        gzip.compress(json.dumps(result, sort_keys=True).encode(), mtime=0)
    )
    write_json(output / "confirmation-amendment.json", plan)
    write_json(output / "confirmation-workloads.json", data)
    write_json(
        output / "confirmation-summary.json",
        {key: result[key] for key in ("means", "adoptions", "primary_contrast", "effort", "meta")},
    )
    write_json(
        output / "confirmation-validation.json",
        {
            "registered_before_meta_and_final_freeze": True,
            "original_128_scores_replayed_exactly": True,
            "new_workloads": 384,
            "extra_model_calls": 0,
            "frozen_systems": len(report["runs"]),
            "native_outcomes_unchanged": result["runs"] == report["runs"],
            "analysis_source_sha256": plan["analysis_source_sha256"],
        },
    )
    print(
        json.dumps({key: result[key] for key in ("means", "adoptions", "primary_contrast")}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.register:
        register(args.source)
    elif args.output is not None:
        run(args.source, args.output)
    else:
        parser.error("--output or --register is required")
