"""Render the measured LLM benchmark; all plotted values come from its report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def plot(report_path: Path, output: Path) -> None:
    report = json.loads(report_path.read_text())
    stages, scores = report["stages"], report["scores"]
    model = report["model"]["ordinary_proposer"]
    if any(report["model"][role] != model for role in ("meta_proposer", "meta_inner_proposer")):
        raise ValueError("update role labels for a mixed-model run")
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig, (quality, effort) = plt.subplots(
        1, 2, figsize=(13, 7), gridspec_kw={"width_ratios": [1.1, 1]}
    )
    fig.patch.set_facecolor("#f7f9fc")
    adopted = stages["meta"]["adopted"]
    fig.suptitle(
        "LLM-driven search: testing changes to the improver"
        if adopted
        else "LLM-driven search: the meta attempt did not earn adoption",
        x=0.06,
        y=0.96,
        ha="left",
        fontsize=19,
        fontweight="bold",
        color="#14243a",
    )
    fig.text(
        0.06,
        0.885,
        f"Ordinary + meta LLM: OpenAI {model} · reasoning: high · Codex CLI\n"
        "Search target: lexical formulas (no LLM at query time) · Reviewer: deterministic Python",
        fontsize=11,
        color="#394d65",
        linespacing=1.6,
        va="top",
    )
    keys = ["baseline", "ordinary", "post_meta"]
    values = [100 * scores[key]["mrr_at_5"] for key in keys]
    colors = ["#a4afc0", "#3e70c9", "#008b7d"]
    quality.bar(range(3), values, color=colors, width=0.64)
    quality.set_xticks(
        range(3),
        [
            "Original\nterm counts",
            "Ordinary\nLLM proposals",
            "After meta\nLLM proposals" if adopted else "After meta attempt\nsame instructions",
        ],
    )
    quality.set_ylim(0, 100)
    quality.set_ylabel("MRR@5 × 100 (higher is better)")
    quality.set_title("Quality on 300 official test queries", loc="left", pad=20, fontweight="bold")
    quality.grid(axis="y", alpha=0.14)
    quality.set_axisbelow(True)
    for i, key in enumerate(keys):
        quality.text(
            i, values[i] + 2, f"{values[i]:.1f}", ha="center", fontweight="bold", fontsize=17
        )
        quality.text(
            i,
            max(values[i] / 2, 3),
            f"{scores[key]['top_1']}/300 top-1",
            ha="center",
            va="center",
            color="white" if i else "#14243a",
            fontsize=9,
        )
    control = 100 * scores["fixed_bm25"]["mrr_at_5"]
    quality.axhline(control, color="#9b5d25", linestyle="--", linewidth=1.4)
    quality.text(
        0.02,
        control + 2,
        f"Fixed BM25 + title bonus: {control:.1f}",
        transform=quality.get_yaxis_transform(),
        color="#8a4f1a",
        fontsize=9,
    )
    ordinary = stages["ordinary"]["model_usage"]
    after = stages["post_meta"]["model_usage"]
    meta = stages["meta"]["model_usage"]
    # Cached input tokens are a subset of input tokens, not an extra charge.
    ordinary_tokens = ordinary.get("input_tokens", 0) + ordinary.get("output_tokens", 0)
    after_tokens = after.get("input_tokens", 0) + after.get("output_tokens", 0)
    meta_tokens = meta.get("input_tokens", 0) + meta.get("output_tokens", 0)
    effort.bar(
        [0, 1],
        [ordinary_tokens / 1000, after_tokens / 1000],
        color="#3e70c9",
        width=0.55,
        label="Downstream improvement",
    )
    effort.bar(
        1,
        meta_tokens / 1000,
        bottom=after_tokens / 1000,
        color="#008b7d",
        width=0.55,
        label="Meta step (includes inner model calls)",
    )
    effort.set_xticks([0, 1], ["Ordinary", "Meta + downstream"])
    effort.set_ylabel("Reported input + output tokens (thousands)")
    effort.set_title("Effort, including the meta step", loc="left", pad=20, fontweight="bold")
    effort.set_ylim(0, max(ordinary_tokens, after_tokens + meta_tokens) / 1000 * 1.32)
    effort.grid(axis="y", alpha=0.14)
    effort.set_axisbelow(True)
    for i, names in enumerate([["ordinary"], ["meta", "post_meta"]]):
        count = sum(stages[name]["model_calls"] for name in names)
        seconds = sum(stages[name]["wall_seconds"] for name in names)
        tokens = ordinary_tokens if i == 0 else after_tokens + meta_tokens
        effort.text(
            i,
            tokens / 1000 + effort.get_ylim()[1] * 0.03,
            f"{count} model {'call' if count == 1 else 'calls'}\n{seconds / 60:.1f} min elapsed",
            ha="center",
            fontsize=10,
        )
    effort.legend(loc="upper left", frameon=False, fontsize=9)
    disposition = "adopted" if stages["meta"]["adopted"] else "not adopted"
    fig.text(
        0.06,
        0.09,
        f"Meta instructions: {disposition}. One stochastic run; equal downstream budget: 2 proposals each.\n"
        "Meta has extra data and compute. Dollar cost unavailable with subscription credentials; not zero cost.\n"
        "Source: BEIR SciFact · 5,183 abstracts · frozen strategies before final test scoring.",
        fontsize=10,
        color="#394d65",
        linespacing=1.6,
    )
    fig.subplots_adjust(left=0.07, right=0.97, top=0.72, bottom=0.25, wspace=0.34)
    output.parent.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg"):
        target = output.with_suffix(f".{extension}")
        fig.savefig(target, dpi=180, facecolor=fig.get_facecolor())
        if extension == "svg":
            target.write_text(
                "\n".join(line.rstrip() for line in target.read_text().splitlines()) + "\n"
            )
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.report, args.output)
