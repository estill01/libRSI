"""End-to-end Astra/libRSI scheduler and improver experiment (no selection proxy).

Each model draw runs a real AdaptiveLoop from the same original scheduler. The
outer AdaptiveLoop measures those retained systems, then passes its reopened
active instruction to another 32 independent native optimization runs.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from benchmark_document_search import MeasuredReviewer, provenance, write_json
from benchmark_llm_search import usage_total
from benchmark_setup_sequence import bounded_parallel, hypotheses, interval
from llm_search import CodexSampler, validate_instructions
from sequence_program import (
    BASE_INSTRUCTIONS,
    BASE_PROGRAM,
    BUDGET,
    PROGRAM_CONTRACT,
    execute,
    parse_program,
)
from setup_sequence import SequenceProblem, build_oracle, cost, workload

from librsi import (
    AdaptiveLoop,
    LearningCase,
    LearningPolicy,
    LocalLearningStore,
    Metric,
    TaskMeasurement,
)
from librsi.identity import canonical_json, digest

MODEL = "gpt-6-astra"
N_FINAL = 32
N_DEVELOPMENT = 8  # independent inner runs in each of three outer evaluation splits
INNER_EFFECT = 0.02
META_EFFECT = 0.005
NATIVE_WORKERS = 2
CONTRACT = PROGRAM_CONTRACT.replace(
    "the cheapest nearest-neighbor cycle over all starting jobs",
    "a nearest-neighbor cycle starting at job 0",
)
# New partition identities, distinct from all previous calibration/study data.
SEEDS = {
    name: 830000 + 1000 * i
    for i, name in enumerate(
        [
            "dev_train",
            "dev_shadow",
            "dev_verify",
            "meta_train",
            "meta_shadow",
            "meta_verify",
            "final_train",
            "final_shadow",
            "final_verify",
            "test",
        ]
    )
}


def fresh_problem(row, oracle):
    problem = SequenceProblem(row, oracle)
    order = [0]
    while len(order) < problem.n:
        order.append(
            min(
                (i for i in range(problem.n) if i not in order),
                key=lambda i: (problem.matrix[order[-1]][i], i),
            )
        )
    problem.starting_order = order
    problem.starting_cost = cost(problem.matrix, order)
    return problem


def dump_gz(path, value):
    path.write_bytes(gzip.compress(canonical_json(value).encode(), mtime=0))


class FixedProposer:
    """Bind independently recorded LLM proposals to the exact native request."""

    def __init__(self, choices):
        self.choices = choices

    def respond(self, request):
        return hypotheses(request, self.choices, "cost_reduction")


class SchedulerAdapter:
    adapter_id = "single-start-sequence-program-v1"
    validate_configuration = staticmethod(parse_program)

    def __init__(self, problems):
        self.problems = problems
        self.cache = {}

    def rows(self, configuration, split):
        key = (digest(dict(configuration)), split)
        if key not in self.cache:
            self.cache[key] = [execute(configuration, p) for p in self.problems[split]]
        return self.cache[key]

    def evaluate(self, configuration, case):
        split, group = case.payload["split"], case.payload["group"]
        values = [
            r["cost_reduction"]
            for r in self.rows(configuration, split)[group * 16 : (group + 1) * 16]
        ]
        return TaskMeasurement({"values": values, "workloads": 16}, statistics.mean(values))


def native_loop(store, adapter, proposer, *, meta=False):
    return AdaptiveLoop(
        store,
        adapter=adapter,
        proposer=proposer,
        proposer_id="astra-meta-instructions-v1" if meta else "astra-sequence-programs-v2",
        reviewer=MeasuredReviewer(),
        reviewer_id="search-measured-review-v1",
        policy=LearningPolicy(
            objective="Reduce setup cost relative to the original single-start greedy scheduler"
            if not meta
            else "Increase retained-system cost reduction after a full libRSI optimization run",
            metric=Metric(metric_id="cost_reduction", direction="increase"),
            minimum_effect=META_EFFECT if meta else INNER_EFFECT,
            max_feedback=2,
            max_cases=2,
            max_candidates=2,
            history_limit=0,
        ),
    )


def scheduler_run(job):
    """Worker executes the entire native workflow, persisting actual active state."""
    output, label, choices, instruction, problems, phase = job
    started = perf_counter()
    adapter = SchedulerAdapter(problems)
    prefix = "dev" if phase == "development" else "final"

    def cases(stage):
        return [
            LearningCase(f"{prefix}_{stage}-{i}", {"split": f"{prefix}_{stage}", "group": i})
            for i in range(2)
        ]

    with LocalLearningStore(
        output / "stores" / label, profile_id=label, initial_configuration=BASE_PROGRAM
    ) as store:
        loop = native_loop(store, adapter, FixedProposer(choices))
        for case in cases("train"):
            loop.run_task(case)
        result = loop.learn(
            "optimize",
            shadow_cases=cases("shadow"),
            verification_cases=cases("verify"),
            activate=True,
        )
        if (
            result is None
            or store.pending_pass is not None
            or store.active != result.strategy_after
        ):
            raise RuntimeError(f"unfinished native pass: {label}")
        active, root = dict(store.active.state), store.active.root
        inputs = store.pass_input("optimize")
        assert inputs is not None
        evidence = {
            "native": result.native.to_dict(),
            "active": store.active.to_dict(),
            "inputs": inputs.to_dict(),
        }
        dump_gz(output / "native" / f"{label}.json.gz", evidence)
        row = {
            "label": label,
            "phase": phase,
            "instruction": instruction,
            "choices": choices,
            "adopted": result.adopted,
            "disposition": result.disposition,
            "configuration": active,
            "active_root": root,
            "native_root": result.native.root,
            "wall_seconds": perf_counter() - started,
        }
    with LocalLearningStore(output / "stores" / label, profile_id=label) as store:
        assert store.active.root == root and dict(store.active.state) == active
    if phase == "development":
        row["evaluation"] = {
            split: statistics.mean(r["cost_reduction"] for r in adapter.rows(active, split))
            for split in ("meta_train", "meta_shadow", "meta_verify")
        }
    write_json(output / "runs" / f"{label}.json", row)
    print("NATIVE", label, row["disposition"], f"{row['wall_seconds']:.1f}s", flush=True)
    return row


class Study:
    def __init__(self, output, problems, sampler):
        self.output, self.problems, self.sampler = output, problems, sampler
        self.development = {}

    def propose(self, instruction, phase, label):
        split = "dev_train" if phase == "development" else "final_train"
        prompt = CONTRACT + "\nPROPOSER INSTRUCTION:\n" + instruction["instruction"]
        prompt += "\nOBJECTIVE: reduce mean setup cost by at least 2 percentage points relative to the original scheduler. Each proposal gets exactly 256 cost evaluations per workload.\n"
        prompt += "The native optimizer compares measured training, forward-shadow and verification batches; unaccepted or rolled-back proposals leave the original scheduler active.\nTRAINING EXAMPLES:\n"
        prompt += canonical_json([p.prompt_data() for p in self.problems[split][:4]])
        try:
            choices = self.sampler.call(prompt, field="program", role=label)
        except ValueError as error:
            # A malformed response consumes its slot and enters a failed native
            # proposal. Transport failures still stop the run with receipts.
            choices = [
                {
                    "configuration": {"invalid_output": str(error), "slot": i},
                    "reason": "Invalid model output",
                }
                for i in range(2)
            ]
        return choices

    def generate(self, instruction, phase, label):
        choices = self.propose(instruction, phase, label)
        write_json(
            self.output / "proposals" / f"{label}.json",
            {"instruction": instruction, "phase": phase, "choices": choices},
        )
        return (self.output, label, choices, instruction, self.problems, phase)

    def run_jobs(self, specs):
        generated = bounded_parallel(specs, self.generate)
        with ProcessPoolExecutor(max_workers=NATIVE_WORKERS) as pool:
            rows = list(pool.map(scheduler_run, generated))
        return sorted(rows, key=lambda r: r["label"])

    def prepare(self, instruction):
        key = digest(instruction)
        if key not in self.development:
            rows = self.run_jobs(
                [
                    (instruction, "development", f"dev-{key[:12]}-{i:02d}")
                    for i in range(N_DEVELOPMENT * 3)
                ]
            )
            self.development[key] = rows
        return self.development[key]


class MetaAdapter:
    adapter_id = "native-sequence-improver-utility-v1"
    validate_configuration = staticmethod(validate_instructions)

    def __init__(self, study):
        self.study = study

    def evaluate(self, configuration, case):
        split, group = case.payload["split"], case.payload["group"]
        start = {"meta_train": 0, "meta_shadow": 8, "meta_verify": 16}[split] + group * 4
        selected = self.study.prepare(configuration)[start : start + 4]
        baseline = self.study.prepare(BASE_INSTRUCTIONS)[start : start + 4]
        effects = [
            a["evaluation"][split] - b["evaluation"][split]
            for a, b in zip(selected, baseline, strict=True)
        ]
        return TaskMeasurement(
            {
                "native_runs": [r["label"] for r in selected],
                "reference_runs": [r["label"] for r in baseline],
                "effects": effects,
            },
            statistics.mean(effects),
        )


class MetaProposer:
    def __init__(self, study):
        self.study, self.choices = study, []

    def respond(self, request):
        rows = self.study.prepare(BASE_INSTRUCTIONS)[:8]
        detail = [
            {
                "choices": r["choices"],
                "adopted": r["adopted"],
                "disposition": r["disposition"],
                "retained_configuration": r["configuration"],
                "retained_cost_reduction": r["evaluation"]["meta_train"],
            }
            for r in rows
        ]
        prompt = (
            "Improve the instruction used by gpt-6-astra with high reasoning to design scheduling search programs. "
            "Return exactly TWO different instruction strings <=2400 characters each. Same Astra model, two proposed programs per call, "
            "same 256 cost-evaluation budget. You may improve reasoning, exploration, program construction and use of feedback. "
            "Your metric is performance of the system ACTUALLY ADOPTED by a full libRSI optimization, not best proposed candidate. "
            "Your revised improver must increase mean retained-system cost reduction by at least 0.5 percentage points on new draws. "
            "Do not change model, host language, metrics, workload distributions, native gates or runtime budget. "
            "Use these eight actual training runs to diagnose weak program design and propose a better strategy. "
            "No final or held-out feedback is available. Reasons are hypotheses, not established gains.\nPROGRAM CONTRACT:\n"
            + CONTRACT
            + "\nORIGINAL INSTRUCTION:\n"
            + BASE_INSTRUCTIONS["instruction"]
            + "\nACTUAL NATIVE TRAINING RUNS:\n"
            + canonical_json(detail)
        )
        self.choices = self.study.sampler.call(
            prompt, field="instruction", role="meta-revise-improver"
        )
        for choice in self.choices:
            validate_instructions(choice["configuration"])
            if choice["configuration"] == BASE_INSTRUCTIONS:
                raise ValueError("meta proposal repeats original instruction")
            self.study.prepare(choice["configuration"])
        return hypotheses(request, self.choices, "cost_reduction")


def meta_run(study):
    proposer = MetaProposer(study)

    def cases(split):
        return [LearningCase(f"{split}-{i}", {"split": split, "group": i}) for i in range(2)]

    with LocalLearningStore(
        study.output / "stores" / "meta", profile_id="meta", initial_configuration=BASE_INSTRUCTIONS
    ) as store:
        loop = native_loop(store, MetaAdapter(study), proposer, meta=True)
        for case in cases("meta_train"):
            loop.run_task(case)
        result = loop.learn(
            "improve-improver",
            shadow_cases=cases("meta_shadow"),
            verification_cases=cases("meta_verify"),
            activate=True,
        )
        if (
            result is None
            or store.pending_pass is not None
            or store.active != result.strategy_after
        ):
            raise RuntimeError("unfinished meta pass")
        row = {
            "adopted": result.adopted,
            "disposition": result.disposition,
            "active": dict(store.active.state),
            "active_root": store.active.root,
            "native_root": result.native.root,
            "choices": proposer.choices,
        }
        inputs = store.pass_input("improve-improver")
        assert inputs is not None
        dump_gz(
            study.output / "native" / "meta.json.gz",
            {
                "native": result.native.to_dict(),
                "active": store.active.to_dict(),
                "inputs": inputs.to_dict(),
            },
        )
    with LocalLearningStore(study.output / "stores" / "meta", profile_id="meta") as store:
        assert store.active.root == row["active_root"] and dict(store.active.state) == row["active"]
    write_json(study.output / "frozen-improver.json", row)
    return row


def run(output):
    started = perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    for name in ("native", "runs", "proposals", "source"):
        (output / name).mkdir()
    identity = provenance()
    root = Path(__file__).resolve().parents[1]
    sources = (
        sorted((root / "src/librsi").rglob("*.py"))
        + sorted((root / "examples").glob("*.py"))
        + [root / "examples/sequence_oracle.cpp"]
    )
    for path in sources:
        relative = path.relative_to(root)
        target = output / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        identity["files_sha256"][str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    protocol = {
        "created_at": datetime.now(UTC).isoformat(),
        "provenance": identity,
        "model": MODEL,
        "reasoning_effort": "high",
        "reasoning_roles": ["scheduler-proposer", "meta-improver-proposer"],
        "base": "14-job single-start nearest-neighbor scheduler, starting at job 0",
        "workloads": "synthetic asymmetric setup matrices in four balanced families",
        "seed_bases": SEEDS,
        "inner_minimum_effect": INNER_EFFECT,
        "meta_minimum_effect": META_EFFECT,
        "native_training_shadow_verification": "Each has two case batches of sixteen workloads; each final model draw runs full native selection, shadow, adoption and verification from the SAME original base.",
        "outer_training_shadow_verification": "Each has eight independent complete native optimization runs, grouped into two batches of four; distinct model draws and evaluation workloads across the three stages.",
        "meta_development_calls": 73,
        "final_samples_per_arm": N_FINAL,
        "test_workloads": 128,
        "runtime_cost_evaluations": BUDGET,
        "model_call_limit": 169,
        "final_policy": "Use the reopened ACTIVE improver after the native meta pass. If meta is rejected, retain the original instruction. Never force a proposed revision into the primary third arm.",
        "diagnostic": "If meta is rejected, additionally run 32 full inner native optimizations with the better training-scoring proposed instruction. Label as forced instruction diagnostic, not actual meta adoption.",
        "analysis": "Primary contrast: after-meta minus ordinary. 10000 crossed bootstrap draws over independent model draws and paired workload samples stratified by family; 95% interval. Conditional on one meta-development run, not uncertainty over repeated meta training. No optional stopping or replacing failures.",
        "costs": "Record calls, input/output tokens, wall time. Subscription dollar billing unknown. No equal-total-budget control; no claim that meta is more compute efficient.",
        "gate_version": 3,
        "limits": [
            "Synthetic workload, not production throughput",
            "Same model alias, not immutable weights",
            "LLM optimization with deterministic non-LLM scoring and review",
            "No LLM calls at scheduler inference time",
        ],
    }
    write_json(output / "protocol.json", protocol)
    data = {
        split: [workload(seed + i, i % 4) for i in range(128 if split == "test" else 32)]
        for split, seed in SEEDS.items()
    }
    write_json(output / "workloads.json", data)
    oracle = build_oracle(output / "oracle")
    problems = {split: [fresh_problem(row, oracle) for row in rows] for split, rows in data.items()}
    sampler = CodexSampler(output / "model-calls", MODEL, max_calls=169, reasoning_effort="high")
    study = Study(output, problems, sampler)
    try:
        meta = meta_run(study)
        assert len(sampler.receipts) == 73
        print("META FROZEN", json.dumps(meta), flush=True)
        instructions = {"ordinary": BASE_INSTRUCTIONS, "after_meta": meta["active"]}
        if not meta["adopted"]:
            candidate = max(
                meta["choices"],
                key=lambda c: statistics.mean(
                    r["evaluation"]["meta_train"]
                    for r in study.development[digest(c["configuration"])][:8]
                ),
            )
            instructions["forced_revision_diagnostic"] = candidate["configuration"]
        write_json(output / "final-instructions.json", instructions)
        jobs = [
            (instruction, "final", f"{arm}-{i:02d}")
            for arm, instruction in instructions.items()
            for i in range(N_FINAL)
        ]
        random.Random(2026111209).shuffle(jobs)
        rows = study.run_jobs(jobs)
        write_json(output / "frozen-final-systems.json", rows)
        # Final evaluation begins only after every native workflow has finished.
        scores = {
            arm: [
                [execute(r["configuration"], p)["cost_reduction"] for p in problems["test"]]
                for r in rows
                if r["label"].startswith(arm + "-")
            ]
            for arm in instructions
        }
        families = [p.data["family"] for p in problems["test"]]
        contrast = interval(scores, "ordinary", "after_meta", families, seed=2026111210)
        assert all(len(grid) == N_FINAL for grid in scores.values())
        report = {
            "protocol": protocol,
            "meta": meta,
            "instructions": instructions,
            "runs": rows,
            "development": study.development,
            "scores": scores,
            "primary_contrast": contrast,
            "means": {arm: float(np.mean(grid)) for arm, grid in scores.items()},
            "adoptions": {
                arm: sum(r["adopted"] for r in rows if r["label"].startswith(arm + "-"))
                for arm in scores
            },
            "effort": {
                "model_calls": len(sampler.receipts),
                "meta_development_calls": 73,
                "ordinary_final_calls": 32,
                "after_meta_final_calls": 32,
                "forced_diagnostic_calls": 32 if not meta["adopted"] else 0,
                "usage": usage_total(sampler.receipts),
                "wall_seconds": perf_counter() - started,
                "native_inner_runs": 72 + len(rows),
                "native_outer_runs": 1,
                "provider_cost_usd": None,
            },
            "test_baseline_costs": [p.starting_cost for p in problems["test"]],
            "test_optimal_costs": [p.optimal_cost for p in problems["test"]],
        }
        dump_gz(output / "report.json.gz", report)
        write_json(
            output / "summary.json",
            {
                key: report[key]
                for key in ("means", "adoptions", "primary_contrast", "effort", "meta")
            },
        )
        print(
            "COMPLETE",
            json.dumps(
                {k: report[k] for k in ("means", "adoptions", "primary_contrast", "effort")}
            ),
            flush=True,
        )
    finally:
        write_json(output / "receipts.json", sampler.receipts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
