"""Measure ordinary improvement and improvement of its proposal policy.

Run from an installed source checkout:
    python examples/benchmark_document_search.py --dataset /path/to/scifact.zip --output /path/to/fresh-directory

All three passes use the real libRSI AdaptiveLoop. The outer pass measures a
cheap proposal-utility proxy; transfer is tested through a new native inner pass.
The official 300 test questions are evaluated only after all strategy choices are frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from document_search import (
    BASE_PROPOSER,
    BASE_RANKER,
    MINIMUM_EFFECT,
    PORTFOLIOS,
    PortfolioProposer,
    ProposalAdapter,
    SearchAdapter,
    SearchIndex,
    SearchProposer,
)
from scifact_data import load as load_data

from librsi import (
    Action,
    ActionResult,
    AdaptiveLoop,
    CandidateReview,
    LearningCase,
    LearningPolicy,
    LocalLearningStore,
    Metric,
    make_review_result,
    review_command_from_action,
)
from librsi.identity import canonical_json

HERE = Path(__file__).resolve().parent


def write_json(path: Path, value: Any) -> None:
    path.write_text(canonical_json(value) + "\n")


def cases(rows: Sequence[str], prefix: str, *, meta: bool) -> tuple[LearningCase, ...]:
    if len(rows) % 4:
        raise ValueError("each split must divide into four equal task batches")
    width = len(rows) // 4
    batches = [rows[i : i + width] for i in range(0, len(rows), width)]
    if meta:
        return tuple(
            LearningCase(
                f"{prefix}-{i}",
                {
                    "tuning": batch[: len(batch) // 2],
                    "scoring": batch[len(batch) // 2 :],
                },
            )
            for i, batch in enumerate(batches)
        )
    return tuple(
        LearningCase(f"{prefix}-{i}", {"queries": batch}) for i, batch in enumerate(batches)
    )


class MeasuredReviewer:
    """Separate deterministic review callback; not an independent human assessment."""

    def review(self, action: Action) -> ActionResult:
        command = review_command_from_action(action)
        passed = command.evaluation.disposition == "passed"
        return make_review_result(
            action=action,
            review=CandidateReview(
                review_id=f"{action.action_id}:review",
                reviewer_id="search-measured-review-v1",
                candidate=command.candidate,
                experiment=command.experiment,
                evaluation=command.evaluation,
                disposition="accepted" if passed else "rejected",
                findings=("Fresh shadow measurements pass" if passed else "Criterion failed",),
                lineage=(command.candidate.ref, command.experiment.ref, command.evaluation.ref),
            ),
        )


def make_loop(
    store: LocalLearningStore, index: SearchIndex, policy: Mapping[str, Any], *, meta: bool
) -> AdaptiveLoop:
    return AdaptiveLoop(
        store,
        adapter=ProposalAdapter(index) if meta else SearchAdapter(index),
        proposer=PortfolioProposer() if meta else SearchProposer(policy),
        proposer_id="search-portfolio-proposer-v1"
        if meta
        else f"search-proposer-v1:{policy['portfolio']}",
        reviewer=MeasuredReviewer(),
        reviewer_id="search-measured-review-v1",
        policy=LearningPolicy(
            objective="Increase paired MRR@5 lift over the fixed reference on the same queries",
            metric=Metric(
                metric_id="paired-mrr-at-5-lift", direction="increase", unit="reciprocal-rank"
            ),
            minimum_effect=MINIMUM_EFFECT,
            max_feedback=4,
            max_cases=4,
            max_candidates=2,
            history_limit=0,
        ),
    )


def run_pass(
    output: Path,
    name: str,
    index: SearchIndex,
    splits: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    meta: bool = False,
) -> dict[str, Any]:
    print(f"Running {name}...", flush=True)
    started, cpu = perf_counter(), process_time()
    queries_before, measurements_before = index.ranked_queries, index.measurements
    adapter_calls_before = index.adapter_evaluations
    initial = BASE_PROPOSER if meta else BASE_RANKER
    prefix = "meta" if meta else "ordinary"
    directory = output / name
    with LocalLearningStore(directory, profile_id=name, initial_configuration=initial) as store:
        loop = make_loop(store, index, policy, meta=meta)
        feedback = [
            loop.run_task(case) for case in cases(splits[f"{prefix}_train"], "train", meta=meta)
        ]
        result = loop.learn(
            "improve-1",
            shadow_cases=cases(splits[f"{prefix}_shadow"], "shadow", meta=meta),
            verification_cases=cases(splits[f"{prefix}_verification"], "verification", meta=meta),
            activate=True,
        )
        if result is None or store.pending_pass is not None:
            raise RuntimeError(f"{name} did not settle: inspect retained store before continuing")
        strategy = store.active
        if strategy != result.strategy_after:
            raise RuntimeError("result and actual active strategy differ")
        native = result.native.to_dict()
        write_json(
            output / f"{name}-evidence.json",
            {
                "feedback": [row.to_dict() for row in feedback],
                "native_result": native,
                "strategy": strategy.to_dict(),
            },
        )
    # Reopen durable state before returning the configuration to its actual consumer.
    with LocalLearningStore(directory, profile_id=name) as store:
        if store.active != strategy:
            raise RuntimeError("active strategy did not survive store reopen")
        configuration = dict(store.active.state)
    report = {
        "name": name,
        "configuration": configuration,
        "disposition": result.disposition,
        "adopted": result.adopted,
        "strategy_root": strategy.root,
        "native_result_root": result.native.root,
        "candidate_budget": 2,
        "ranked_queries": index.ranked_queries - queries_before,
        "scoring_batches": index.measurements - measurements_before,
        "adapter_evaluations": index.adapter_evaluations - adapter_calls_before,
        "proposer_configuration": dict(policy)
        if not meta
        else {"portfolio": "outer-fixed-hypotheses"},
        "wall_seconds": perf_counter() - started,
        "cpu_seconds": process_time() - cpu,
        "evidence": f"{name}-evidence.json",
    }
    write_json(output / f"{name}-summary.json", report)
    print(json.dumps(report), flush=True)
    return report


def score_active(
    output: Path,
    stage: Mapping[str, Any],
    index: SearchIndex,
    policy: Mapping[str, Any],
    test_queries: Sequence[str],
) -> dict[str, Any]:
    name = stage["name"]
    with LocalLearningStore(output / name, profile_id=name) as store:
        loop = make_loop(store, index, policy, meta=False)
        observations = [
            loop.run_task(case) for case in cases(test_queries, "final-test", meta=False)
        ]
        if any(
            row.target_snapshot is None or row.target_snapshot.root != stage["strategy_root"]
            for row in observations
        ):
            raise RuntimeError("ordinary test task did not consume the verified strategy")
        raw = index.measure(stage["configuration"], index.resolve(test_queries))
        measured_mrr = sum(row.value["output"]["mrr_at_5"] for row in observations) / len(
            observations
        )
        if abs(measured_mrr - raw.value) > 1e-12:
            raise RuntimeError("fresh final rankings differ from actual ordinary task measurements")
        write_json(output / f"{name}-test-evidence.json", [row.to_dict() for row in observations])
    return summarize(raw.output["queries"])


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "mrr_at_5": sum(row["reciprocal_rank"] for row in rows) / len(rows),
        "top_1": sum(row["reciprocal_rank"] == 1 for row in rows),
        "queries": len(rows),
        "per_query": [dict(row) for row in rows],
    }


def provenance() -> dict[str, Any]:
    root = HERE.parent
    source_paths = sorted((root / "src/librsi").rglob("*.py"))
    runtime = hashlib.sha256()
    for path in source_paths:
        runtime.update(
            path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0"
        )
    paths = [
        HERE / "document_search.py",
        Path(__file__),
        HERE / "scifact_data.py",
        HERE / "data/scifact-split.json",
    ]
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    return {
        "checkout_revision": revision,
        "files_sha256": {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
        "runtime_python_sha256": runtime.hexdigest(),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def run(output: Path, dataset_path: Path) -> dict[str, Any]:
    started, cpu = perf_counter(), process_time()
    output.mkdir(parents=True, exist_ok=False)
    corpus, dataset = load_data(dataset_path)
    identity = provenance()
    write_json(output / "input-manifest.json", identity)
    index = SearchIndex(corpus["documents"], dataset["queries"])
    splits = dataset["splits"]
    write_json(
        output / "split-manifest.json",
        {"archive_sha256": dataset["archive_sha256"], "seed": dataset["seed"], "splits": splits},
    )
    ordinary = run_pass(output, "ordinary", index, splits, BASE_PROPOSER)
    meta = run_pass(output, "meta", index, splits, BASE_PROPOSER, meta=True)
    enhanced = run_pass(output, "enhanced", index, splits, meta["configuration"])
    # Do not access final judgments until both consumer strategies are committed.
    write_json(
        output / "frozen-strategies.json",
        {"ordinary": ordinary, "meta": meta, "enhanced": enhanced},
    )
    adaptation_queries = index.ranked_queries
    test_queries = index.resolve(splits["test"])
    baseline = index.measure(BASE_RANKER, test_queries)
    scores = {"baseline": summarize(baseline.output["queries"])}
    scores["ordinary"] = score_active(output, ordinary, index, BASE_PROPOSER, splits["test"])
    scores["enhanced"] = score_active(
        output, enhanced, index, meta["configuration"], splits["test"]
    )

    # Controls share the frozen test set. They never influence libRSI selection.
    fixed = {"method": "bm25", "title_weight": 2}
    scores["fixed_bm25"] = summarize(index.measure(fixed, test_queries).output["queries"])
    unique = {canonical_json(item): item for portfolio in PORTFOLIOS.values() for item in portfolio}
    sweep = [BASE_RANKER, *unique.values()]
    sweep_before = index.ranked_queries
    sweep_training = [
        index.measure(item, index.resolve(splits["ordinary_train"])).value for item in sweep
    ]
    sweep_best = max(range(len(sweep)), key=lambda i: sweep_training[i])
    sweep_queries = index.ranked_queries - sweep_before
    scores["training_sweep"] = summarize(
        index.measure(sweep[sweep_best], test_queries).output["queries"]
    )
    report = {
        "schema": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "provenance": identity,
        "corpus_revision": corpus["source_revision"],
        "documents": len(corpus["documents"]),
        "split_counts": {key: len(value) for key, value in splits.items()},
        "stages": {"ordinary": ordinary, "meta": meta, "enhanced": enhanced},
        "scores": scores,
        "controls": {
            "fixed_bm25": fixed,
            "training_sweep": {
                "configuration": sweep[sweep_best],
                "configurations": len(sweep),
                "tuning_ranked_queries": sweep_queries,
                "training_mrr": sweep_training,
            },
        },
        "effort": {
            "adaptation_ranked_queries": adaptation_queries,
            "reporting_and_controls_ranked_queries": index.ranked_queries - adaptation_queries,
            "total_ranked_queries": index.ranked_queries,
            "model_calls": 0,
            "provider_cost_usd": 0,
            "total_wall_seconds": perf_counter() - started,
            "total_cpu_seconds": process_time() - cpu,
            "scope": "From run() entry through all native passes, durable reopen, final tasks and controls; includes evidence writes, excludes imports, environment setup, final report serialization and plotting. Provider cost excludes machine and authoring cost. Query counts include repeated native measurements.",
        },
        "limitations": [
            "BEIR SciFact official test set; one deterministic run, not a general benchmark of libRSI or a comparison to published retrieval systems.",
            "Fixed deterministic engineering proposals; no LLM, weight training, library code rewriting or autonomous discovery of retrieval algorithms.",
            "The outer pass optimizes a proposal-utility proxy; only the final transfer uses native inner passes.",
            "All modes share the corpus and downstream training/shadow/verification splits. Meta training queries are separate, but the meta arm has additional data and computation.",
            "One run on one corpus; timings are machine dependent. No statistical or cross-domain improvement claim.",
        ],
    }
    write_json(output / "report.json", report)
    print(
        json.dumps(
            {
                key: {k: v for k, v in value.items() if k != "per_query"}
                for key, value in scores.items()
            },
            indent=2,
        ),
        flush=True,
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for reports and native stores"
    )
    parser.add_argument(
        "--dataset", type=Path, required=True, help="Pinned BEIR SciFact ZIP archive"
    )
    args = parser.parse_args()
    run(args.output, args.dataset)
