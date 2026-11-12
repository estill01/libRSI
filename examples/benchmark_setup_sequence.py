"""Astra interprets a goal, improves a scheduler, then improves its improver.

32 independent model draws and 128 held-out workloads; an original-improver
control spends exactly the same model-call budget as meta development + reuse.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import statistics
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

import numpy as np
from benchmark_document_search import MeasuredReviewer, provenance, write_json
from benchmark_llm_search import usage_total
from llm_search import CodexSampler, validate_instructions
from sequence_intent import operationalize
from sequence_program import (
    BASE_INSTRUCTIONS,
    BASE_PROGRAM,
    BUDGET,
    PROGRAM_CONTRACT,
    execute,
    parse_program,
)
from setup_sequence import SequenceProblem, build_oracle, cost, local_search, workload

from librsi import (
    AdaptiveLoop,
    LearningCase,
    LearningPolicy,
    LocalLearningStore,
    Metric,
    ReasoningResult,
    TaskMeasurement,
)
from librsi.identity import canonical_json, digest

SAMPLES = 32
WORKERS = 6
SPLITS = {
    "generation": 16,
    "scoring": 16,
    "shadow": 16,
    "verification": 16,
    "final_generation": 16,
    "test": 128,
}
SEEDS = {name: 610000 + 1000 * i for i, name in enumerate(SPLITS)}


def hypotheses(request, choices, metric):
    return ReasoningResult.propose(
        request=request,
        content={
            "hypotheses": [
                {
                    "statement": row["reason"],
                    "causal_model": {"configuration": row["configuration"]},
                    "predictions": [{metric: "increase"}],
                    "confidence": 0.5,
                }
                for row in choices
            ]
        },
    )


def bounded_parallel(jobs, function):
    """Submit at most six requests; stop new submissions on a transport failure."""
    pending: set[Future[Any]] = set()
    remaining = iter(jobs)
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:

        def fill():
            while len(pending) < WORKERS:
                job = next(remaining, None)
                if job is None:
                    break
                pending.add(pool.submit(function, *job))

        fill()
        try:
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    results.append(future.result())
                fill()
        finally:
            for future in pending:
                future.cancel()
    return results


class ProgramStudy:
    def __init__(self, output, problems, sampler, plan):
        self.output, self.problems, self.sampler, self.plan = output, problems, sampler, plan
        self.draws: dict[str, list[dict[str, Any]]] = {}
        self.measurements: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.final_frozen = False
        self.program_executions = 0
        self.cost_evaluations = 0
        (output / "draws").mkdir(exist_ok=False)

    def measured(self, config, split):
        key = (digest(dict(config)), split)
        if key not in self.measurements:
            rows = [execute(config, p) for p in self.problems[split]]
            self.measurements[key] = rows
            self.program_executions += len(rows)
            self.cost_evaluations += sum(row["evaluations"] for row in rows)
        return self.measurements[key]

    def value(self, config, split):
        return statistics.mean(r[self.plan["metric"]] for r in self.measured(config, split))

    def diagnostics(self, split):
        rows = self.measured(BASE_PROGRAM, split)
        return {
            "baseline_configuration": BASE_PROGRAM,
            "baseline_mean": self.value(BASE_PROGRAM, split),
            "workload_count": len(rows),
            "baseline_scores": [r[self.plan["metric"]] for r in rows],
            "representative_workloads": [p.prompt_data() for p in self.problems[split][:4]],
        }

    def propose(self, instruction, split, role):
        prompt = (
            PROGRAM_CONTRACT
            + "\nVALIDATED GOAL INTERPRETATION:\n"
            + canonical_json(self.plan)
            + "\nPROPOSER STRATEGY:\n"
            + instruction["instruction"]
            + "\nMEASURED GENERATION FEEDBACK:\n"
            + canonical_json(self.diagnostics(split))
        )
        return self.sampler.call(prompt, field="program", role=role)

    def generate(self, instruction, phase, number):
        if self.final_frozen:
            raise RuntimeError("model samples are frozen")
        key = digest({"instruction": dict(instruction), "phase": phase})
        split = "generation" if phase == "development" else "final_generation"
        role = f"program-{phase}:{key[:12]}:sample-{number}"
        error = None
        try:
            choices = self.propose(instruction, split, role)
        except ValueError as exc:
            choices = []
            error = str(exc)
        # Pure data validation failures spend their slots. No replacement calls.
        candidates = []
        for choice in choices:
            try:
                parse_program(choice["configuration"], allow_baseline=False)
                candidates.append({**choice, "valid": True})
            except (ValueError, TypeError, KeyError) as exc:
                candidates.append({**choice, "valid": False, "error": str(exc)})
        # Selection sees only generation workloads, never scoring/shadow/final.
        row = {
            "phase": phase,
            "sample": number,
            "policy_key": key,
            "instruction": dict(instruction),
            "role": role,
            "proposal_error": error,
            "candidates": candidates,
        }
        write_json(self.output / "draws" / f"{key}-{number}-generated.json", row)
        return row

    def finish_draw(self, row):
        split = "generation" if row["phase"] == "development" else "final_generation"
        configs = [BASE_PROGRAM, *[r["configuration"] for r in row["candidates"] if r["valid"]]]
        values = [self.value(config, split) for config in configs]
        selected = max(range(len(values)), key=values.__getitem__)
        row = {
            **row,
            "selection_values": values,
            "selected": dict(configs[selected]),
            "selection_value": values[selected],
        }
        write_json(
            self.output / "draws" / f"{row['policy_key']}-{row['sample']}-selected.json", row
        )
        return row

    def prepare(self, instruction, phase="development", count=SAMPLES):
        key = digest({"instruction": dict(instruction), "phase": phase})
        if key in self.draws:
            if len(self.draws[key]) != count:
                raise ValueError("sample-count identity changed")
            return self.draws[key]
        self.diagnostics("generation" if phase == "development" else "final_generation")
        generated = bounded_parallel([(instruction, phase, i) for i in range(count)], self.generate)
        rows = [self.finish_draw(row) for row in sorted(generated, key=lambda row: row["sample"])]
        self.draws[key] = rows
        return rows

    def native_value(self, instruction, sample, split):
        rows = self.prepare(instruction)
        return self.value(rows[sample]["selected"], split)


class MetaAdapter:
    adapter_id = "astra-sequence-program-proposal-utility-v1"
    validate_configuration = staticmethod(validate_instructions)

    def __init__(self, study):
        self.study = study

    def evaluate(self, configuration, case):
        sample, split = case.payload["sample"], case.payload["split"]
        value = self.study.native_value(configuration, sample, split)
        baseline = self.study.native_value(BASE_INSTRUCTIONS, sample, split)
        return TaskMeasurement(
            {"sample": sample, "score": value, "reference": baseline}, value - baseline
        )


class MetaProposer:
    def __init__(self, study):
        self.study = study
        self.choices = []

    def respond(self, request):
        rows = self.study.prepare(BASE_INSTRUCTIONS)
        details = [
            {
                "sample": r["sample"],
                "selected": r["selected"],
                "generation_score": r["selection_value"],
                "scoring_value": self.study.value(r["selected"], "scoring"),
            }
            for r in rows
        ]
        ordered = sorted(details, key=lambda row: row["scoring_value"])
        prompt = (
            "Improve the reasoning strategy used by an Astra proposer to design bounded scheduling-search programs. "
            'Return exactly TWO different instructions, each <=2400 characters, configuration {"instruction":"text"}. '
            "Your instructions will be executed by the SAME model, gpt-6-astra, high reasoning. "
            "Each call still proposes exactly two new programs. Improve its experimental/search strategy using these "
            "actual development results. You may change what combinations it explores and how it reasons from feedback. "
            "Do not change the model, executable language, evaluation budget, metric, minimum effect, or data. "
            "Do not treat this training feedback as independent confirmation. No tools. "
            "Return reasons as causal hypotheses, not established improvements.\nPROGRAM LANGUAGE:\n"
            + PROGRAM_CONTRACT
            + "\nVALIDATED GOAL:\n"
            + canonical_json(self.study.plan)
            + "\nCURRENT INSTRUCTION:\n"
            + BASE_INSTRUCTIONS["instruction"]
            + "\nALL DEVELOPMENT SCORES:\n"
            + canonical_json(
                [
                    {
                        "sample": r["sample"],
                        "generation": r["generation_score"],
                        "scoring": r["scoring_value"],
                    }
                    for r in details
                ]
            )
            + "\nSIX LOWEST AND SIX HIGHEST PROGRAMS:\n"
            + canonical_json(ordered[:6] + ordered[-6:])
        )
        self.choices = self.study.sampler.call(
            prompt, field="instruction", role="meta-proposer-revision"
        )
        for row in self.choices:
            validate_instructions(row["configuration"])
            if row["configuration"] == BASE_INSTRUCTIONS:
                raise ValueError("unchanged instruction")
            self.study.prepare(row["configuration"])
        return hypotheses(request, self.choices, self.study.plan["metric"])


class EngineAdapter:
    adapter_id = "bounded-scheduling-program-execution-v1"

    @staticmethod
    def validate_configuration(configuration):
        parse_program(configuration)

    def __init__(self, study):
        self.study = study

    def evaluate(self, configuration, case):
        split, index = case.payload["split"], case.payload["index"]
        rows = self.study.measured(configuration, split)
        baseline = self.study.measured(BASE_PROGRAM, split)
        metric = self.study.plan["metric"]
        return TaskMeasurement(rows[index], rows[index][metric] - baseline[index][metric])


class EngineProposer:
    def __init__(self, study, instruction, role):
        self.study, self.instruction, self.role = study, instruction, role
        self.choices = []

    def respond(self, request):
        self.choices = self.study.propose(self.instruction, "generation", self.role)
        for choice in self.choices:
            parse_program(choice["configuration"], allow_baseline=False)
        return hypotheses(request, self.choices, self.study.plan["metric"])


def native_loop(store, adapter, proposer, plan, *, meta):
    return AdaptiveLoop(
        store,
        adapter=adapter,
        proposer=proposer,
        proposer_id="astra-meta" if meta else "astra-program-proposer",
        reviewer=MeasuredReviewer(),
        reviewer_id="search-measured-review-v1",
        policy=LearningPolicy(
            objective=plan["objective"],
            metric=Metric(metric_id=plan["metric"], direction="increase", unit="dimensionless"),
            minimum_effect=plan["minimum_effect"],
            max_feedback=SAMPLES if meta else 16,
            max_cases=SAMPLES if meta else 16,
            max_candidates=2,
            history_limit=0,
        ),
    )


def engine_pass(study, output, name, instruction):
    proposer = EngineProposer(study, instruction, name)
    with LocalLearningStore(
        output / name, profile_id="production-engine", initial_configuration=BASE_PROGRAM
    ) as store:
        loop = native_loop(store, EngineAdapter(study), proposer, study.plan, meta=False)

        def cases(split):
            return [LearningCase(f"{split}-{i}", {"split": split, "index": i}) for i in range(16)]

        for case in cases("scoring"):
            loop.run_task(case)
        result = loop.learn(
            "improve",
            shadow_cases=cases("shadow"),
            verification_cases=cases("verification"),
            activate=True,
        )
        if result is None or store.pending_pass is not None:
            raise RuntimeError("engine pass unfinished")
        evidence = {
            "result": result.native.to_dict(),
            "active": store.active.to_dict(),
            "instruction": instruction,
            "choices": proposer.choices,
        }
        (output / f"{name}-native.json.gz").write_bytes(
            gzip.compress(json.dumps(evidence, sort_keys=True).encode(), mtime=0)
        )
        record = {
            "adopted": result.adopted,
            "disposition": result.disposition,
            "configuration": dict(store.active.state),
            "root": store.active.root,
            "native_root": result.native.root,
            "instruction": instruction,
        }
    with LocalLearningStore(output / name, profile_id="production-engine") as store:
        assert store.active.root == record["root"]
    write_json(output / f"{name}.json", record)
    return record


def interval(grids, left, right, families, *, seed=2026111204):
    """Crossed bootstrap: independent model draws, paired stratified workloads."""
    a, b = np.asarray(grids[left]), np.asarray(grids[right])
    assert a.shape == b.shape == (SAMPLES, 128)
    rng = np.random.default_rng(seed)
    draws = []
    family_indices = [np.flatnonzero(np.asarray(families) == i) for i in range(4)]
    for _ in range(10000):
        tasks = np.concatenate([rng.choice(ids, len(ids), replace=True) for ids in family_indices])
        ai = rng.integers(0, SAMPLES, SAMPLES)
        bi = rng.integers(0, SAMPLES, SAMPLES)
        draws.append(float(b[bi][:, tasks].mean() - a[ai][:, tasks].mean()))
    return {
        "mean_effect": float(b.mean() - a.mean()),
        "bootstrap_95_percentile": np.quantile(draws, [0.025, 0.975]).tolist(),
        "bootstrap_97_5_percentile": np.quantile(draws, [0.0125, 0.9875]).tolist(),
        "method": "10000 crossed bootstrap draws: independent program-generation samples by arm, shared workloads resampled within family",
        "model_samples_per_arm": SAMPLES,
        "independent_workloads": 128,
    }


def run(output: Path, model: str):
    started, cpu = perf_counter(), process_time()
    output.mkdir(parents=True, exist_ok=False)
    identity = provenance()
    root = Path(__file__).resolve().parent.parent
    for name in [
        "examples/benchmark_setup_sequence.py",
        "examples/sequence_program.py",
        "examples/setup_sequence.py",
        "examples/sequence_oracle.cpp",
        "examples/sequence_intent.py",
        "examples/llm_search.py",
        "examples/benchmark_llm_search.py",
    ]:
        identity["files_sha256"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    for name in identity["files_sha256"]:
        destination = output / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((root / name).read_bytes())
    protocol = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "provenance": identity,
        "model": model,
        "reasoning_effort": "high",
        "model_for_every_reasoning_role": model,
        "samples_per_policy": SAMPLES,
        "splits": SPLITS,
        "seed_bases": SEEDS,
        "cost_evaluations_per_program": BUDGET,
        "model_call_ceiling": 300,
        "concurrent_calls": WORKERS,
        "plan": "Astra operationalizes the broad goal before candidate search. Native ordinary pass, native meta pass, actual active-policy transfer, then fixed confirmation.",
        "primary_null": "Mean gain from revised instructions is at most the model-proposed, host-validated minimum worthwhile effect.",
        "confirmation": "Freeze instructions before final sampling. 32 independent generation draws per primary arm, each two programs selected on 16 fresh tuning workloads, then score 128 final workloads. No optional stopping or extra meta rounds.",
        "equal_call_control": "Original improver receives 129 calls (one pool of five and 31 pools of four), matching 97 meta-development calls plus 32 final revised-improver calls. Each pool selects its program only on final-generation workloads.",
        "analysis": "Two prespecified contrasts: revised minus ordinary; revised minus call-budget-matched original. Crossed bootstrap accounts for model draws and workloads; report 95% descriptive intervals and 97.5% intervals for the two-contrast family.",
        "safety": "Only host-interpreted JSON search programs; no model-generated code execution, tools or external effects.",
        "limits": [
            "Synthetic setup matrices, not measured factory throughput.",
            "The outer native loop governs proposer instructions. Inner program selection is a scoring proxy; separate native ordinary passes exercise full program adoption.",
            "Instruction revisions are measured even if rejected; active-policy results are distinguished.",
            "Model alias, not immutable weights; subscription dollar billing unavailable.",
        ],
    }
    write_json(output / "protocol.json", protocol)
    oracle = build_oracle(output / "oracle")
    data = {
        split: [workload(SEEDS[split] + i, i % 4) for i in range(count)]
        for split, count in SPLITS.items()
    }
    write_json(output / "workloads.json", data)
    problems = {
        split: [SequenceProblem(row, oracle) for row in rows] for split, rows in data.items()
    }
    sampler = CodexSampler(output / "model-calls", model, max_calls=300, reasoning_effort="high")
    try:
        baseline_quality = statistics.mean(
            p.optimal_cost / p.starting_cost for p in problems["generation"]
        )
        plan, accepted = operationalize(sampler, output, baseline_quality)
        study = ProgramStudy(output, problems, sampler, plan)
        print("INTENT ACCEPTED", json.dumps(plan), flush=True)
        initial = engine_pass(study, output, "ordinary-native", BASE_INSTRUCTIONS)
        print("ORDINARY NATIVE", json.dumps(initial), flush=True)
        before_meta = len(sampler.receipts)
        study.prepare(BASE_INSTRUCTIONS)
        proposer = MetaProposer(study)
        with LocalLearningStore(
            output / "meta-native",
            profile_id="program-improver",
            initial_configuration=BASE_INSTRUCTIONS,
        ) as store:
            loop = native_loop(store, MetaAdapter(study), proposer, plan, meta=True)

            def cases(split):
                return [
                    LearningCase(f"{split}-{i}", {"sample": i, "split": split})
                    for i in range(SAMPLES)
                ]

            for case in cases("scoring"):
                loop.run_task(case)
            result = loop.learn(
                "meta-1",
                shadow_cases=cases("shadow"),
                verification_cases=cases("verification"),
                activate=True,
            )
            if (
                result is None
                or store.pending_pass is not None
                or store.active != result.strategy_after
            ):
                raise RuntimeError("meta pass unfinished")
            active = dict(store.active.state)
            active_root = store.active.root
            evidence = {
                "native": result.native.to_dict(),
                "active": store.active.to_dict(),
                "choices": proposer.choices,
            }
            (output / "meta-native.json.gz").write_bytes(
                gzip.compress(json.dumps(evidence, sort_keys=True).encode(), mtime=0)
            )
        with LocalLearningStore(output / "meta-native", profile_id="program-improver") as store:
            assert store.active.root == active_root and dict(store.active.state) == active
        meta_calls = len(sampler.receipts) - before_meta
        assert meta_calls == 97
        candidates = []
        for instruction in [BASE_INSTRUCTIONS, *[c["configuration"] for c in proposer.choices]]:
            rows = study.prepare(instruction)
            values = [study.value(r["selected"], "scoring") for r in rows]
            candidates.append(
                {
                    "instruction": dict(instruction),
                    "mean": statistics.mean(values),
                    "samples": values,
                }
            )
        challenger = (
            active
            if result.adopted
            else max(candidates[1:], key=lambda r: r["mean"])["instruction"]
        )
        # This is a genuine later use of the reopened active improver, even when
        # the outcome was no change. It is not substituted for candidate testing.
        transfer = engine_pass(study, output, "after-meta-native", active)
        frozen = {
            "ordinary": BASE_INSTRUCTIONS,
            "challenger": challenger,
            "active": active,
            "active_root": active_root,
            "native_adopted": result.adopted,
            "native_disposition": result.disposition,
            "native_root": result.native.root,
            "training": candidates,
            "frozen_at_utc": datetime.now(UTC).isoformat(),
        }
        write_json(output / "frozen-policies.json", frozen)
        print(
            "FINAL POLICIES FROZEN",
            json.dumps(
                {
                    "adopted": result.adopted,
                    "disposition": result.disposition,
                    "training_means": [c["mean"] for c in candidates],
                }
            ),
            flush=True,
        )
        # Interleave final model requests across policies and pool groups.
        jobs = [(BASE_INSTRUCTIONS, "final", i) for i in range(129)] + [
            (challenger, "final", i) for i in range(SAMPLES)
        ]
        random.Random(2026111205).shuffle(jobs)
        study.diagnostics("final_generation")
        generated = bounded_parallel(jobs, study.generate)
        final = {}
        for row in generated:
            selected = study.finish_draw(row)
            final[(row["policy_key"], row["sample"])] = selected
        base_key = digest({"instruction": BASE_INSTRUCTIONS, "phase": "final"})
        meta_key = digest({"instruction": challenger, "phase": "final"})
        controls = []
        ordinary = []
        offset = 0
        for i in range(SAMPLES):
            size = 5 if i == 0 else 4
            group = [final[(base_key, j)] for j in range(offset, offset + size)]
            offset += size
            ordinary.append(group[0])
            controls.append(max(group, key=lambda r: r["selection_value"]))
        revised = [final[(meta_key, i)] for i in range(SAMPLES)]
        selected = {"ordinary": ordinary, "revised": revised, "equal_calls": controls}
        write_json(output / "frozen-programs.json", selected)
        study.final_frozen = True
        frozen_calls = len(sampler.receipts)
        grids = {
            name: [
                [r[plan["metric"]] for r in study.measured(draw["selected"], "test")]
                for draw in rows
            ]
            for name, rows in selected.items()
        }
        assert len(sampler.receipts) == frozen_calls
        families = [p.data["family"] for p in problems["test"]]
        contrasts = {
            name: interval(grids, name, "revised", families) for name in ("ordinary", "equal_calls")
        }
        baseline = [execute(BASE_PROGRAM, p)[plan["metric"]] for p in problems["test"]]
        fixed = []
        for p in problems["test"]:
            fixed_cost = cost(p.matrix, local_search(p.matrix, p.starting_order))
            fixed.append(
                p.optimal_cost / fixed_cost
                if plan["metric"] == "quality"
                else 1 - fixed_cost / p.starting_cost
            )
        report = {
            "protocol": protocol,
            "intent_root": accepted.root,
            "model_plan": plan,
            "ordinary_native": initial,
            "transfer_native": transfer,
            "frozen_policies": frozen,
            "scores": grids,
            "contrasts": contrasts,
            "baseline_scores": baseline,
            "fixed_local_search_scores": fixed,
            "means": {name: float(np.asarray(grid).mean()) for name, grid in grids.items()},
            "program_evaluations": {
                f"{key[0]}:{key[1]}": value for key, value in study.measurements.items()
            },
            "effort": {
                "model_calls": len(sampler.receipts),
                "meta_development_calls": meta_calls,
                "ordinary_confirmation_calls": 32,
                "revised_confirmation_calls": 32,
                "equal_call_original_total": 129,
                "meta_plus_confirmation_total": meta_calls + 32,
                "input_output_tokens": sum(
                    u["input_tokens"] + u["output_tokens"]
                    for r in sampler.receipts
                    for u in r["usage"]
                ),
                "usage": usage_total(sampler.receipts),
                "program_executions": study.program_executions,
                "cost_evaluations": study.cost_evaluations,
                "total_wall_seconds": perf_counter() - started,
                "python_cpu_seconds": process_time() - cpu,
                "provider_cost_usd": None,
            },
            "receipts": sampler.receipts,
        }
        write_json(output / "report.json", report)
        print(
            "FINAL",
            json.dumps(
                {"means": report["means"], "contrasts": contrasts, "effort": report["effort"]}
            ),
            flush=True,
        )
    finally:
        write_json(output / "model-receipts.json", sampler.receipts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    run(args.output, args.model)
