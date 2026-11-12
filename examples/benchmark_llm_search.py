"""Run ordinary LLM improvement, LLM meta improvement, and measured transfer.

Requires an authenticated Codex CLI and libRSI's development dependencies.
One run only; no automatic retries, model changes, or reruns after viewing test results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from benchmark_document_search import MeasuredReviewer, cases, provenance, summarize, write_json
from llm_search import (
    BASE_FORMULA,
    BASE_INSTRUCTIONS,
    CodexSampler,
    FormulaAdapter,
    FormulaIndex,
    FormulaProposer,
    InstructionAdapter,
    InstructionProposer,
)
from scifact_data import load

from librsi import AdaptiveLoop, LearningCase, LearningPolicy, LocalLearningStore, Metric


def meta_cases(ids: list[str], prefix: str) -> tuple[LearningCase, ...]:
    if len(ids) != 200:
        raise ValueError("expected the frozen 200-query meta partition")
    return tuple(
        LearningCase(
            f"{prefix}-{i}",
            {"tuning": ids[i * 100 : i * 100 + 50], "scoring": ids[i * 100 + 50 : (i + 1) * 100]},
        )
        for i in range(2)
    )


def loop_for(
    store: LocalLearningStore,
    index: FormulaIndex,
    sampler: CodexSampler,
    instruction: Mapping[str, Any],
    name: str,
    *,
    meta: bool = False,
) -> AdaptiveLoop:
    return AdaptiveLoop(
        store,
        adapter=InstructionAdapter(index, sampler) if meta else FormulaAdapter(index),
        proposer=InstructionProposer(sampler)
        if meta
        else FormulaProposer(sampler, index, instruction, name),
        proposer_id=f"llm-search:{sampler.model}:{name}",
        reviewer=MeasuredReviewer(),
        reviewer_id="search-measured-review-v1",
        policy=LearningPolicy(
            objective="Increase paired held-out MRR@5 lift over the fixed baseline",
            metric=Metric(
                metric_id="paired-mrr-at-5-lift", direction="increase", unit="reciprocal-rank"
            ),
            minimum_effect=0.01,
            max_feedback=2 if meta else 4,
            max_cases=2 if meta else 4,
            max_candidates=2,
            history_limit=0,
        ),
    )


def usage_total(receipts: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for receipt in receipts:
        for usage in receipt.get("usage", []):
            for key, value in usage.items():
                result[key] = result.get(key, 0) + value
    return result


def run_stage(
    output: Path,
    name: str,
    index: FormulaIndex,
    sampler: CodexSampler,
    splits: Mapping[str, Any],
    instructions: Mapping[str, Any],
    *,
    meta: bool = False,
) -> dict[str, Any]:
    print(f"Starting {name}", flush=True)
    started, cpu = perf_counter(), process_time()
    calls, rankings, evaluations = (
        len(sampler.receipts),
        index.ranked_queries,
        index.adapter_evaluations,
    )
    prefix = "meta" if meta else "ordinary"
    partitions = {
        part: meta_cases(splits[f"{prefix}_{part}"], part)
        if meta
        else cases(splits[f"{prefix}_{part}"], part, meta=False)
        for part in ("train", "shadow", "verification")
    }
    with LocalLearningStore(
        output / name,
        profile_id=name,
        initial_configuration=BASE_INSTRUCTIONS if meta else BASE_FORMULA,
    ) as store:
        loop = loop_for(store, index, sampler, instructions, name, meta=meta)
        feedback = [loop.run_task(case) for case in partitions["train"]]
        result = loop.learn(
            "improve-1",
            shadow_cases=partitions["shadow"],
            verification_cases=partitions["verification"],
            activate=True,
        )
        if (
            result is None
            or store.pending_pass is not None
            or store.active != result.strategy_after
        ):
            raise RuntimeError(
                "native pass did not settle consistently; retain and inspect evidence"
            )
        strategy = store.active
        write_json(
            output / f"{name}-evidence.json",
            {
                "feedback": [row.to_dict() for row in feedback],
                "native_result": result.native.to_dict(),
                "strategy": strategy.to_dict(),
            },
        )
    with LocalLearningStore(output / name, profile_id=name) as store:
        if store.active != strategy:
            raise RuntimeError("durable active strategy differs")
    stage = {
        "name": name,
        "configuration": dict(strategy.state),
        "strategy_root": strategy.root,
        "native_result_root": result.native.root,
        "disposition": result.disposition,
        "adopted": result.adopted,
        "proposer_instructions": dict(instructions),
        "candidate_budget": 2,
        "model_calls": len(sampler.receipts) - calls,
        "model_usage": usage_total(sampler.receipts[calls:]),
        "provider_cost_usd": None,
        "ranked_queries": index.ranked_queries - rankings,
        "adapter_evaluations": index.adapter_evaluations - evaluations,
        "wall_seconds": perf_counter() - started,
        "cpu_seconds": process_time() - cpu,
    }
    write_json(output / f"{name}-summary.json", stage)
    write_json(output / "model-receipts.json", sampler.receipts)
    print(json.dumps(stage), flush=True)
    return stage


def score_active(
    output: Path,
    stage: Mapping[str, Any],
    index: FormulaIndex,
    sampler: CodexSampler,
    instructions: Mapping[str, Any],
    ids: list[str],
) -> dict[str, Any]:
    with LocalLearningStore(output / stage["name"], profile_id=stage["name"]) as store:
        loop = loop_for(store, index, sampler, instructions, stage["name"])
        observations = [loop.run_task(case) for case in cases(ids, "final-test", meta=False)]
        if any(
            row.target_snapshot is None or row.target_snapshot.root != stage["strategy_root"]
            for row in observations
        ):
            raise RuntimeError("test did not use the frozen active strategy")
        write_json(
            output / f"{stage['name']}-test-evidence.json", [row.to_dict() for row in observations]
        )
        measured = index.measure(stage["configuration"], index.resolve(ids))
        observed = sum(row.value["output"]["mrr_at_5"] for row in observations) / len(observations)
        if abs(measured.value - observed) > 1e-12:
            raise RuntimeError("fresh ranking and native task scores differ")
        return summarize(measured.output["queries"])


def run(dataset: Path, output: Path, model: str) -> None:
    started, cpu = perf_counter(), process_time()
    output.mkdir(parents=True, exist_ok=False)
    corpus, data = load(dataset)
    identity = provenance()
    for name in ("llm_search.py", "benchmark_llm_search.py"):
        path = Path(__file__).parent / name
        identity["files_sha256"][f"examples/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(
        output / "protocol.json",
        {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "provenance": identity,
            "model": model,
            "reasoning_effort": "high",
            "model_call_ceiling": 24,
            "timeout_seconds_per_call": 180,
            "candidates_per_generation": 2,
            "minimum_effect": 0.01,
            "splits": data["splits"],
            "base_instructions": BASE_INSTRUCTIONS,
            "base_formula": BASE_FORMULA,
            "stopping_rule": "One ordinary pass, one meta pass, one post-meta pass; no retries or test-driven tuning.",
        },
    )
    index = FormulaIndex(corpus["documents"], data["queries"])
    sampler = CodexSampler(output / "model-calls", model)
    ordinary = run_stage(output, "ordinary", index, sampler, data["splits"], BASE_INSTRUCTIONS)
    meta = run_stage(output, "meta", index, sampler, data["splits"], BASE_INSTRUCTIONS, meta=True)
    enhanced = run_stage(output, "post_meta", index, sampler, data["splits"], meta["configuration"])
    write_json(
        output / "frozen-strategies.json",
        {"ordinary": ordinary, "meta": meta, "post_meta": enhanced},
    )
    adaptation_rankings = index.ranked_queries
    ids = data["splits"]["test"]
    scores = {
        "baseline": summarize(index.measure(BASE_FORMULA, index.resolve(ids)).output["queries"])
    }
    scores["ordinary"] = score_active(output, ordinary, index, sampler, BASE_INSTRUCTIONS, ids)
    scores["post_meta"] = score_active(output, enhanced, index, sampler, meta["configuration"], ids)
    fixed = {
        "formula": "idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length)) + 2 * idf * minimum(title_tf, 1)"
    }
    scores["fixed_bm25"] = summarize(index.measure(fixed, index.resolve(ids)).output["queries"])
    report = {
        "schema": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "provenance": identity,
        "model": {
            "ordinary_proposer": model,
            "meta_proposer": model,
            "meta_inner_proposer": model,
            "provider": "OpenAI via authenticated Codex CLI",
            "reasoning_effort": "high",
            "cli_version": sampler.version,
            "immutable_snapshot": None,
            "reviewer": "deterministic MeasuredReviewer; no model",
            "target": "lexical scoring formula; no model at retrieval time",
        },
        "documents": len(corpus["documents"]),
        "archive_sha256": data["archive_sha256"],
        "split_counts": {k: len(v) for k, v in data["splits"].items()},
        "stages": {"ordinary": ordinary, "meta": meta, "post_meta": enhanced},
        "scores": scores,
        "fixed_control": fixed,
        "model_receipts": sampler.receipts,
        "effort": {
            "adaptation_ranked_queries": adaptation_rankings,
            "total_ranked_queries": index.ranked_queries,
            "model_calls": len(sampler.receipts),
            "model_usage": usage_total(sampler.receipts),
            "provider_cost_usd": None,
            "billing_note": "Subscription credentials; CLI does not report billed dollars. Not zero cost.",
            "total_wall_seconds": perf_counter() - started,
            "total_cpu_seconds": process_time() - cpu,
        },
        "limitations": [
            "One stochastic model run on one dataset; no repeated-seed or cross-domain claim.",
            "Meta uses extra data and computation; downstream budgets alone are matched.",
            "Meta measures a two-formula proposal-utility proxy, not full nested adoption loops.",
            "One frozen model sample per instruction/tuning task is reused during native replay; rankings are remeasured.",
            "Official test judgments are evaluated after strategy freeze; this public dataset and earlier deterministic results are not novel unseen data.",
            "Codex exposes requested model alias and token usage, not an immutable weight snapshot or billed dollar cost.",
            "Authentication preflight, software authoring, environment setup and plotting are outside timed experiment; separately disclosed.",
        ],
    }
    write_json(output / "report.json", report)
    print(
        json.dumps(
            {k: {a: b for a, b in v.items() if a != "per_query"} for k, v in scores.items()},
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Fresh output directory")
    parser.add_argument(
        "--model", required=True, help="Exact authenticated Codex model ID; no implicit default"
    )
    args = parser.parse_args()
    run(args.dataset, args.output, args.model)
