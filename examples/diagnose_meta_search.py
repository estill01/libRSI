"""Recompute the failed search-meta experiments without making model calls."""

from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from llm_search import FormulaIndex
from scifact_data import load

from librsi.identity import thaw


def run(dataset: Path, output: Path) -> None:
    root = Path(__file__).resolve().parent.parent
    public = root / "docs/benchmarks/recursive-search"
    report = json.loads((public / "report.json").read_text())
    samples = json.loads(gzip.decompress((public / "cascade-samples.json.gz").read_bytes()))
    native = json.loads((public / "native-decisions.json").read_text())
    corpus, data = load(dataset)
    index = FormulaIndex(corpus["documents"], data["queries"])
    cache = {}
    rng = np.random.default_rng(2026111201)
    result = {"model_calls": 0, "source_model": report["model"], "stages": {}}
    splits = {
        "training": data["splits"]["meta_train"][100:],
        "shadow": data["splits"]["meta_shadow"],
        "verification": data["splits"]["meta_verification"],
    }
    for stage in report["stages"]:
        policies = []
        matrices: list[dict[str, Any]] = []
        for policy in stage["training_policies"]:
            rows = [
                samples[f"{stage['name']}-samples/{policy['sample_key']}-{i}-selected.json"]
                for i in range(5)
            ]
            matrices.append({})
            values = {}
            for split, ids in splits.items():
                arrays = []
                for row in rows:
                    formula = row["selected"]["formula"]
                    key = (formula, split)
                    if key not in cache:
                        cache[key] = thaw(
                            index.measure({"formula": formula}, index.resolve(ids)).output
                        )["queries"]
                    arrays.append([item["reciprocal_rank"] for item in cache[key]])
                matrix = np.asarray(arrays)
                matrices[-1][split] = matrix
                values[split] = {
                    "mean": float(matrix.mean()),
                    "model_sample_sd": float(matrix.mean(axis=1).std(ddof=1)),
                    "samples": matrix.mean(axis=1).tolist(),
                }
            policies.append(
                {
                    "instruction": policy["configuration"]["instruction"],
                    "selected_formulas": [r["selected"]["formula"] for r in rows],
                    "unique_selected_formula_strings": len(
                        {r["selected"]["formula"] for r in rows}
                    ),
                    "scores": values,
                }
            )
        comparisons = []
        for i in (1, 2):
            by_split = {}
            for split in splits:
                delta = matrices[i][split] - matrices[0][split]
                model_deltas = delta.mean(axis=1)
                mean, se = (
                    float(model_deltas.mean()),
                    float(model_deltas.std(ddof=1) / math.sqrt(5)),
                )
                query_deltas = delta.mean(axis=0)
                draws = query_deltas[
                    rng.integers(0, len(query_deltas), size=(10000, len(query_deltas)))
                ].mean(axis=1)
                by_split[split] = {
                    "mean_effect": mean,
                    "native_one_se_bounds": [mean - se, mean + se],
                    "mean_effect_passes_0_01": mean >= 0.01,
                    "native_bound_passes_0_01": mean - se >= 0.01,
                    "query_bootstrap_95_percentile": np.quantile(draws, [0.025, 0.975]).tolist(),
                    "query_wins": int((query_deltas > 0).sum()),
                    "query_losses": int((query_deltas < 0).sum()),
                }
            comparisons.append(by_split)
        result["stages"][stage["name"]] = {
            "policies": policies,
            "comparisons": comparisons,
            "native": native[stage["name"]],
        }
        print(stage["name"], json.dumps(comparisons), flush=True)
    result["limits"] = [
        "Post-hoc diagnostic, no new model samples or adopted changes.",
        "Bootstrap resamples queries while conditioning on the five already-generated model draws.",
        "Native intervals only represent model-draw variation; one standard error is not a 95% interval.",
        "Distinct strings can encode equivalent rankings; zero score variance alone does not prove identical algorithms.",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.dataset, args.output)
