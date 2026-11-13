"""Native Astra meta-meta selection, fresh downward propagation, and final scoring."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import statistics
import subprocess
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import benchmark_native_sequence as native
import numpy as np
from benchmark_document_search import write_json
from benchmark_llm_search import usage_total
from checkpoint_codex_sampler import CheckpointSampler
from compact_benchmark_store import pack_store, unpacked_store
from llm_search import validate_instructions
from resume_native_sequence import completed_row
from sequence_program import BASE_INSTRUCTIONS, execute
from setup_sequence import build_oracle, workload

from librsi import LearningCase, LocalLearningStore
from librsi.identity import canonical_json, digest

MAX_INNER = 512
MAX_LOGICAL_CALLS = 518
GIB = 1024**3
NEW_SPACE = 3 * GIB
ROOT = Path(__file__).resolve().parents[1]


def capacity(output, *, initial=False):
    subprocess.run(
        ["/srv/patent-studio/tooling/bin/patent-storage-preflight"],
        check=True,
        capture_output=True,
        text=True,
    )
    fs = os.statvfs(output.parent)
    available = fs.f_bavail * fs.f_frsize
    completed = 0 if initial else len(list(output.glob("phases/*/store-archives/*.tar.gz.json")))
    # Four MiB per remaining compressed run plus one GiB for active stores,
    # model transcripts, upper gates, source snapshots, and publication work.
    needed = max(GIB, NEW_SPACE - completed * 4 * 1024**2)
    if available - 8 * GIB < needed:
        raise RuntimeError(
            f"Insufficient study capacity: available={available}, hard_reserve={8 * GIB}, "
            f"new_work_required={needed}. Preserve evidence; restore capacity before running."
        )


def source_hashes():
    paths = sorted((ROOT / "src/librsi").rglob("*.py")) + sorted((ROOT / "examples").glob("*.py"))
    paths += [ROOT / "examples/sequence_oracle.cpp"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def interval(grids, left, right, families, *, seed):
    """Crossed uncertainty for the registered 32-draw, 512-workload panel."""
    a, b = np.asarray(grids[left]), np.asarray(grids[right])
    assert a.shape == b.shape == (32, 512)
    assert len(families) == 512 and set(families) == set(range(4))
    rng = np.random.default_rng(seed)
    family_indices = [np.flatnonzero(np.asarray(families) == i) for i in range(4)]
    draws = []
    for _ in range(10000):
        tasks = np.concatenate([rng.choice(ids, len(ids), replace=True) for ids in family_indices])
        ai, bi = rng.integers(0, 32, 32), rng.integers(0, 32, 32)
        draws.append(float(b[bi][:, tasks].mean() - a[ai][:, tasks].mean()))
    return {
        "mean_effect": float(b.mean() - a.mean()),
        "bootstrap_95_percentile": np.quantile(draws, [0.025, 0.975]).tolist(),
        "method": "10000 crossed bootstrap draws: independent model draws by arm; shared workload draws stratified by four families",
        "model_samples_per_arm": 32,
        "independent_workloads": 512,
    }


def prior_development(directory):
    manifest = json.loads((directory / "evidence-manifest.json").read_text())
    for name in ("report.json.gz", "model-transcripts.json.gz"):
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == manifest[name]
    report = json.loads(gzip.decompress((directory / "report.json.gz").read_bytes()))
    transcripts = json.loads(
        gzip.decompress((directory / "model-transcripts.json.gz").read_bytes())
    )
    original = next(
        t["prompt"] for t in transcripts if t["receipt"]["role"] == "meta-revise-improver"
    )
    original = {"instruction": original.split("\nPROGRAM CONTRACT:\n")[0]}
    validate_instructions(original)
    # Deliberately omit every previous final score, test workload and forced diagnostic.
    feedback = {
        "original_meta_instruction": original,
        "meta_disposition": report["meta"]["disposition"],
        "development": report["development"],
        "proposed_optimizer_instructions": report["meta"]["choices"],
        "source_report_sha256": manifest["report.json.gz"],
        "scope": "Previously completed development evidence only; no final-test data.",
    }
    return original, feedback


def training_detail(rows):
    return [
        {
            "choices": r["choices"],
            "adopted": r["adopted"],
            "disposition": r["disposition"],
            "retained_configuration": r["configuration"],
            "retained_cost_reduction": r["evaluation"]["meta_train"],
        }
        for r in rows[:8]
    ]


def meta_prompt(instruction, rows):
    return (
        instruction["instruction"]
        + "\nPROGRAM CONTRACT:\n"
        + native.CONTRACT
        + "\nORIGINAL INSTRUCTION:\n"
        + BASE_INSTRUCTIONS["instruction"]
        + "\nACTUAL NATIVE TRAINING RUNS:\n"
        + canonical_json(training_detail(rows))
    )


def valid_instruction(configuration):
    try:
        validate_instructions(configuration)
        return True
    except (ValueError, TypeError):
        return False


def proposals(sampler, prompt, label):
    try:
        return sampler.call(prompt, field="instruction", role=label)
    except ValueError as error:
        return [
            {
                "configuration": {"invalid_output": str(error), "slot": i},
                "reason": "Invalid completed model output; slot consumed",
            }
            for i in range(2)
        ]


class Phase(native.Study):
    def __init__(self, root, tag, problems, sampler):
        output = root / "phases" / tag
        for folder in ("native", "runs", "proposals"):
            (output / folder).mkdir(parents=True, exist_ok=True)
        super().__init__(output, problems, sampler)
        self.root, self.tag = root, tag

    def prepare(self, instruction):
        key = digest(instruction)
        if key not in self.development:
            specs = [
                (instruction, "development", f"{self.tag}-{key[:12]}-{i:02d}") for i in range(24)
            ]
            self.development[key] = self.run_jobs(specs)
        return self.development[key]

    def run_jobs(self, specs):
        capacity(self.root)
        generated: list[tuple] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for start in range(0, len(specs), 2):
                capacity(self.root)
                generated.extend(
                    pool.map(lambda job: self.generate(*job), specs[start : start + 2])
                )
        rows, pending = [], []
        for job in generated:
            row = compact_completed_row(job)
            if row is None:
                pending.append(job)
            else:
                rows.append(row)
        print(
            f"PHASE {self.tag}: {len(rows)} recovered, {len(pending)} new native runs", flush=True
        )
        with ProcessPoolExecutor(max_workers=2) as pool:
            for start in range(0, len(pending), 2):
                capacity(self.root)
                rows.extend(pool.map(compact_scheduler_run, pending[start : start + 2]))
        return sorted(rows, key=lambda r: r["label"])


def compact_scheduler_run(job):
    row = native.scheduler_run(job)
    output, label = job[:2]
    pack_store(output / "stores" / label, output / "store-archives" / f"{label}.tar.gz")
    return row


def compact_completed_row(job):
    output, label = job[:2]
    archive = output / "store-archives" / f"{label}.tar.gz"
    if not archive.exists():
        row = completed_row(job)
        if row is not None:
            pack_store(output / "stores" / label, archive)
        return row
    # Finish an interrupted archive commit/removal before opening a temporary copy.
    pack_store(output / "stores" / label, archive)
    with unpacked_store(archive, output / "stores" / label) as restored:
        row = json.loads((output / "runs" / f"{label}.json").read_text())
        assert row["choices"] == job[2] and row["instruction"] == job[3] and row["phase"] == job[5]
        evidence = json.loads(
            gzip.decompress((output / "native" / f"{label}.json.gz").read_bytes())
        )
        with LocalLearningStore(restored, profile_id=label) as store:
            assert store.pending_pass is None and store.active.root == row["active_root"]
            assert dict(store.active.state) == row["configuration"]
            result, inputs = store.cached("optimize", "result"), store.pass_input("optimize")
            assert result is not None and result.root == row["native_root"]
            assert inputs is not None and inputs.root == evidence["inputs"]["root"]
        assert evidence["active"]["root"] == row["active_root"]
        assert evidence["native"]["root"] == row["native_root"]
        return row


class CascadeAdapter:
    adapter_id = "native-meta-meta-cascade-v1"
    validate_configuration = staticmethod(validate_instructions)

    def __init__(self, study, children):
        self.inner = native.MetaAdapter(study)
        self.children = children

    def evaluate(self, configuration, case):
        # Only the child pass's actual retained optimizer may drive the top-level utility.
        active = self.children[digest(configuration)]["active"]
        return self.inner.evaluate(active, case)


def gate(output, label, baseline, choices, adapter):
    path = output / "gates" / f"{label}.json"
    store_path = output / "gate-stores" / label
    if path.exists():
        row = json.loads(path.read_text())
        assert row["choices"] == choices and row["initial"] == baseline
        with LocalLearningStore(store_path, profile_id=label) as store:
            result = store.cached("improve", "result")
            assert store.pending_pass is None and store.active.root == row["active_root"]
            assert dict(store.active.state) == row["active"]
            assert result is not None and result.root == row["native_root"]
        return row

    def cases(stage):
        return [
            LearningCase(f"{label}-{stage}-{i}", {"split": f"meta_{stage}", "group": i})
            for i in range(2)
        ]

    with LocalLearningStore(store_path, profile_id=label, initial_configuration=baseline) as store:
        loop = native.native_loop(store, adapter, native.FixedProposer(choices), meta=True)
        for case in cases("train"):
            loop.run_task(case)
        result = loop.learn(
            "improve",
            shadow_cases=cases("shadow"),
            verification_cases=cases("verify"),
            activate=True,
        )
        assert result is not None and store.pending_pass is None
        assert store.active == result.strategy_after
        inputs = store.pass_input("improve")
        assert inputs is not None
        row = {
            "label": label,
            "initial": baseline,
            "choices": choices,
            "active": dict(store.active.state),
            "adopted": result.adopted,
            "disposition": result.disposition,
            "active_root": store.active.root,
            "native_root": result.native.root,
        }
        native.dump_gz(
            output / "native-gates" / f"{label}.json.gz",
            {
                "native": result.native.to_dict(),
                "active": store.active.to_dict(),
                "inputs": inputs.to_dict(),
            },
        )
    with LocalLearningStore(store_path, profile_id=label) as store:
        assert store.active.root == row["active_root"] and dict(store.active.state) == row["active"]
    write_json(path, row)
    print("GATE", label, row["disposition"], flush=True)
    return row


def child_meta(output, phase, instruction, label):
    choices = proposals(
        phase.sampler, meta_prompt(instruction, phase.prepare(BASE_INSTRUCTIONS)), label
    )
    for choice in choices:
        if valid_instruction(choice["configuration"]):
            phase.prepare(choice["configuration"])
    return gate(output, label, BASE_INSTRUCTIONS, choices, native.MetaAdapter(phase))


def make_problems(output, name, seed, oracle, *, final=False):
    splits = (
        ["final_train", "final_shadow", "final_verify"]
        if final
        else ["dev_train", "dev_shadow", "dev_verify", "meta_train", "meta_shadow", "meta_verify"]
    )
    data = {
        split: [workload(seed + j * 1000 + i, i % 4) for i in range(32)]
        for j, split in enumerate(splits)
    }
    path = output / "workloads" / f"{name}.json"
    if path.exists():
        assert json.loads(path.read_text()) == data
    else:
        write_json(path, data)
    return {
        split: [native.fresh_problem(row, oracle) for row in rows] for split, rows in data.items()
    }


def meta_meta_prompt(original, prior, base_rows):
    concise_prior = []
    base_key = digest(BASE_INSTRUCTIONS)
    base = prior["development"][base_key]
    for choice in prior["proposed_optimizer_instructions"]:
        rows = prior["development"][digest(choice["configuration"])]
        effects = {}
        for stage, offset in (("meta_train", 0), ("meta_shadow", 8), ("meta_verify", 16)):
            effects[stage] = statistics.mean(
                rows[i]["evaluation"][stage] - base[i]["evaluation"][stage]
                for i in range(offset, offset + 8)
            )
        concise_prior.append(
            {"instruction": choice["configuration"], "development_effects": effects}
        )
    return (
        "You are improving the META OPTIMIZER: the instruction that guides another gpt-6-astra/high call "
        "to propose two revised ordinary-optimizer instructions. Those ordinary optimizers then propose "
        'scheduling search programs. Return exactly TWO distinct configurations {"instruction":"..."}, '
        "each at most 3000 characters, with brief reasons. Improve the method for diagnosing evidence and "
        "designing optimizer revisions, not the model, scoring, data, native gates or execution budget. "
        "The downstream model must still return exactly two ordinary instruction candidates, at most 3000 "
        "characters each. Your instructions will be tested by complete native child meta passes and fresh "
        "native optimizer runs. Utility is the performance of ACTUALLY RETAINED systems, including rejection. "
        "Seek at least +0.5 percentage points in retained setup-cost reduction. That is a target, not a proven gain. "
        "You may learn from failed development revisions, but cannot assume that adding constraints, stages "
        "or recursion helps. There is no final-test feedback.\nORIGINAL META INSTRUCTION:\n"
        + original["instruction"]
        + "\nPROGRAM CONTRACT:\n"
        + native.CONTRACT
        + "\nEARLIER META DEVELOPMENT (not final test):\n"
        + canonical_json(concise_prior)
        + "\nNEW ORIGINAL-OPTIMIZER TRAINING EXAMPLES:\n"
        + canonical_json(training_detail(base_rows))
    )


def run(output, prior_directory):
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    capacity(output, initial=not output.exists())
    output.mkdir(exist_ok=True)
    for folder in ("gates", "native-gates", "workloads", "source"):
        (output / folder).mkdir(exist_ok=True)
    hashes = source_hashes()
    protocol_path = output / "protocol.json"
    if protocol_path.exists():
        protocol = json.loads(protocol_path.read_text())
        assert protocol["source_sha256"] == hashes, "source changed since study registration"
    else:
        protocol = {
            "created_at": datetime.now(UTC).isoformat(),
            "model": "gpt-6-astra",
            "reasoning_effort": "high",
            "model_roles": ["optimizer", "meta-optimizer", "meta-meta-optimizer"],
            "source_sha256": hashes,
            "final_samples_per_arm": 32,
            "test_workloads": 512,
            "maximum_native_inner_runs": MAX_INNER,
            "maximum_logical_calls": MAX_LOGICAL_CALLS,
            "extra_timeout_attempts": 8,
            "storage": {
                "required_initial_bytes_above_reserve": NEW_SPACE,
                "closed_inner_stores": "Lossless tar.gz with per-file SHA-256 and verified restoration; full records retained",
                "working_copy_removal": "Only after archive verification and durable receipt; original earlier studies unchanged",
            },
            "timeout_seconds": 600,
            "seed_bases": {
                "development": 900000,
                "upper": 906000,
                "propagation": 912000,
                "final": 918000,
                "test": 921000,
            },
            "analysis": "Primary: after_meta_meta minus after_meta, 10000 crossed bootstrap draws, 95% interval; conditional on one meta-meta training round and one fresh propagation per arm.",
            "forced_diagnostic": "Best proposed meta policy by upper training; then its proposed optimizer with best child training; bypass upper adoption, retain all inner native gates.",
            "limits": "Synthetic setup costs; no equal-compute control; model alias is not immutable weights; repeated final draws do not repeat meta-meta training.",
        }
        write_json(protocol_path, protocol)
        for name in hashes:
            target = output / "source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        (output / "protocol.md").write_bytes(
            (ROOT / "docs/meta-meta-sequence-protocol.md").read_bytes()
        )
    if (output / "report.json.gz").exists():
        raise ValueError("Completed report already exists; audit it rather than restarting")
    original, prior = prior_development(prior_directory)
    write_json(output / "prior-development.json", prior)
    sampler = CheckpointSampler(output / "model-calls")
    oracle = output / "oracle"
    if not oracle.exists():
        build_oracle(oracle)
    try:
        development = Phase(
            output, "development", make_problems(output, "development", 900000, oracle), sampler
        )
        base = development.prepare(BASE_INSTRUCTIONS)
        upper_choices = proposals(
            sampler, meta_meta_prompt(original, prior, base), "meta-meta-proposals"
        )
        write_json(output / "meta-meta-proposals.json", upper_choices)
        children = {
            digest(original): child_meta(output, development, original, "develop-original-meta")
        }
        valid_choices = [c for c in upper_choices if valid_instruction(c["configuration"])]
        for i, choice in enumerate(valid_choices, 1):
            key = digest(choice["configuration"])
            if key not in children:
                children[key] = child_meta(
                    output, development, choice["configuration"], f"develop-proposed-meta-{i}"
                )
        upper = Phase(output, "upper", make_problems(output, "upper", 906000, oracle), sampler)
        upper.prepare(BASE_INSTRUCTIONS)
        for row in children.values():
            upper.prepare(row["active"])
        top = gate(output, "meta-meta", original, upper_choices, CascadeAdapter(upper, children))
        write_json(output / "frozen-meta-optimizer.json", top)

        propagation = Phase(
            output, "propagation", make_problems(output, "propagation", 912000, oracle), sampler
        )
        control = child_meta(output, propagation, original, "propagate-original-meta")
        treatment = child_meta(output, propagation, top["active"], "propagate-retained-meta")
        instructions = {
            "ordinary": BASE_INSTRUCTIONS,
            "after_meta": control["active"],
            "after_meta_meta": treatment["active"],
        }
        if valid_choices:
            chosen_meta = max(
                valid_choices,
                key=lambda c: statistics.mean(
                    r["evaluation"]["meta_train"]
                    for r in upper.prepare(children[digest(c["configuration"])]["active"])[:8]
                ),
            )
            child = children[digest(chosen_meta["configuration"])]
            child_choices = [c for c in child["choices"] if valid_instruction(c["configuration"])]
            if child_choices:
                chosen_optimizer = max(
                    child_choices,
                    key=lambda c: statistics.mean(
                        r["evaluation"]["meta_train"]
                        for r in development.prepare(c["configuration"])[:8]
                    ),
                )
                instructions["forced_cascade_diagnostic"] = chosen_optimizer["configuration"]
        write_json(
            output / "frozen-final-instructions.json",
            {
                "instructions": instructions,
                "meta_meta": top,
                "original_meta_propagation": control,
                "meta_meta_propagation": treatment,
            },
        )
        final = Phase(
            output, "final", make_problems(output, "final", 918000, oracle, final=True), sampler
        )
        specs = [
            (instruction, "final", f"{arm}-{i:02d}")
            for arm, instruction in instructions.items()
            for i in range(32)
        ]
        random.Random(2026111307).shuffle(specs)
        rows = final.run_jobs(specs)
        write_json(output / "frozen-final-systems.json", rows)
        data = [workload(921000 + i, i % 4) for i in range(512)]
        write_json(output / "workloads/test.json", data)
        test = [native.fresh_problem(row, oracle) for row in data]
        scores = {
            arm: [
                [execute(r["configuration"], p)["cost_reduction"] for p in test]
                for r in rows
                if r["label"].startswith(arm + "-")
            ]
            for arm in instructions
        }
        families = [p.data["family"] for p in test]
        primary = interval(scores, "after_meta", "after_meta_meta", families, seed=2026111309)
        report = {
            "protocol": protocol,
            "meta_meta": top,
            "children": children,
            "propagation": {"original_meta": control, "retained_meta": treatment},
            "instructions": instructions,
            "runs": rows,
            "scores": scores,
            "primary_contrast": primary,
            "means": {k: float(np.mean(v)) for k, v in scores.items()},
            "development": {
                phase.tag: phase.development for phase in (development, upper, propagation)
            },
            "adoptions": {
                arm: sum(r["adopted"] for r in rows if r["label"].startswith(arm + "-"))
                for arm in instructions
            },
            "test_baseline_costs": [p.starting_cost for p in test],
            "test_optimal_costs": [p.optimal_cost for p in test],
            "effort": {
                "attempts": len(sampler.receipts),
                "logical_calls": len(sampler.roles),
                "timeout_attempts": sum(r.get("status") == "timeout" for r in sampler.receipts),
                "usage": usage_total(sampler.receipts),
                "native_inner_runs": len(list(output.glob("phases/*/runs/*.json"))),
                "native_upper_passes": len(list((output / "gates").glob("*.json"))),
                "wall_seconds": datetime.now(UTC).timestamp()
                - datetime.fromisoformat(protocol["created_at"]).timestamp(),
                "provider_cost_usd": None,
            },
        }
        report["exploratory_contrasts"] = {
            arm: interval(scores, "ordinary", arm, families, seed=2026111310 + i)
            for i, arm in enumerate(instructions)
            if arm != "ordinary"
        }
        archives = [
            json.loads(path.read_text())
            for path in output.glob("phases/*/store-archives/*.tar.gz.json")
        ]
        assert len(archives) == report["effort"]["native_inner_runs"]
        report["storage"] = {
            "complete_inner_store_archives": len(archives),
            "uncompressed_bytes": sum(row["uncompressed_bytes"] for row in archives),
            "archive_bytes": sum(row["archive_bytes"] for row in archives),
            "all_records_retained": True,
            "initial_working_space_requirement_bytes": NEW_SPACE,
        }
        native.dump_gz(output / "report.json.gz", report)
        write_json(
            output / "summary.json",
            {key: report[key] for key in ("means", "adoptions", "primary_contrast", "effort")},
        )
        print(
            "COMPLETE",
            canonical_json({key: report[key] for key in ("means", "primary_contrast", "effort")}),
            flush=True,
        )
    finally:
        write_json(output / "receipts.json", sampler.receipts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior", type=Path, default=ROOT / "docs/benchmarks/native-sequence")
    args = parser.parse_args()
    run(args.output, args.prior.resolve())
