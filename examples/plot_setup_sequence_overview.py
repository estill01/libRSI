"""Show the base, ordinary LLM optimization and meta-optimized LLM comparison."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def plot(report_path: Path, output: Path) -> None:
    data = report_path.read_bytes()
    report = json.loads(gzip.decompress(data) if report_path.suffix == ".gz" else data)
    if report["model_plan"]["metric"] != "cost_reduction":
        raise ValueError("This overview requires the setup-cost reduction metric")
    original = 100 * np.asarray(report["scores"]["ordinary"]).mean(axis=1)
    meta = 100 * np.asarray(report["scores"]["revised"]).mean(axis=1)
    baseline = float(100 * np.mean(report["baseline_scores"]))
    assert original.shape == meta.shape == (32,)
    values = [baseline, float(original.mean()), float(meta.mean())]
    colors = ["#8793a5", "#3e70b4", "#008779"]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig, axis = plt.subplots(figsize=(13, 8.2), facecolor="#f7f9fc")
    fig.suptitle(
        "Base → libRSI optimization → meta-optimized libRSI",
        x=0.07,
        y=0.965,
        ha="left",
        fontsize=20,
        fontweight="bold",
        color="#14243a",
    )
    fig.text(
        0.07,
        0.903,
        "Both optimization cases restart from the same base planner. Meta changes the improver.\n"
        f"LLM at both levels: OpenAI {report['protocol']['model']} · {report['protocol']['reasoning_effort']} reasoning",
        va="top",
        color="#394d65",
        linespacing=1.7,
    )
    axis.bar(
        range(3),
        values,
        width=0.58,
        facecolor="white",
        edgecolor=colors,
        linewidth=2,
        hatch="//",
        zorder=2,
    )
    axis.scatter([0], [baseline], color=colors[0], s=45, zorder=3, clip_on=False)
    for i, samples in enumerate((original, meta), 1):
        axis.scatter(
            i + np.linspace(-0.17, 0.17, len(samples)),
            samples,
            c=colors[i],
            s=25,
            edgecolors="white",
            linewidths=0.4,
            zorder=3,
        )
    for i, value in enumerate(values):
        top = [baseline, float(max(original)), float(max(meta))][i]
        axis.text(
            i,
            top + 0.3,
            f"{value:.2f}%",
            ha="center",
            fontsize=19,
            fontweight="bold",
            color=colors[i],
        )
    axis.set_xticks(
        range(3),
        [
            "1. Base case\nExisting planner",
            "2. libRSI optimizes base\nOriginal LLM improver",
            "3. Meta optimizes improver\nRevised LLM improver optimizes base",
        ],
    )
    axis.tick_params(axis="x", length=0, pad=14)
    axis.set_ylim(0, max(max(original), max(meta), baseline) * 1.2 + 0.6)
    axis.set_ylabel("Setup cost saved versus the base (%)")
    axis.set_title(
        "Candidate output quality — not adopted changes", loc="left", pad=18, fontweight="bold"
    )
    axis.grid(axis="y", alpha=0.15)
    axis.set_axisbelow(True)
    for i, text in enumerate(
        (
            "No optimization LLM",
            "32 fresh Astra calls",
            "97 meta-development + 32 fresh Astra calls",
        )
    ):
        axis.text(
            i,
            -0.23,
            text,
            transform=axis.get_xaxis_transform(),
            ha="center",
            fontsize=10,
            color="#394d65",
        )
    unchanged = all(
        json.loads(report[key]["configuration"]["program"])["stages"] == []
        for key in ("ordinary_native", "transfer_native")
    )
    status = (
        "Actual native outcome: the base planner remained active. The proposed meta revision was not adopted."
        if unchanged and not report["frozen_policies"]["native_adopted"]
        else f"Native outcomes: ordinary {report['ordinary_native']['disposition']}; after meta {report['transfer_native']['disposition']}."
    )
    fig.text(0.07, 0.12, status, color="#8b4d1f", fontweight="bold", fontsize=10)
    effect = report["contrasts"]["ordinary"]
    lo, hi = 100 * np.asarray(effect["bootstrap_97_5_percentile"])
    fig.text(
        0.07,
        0.082,
        f"Meta's extra candidate gain: {100 * effect['mean_effect']:+.2f} points; adjusted interval [{lo:+.2f}, {hi:+.2f}].\n"
        "32 separate proposal draws per optimization case · 128 unseen workloads · same 256-evaluation program budget.\n"
        "Stage 3 tests the proposed revision separately after its rejection; it does not show successful native meta adoption.",
        fontsize=9.5,
        color="#394d65",
        linespacing=1.5,
        va="top",
    )
    fig.subplots_adjust(left=0.07, right=0.98, top=0.72, bottom=0.32)
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
