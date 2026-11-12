"""Plot frozen scheduling results, uncertainty and model-call effort."""

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
    keys = ["ordinary", "revised", "equal_calls"]
    adopted = report["frozen_policies"]["native_adopted"]
    revision = "Adopted revision" if adopted else "Proposed revision"
    names = ["Original\ninstructions", revision.replace(" ", "\n", 1), "Original\nsame call budget"]
    colors = ["#4d77b9", "#078879", "#9b6fbd"]
    metric = report["model_plan"]["metric"]
    metric_label = (
        "Setup cost saved (%)" if metric == "cost_reduction" else "Optimal / actual cost (%)"
    )
    threshold = 100 * report["model_plan"]["minimum_effect"]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig = plt.figure(figsize=(15, 9), facecolor="#f7f9fc")
    grid = fig.add_gridspec(2, 2, width_ratios=[1.15, 1], height_ratios=[1, 0.65])
    quality = fig.add_subplot(grid[:, 0])
    contrast = fig.add_subplot(grid[0, 1])
    effort = fig.add_subplot(grid[1, 1])
    fig.suptitle(
        "Does improving the improver pay off?",
        x=0.065,
        y=0.965,
        ha="left",
        fontsize=23,
        fontweight="bold",
        color="#14243a",
    )
    fig.text(
        0.065,
        0.905,
        f"Every reasoning role: OpenAI {report['protocol']['model']} · high reasoning · Codex CLI\n"
        "32 model draws per arm · 128 unseen synthetic scheduling workloads · 256 search evaluations per program",
        fontsize=11,
        color="#394d65",
        linespacing=1.7,
        va="top",
    )
    samples = [100 * np.asarray(report["scores"][key]).mean(axis=1) for key in keys]
    means = [float(values.mean()) for values in samples]
    quality.bar(range(3), means, color=colors, alpha=0.55, width=0.65)
    for i, values in enumerate(samples):
        quality.scatter(
            i + np.linspace(-0.19, 0.19, len(values)),
            values,
            c=colors[i],
            s=27,
            edgecolors="#14243a",
            linewidths=0.35,
            zorder=3,
        )
        quality.text(i, max(values) + 0.4, f"{means[i]:.2f}", ha="center", fontweight="bold")
    baseline = 100 * np.mean(report["baseline_scores"])
    quality.axhline(
        baseline,
        color="#667487",
        linestyle="--",
        linewidth=1,
        label=f"Starting planner: {baseline:.1f}",
    )
    quality.set_xticks(range(3), names)
    quality.set_ylabel(metric_label)
    quality.set_ylim(0, max(max(v) for v in samples) * 1.2 + 1)
    quality.set_title(
        "Candidate performance; dots are all 32 draws", loc="left", pad=16, fontweight="bold"
    )
    quality.legend(frameon=False, loc="upper left", fontsize=9)

    for y, key in enumerate(("ordinary", "equal_calls")):
        row = report["contrasts"][key]
        lo, hi = 100 * np.asarray(row["bootstrap_97_5_percentile"])
        mean = 100 * row["mean_effect"]
        contrast.hlines(y, lo, hi, colors="#078879", linewidth=3)
        contrast.plot(mean, y, "o", color="#078879", markersize=8)
        contrast.text(
            mean, y + 0.14, f"{mean:+.2f} [{lo:+.2f}, {hi:+.2f}]", ha="center", fontsize=9
        )
    contrast.axvline(0, color="#667487", linewidth=1)
    contrast.axvline(
        threshold,
        color="#bf7136",
        linestyle="--",
        linewidth=1.2,
        label=f"Worthwhile gain: +{threshold:g} points",
    )
    contrast.set_yticks([0, 1], ["vs ordinary", "vs same calls"])
    contrast.set_ylim(-0.35, 1.7)
    contrast.set_xlabel("Revision's additional gain (percentage points)")
    contrast.set_title(
        "Held-out effect with adjusted uncertainty", loc="left", pad=16, fontweight="bold"
    )
    contrast.legend(frameon=False, loc="upper right", fontsize=9)

    e = report["effort"]
    calls = [
        e["ordinary_confirmation_calls"],
        e["meta_plus_confirmation_total"],
        e["equal_call_original_total"],
    ]
    effort.bar(range(3), calls, color=colors, width=0.65)
    for i, count in enumerate(calls):
        effort.text(i, count + 4, str(count), ha="center", fontweight="bold")
    effort.set_xticks(range(3), ["Ordinary", "Meta + reuse", "Original control"])
    effort.set_ylim(0, max(calls) * 1.25)
    effort.set_ylabel("Astra calls")
    effort.set_title("Effort includes meta development", loc="left", pad=12, fontweight="bold")
    for axis in (quality, contrast, effort):
        axis.grid(axis="y", alpha=0.13)
        axis.set_axisbelow(True)
    fig.text(
        0.065,
        0.135,
        f"Native meta decision: {report['frozen_policies']['native_disposition']}. "
        + (
            "Revision became active."
            if adopted
            else "Revision tested separately; active instructions stayed unchanged."
        )
        + "\nIntervals: crossed bootstrap over model draws and workloads; 97.5% per contrast, nominal 95% across two contrasts.\n"
        f"Native engine decisions: {report['ordinary_native']['disposition']} before meta; {report['transfer_native']['disposition']} after meta.\n"
        f"Complete run: {e['model_calls']} calls · {e['input_output_tokens']:,} reported input/output tokens · "
        f"{e['total_wall_seconds'] / 60:.1f} min. Dollar billing unavailable.\n"
        "Call bars share original samples and exclude 3 common/demo calls; do not sum. Calls, not tokens or wall time, are matched.",
        fontsize=10,
        color="#394d65",
        linespacing=1.65,
        va="top",
    )
    fig.subplots_adjust(left=0.065, right=0.98, top=0.77, bottom=0.24, wspace=0.34, hspace=0.72)
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
