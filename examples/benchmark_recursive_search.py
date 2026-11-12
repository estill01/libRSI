"""Five-sample recursive LLM experiment, with at most 160 model turns.

Always test meta and meta-meta optimization. Test meta-meta-meta if meta-meta
does not adopt a supported change. Freeze every final cascade before test scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from benchmark_document_search import MeasuredReviewer, provenance, summarize, write_json
from benchmark_llm_search import usage_total
from llm_search import BASE_FORMULA, CodexSampler, FormulaIndex
from recursive_search import (
    DEFAULTS,
    REPLICATES,
    WORKERS,
    AuditAdapter,
    CascadeAdapter,
    CascadeCache,
    CascadePolicyProposer,
)
from scifact_data import load

from librsi import AdaptiveLoop, LearningCase, LearningPolicy, LocalLearningStore, Metric


def stats(values: Sequence[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "sample_sd": statistics.stdev(values),
        "min": min(values),
        "max": max(values),
        "samples": list(values),
    }


def sample_cases(ids: Sequence[str], phase: str) -> tuple[LearningCase, ...]:
    return tuple(
        LearningCase(f"{phase}-{i}", {"sample": i, "scoring": list(ids)}) for i in range(REPLICATES)
    )


def make_loop(
    store: LocalLearningStore,
    cache: CascadeCache,
    depth: int,
    prior: Sequence[Mapping[str, Any]],
    *,
    audit: bool = False,
) -> AdaptiveLoop:
    return AdaptiveLoop(
        store,
        adapter=AuditAdapter(cache, depth)
        if audit
        else CascadeAdapter(cache, depth, DEFAULTS[depth]),
        proposer=CascadePolicyProposer(cache, depth, prior),
        proposer_id=f"recursive-search:{cache.sampler.model}:depth-{depth}",
        reviewer=MeasuredReviewer(),
        reviewer_id="search-measured-review-v1",
        policy=LearningPolicy(
            objective="Improve average out-of-sample MRR@5 across five independent model samples",
            metric=Metric(
                metric_id="five-sample-paired-mrr", direction="increase", unit="reciprocal-rank"
            ),
            minimum_effect=0.01,
            max_feedback=REPLICATES,
            max_cases=REPLICATES,
            max_candidates=2,
            history_limit=0,
        ),
    )


def stage(
    output: Path,
    depth: int,
    index: FormulaIndex,
    sampler: CodexSampler,
    splits: Mapping[str, Any],
    child_seeds: Mapping[int, Mapping[str, Any]],
    prior: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    name = {1: "meta", 2: "meta_meta", 3: "meta_meta_meta"}[depth]
    print(f"Starting {name}; five independent cascade samples per policy", flush=True)
    started, cpu = perf_counter(), process_time()
    before_calls, before_rankings = len(sampler.receipts), index.ranked_queries
    cache = CascadeCache(
        index, sampler, output / f"{name}-samples", splits["meta_train"][:100], child_seeds
    )
    scoring = splits["meta_train"][100:]
    with LocalLearningStore(
        output / name, profile_id=name, initial_configuration=DEFAULTS[depth]
    ) as store:
        loop = make_loop(store, cache, depth, prior)
        feedback = [loop.run_task(case) for case in sample_cases(scoring, "train")]
        result = loop.learn(
            "improve-1",
            shadow_cases=sample_cases(splits["meta_shadow"], "shadow"),
            verification_cases=sample_cases(splits["meta_verification"], "verification"),
            activate=True,
        )
        if (
            result is None
            or store.pending_pass is not None
            or store.active != result.strategy_after
        ):
            raise RuntimeError("recursive native pass did not settle consistently")
        active = store.active
        write_json(
            output / f"{name}-evidence.json",
            {
                "feedback": [row.to_dict() for row in feedback],
                "native_result": result.native.to_dict(),
                "strategy": active.to_dict(),
            },
        )
    with LocalLearningStore(output / name, profile_id=name) as store:
        if store.active != active:
            raise RuntimeError("persisted root policy changed")
    training_policies = []
    for samples in cache.samples.values():
        configuration = samples[0]["root_configuration"]
        values = [cache.measure(depth, configuration, i, scoring).value for i in range(REPLICATES)]
        training_policies.append(
            {
                "configuration": configuration,
                "scoring": stats(values),
                "sample_key": samples[0]["sample_key"],
            }
        )
    report = {
        "name": name,
        "depth": depth,
        "configuration": dict(active.state),
        "strategy_root": active.root,
        "native_result_root": result.native.root,
        "adopted": result.adopted,
        "disposition": result.disposition,
        "training_policies": training_policies,
        "child_seeds": {str(k): dict(v) for k, v in child_seeds.items()},
        "model_calls": len(sampler.receipts) - before_calls,
        "model_usage": usage_total(sampler.receipts[before_calls:]),
        "ranked_queries": index.ranked_queries - before_rankings,
        "wall_seconds": perf_counter() - started,
        "cpu_seconds": process_time() - cpu,
    }
    write_json(output / f"{name}-summary.json", report)
    write_json(output / "model-receipts.json", sampler.receipts)
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"training_policies", "child_seeds", "configuration"}
            }
        ),
        flush=True,
    )
    return report


def audit(
    output: Path,
    name: str,
    depth: int,
    configuration: Mapping[str, Any],
    source_root: str | None,
    cache: CascadeCache,
    ids: Sequence[str],
) -> dict[str, Any]:
    with LocalLearningStore(
        output / f"audit-{name}", profile_id=f"audit-{name}", initial_configuration=configuration
    ) as store:
        loop = make_loop(store, cache, depth, [], audit=True)
        observations = [loop.run_task(case) for case in sample_cases(ids, "final-test")]
        if dict(store.active.state) != dict(configuration) or any(
            row.target_snapshot is None or row.target_snapshot.root != store.active.root
            for row in observations
        ):
            raise RuntimeError("native audit did not consume the frozen root policy")
        write_json(
            output / f"{name}-test-evidence.json",
            {
                "source_strategy_root": source_root,
                "audit_strategy": store.active.to_dict(),
                "observations": [row.to_dict() for row in observations],
            },
        )
        results = []
        for i, observation in enumerate(observations):
            selected = cache.prepare(depth, configuration)[i]["selected"]
            measured = cache.index.measure(selected, cache.index.resolve(ids))
            if abs(measured.value - observation.value["value"]) > 1e-12:
                raise RuntimeError("fresh scoring differs from native audit")
            results.append(
                {"sample": i, "configuration": selected, **summarize(measured.output["queries"])}
            )
    return {
        "depth": depth,
        "source_strategy_root": source_root,
        "configuration": dict(configuration),
        "sample_key": cache.key(depth, configuration),
        "mrr_at_5": stats([row["mrr_at_5"] for row in results]),
        "top_1": stats([row["top_1"] for row in results]),
        "results": results,
    }


def run(dataset: Path, output: Path, model: str) -> None:
    started, cpu = perf_counter(), process_time()
    output.mkdir(parents=True, exist_ok=False)
    corpus, data = load(dataset)
    identity = provenance()
    for name in (
        "llm_search.py",
        "benchmark_llm_search.py",
        "recursive_search.py",
        "benchmark_recursive_search.py",
    ):
        path = Path(__file__).parent / name
        identity["files_sha256"][f"examples/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name, expected in identity["files_sha256"].items():
        path = Path(__file__).resolve().parent.parent / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("source changed during manifest creation")
        destination = output / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    write_json(
        output / "protocol.json",
        {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "provenance": identity,
            "model": model,
            "reasoning_effort": "high",
            "replicates": REPLICATES,
            "concurrent_inference_workers": WORKERS,
            "model_call_ceiling": 160,
            "timeout_seconds_per_call": 180,
            "formula_candidates_per_sample": 2,
            "child_instructions_per_rewrite": 1,
            "root_candidates_per_pass": 2,
            "minimum_effect": 0.01,
            "defaults": {str(k): v for k, v in DEFAULTS.items()},
            "splits": data["splits"],
            "stopping_rule": "Run meta and meta-meta. Run meta-meta-meta only if meta-meta does not adopt. No test-driven tuning or retries.",
            "generation_queries": data["splits"]["meta_train"][:100],
            "training_scoring_queries": data["splits"]["meta_train"][100:],
            "final_generation_queries": data["splits"]["ordinary_train"],
            "caveat": "Official test results were reported in earlier experiments; they are withheld from model inputs and all selection in this follow-up.",
        },
    )
    index = FormulaIndex(corpus["documents"], data["queries"])
    sampler = CodexSampler(output / "model-calls", model, max_calls=160)
    seeds = {k: dict(v) for k, v in DEFAULTS.items()}
    stages: list[dict[str, Any]] = []
    for depth in (1, 2, 3):
        if depth == 3 and stages[-1]["adopted"]:
            break
        result = stage(output, depth, index, sampler, data["splits"], seeds, stages)
        stages.append(result)
        seeds[depth] = result["configuration"]
    adaptation_calls, adaptation_rankings = len(sampler.receipts), index.ranked_queries
    preparation_started = perf_counter()
    final_cache = CascadeCache(
        index, sampler, output / "audit-samples", data["splits"]["ordinary_train"], seeds
    )
    arms: dict[str, dict[str, Any]] = {
        "ordinary": {"depth": 1, "configuration": DEFAULTS[1], "source_root": None}
    }
    for stage_result in stages:
        name, depth = stage_result["name"], stage_result["depth"]
        # Reopen the actual saved decision before propagating it to a fresh workload.
        with LocalLearningStore(output / name, profile_id=name) as store:
            if store.active.root != stage_result["strategy_root"]:
                raise RuntimeError("stored policy differs before propagation")
            arms[name] = {
                "depth": depth,
                "configuration": dict(store.active.state),
                "source_root": store.active.root,
            }
        if depth > 1:
            arms[f"{name}_default"] = {
                "depth": depth,
                "configuration": DEFAULTS[depth],
                "source_root": None,
            }
    for name, arm in arms.items():
        print(f"Preparing five fresh final samples: {name}", flush=True)
        final_cache.prepare(arm["depth"], arm["configuration"])
    final_cache.frozen = True
    write_json(
        output / "frozen-final-cascades.json", {"arms": arms, "samples": final_cache.samples}
    )
    final_preparation_seconds = perf_counter() - preparation_started
    frozen_calls = len(sampler.receipts)
    scores = {
        name: audit(
            output,
            name,
            arm["depth"],
            arm["configuration"],
            arm["source_root"],
            final_cache,
            data["splits"]["test"],
        )
        for name, arm in arms.items()
    }
    if len(sampler.receipts) != frozen_calls:
        raise RuntimeError("model called after final test evaluation began")
    baseline = summarize(
        index.measure(BASE_FORMULA, index.resolve(data["splits"]["test"])).output["queries"]
    )
    report = {
        "schema": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "provenance": identity,
        "model": model,
        "provider": "OpenAI via authenticated Codex CLI",
        "reasoning_effort": "high",
        "cli_version": sampler.version,
        "model_snapshot": None,
        "replicates": REPLICATES,
        "reviewer": "deterministic MeasuredReviewer; no model",
        "target": "lexical formulas; no query-time model",
        "stages": stages,
        "scores": scores,
        "term_count_baseline": baseline,
        "model_receipts": sampler.receipts,
        "effort": {
            "model_calls": len(sampler.receipts),
            "model_usage": usage_total(sampler.receipts),
            "adaptation_model_calls": adaptation_calls,
            "final_sampling_model_calls": len(sampler.receipts) - adaptation_calls,
            "adaptation_ranked_queries": adaptation_rankings,
            "total_ranked_queries": index.ranked_queries,
            "final_sampling_wall_seconds": final_preparation_seconds,
            "total_wall_seconds": perf_counter() - started,
            "python_cpu_seconds": process_time() - cpu,
            "provider_cost_usd": None,
            "concurrent_inference_workers": WORKERS,
        },
        "limitations": [
            "Five stochastic samples per policy, not five independent datasets; no large-sample or cross-domain claim.",
            "Inner cascades are proposal-utility proxies; root policy changes use native libRSI adoption and final audits use native tasks.",
            "One child instruction per rewrite, then two formulas; five fixed samples are reused across native shadow and verification measurements.",
            "Higher depths have more model work and token use per sample. Every actual call is counted; unchanged policies reuse identical final samples.",
            "Same-depth default cascades are controls. Improvement from additional rewriting alone is not evidence that libRSI adopted a better root policy.",
            "Official test set was used in earlier reports, but is absent from all model prompts and selection inputs in this run.",
            "Native local timings include bookkeeping; inference is concurrent with up to three calls. Dollar billing and immutable model snapshot are unavailable.",
        ],
    }
    write_json(output / "report.json", report)
    write_json(output / "model-receipts.json", sampler.receipts)
    print(json.dumps({name: row["mrr_at_5"] for name, row in scores.items()}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    run(args.dataset, args.output, args.model)
