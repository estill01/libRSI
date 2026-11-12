"""Descriptive diagnostics for the completed native study; no extra model calls."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path

import numpy as np
from benchmark_native_sequence import BASE_INSTRUCTIONS
from sequence_program import parse_program

from librsi.identity import digest


def summarize(report, workloads, receipts):
    baseline = np.asarray(report["test_baseline_costs"])
    optimal = np.asarray(report["test_optimal_costs"])
    ceiling = 1 - optimal / baseline
    families = sorted({row["family"] for row in workloads})
    by_family = {}
    for family in families:
        mask = np.asarray([row["family"] == family for row in workloads])
        by_family[family] = {
            "workloads": int(mask.sum()),
            "exact_search_ceiling": float(ceiling[mask].mean()),
            **{
                arm: float(np.asarray(grid)[:, mask].mean())
                for arm, grid in report["scores"].items()
            },
        }
    diversity = {}
    for arm in report["scores"]:
        rows = [row for row in report["runs"] if row["label"].startswith(arm + "-")]
        programs = [parse_program(row["configuration"]) for row in rows]
        diversity[arm] = {
            "native_dispositions": dict(Counter(row["disposition"] for row in rows)),
            "distinct_program_json": len({json.dumps(p, sort_keys=True) for p in programs}),
            "mean_stage_count": float(np.mean([len(p["stages"]) for p in programs])),
            "run_mean_standard_deviation": float(
                np.asarray(report["scores"][arm]).mean(axis=1).std(ddof=1)
            ),
            "remaining_ceiling_gap": float(ceiling.mean() - report["means"][arm]),
        }
    base = report["development"][digest(BASE_INSTRUCTIONS)]
    development = []
    for i, choice in enumerate(report["meta"]["choices"], 1):
        rows = report["development"][digest(choice["configuration"])]
        stages = {}
        for stage, offset in (("meta_train", 0), ("meta_shadow", 8), ("meta_verify", 16)):
            effects = np.asarray(
                [
                    rows[j]["evaluation"][stage] - base[j]["evaluation"][stage]
                    for j in range(offset, offset + 8)
                ]
            )
            grouped = effects.reshape(2, 4).mean(axis=1)
            stages[stage] = {
                "mean_effect": float(effects.mean()),
                "native_two_group_one_se_lower_bound": float(
                    grouped.mean() - grouped.std(ddof=1) / np.sqrt(2)
                ),
                "run_effects": effects.tolist(),
            }
        development.append(
            {"candidate": i, "instruction": choice["configuration"], "stages": stages}
        )
    effort = {}
    for name, prefixes in (
        ("ordinary", ("ordinary-",)),
        ("meta_development", ("dev-", "meta-")),
        ("after_meta", ("after_meta-",)),
        ("forced_diagnostic", ("forced_revision_diagnostic-",)),
    ):
        rows = [row for row in receipts if row["role"].startswith(prefixes)]
        effort[name] = {
            "model": "gpt-6-astra",
            "reasoning_effort": "high",
            "calls": len(rows) + sum("transport_retry" in row for row in rows),
            "completed_calls": len(rows),
            "unknown_usage_timeout_calls": sum("transport_retry" in row for row in rows),
            "input_tokens": sum(u.get("input_tokens", 0) for row in rows for u in row["usage"]),
            "output_tokens": sum(u.get("output_tokens", 0) for row in rows for u in row["usage"]),
            "cached_input_tokens": sum(
                u.get("cached_input_tokens", 0) for row in rows for u in row["usage"]
            ),
        }
    return {
        "model": "gpt-6-astra",
        "reasoning_effort": "high",
        "model_roles": "scheduler proposals and meta-improver proposals",
        "scope": "Post-hoc descriptive diagnostics, not additional confirmatory tests. The exact-search ceiling is an unconstrained oracle, not a 256-evaluation competitor. Distinct JSON programs are not necessarily distinct algorithms.",
        "exact_search_ceiling": float(ceiling.mean()),
        "by_family": by_family,
        "retained_programs": diversity,
        "meta_development": development,
        "effort_by_phase": effort,
    }


def export_run_csv(report, output):
    """One row per independent optimizer draw, plus the unchanged reference."""
    fields = [
        "case",
        "optimization_model",
        "reasoning_effort",
        "meta_model",
        "meta_revision_adopted",
        "optimization_run",
        "native_disposition",
        "scheduler_adopted",
        "test_workloads",
        "mean_cost_reduction_percent",
    ]
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "case": "base",
                "optimization_model": "none",
                "reasoning_effort": "none",
                "meta_model": "none",
                "native_disposition": "original",
                "test_workloads": len(report["test_baseline_costs"]),
                "mean_cost_reduction_percent": 0,
            }
        )
        for arm, grid in report["scores"].items():
            rows = [row for row in report["runs"] if row["label"].startswith(arm + "-")]
            for row, scores in zip(rows, grid, strict=True):
                writer.writerow(
                    {
                        "case": arm,
                        "optimization_model": "gpt-6-astra",
                        "reasoning_effort": "high",
                        "meta_model": "none" if arm == "ordinary" else "gpt-6-astra (high)",
                        "meta_revision_adopted": ""
                        if arm == "ordinary"
                        else report["meta"]["adopted"],
                        "optimization_run": row["label"],
                        "native_disposition": row["disposition"],
                        "scheduler_adopted": row["adopted"],
                        "test_workloads": len(scores),
                        "mean_cost_reduction_percent": float(np.mean(scores) * 100),
                    }
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(gzip.decompress((args.data / "confirmed-report.json.gz").read_bytes()))
    result = summarize(
        report,
        json.loads((args.data / "confirmation-workloads.json").read_text()),
        json.loads((args.data / "receipts.json").read_text()),
    )
    (args.data / "descriptive-diagnostics.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    export_run_csv(report, args.data / "run-scores.csv")
    print(json.dumps(result, indent=2))
