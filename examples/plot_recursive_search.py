"""Plot every final sample and the complete recursive effort allocation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def plot(report_path: Path, output: Path) -> None:
    report = json.loads(report_path.read_text())
    scores, stages = report["scores"], report["stages"]
    keys = ["ordinary", *(row["name"] for row in stages)]
    names = {
        "ordinary": "Ordinary",
        "meta": "Meta",
        "meta_meta": "Meta-meta",
        "meta_meta_meta": "Meta-meta-meta",
    }
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig, (quality, effort) = plt.subplots(
        1, 2, figsize=(15, 8), gridspec_kw={"width_ratios": [1.2, 1]}
    )
    fig.patch.set_facecolor("#f7f9fc")
    fig.suptitle(
        "Recursive improvement with five independent model samples",
        x=0.06,
        y=0.96,
        ha="left",
        fontsize=20,
        fontweight="bold",
        color="#14243a",
    )
    fig.text(
        0.06,
        0.885,
        f"Every reasoning role: OpenAI {report['model']} · {report['reasoning_effort']} reasoning · Codex CLI\n"
        "Target: lexical search (no query-time LLM) · Reviewer: deterministic Python · 300 SciFact test queries",
        va="top",
        fontsize=11,
        color="#394d65",
        linespacing=1.6,
    )
    colors = ["#a4afc0", "#3e70c9", "#008b7d", "#7658b5", "#bd7142"]
    values = [
        100 * report["term_count_baseline"]["mrr_at_5"],
        *[100 * scores[key]["mrr_at_5"]["mean"] for key in keys],
    ]
    deviations = [0, *[100 * scores[key]["mrr_at_5"]["sample_sd"] for key in keys]]
    xs = np.arange(len(values))
    quality.bar(xs, values, color=colors[: len(values)], width=0.61, alpha=0.65)
    quality.errorbar(
        xs[1:],
        values[1:],
        yerr=deviations[1:],
        fmt="none",
        color="#14243a",
        capsize=5,
        linewidth=1.5,
    )
    for i, key in enumerate(keys, 1):
        samples = scores[key]["mrr_at_5"]["samples"]
        quality.scatter(
            i + np.linspace(-0.16, 0.16, len(samples)),
            100 * np.array(samples),
            color=colors[i],
            edgecolor="#14243a",
            s=27,
            linewidth=0.5,
            zorder=4,
        )
        if key != "ordinary":
            control = scores["ordinary" if key == "meta" else f"{key}_default"]["mrr_at_5"]["mean"]
            quality.scatter(
                i + 0.34,
                100 * control,
                marker="D",
                color="#657080",
                s=38,
                zorder=5,
                label="Default pipeline at same depth" if key == "meta" else None,
            )
    for i, value in enumerate(values):
        quality.text(
            i,
            value + deviations[i] + 2,
            f"{value:.1f}",
            ha="center",
            fontsize=12,
            fontweight="bold",
        )
    labels = ["Original\nterm counts", "Ordinary\nLLM proposer"]
    labels += [
        f"{names[row['name']]}\n{'adopted' if row['adopted'] else 'no change'}" for row in stages
    ]
    quality.set_xticks(xs, labels, fontsize=9)
    quality.set_ylim(0, 100)
    quality.set_ylabel("MRR@5 × 100 (higher is better)")
    quality.set_title(
        "Quality: all five samples, mean ± sample SD", loc="left", pad=18, fontweight="bold"
    )
    quality.legend(loc="upper left", frameon=False, fontsize=9)
    quality.grid(axis="y", alpha=0.14)
    quality.set_axisbelow(True)

    cumulative_calls, cumulative_tokens = 0, 0
    calls, tokens = [], []
    for i, key in enumerate(keys):
        if i:
            stage = stages[i - 1]
            cumulative_calls += stage["model_calls"]
            cumulative_tokens += (
                stage["model_usage"]["input_tokens"] + stage["model_usage"]["output_tokens"]
            )
        sample_key = scores[key]["sample_key"][:12]
        receipts = [row for row in report["model_receipts"] if f":{sample_key}:" in row["role"]]
        calls.append(cumulative_calls + len(receipts))
        tokens.append(
            cumulative_tokens
            + sum(u["input_tokens"] + u["output_tokens"] for row in receipts for u in row["usage"])
        )
    effort.bar(range(len(keys)), calls, color=colors[1 : len(keys) + 1], width=0.58)
    for i, count in enumerate(calls):
        effort.text(
            i,
            count + max(calls) * 0.025,
            f"{count} calls\n{tokens[i] / 1000:.0f}k tokens",
            ha="center",
            fontsize=10,
        )
    effort.set_xticks(range(len(keys)), [names[key] for key in keys], fontsize=9)
    effort.set_ylim(0, max(calls) * 1.25)
    effort.set_ylabel("Cumulative optimization + five final samples (model calls)")
    effort.set_title(
        "Effort: include every preceding meta level", loc="left", pad=18, fontweight="bold"
    )
    effort.grid(axis="y", alpha=0.14)
    effort.set_axisbelow(True)
    e = report["effort"]
    fig.text(
        0.06,
        0.13,
        "Dots: independent model samples, not independent datasets. Identical unchanged policies share frozen samples.\n"
        f"Total run including controls: {e['model_calls']} model calls · {e['total_wall_seconds'] / 60:.1f} min elapsed · up to 3 concurrent inference calls.\n"
        "Comparison bars share earlier work; do not sum them. Dollar billing unavailable with subscription credentials; not zero cost.",
        fontsize=10,
        color="#394d65",
        linespacing=1.6,
    )
    fig.subplots_adjust(left=0.065, right=0.975, top=0.72, bottom=0.29, wspace=0.3)
    output.parent.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg"):
        path = output.with_suffix(f".{extension}")
        fig.savefig(path, dpi=180, facecolor=fig.get_facecolor())
        if extension == "svg":
            path.write_text(
                "\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n"
            )
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.report, args.output)
