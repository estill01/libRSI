"""Replay a completed scheduling study without making model calls, then export evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import statistics
from collections import Counter
from pathlib import Path

import numpy as np
from benchmark_document_search import provenance, write_json
from benchmark_setup_sequence import SEEDS, SPLITS, interval
from sequence_program import BASE_PROGRAM, execute, parse_program
from setup_sequence import SequenceProblem, build_oracle, cost, local_search, workload

from librsi.epistemics import LinearEvidenceAggregator
from librsi.identity import digest


def read(path):
    return json.loads(path.read_text())


def packed(path, value):
    path.write_bytes(gzip.compress(json.dumps(value, sort_keys=True).encode(), mtime=0))


def investigation_diagnosis(record):
    """Keep post-hoc gate diagnostics separate from registered confirmation."""
    if record["record_type"] != "investigation_result":
        embedded = {}

        def collect(value):
            if isinstance(value, dict):
                if (
                    value.get("record_type") == "investigation_result"
                    and isinstance(value.get("data"), dict)
                    and "branches" in value["data"]
                ):
                    embedded[value["root"]] = value
                    return
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(record)
        return {
            "native_record_type": record["record_type"],
            "stopped_before_comparison": False,
            "embedded_investigations": [
                investigation_diagnosis(value) for value in embedded.values()
            ],
        }
    rows = []
    aggregator = LinearEvidenceAggregator()
    for branch in record["data"]["branches"]:
        data = branch["data"]
        values = [
            e["data"]["data"]["items"]["candidate"] - e["data"]["data"]["items"]["baseline"]
            for e in data["evidence"]
        ]
        if not values:
            continue
        wins, ties, losses = (
            sum(v > 0 for v in values),
            sum(v == 0 for v in values),
            sum(v < 0 for v in values),
        )
        row = {
            "branch_id": data["branch_id"],
            "status": data["status"],
            "native_confidence": data["belief"]["data"]["confidence"],
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "values": values,
            "mean": statistics.mean(values),
            "one_se_lower": statistics.mean(values) - statistics.stdev(values) / len(values) ** 0.5,
        }
        # Exhaust the small ordinary-pass case, not 32-choose-k meta permutations.
        if len(values) == 16 and losses == 0:
            outcomes: Counter[str] = Counter()
            for positions in itertools.combinations(range(len(values)), wins):
                positive = set(positions)
                status, confidence = "proposed", 0.5
                for i in range(len(values)):
                    status, confidence = aggregator.transition(
                        current_status=status,
                        current_confidence=confidence,
                        relationship="support" if i in positive else "counterexample",
                        weight=1,
                    )
                outcomes[status] += 1
            row["sign_order_status_counts"] = dict(outcomes)
        rows.append(row)
    return {
        "native_record_type": record["record_type"],
        "stopped_before_comparison": not any(row["status"] == "supported" for row in rows),
        "native_root": record["root"],
        "branches": rows,
        "scope": "Post-hoc diagnostic, not confirmation. Sign-order counts show possible aggregator outcomes, not probabilities of real root orderings.",
    }


def audit(run: Path, output: Path):
    report = read(run / "report.json")
    protocol = read(run / "protocol.json")
    assert report["protocol"] == protocol
    assert protocol["model"] == "gpt-6-astra" and protocol["reasoning_effort"] == "high"
    root = Path(__file__).resolve().parents[1]
    sources = {}
    for name, expected in protocol["provenance"]["files_sha256"].items():
        source = (run / "source" / name).read_bytes()
        assert hashlib.sha256(source).hexdigest() == expected
        assert (root / name).read_bytes() == source, f"replay source changed: {name}"
        sources[name] = source.decode()
    assert provenance()["runtime_python_sha256"] == protocol["provenance"]["runtime_python_sha256"]
    data = read(run / "workloads.json")
    ids = set()
    for split, count in SPLITS.items():
        assert len(data[split]) == count
        for i, row in enumerate(data[split]):
            assert row == workload(SEEDS[split] + i, i % 4)
            assert row["id"] not in ids
            ids.add(row["id"])

    receipts = read(run / "model-receipts.json")
    assert receipts == report["receipts"] and len(receipts) == 261
    transcripts = []
    roles: Counter[str] = Counter()
    tokens = 0
    test_ids = {row["id"] for row in data["test"]}
    for i, receipt in enumerate(receipts, 1):
        folder = run / "model-calls" / f"{i:03d}"
        assert receipt == read(folder / "receipt.json")
        assert receipt["number"] == i and receipt["returncode"] == receipt["tool_items"] == 0
        assert receipt["model"] == "gpt-6-astra" and receipt["reasoning_effort"] == "high"
        prompt = (folder / "prompt.txt").read_text()
        assert digest(prompt) == receipt["prompt_sha256"]
        assert not any(identifier in prompt for identifier in test_ids)
        assert len(receipt["usage"]) == 1
        tokens += sum(u["input_tokens"] + u["output_tokens"] for u in receipt["usage"])
        roles[receipt["role"].split(":")[0]] += 1
        transcripts.append(
            {
                "receipt": receipt,
                "prompt": prompt,
                "schema": read(folder / "schema.json"),
                "response": read(folder / "response.json")
                if (folder / "response.json").exists()
                else None,
            }
        )
    assert roles == {
        "broad-goal-operationalization": 1,
        "ordinary-native": 1,
        "program-development": 96,
        "meta-proposer-revision": 1,
        "after-meta-native": 1,
        "program-final": 161,
    }
    assert tokens == report["effort"]["input_output_tokens"]
    intent = read(run / "intent.json")
    assert intent["model_plan"] == report["model_plan"]
    plan_response = transcripts[0]["response"]["candidates"][0]["configuration"]["plan"]
    assert json.loads(plan_response) == intent["model_plan"]
    plan = report["model_plan"]
    frozen = read(run / "frozen-policies.json")
    assert frozen == report["frozen_policies"]
    assert report["transfer_native"]["instruction"] == frozen["active"]
    if not frozen["native_adopted"]:
        assert frozen["active"] == frozen["ordinary"]
        expected = max(frozen["training"][1:], key=lambda row: row["mean"])["instruction"]
        assert frozen["challenger"] == expected
    else:
        assert frozen["challenger"] == frozen["active"]

    output.mkdir(parents=True, exist_ok=False)
    oracle = build_oracle(output / "audit-oracle")
    problems = {
        split: [SequenceProblem(row, oracle) for row in rows] for split, rows in data.items()
    }
    measurements = {}
    replayed = 0

    def measured(config, split):
        nonlocal replayed
        key = f"{digest(config)}:{split}"
        if key not in measurements:
            measurements[key] = [execute(config, p) for p in problems[split]]
            replayed += len(problems[split])
        return measurements[key]

    def value(config, split):
        return statistics.mean(row[plan["metric"]] for row in measured(config, split))

    draws = []
    by_key = {}
    configs = {digest(BASE_PROGRAM): BASE_PROGRAM}
    invalid = 0
    for path in sorted((run / "draws").glob("*-selected.json")):
        row = read(path)
        generated = read(path.with_name(path.name.replace("-selected", "-generated")))
        assert all(row[key] == val for key, val in generated.items())
        matching = [t for t in transcripts if t["receipt"]["role"] == row["role"]]
        assert len(matching) == 1
        response = matching[0]["response"]
        if response is not None:
            assert len(row["candidates"]) == len(response["candidates"])
            for candidate, original in zip(row["candidates"], response["candidates"], strict=True):
                assert candidate["configuration"] == original["configuration"]
                assert candidate["reason"] == original["reason"]
        candidates = [BASE_PROGRAM]
        for candidate in row["candidates"]:
            try:
                parse_program(candidate["configuration"], allow_baseline=False)
                valid = True
            except (ValueError, TypeError, KeyError):
                valid = False
            assert candidate["valid"] == valid
            if valid:
                config = candidate["configuration"]
                candidates.append(config)
                configs[digest(config)] = config
            else:
                invalid += 1
        split = "generation" if row["phase"] == "development" else "final_generation"
        values = [value(config, split) for config in candidates]
        assert values == row["selection_values"]
        best = max(range(len(values)), key=values.__getitem__)
        assert candidates[best] == row["selected"] and values[best] == row["selection_value"]
        assert row["policy_key"] == digest(
            {"instruction": row["instruction"], "phase": row["phase"]}
        )
        by_key[(row["policy_key"], row["sample"])] = row
        draws.append(row)
    assert len(draws) == 257
    gate_diagnostics = {}
    for name in ("ordinary-native", "after-meta-native"):
        evidence = json.loads(gzip.decompress((run / f"{name}-native.json.gz").read_bytes()))
        gate_diagnostics[name] = investigation_diagnosis(evidence["result"])
        for choice in evidence["choices"]:
            configs[digest(choice["configuration"])] = choice["configuration"]
    selected = read(run / "frozen-programs.json")
    base_key = digest({"instruction": frozen["ordinary"], "phase": "final"})
    meta_key = digest({"instruction": frozen["challenger"], "phase": "final"})
    offset = 0
    for i in range(32):
        size = 5 if i == 0 else 4
        group = [by_key[(base_key, j)] for j in range(offset, offset + size)]
        offset += size
        assert selected["ordinary"][i] == group[0]
        assert selected["equal_calls"][i] == max(group, key=lambda row: row["selection_value"])
        assert selected["revised"][i] == by_key[(meta_key, i)]
    for key, expected in report["program_evaluations"].items():
        config_id, split = key.split(":")
        assert measured(configs[config_id], split) == expected
    for arm, rows in selected.items():
        grid = [[r[plan["metric"]] for r in measured(row["selected"], "test")] for row in rows]
        assert grid == report["scores"][arm]
        assert float(np.asarray(grid).mean()) == report["means"][arm]
    families = [row["family"] for row in data["test"]]
    for name, expected in report["contrasts"].items():
        assert interval(report["scores"], name, "revised", families) == expected
    assert [execute(BASE_PROGRAM, p)[plan["metric"]] for p in problems["test"]] == report[
        "baseline_scores"
    ]
    fixed = []
    for p in problems["test"]:
        c = cost(p.matrix, local_search(p.matrix, p.starting_order))
        fixed.append(p.optimal_cost / c if plan["metric"] == "quality" else 1 - c / p.starting_cost)
    assert fixed == report["fixed_local_search_scores"]
    effort = report["effort"]
    assert effort["program_executions"] == sum(
        len(rows) for rows in report["program_evaluations"].values()
    )
    assert effort["cost_evaluations"] == sum(
        r["evaluations"] for rows in report["program_evaluations"].values() for r in rows
    )
    assert effort["meta_development_calls"] == 97
    assert effort["equal_call_original_total"] == effort["meta_plus_confirmation_total"] == 129
    family_means = {
        arm: {
            str(i): float(np.asarray(grid)[:, np.asarray(families) == i].mean()) for i in range(4)
        }
        for arm, grid in report["scores"].items()
    }
    validation = {
        "status": "passed",
        "model_calls_reconciled": len(receipts),
        "selected_draws_replayed": len(draws),
        "program_workload_executions_replayed": replayed,
        "invalid_candidates": invalid,
        "family_means": family_means,
        "unique_final_programs": {
            arm: len({digest(r["selected"]) for r in rows}) for arm, rows in selected.items()
        },
        "checks": [
            "source and runtime identity",
            "all workload seeds and disjointness",
            "model/effort/usage/prompt hashes and no final workload identifiers in prompts",
            "LLM plan matches accepted interpretation",
            "actual active-policy transfer",
            "all candidate selection and control pools",
            "every recorded program execution",
            "all final scores and bootstrap intervals",
            "effort totals",
        ],
    }
    write_json(output / "validation.json", validation)
    meta_evidence = json.loads(gzip.decompress((run / "meta-native.json.gz").read_bytes()))
    gate_diagnostics["meta-native"] = investigation_diagnosis(meta_evidence["native"])
    ordinary_choices = json.loads(
        gzip.decompress((run / "ordinary-native-native.json.gz").read_bytes())
    )["choices"]
    transfer_choices = json.loads(
        gzip.decompress((run / "after-meta-native-native.json.gz").read_bytes())
    )["choices"]
    gate_diagnostics["same_program_configurations_in_native_passes"] = [
        r["configuration"] for r in ordinary_choices
    ] == [r["configuration"] for r in transfer_choices]
    write_json(output / "native-gate-diagnosis.json", gate_diagnostics)
    packed(output / "report.json.gz", report)
    packed(output / "model-transcripts.json.gz", transcripts)
    packed(output / "executed-sources.json.gz", sources)
    packed(output / "draws.json.gz", draws)
    packed(output / "frozen-programs.json.gz", selected)
    for name in (
        "protocol.json",
        "workloads.json",
        "intent.json",
        "frozen-policies.json",
        "model-receipts.json",
        "ordinary-native.json",
        "after-meta-native.json",
        "ordinary-native-native.json.gz",
        "after-meta-native-native.json.gz",
        "meta-native.json.gz",
    ):
        (output / name).write_bytes((run / name).read_bytes())
    summary = {
        key: report[key]
        for key in (
            "model_plan",
            "means",
            "contrasts",
            "effort",
            "ordinary_native",
            "transfer_native",
        )
    }
    summary["native_meta"] = {
        key: frozen[key]
        for key in ("native_adopted", "native_disposition", "active_root", "native_root")
    }
    summary["family_means"] = family_means
    summary["model"] = protocol["model"]
    summary["reasoning_effort"] = protocol["reasoning_effort"]
    write_json(output / "summary.json", summary)
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.iterdir())
        if p.is_file() and p.name != "audit-oracle"
    }
    write_json(
        output / "evidence-manifest.json",
        {
            "sha256": manifest,
            "excluded": "Compiled replay oracle, provider event streams and local stores remain private; only application prompts and final structured proposals are published.",
        },
    )
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.run, args.output)
