"""Plot actual adopted systems and recorded effort from the native Astra study."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

COLORS = ["#8993a6", "#2777b5", "#6b4cbb"]


def attempts(rows):
    return len(rows) + sum("transport_retry" in row for row in rows)


def bootstrap_mean(grid, seed):
    values = np.asarray(grid)
    rng = np.random.default_rng(seed)
    families = [np.arange(i, values.shape[1], 4) for i in range(4)]
    draws = []
    for _ in range(10000):
        rows = rng.integers(0, len(values), len(values))
        tasks = np.concatenate([rng.choice(ids, len(ids), replace=True) for ids in families])
        draws.append(values[rows][:, tasks].mean())
    return np.quantile(draws, [0.025, 0.975]) * 100


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
    arms = ["ordinary", "after_meta"]
    test_count = len(report["test_baseline_costs"])
    means = [0, *[report["means"][arm] * 100 for arm in arms]]
    bounds = [
        [0, 0],
        *[bootstrap_mean(report["scores"][arm], 2026111211 + i) for i, arm in enumerate(arms)],
    ]
    labels = [
        "Base\nscheduler",
        "libRSI\noptimization",
        "After meta pass\n(original retained)"
        if not report["meta"]["adopted"]
        else "Meta → libRSI\noptimization",
    ]
    fig, (ax, effort_ax) = plt.subplots(
        1, 2, figsize=(13, 6.9), gridspec_kw={"width_ratios": [1.7, 1]}
    )
    fig.subplots_adjust(left=0.10, right=0.97, bottom=0.28, top=0.78, wspace=0.35)
    fig.suptitle(
        "Base vs. libRSI vs. libRSI after a meta pass",
        fontsize=19,
        x=0.10,
        ha="left",
        y=0.96,
        weight="bold",
    )
    fig.text(
        0.10,
        0.90,
        "gpt-6-astra · high reasoning · scheduler AND meta proposals",
        fontsize=11,
    )
    fig.text(
        0.10,
        0.855,
        "32 complete libRSI runs per optimization arm; each starts from the same base",
        fontsize=11,
    )
    ax.bar(range(3), means, width=0.6, color=COLORS, alpha=0.88)
    for i, (mean, bound) in enumerate(zip(means, bounds, strict=True)):
        ax.errorbar(
            i,
            mean,
            yerr=[[max(0, mean - bound[0])], [max(0, bound[1] - mean)]],
            color="#202b3c",
            capsize=6,
            linewidth=1.5,
        )
        ax.text(i, bound[1] + 1.3, f"{mean:.2f}%", ha="center", weight="bold", fontsize=14)
    for i, arm in enumerate(arms, 1):
        points = np.asarray(report["scores"][arm]).mean(axis=1) * 100
        jitter = np.random.default_rng(41 + i).uniform(-0.21, 0.21, len(points))
        ax.scatter(i + jitter, points, c="#182437", s=20, alpha=0.55, linewidths=0, zorder=4)
    ax.set_xticks(range(3), labels)
    ax.set_ylabel("Mean setup-cost reduction vs. base (%)")
    ax.set_ylim(0, max(max(v[1] for v in bounds), max(means)) + 7)
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    ordinary = [r for r in receipts if r["role"].startswith("ordinary-")]
    meta_rows = [r for r in receipts if r["role"].startswith(("dev-", "meta-", "after_meta-"))]
    calls = [0, attempts(ordinary), attempts(meta_rows)]
    effort_ax.bar(range(3), calls, color=COLORS, width=0.6)
    effort_ax.set_xticks(range(3), ["Base", "libRSI", "Meta → libRSI"])
    effort_ax.set_ylabel("Model request attempts")
    effort_ax.set_ylim(0, max(calls) * 1.25)
    effort_ax.grid(axis="y", alpha=0.18)
    effort_ax.set_axisbelow(True)
    for i, value in enumerate(calls):
        effort_ax.text(i, value + 4, str(value), ha="center", weight="bold", fontsize=13)
    ordinary_retries = attempts(ordinary) - len(ordinary)
    meta_retries = attempts(meta_rows) - len(meta_rows)
    effort_ax.set_title(
        f"Meta includes 73 development calls + {meta_retries} retry"
        if meta_retries
        else "Meta includes 73 development calls",
        fontsize=10,
        pad=12,
    )
    meta = report["meta"]
    status = (
        "Meta revision adopted and reopened"
        if meta["adopted"]
        else f"Meta revision not adopted ({meta['disposition']}); third arm uses the retained original improver"
    )
    delta = report["primary_contrast"]
    low, high = np.asarray(delta["bootstrap_95_percentile"]) * 100
    fig.text(0.10, 0.16, status, fontsize=10, color="#4a385f")
    fig.text(
        0.10,
        0.115,
        f"Meta − ordinary: {delta['mean_effect'] * 100:+.2f} percentage points; 95% CI [{low:+.2f}, {high:+.2f}]",
        fontsize=11,
    )
    fig.text(
        0.10,
        0.065,
        f"Dots: retained-system mean per run. Whiskers: crossed-bootstrap 95% intervals over runs and {test_count} test workloads.\nSynthetic setup costs; deterministic scheduler at runtime. Uncertainty is conditional on one meta-development run.",
        fontsize=9,
        color="#4c5564",
    )
    for suffix in ("png", "svg"):
        fig.savefig(output / f"native-sequence-results.{suffix}", dpi=180, facecolor="white")
    plt.close(fig)

    def tokens(rows):
        return sum(
            u.get("input_tokens", 0) + u.get("output_tokens", 0)
            for r in rows
            for u in r.get("usage", [])
        )

    ordinary = [r for r in receipts if r["role"].startswith("ordinary-")]
    meta_rows = [r for r in receipts if r["role"].startswith(("dev-", "meta-", "after_meta-"))]
    calls = [0, attempts(ordinary), attempts(meta_rows)]
    token_counts = [0, tokens(ordinary), tokens(meta_rows)]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 6.4))
    fig.subplots_adjust(left=0.09, right=0.97, bottom=0.30, top=0.76, wspace=0.35)
    fig.suptitle(
        "Model effort for each comparison",
        fontsize=19,
        x=0.09,
        ha="left",
        y=0.96,
        weight="bold",
    )
    fig.text(
        0.09,
        0.89,
        "gpt-6-astra · high reasoning · all reasoning roles",
        fontsize=11,
    )
    short = ["Base", "libRSI", "Meta → libRSI"]
    for ax, values, ylabel, fmt in zip(
        axes,
        [[float(x) for x in calls], [x / 1e6 for x in token_counts]],
        ["Total model request attempts", "Reported input + output tokens (millions)"],
        [".0f", ".2f"],
        strict=True,
    ):
        ax.bar(range(3), values, color=COLORS, width=0.6)
        for i, value in enumerate(values):
            ax.text(i, value + max(values) * 0.04, format(value, fmt), ha="center", weight="bold")
        ax.set_xticks(range(3), short)
        ax.set_ylim(0, max(values) * 1.22)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.18)
        ax.set_axisbelow(True)
    extra = report["effort"]["forced_diagnostic_calls"]
    phase_seconds = report["effort"]["wall_seconds"] + report["effort"].get(
        "prior_generation_wall_seconds", 0
    )
    wall_note = (
        "Includes reused generation time, interruptions and recovery pauses."
        if report["effort"].get("wall_time_includes_interruptions")
        else "Includes reused generation time; excludes recovery work."
    )
    fig.text(
        0.09,
        0.21,
        f"32 native optimizations per arm; meta adds 73 development calls. Timeout retries: ordinary {ordinary_retries}, meta {meta_retries}.",
        fontsize=10,
    )
    fig.text(
        0.09,
        0.15,
        f"Full study: {report['effort']['model_calls']} calls, {phase_seconds / 60:.1f} recorded phase minutes.\nAdditional forced-revision diagnostic: {extra} calls (excluded from the two primary treatment budgets).",
        fontsize=10,
    )
    fig.text(
        0.09,
        0.065,
        "No model calls during scheduler execution; both optimized schedulers get 256 cost evaluations per workload.\n"
        f"{wall_note} Cached input included; timeout usage and billing unknown.\n"
        "This comparison does not establish superiority at equal total compute.",
        fontsize=9,
        color="#4c5564",
    )
    for suffix in ("png", "svg"):
        fig.savefig(output / f"native-sequence-effort.{suffix}", dpi=180, facecolor="white")
    plt.close(fig)
    if "exploratory_forced_contrast" in report:
        fig, ax = plt.subplots(figsize=(11.5, 5.6))
        fig.subplots_adjust(left=0.29, right=0.96, bottom=0.30, top=0.70)
        fig.suptitle(
            "Using the proposed meta revision anyway",
            x=0.06,
            y=0.95,
            ha="left",
            fontsize=18,
            weight="bold",
        )
        fig.text(
            0.06,
            0.86,
            "gpt-6-astra · high reasoning · both optimizer and meta optimizer",
            fontsize=11,
        )
        fig.text(
            0.06,
            0.80,
            f"32 native runs per arm · {test_count} unseen synthetic workloads · 95% crossed-bootstrap intervals",
            fontsize=10,
        )
        contrasts = [report["primary_contrast"], report["exploratory_forced_contrast"]]
        for y, contrast in zip([1, 0], contrasts, strict=True):
            mean = contrast["mean_effect"] * 100
            low, high = np.asarray(contrast["bootstrap_95_percentile"]) * 100
            ax.errorbar(
                mean,
                y,
                xerr=[[mean - low], [high - mean]],
                fmt="o",
                capsize=6,
                markersize=8,
                color=COLORS[2] if y else "#b95735",
            )
            ax.annotate(
                f"{mean:+.2f} pp  [{low:+.2f}, {high:+.2f}]",
                (mean, y),
                xytext=(0, 16),
                textcoords="offset points",
                ha="center",
                fontsize=11,
            )
        ax.axvline(0, color="#687180", linewidth=1, linestyle="--")
        ax.set_yticks(
            [1, 0],
            [
                "After meta pass\n(original retained)",
                "Use proposed instruction\n(forced diagnostic)",
            ],
        )
        ax.set_ylim(-0.55, 1.65)
        low_edge = min(0, *[c["bootstrap_95_percentile"][0] * 100 for c in contrasts])
        high_edge = max(0, *[c["bootstrap_95_percentile"][1] * 100 for c in contrasts])
        margin = max(0.2, (high_edge - low_edge) * 0.18)
        ax.set_xlim(low_edge - margin, high_edge + margin)
        ax.set_xlabel("Additional setup-cost reduction vs. ordinary libRSI (percentage points)")
        ax.grid(axis="x", alpha=0.18)
        fig.text(
            0.06,
            0.13,
            "The meta pass rejected both revisions. The forced diagnostic uses the training-selected revision anyway.\n"
            "That diagnostic is exploratory; it does not represent native meta adoption. Both arms start from the same base.",
            fontsize=10,
            color="#4c5564",
        )
        for suffix in ("png", "svg"):
            fig.savefig(
                output / f"native-sequence-meta-diagnostic.{suffix}", dpi=180, facecolor="white"
            )
        plt.close(fig)
    return {
        "means_percent": means,
        "intervals_percent": [list(x) for x in bounds],
        "calls": calls,
        "input_output_tokens": token_counts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.report.read_bytes()
    report = json.loads(gzip.decompress(data) if args.report.suffix == ".gz" else data)
    result = render(report, json.loads(args.receipts.read_text()), args.output)
    print(json.dumps(result))
