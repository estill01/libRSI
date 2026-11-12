"""Render a measured benchmark report; requires matplotlib only for plotting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def plot(report_path: Path, output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    report = json.loads(report_path.read_text())
    scores, stages = report["scores"], report["stages"]
    colors = ["#9aaabd", "#187d97", "#7754bb"]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#b9c3d0",
            "text.color": "#172b45",
            "axes.labelcolor": "#172b45",
            "xtick.color": "#172b45",
            "ytick.color": "#172b45",
            "svg.fonttype": "none",
        }
    )
    figure, (quality, effort) = plt.subplots(
        1, 2, figsize=(12.4, 6.5), gridspec_kw={"width_ratios": [1.25, 1]}
    )
    figure.patch.set_facecolor("#f7f9fc")
    for ax in (quality, effort):
        ax.set_facecolor("#f7f9fc")
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#dce3eb", linewidth=0.7)
    keys = ["baseline", "ordinary", "enhanced"]
    values = [scores[key]["mrr_at_5"] for key in keys]
    quality.bar(range(3), values, color=colors, width=0.6, zorder=3)
    for i, value in enumerate(values):
        quality.text(i, value + 0.025, f"{value:.1%}", ha="center", weight="bold", fontsize=13)
    names = ["Original search", "Ordinary libRSI", "Meta-improved libRSI"]
    method_names = {"tf": "Raw TF", "logtf": "Log TF", "tfidf": "TF-IDF", "bm25": "BM25"}
    rankers = [
        "Raw TF",
        *[
            f"{method_names[stages[key]['configuration']['method']]} (title {stages[key]['configuration']['title_weight']})"
            for key in ("ordinary", "enhanced")
        ],
    ]
    quality.set_xticks(
        range(3),
        [
            f"{name}\n{ranker}\n{scores[key]['top_1']}/{scores[key]['queries']} top-1"
            for name, key, ranker in zip(names, keys, rankers, strict=True)
        ],
        fontsize=9,
    )
    quality.set_ylim(0, 1.08)
    quality.set_ylabel("MRR@5 on 300 official test queries (higher is better)")
    quality.yaxis.set_major_formatter(PercentFormatter(1))
    quality.set_title("Result quality", loc="left", fontsize=14, pad=16, weight="bold")
    quality.axhline(
        scores["fixed_bm25"]["mrr_at_5"],
        color="#b57a1c",
        linestyle="--",
        linewidth=1.4,
        label="Fixed BM25 control (no learning)",
    )
    quality.axhline(
        scores["training_sweep"]["mrr_at_5"],
        color="#435874",
        linestyle=":",
        linewidth=1.6,
        label="Full 6-configuration training sweep",
    )
    quality.legend(loc="upper left", bbox_to_anchor=(0, -0.25), frameon=False, fontsize=8.5)

    ordinary = stages["ordinary"]["ranked_queries"]
    inner = stages["enhanced"]["ranked_queries"]
    meta = stages["meta"]["ranked_queries"]
    effort.bar(
        [0, 1], [ordinary, inner], width=0.55, color=colors[1], label="Ordinary improvement pass"
    )
    effort.bar(1, meta, bottom=inner, width=0.55, color=colors[2], label="Additional meta pass")
    maximum = max(ordinary, inner + meta)
    for i, (count, seconds) in enumerate(
        [
            (ordinary, stages["ordinary"]["wall_seconds"]),
            (inner + meta, stages["enhanced"]["wall_seconds"] + stages["meta"]["wall_seconds"]),
        ]
    ):
        effort.text(
            i,
            count + maximum * 0.025,
            f"{count:,} queries\n{seconds:.1f}s elapsed",
            ha="center",
            fontsize=10,
            weight="bold",
        )
    effort.set_xticks([0, 1], ["Ordinary\nlibRSI", "Meta + ordinary\nlibRSI"])
    effort.set_ylim(0, maximum * 1.3)
    effort.set_ylabel("Query executions during adaptation (lower is cheaper)")
    effort.set_title("Measured effort", loc="left", fontsize=14, pad=16, weight="bold")
    effort.legend(loc="upper left", bbox_to_anchor=(0, -0.20), frameon=False, fontsize=8.5)
    figure.suptitle(
        "Improve search. Then improve what the search improver proposes.",
        x=0.06,
        y=0.97,
        ha="left",
        fontsize=16,
        weight="bold",
    )
    figure.text(
        0.06,
        0.91,
        f"BEIR SciFact · {report['documents']:,} scientific abstracts · two candidate slots per pass",
        fontsize=10,
        color="#50627a",
    )
    figure.text(
        0.06,
        0.865,
        "LLM / provider: NONE — ordinary proposer, meta-proposer and reviewer are fixed Python policies.",
        fontsize=10,
        color="#172b45",
        weight="bold",
    )
    figure.text(
        0.06,
        0.035,
        "One deterministic retrieval benchmark; fixed ranking algorithms and proposal policies. Meta uses 600 additional training queries.\nEffort includes repeated native checks, review, verification and persistence; excludes final scoring, controls, setup and plotting.",
        fontsize=8.5,
        color="#50627a",
    )
    figure.subplots_adjust(left=0.075, right=0.97, top=0.76, bottom=0.31, wspace=0.32)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output.with_suffix(".png"), dpi=180, facecolor=figure.get_facecolor())
    figure.savefig(output.with_suffix(".svg"), facecolor=figure.get_facecolor())
    svg = output.with_suffix(".svg")
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--output", required=True, type=Path, help="Output path stem for PNG and SVG"
    )
    args = parser.parse_args()
    plot(args.report, args.output)
