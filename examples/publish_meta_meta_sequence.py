"""Audit and graph the completed meta-meta cascade without further model calls."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from audit_native_sequence import export_native
from benchmark_document_search import write_json
from benchmark_meta_meta_sequence import interval
from benchmark_native_sequence import BASE_PROGRAM, fresh_problem
from compact_benchmark_store import verify_archive
from plot_native_sequence import bootstrap_mean
from sequence_program import BASE_INSTRUCTIONS, execute
from setup_sequence import build_oracle

from librsi import Observation, TargetSnapshot, record_from_dict
from librsi.identity import digest


def read_gz(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def audit(source, output):
    output.mkdir(parents=True, exist_ok=False)
    report = read_gz(source / "report.json.gz")
    receipts = json.loads((source / "receipts.json").read_text())
    protocol = json.loads((source / "protocol.json").read_text())
    assert report["protocol"] == protocol
    for name, expected in protocol["source_sha256"].items():
        assert hashlib.sha256((source / "source" / name).read_bytes()).hexdigest() == expected
    transcripts = []
    roles: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        assert receipt["model"] == "gpt-6-astra" and receipt["reasoning_effort"] == "high"
        path = source / "model-calls" / f"{receipt['number']:03d}"
        assert json.loads((path / "receipt.json").read_text()) == receipt
        prompt = (path / "prompt.txt").read_text()
        assert digest(prompt) == receipt["prompt_sha256"]
        roles.setdefault(receipt["role"], []).append(receipt)
        if receipt.get("status") == "timeout":
            assert not receipt["usage"] and not (path / "response.json").exists()
        else:
            assert receipt["returncode"] == 0 and receipt["tool_items"] == 0
            assert len(receipt["usage"]) == 1
        transcripts.append(
            {
                "receipt": receipt,
                "prompt": prompt,
                "response": json.loads((path / "response.json").read_text())
                if (path / "response.json").exists()
                else None,
                "invalid_output": json.loads((path / "invalid-output.json").read_text())
                if (path / "invalid-output.json").exists()
                else None,
            }
        )
    assert len(receipts) <= 526 and len(roles) <= 518
    for attempts in roles.values():
        assert len(attempts) in (1, 2) and attempts[-1].get("returncode") == 0
        if len(attempts) == 2:
            assert attempts[0]["status"] == "timeout"
            assert attempts[0]["prompt_sha256"] == attempts[1]["prompt_sha256"]
    assert len(receipts) - len(roles) <= 8

    all_rows = [
        row for groups in report["development"].values() for rows in groups.values() for row in rows
    ]
    all_rows += report["runs"]
    disk_rows = list(source.glob("phases/*/runs/*.json"))
    assert len(all_rows) == len(disk_rows) == report["effort"]["native_inner_runs"] <= 512
    assert len({r["label"] for r in all_rows}) == len(all_rows)
    native_dir = output / "native"
    native_dir.mkdir()
    archive_manifests = output / "store-archive-manifests"
    archive_manifests.mkdir()
    for path in disk_rows:
        row = json.loads(path.read_text())
        assert row in all_rows
        archive = path.parent.parent / "store-archives" / f"{row['label']}.tar.gz"
        verified = verify_archive(archive)
        write_json(archive_manifests / f"{row['label']}.json", verified)
        evidence_path = path.parent.parent / "native" / f"{row['label']}.json.gz"
        evidence = read_gz(evidence_path)
        active = record_from_dict(evidence["active"])
        inputs = record_from_dict(evidence["inputs"])
        assert isinstance(active, TargetSnapshot) and isinstance(inputs, Observation)
        assert inputs.target_snapshot is not None
        assert active.root == row["active_root"] and dict(active.state) == row["configuration"]
        assert dict(inputs.target_snapshot.state) == BASE_PROGRAM
        assert inputs.value["learning_version"] == 3
        assert evidence["native"]["root"] == row["native_root"]
        assert row["adopted"] == (row["configuration"] != BASE_PROGRAM)
        export_native(evidence_path, native_dir / f"{row['label']}.json.xz")
    gates = [json.loads(p.read_text()) for p in sorted((source / "gates").glob("*.json"))]
    for row in gates:
        path = source / "native-gates" / f"{row['label']}.json.gz"
        evidence = read_gz(path)
        active = record_from_dict(evidence["active"])
        inputs = record_from_dict(evidence["inputs"])
        assert isinstance(active, TargetSnapshot) and isinstance(inputs, Observation)
        assert inputs.target_snapshot is not None
        assert active.root == row["active_root"] and dict(active.state) == row["active"]
        assert dict(inputs.target_snapshot.state) == row["initial"]
        assert evidence["native"]["root"] == row["native_root"]
        export_native(path, native_dir / f"gate-{row['label']}.json.xz")
    expected_gates = [
        report["meta_meta"],
        *report["children"].values(),
        *report["propagation"].values(),
    ]
    assert sorted(gates, key=lambda r: r["label"]) == sorted(
        expected_gates, key=lambda r: r["label"]
    )
    expected_roles = (
        {r["label"] for r in all_rows}
        | {r["label"] for r in gates if r["label"] != "meta-meta"}
        | {"meta-meta-proposals"}
    )
    assert set(roles) == expected_roles
    assert report["instructions"]["ordinary"] == BASE_INSTRUCTIONS
    assert all(row["initial"] == BASE_INSTRUCTIONS for row in report["propagation"].values())
    # The propagated gate starts from the original ordinary instruction; its proposal
    # request must contain the active meta instruction, not an unaccepted candidate.
    retained_prompt = next(
        t["prompt"] for t in transcripts if t["receipt"]["role"] == "propagate-retained-meta"
    )
    assert retained_prompt.startswith(report["meta_meta"]["active"]["instruction"])
    assert report["instructions"]["after_meta"] == report["propagation"]["original_meta"]["active"]
    assert (
        report["instructions"]["after_meta_meta"]
        == report["propagation"]["retained_meta"]["active"]
    )
    for row in report["runs"]:
        arm = row["label"].rsplit("-", 1)[0]
        assert row["instruction"] == report["instructions"][arm]

    oracle = build_oracle(output / "oracle")
    workloads = {p.stem: json.loads(p.read_text()) for p in (source / "workloads").glob("*.json")}
    test_data = workloads["test"]
    assert len(test_data) == 512
    all_ids = [
        r["id"]
        for name, splits in workloads.items()
        if name != "test"
        for rows in splits.values()
        for r in rows
    ]
    all_ids += [r["id"] for r in test_data]
    assert len(all_ids) == len(set(all_ids))
    for t in transcripts:
        assert all(row["id"] not in t["prompt"] for row in test_data)
    test = [fresh_problem(row, oracle) for row in test_data]
    cache = {}

    def score(config, key, problems):
        cache_key = digest(config), key
        if cache_key not in cache:
            cache[cache_key] = [execute(config, p)["cost_reduction"] for p in problems]
        return cache[cache_key]

    for phase, groups in report["development"].items():
        for split in ("meta_train", "meta_shadow", "meta_verify"):
            problems = [fresh_problem(row, oracle) for row in workloads[phase][split]]
            for rows in groups.values():
                for row in rows:
                    assert np.isclose(
                        np.mean(score(row["configuration"], phase + split, problems)),
                        row["evaluation"][split],
                        rtol=0,
                        atol=1e-14,
                    )
    for arm, expected in report["scores"].items():
        rows = [r for r in report["runs"] if r["label"].startswith(arm + "-")]
        assert len(rows) == 32
        actual = [score(r["configuration"], "test", test) for r in rows]
        assert np.allclose(actual, expected, rtol=0, atol=1e-14)
        assert float(np.mean(actual)) == report["means"][arm]
        assert sum(r["adopted"] for r in rows) == report["adoptions"][arm]
    families = [p.data["family"] for p in test]
    assert (
        interval(report["scores"], "after_meta", "after_meta_meta", families, seed=2026111309)
        == report["primary_contrast"]
    )
    assert report["runs"] == json.loads((source / "frozen-final-systems.json").read_text())
    assert report["meta_meta"] == json.loads((source / "frozen-meta-optimizer.json").read_text())
    frozen = json.loads((source / "frozen-final-instructions.json").read_text())
    assert frozen["instructions"] == report["instructions"]
    assert frozen["meta_meta"] == report["meta_meta"]
    assert frozen["original_meta_propagation"] == report["propagation"]["original_meta"]
    assert frozen["meta_meta_propagation"] == report["propagation"]["retained_meta"]
    for name in (
        "protocol.json",
        "protocol.md",
        "report.json.gz",
        "summary.json",
        "receipts.json",
        "prior-development.json",
        "meta-meta-proposals.json",
        "frozen-meta-optimizer.json",
        "frozen-final-instructions.json",
        "frozen-final-systems.json",
    ):
        shutil.copyfile(source / name, output / name)
    shutil.copytree(source / "workloads", output / "workloads")
    shutil.copytree(source / "gates", output / "gates")
    (output / "model-transcripts.json.gz").write_bytes(
        gzip.compress(json.dumps(transcripts, sort_keys=True).encode(), mtime=0)
    )
    sources = {
        str(p.relative_to(source / "source")): p.read_text()
        for p in (source / "source").rglob("*")
        if p.is_file()
    }
    (output / "executed-sources.json.gz").write_bytes(
        gzip.compress(json.dumps(sources, sort_keys=True).encode(), mtime=0)
    )
    write_json(
        output / "validation.json",
        {
            "model": "gpt-6-astra",
            "reasoning_effort": "high",
            "verified_inner_runs": len(all_rows),
            "verified_upper_passes": len(gates),
            "verified_attempts": len(receipts),
            "verified_logical_calls": len(roles),
            "development_and_final_scores_replayed": True,
            "primary_bootstrap_replayed": True,
            "source_hashes_verified": True,
            "complete_store_archive_hashes_verified": len(disk_rows),
            "downward_active_instruction_bindings_verified": True,
        },
    )
    return report, receipts


def render(report, receipts, output):
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
        }
    )
    arms = ["ordinary", "after_meta", "after_meta_meta"]
    colors = ["#8993a6", "#2777b5", "#6b4cbb", "#14837d"]
    means = [0, *[report["means"][a] * 100 for a in arms]]
    bounds = [
        [0, 0],
        *[bootstrap_mean(report["scores"][a], 2026111320 + i) for i, a in enumerate(arms)],
    ]
    fig, ax = plt.subplots(figsize=(12.5, 7.2))
    fig.subplots_adjust(left=0.10, right=0.97, bottom=0.30, top=0.76)
    fig.suptitle(
        "Does improving the meta optimizer help the base system?",
        x=0.10,
        ha="left",
        y=0.96,
        fontsize=18,
        weight="bold",
    )
    fig.text(
        0.10,
        0.89,
        "gpt-6-astra · high reasoning · optimizer, meta optimizer AND meta-meta optimizer",
        fontsize=11,
    )
    fig.text(
        0.10,
        0.84,
        "32 independent native runs per optimization arm · 512 unseen synthetic workloads",
        fontsize=11,
    )
    ax.bar(range(4), means, color=colors, width=0.58)
    for i, (mean, bound) in enumerate(zip(means, bounds, strict=True)):
        ax.errorbar(
            i,
            mean,
            yerr=[[max(0, mean - bound[0])], [max(0, bound[1] - mean)]],
            color="#263343",
            capsize=5,
        )
        ax.text(i, bound[1] + 1.1, f"{mean:.2f}%", ha="center", weight="bold", fontsize=13)
    for i, arm in enumerate(arms, 1):
        dots = np.asarray(report["scores"][arm]).mean(axis=1) * 100
        jitter = np.random.default_rng(43 + i).uniform(-0.19, 0.19, len(dots))
        ax.scatter(i + jitter, dots, color="#182437", s=18, alpha=0.5, zorder=3)
    ax.set_xticks(
        range(4),
        [
            "Original\nbase",
            "Ordinary\nlibRSI",
            "Original meta\n→ libRSI",
            "After meta-meta\n→ meta → libRSI",
        ],
    )
    ax.set_ylim(0, max(b[1] for b in bounds) + 6)
    ax.set_ylabel("Mean setup-cost reduction vs. original base (%)")
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    delta = report["primary_contrast"]
    low, high = np.asarray(delta["bootstrap_95_percentile"]) * 100
    fig.text(
        0.10,
        0.18,
        f"Meta-meta policy adopted: {report['meta_meta']['adopted']}. Fresh downstream meta revision adopted: {report['propagation']['retained_meta']['adopted']}.",
        fontsize=10,
    )
    fig.text(
        0.10,
        0.13,
        f"Meta-meta cascade − original-meta cascade: {delta['mean_effect'] * 100:+.2f} pp; 95% CI [{low:+.2f}, {high:+.2f}]",
        fontsize=11,
    )
    fig.text(
        0.10,
        0.065,
        "Dots: per-run retained-system means. Intervals resample model draws and shared test workloads.\nConditional on one meta-meta training round and one fresh propagation per arm; no equal-compute comparison.",
        fontsize=9,
        color="#4c5564",
    )
    for suffix in ("png", "svg"):
        fig.savefig(output / f"meta-meta-sequence-results.{suffix}", dpi=180, facecolor="white")
    plt.close(fig)

    def phase(role):
        if role.startswith(("development-", "develop-", "upper-", "meta-meta-")):
            return "Cascade\ndevelopment"
        if role.startswith(("propagation-", "propagate-")):
            return "Fresh\npropagation"
        if role.startswith("ordinary-"):
            return "Final\nordinary"
        if role.startswith("after_meta_meta-"):
            return "Final\nmeta-meta"
        if role.startswith("after_meta-"):
            return "Final\nmeta"
        return "Forced\ndiagnostic"

    counts = Counter(phase(r["role"]) for r in receipts)
    labels = [
        "Cascade\ndevelopment",
        "Fresh\npropagation",
        "Final\nordinary",
        "Final\nmeta",
        "Final\nmeta-meta",
        "Forced\ndiagnostic",
    ]
    fig, ax = plt.subplots(figsize=(12, 5.7))
    fig.subplots_adjust(left=0.09, right=0.97, bottom=0.25, top=0.75)
    fig.suptitle(
        "Model effort across the meta-meta experiment",
        x=0.09,
        ha="left",
        y=0.96,
        fontsize=18,
        weight="bold",
    )
    fig.text(
        0.09, 0.87, "gpt-6-astra · high reasoning · all three optimization levels", fontsize=11
    )
    values = [counts[label] for label in labels]
    ax.bar(labels, values, color="#2777b5")
    for i, value in enumerate(values):
        ax.text(i, value + max(values) * 0.025, str(value), ha="center", weight="bold")
    ax.set_ylim(0, max(values) * 1.2)
    ax.set_ylabel("Recorded model request attempts")
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    effort = report["effort"]
    tokens = effort["usage"]["input_tokens"] + effort["usage"]["output_tokens"]
    fig.text(
        0.09,
        0.12,
        f"{len(receipts)} attempts · {effort['logical_calls']} logical calls · {tokens:,} known input/output tokens. Timeout usage unknown.\nShared development pools are counted once. These stage totals do not allocate shared training expense to one arm.",
        fontsize=10,
    )
    for suffix in ("png", "svg"):
        fig.savefig(output / f"meta-meta-sequence-effort.{suffix}", dpi=180, facecolor="white")
    plt.close(fig)
    return {
        "means_percent": means,
        "intervals_percent": [list(b) for b in bounds],
        "attempts_by_phase": dict(counts),
    }


def export_csv(report, output):
    fields = [
        "case",
        "optimization_run",
        "optimizer_model",
        "meta_model",
        "meta_meta_model",
        "reasoning_effort",
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
                "optimizer_model": "none",
                "meta_model": "none",
                "meta_meta_model": "none",
                "test_workloads": 512,
                "mean_cost_reduction_percent": 0,
            }
        )
        for arm, grid in report["scores"].items():
            rows = [r for r in report["runs"] if r["label"].startswith(arm + "-")]
            for row, scores in zip(rows, grid, strict=True):
                writer.writerow(
                    {
                        "case": arm,
                        "optimization_run": row["label"],
                        "optimizer_model": "gpt-6-astra",
                        "meta_model": "none" if arm == "ordinary" else "gpt-6-astra",
                        "meta_meta_model": "gpt-6-astra"
                        if arm in ("after_meta_meta", "forced_cascade_diagnostic")
                        else "none",
                        "reasoning_effort": "high",
                        "scheduler_adopted": row["adopted"],
                        "test_workloads": len(scores),
                        "mean_cost_reduction_percent": float(np.mean(scores) * 100),
                    }
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report, receipts = audit(args.source.resolve(), args.output.resolve())
    figures = render(report, receipts, args.output / "plots")
    write_json(args.output / "figure-values.json", figures)
    export_csv(report, args.output / "run-scores.csv")
    (args.output / "analysis-source.py").write_bytes(Path(__file__).read_bytes())
    manifest = {
        str(p.relative_to(args.output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in args.output.rglob("*")
        if p.is_file() and p.name != "oracle"
    }
    write_json(args.output / "evidence-manifest.json", manifest)
    print("AUDITED DATA AND GRAPHS READY", args.output.resolve(), flush=True)
