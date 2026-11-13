"""Resume the exact native experiment after process interruption, without new samples.

Completed outcomes must match their durable native stores. Pending workflows
resume through libRSI's normal recovery path. Existing model responses must
match the exact request; an unfinished provider call requires manual diagnosis.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import statistics
import subprocess
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import benchmark_native_sequence as native
import numpy as np
from benchmark_document_search import write_json
from benchmark_llm_search import usage_total
from benchmark_setup_sequence import interval
from llm_search import CodexSampler
from sequence_program import execute
from setup_sequence import build_oracle

from librsi import LocalLearningStore, record_from_dict
from librsi.identity import digest


class ExistingSampler(CodexSampler):
    def __init__(self, source, protocol):
        self.directory = source / "model-calls"
        self.model = protocol["model"]
        self.reasoning_effort = protocol["reasoning_effort"]
        self.max_calls = protocol["model_call_limit"]
        self.timeout_seconds = protocol["model_timeout_seconds"]
        self._lock = Lock()
        self.version = subprocess.check_output(["codex", "--version"], text=True).strip()
        self.instructions = self.directory / "instructions.txt"
        assert self.instructions.is_file()
        paths = sorted(self.directory.glob("[0-9][0-9][0-9]"))
        self.receipts = []
        self.recorded: dict[str, tuple[Path, dict[str, Any]]] = {}
        for number, path in enumerate(paths, 1):
            receipt = json.loads((path / "receipt.json").read_text())
            if receipt.get("returncode") != 0 or len(receipt.get("usage", [])) != 1:
                raise ValueError(f"unfinished provider call {path}; diagnose before resuming")
            assert receipt["number"] == number and path.name == f"{number:03d}"
            assert receipt["role"] not in self.recorded
            self.receipts.append(receipt)
            self.recorded[receipt["role"]] = (path, receipt)

    def call(self, prompt, *, field, role, count=2):
        if role not in self.recorded:
            return super().call(prompt, field=field, role=role, count=count)
        path, receipt = self.recorded[role]
        assert receipt["model"] == self.model
        assert receipt["reasoning_effort"] == self.reasoning_effort
        assert receipt["tool_items"] == 0 and receipt["candidate_count"] == count
        assert receipt["prompt_sha256"] == digest(prompt)
        assert (path / "prompt.txt").read_text() == prompt
        response = json.loads((path / "response.json").read_text())
        choices = response["candidates"]
        assert len(choices) == count
        assert all(set(c["configuration"]) == {field} for c in choices)
        return choices


def completed_row(job):
    output, label, choices, instruction, _problems, phase = job
    path = output / "runs" / f"{label}.json"
    if not path.exists():
        return None
    row = json.loads(path.read_text())
    assert row["label"] == label and row["phase"] == phase
    assert row["choices"] == choices and row["instruction"] == instruction
    evidence = json.loads(gzip.decompress((output / "native" / f"{label}.json.gz").read_bytes()))
    with LocalLearningStore(output / "stores" / label, profile_id=label) as store:
        assert store.pending_pass is None
        assert store.active.root == row["active_root"]
        assert dict(store.active.state) == row["configuration"]
        inputs = store.pass_input("optimize")
        result = store.cached("optimize", "result")
        assert inputs is not None and result is not None
        assert inputs.root == record_from_dict(evidence["inputs"]).root
        assert result.root == row["native_root"]
    assert record_from_dict(evidence["active"]).root == row["active_root"]
    assert evidence["native"]["root"] == row["native_root"]
    return row


class ResumingStudy(native.Study):
    def run_jobs(self, specs):
        jobs: list[tuple] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for start in range(0, len(specs), 2):
                jobs.extend(pool.map(lambda job: self.generate(*job), specs[start : start + 2]))
        rows, pending = [], []
        for job in jobs:
            row = completed_row(job)
            if row is None:
                pending.append(job)
            else:
                rows.append(row)
        print(f"RESUME: {len(rows)} durable completed runs, {len(pending)} remaining", flush=True)
        with ProcessPoolExecutor(max_workers=native.NATIVE_WORKERS) as pool:
            rows.extend(pool.map(native.scheduler_run, pending))
        return sorted(rows, key=lambda row: row["label"])


def run(source):
    protocol = json.loads((source / "protocol.json").read_text())
    root = Path(__file__).resolve().parents[1]
    # The experiment and runtime remain byte-identical. Only this recovery
    # orchestrator and offline analysis files were added after the source freeze.
    for name in (
        "examples/benchmark_native_sequence.py",
        "examples/llm_search.py",
        "examples/recorded_codex_sampler.py",
        "examples/sequence_program.py",
        "examples/setup_sequence.py",
        "examples/benchmark_setup_sequence.py",
        "examples/benchmark_document_search.py",
    ):
        assert (
            hashlib.sha256((root / name).read_bytes()).hexdigest()
            == protocol["provenance"]["files_sha256"][name]
        ), name
    runtime = hashlib.sha256()
    for path in sorted((root / "src/librsi").rglob("*.py")):
        runtime.update(
            path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0"
        )
    assert runtime.hexdigest() == protocol["provenance"]["runtime_python_sha256"]
    if (source / "report.json.gz").exists():
        raise ValueError("complete report already exists; use the offline audit")
    recovery = {
        "resumed_at": datetime.now(UTC).isoformat(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "completed_native_runs": len(list((source / "runs").glob("*.json"))),
        "rule": "Preserve completed outcomes after durable-store validation; resume pending native workflows; exact provider responses counted once; unchanged source, samples, thresholds and analysis.",
        "wall_time": "End-to-end elapsed time includes interruption and recovery pauses.",
    }
    recovery_dir = source / "recovery"
    recovery_dir.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    write_json(recovery_dir / f"{stamp}.json", recovery)
    (recovery_dir / f"{stamp}.py").write_bytes(Path(__file__).read_bytes())
    data = json.loads((source / "workloads.json").read_text())
    oracle = source / "oracle"
    if not oracle.exists():
        oracle = build_oracle(oracle)
    problems = {
        split: [native.fresh_problem(row, oracle) for row in rows] for split, rows in data.items()
    }
    sampler = ExistingSampler(source, protocol)
    study = ResumingStudy(source, problems, sampler)
    try:
        study.prepare(native.BASE_INSTRUCTIONS)
        meta_choices = []
        if "meta-revise-improver" in sampler.recorded:
            path, _receipt = sampler.recorded["meta-revise-improver"]
            meta_choices = json.loads((path / "response.json").read_text())["candidates"]
            for choice in meta_choices:
                study.prepare(choice["configuration"])
        if (source / "frozen-improver.json").exists():
            meta = json.loads((source / "frozen-improver.json").read_text())
            with LocalLearningStore(source / "stores/meta", profile_id="meta") as store:
                assert store.pending_pass is None and store.active.root == meta["active_root"]
        else:
            meta = native.meta_run(study)
            if not meta["choices"]:
                assert len(meta_choices) == 2
                meta["choices"] = meta_choices
                write_json(source / "frozen-improver.json", meta)
        print("META FROZEN", json.dumps(meta), flush=True)
        instructions = {"ordinary": native.BASE_INSTRUCTIONS, "after_meta": meta["active"]}
        if not meta["adopted"]:
            candidate = max(
                meta["choices"],
                key=lambda c: statistics.mean(
                    r["evaluation"]["meta_train"]
                    for r in study.development[digest(c["configuration"])][:8]
                ),
            )
            instructions["forced_revision_diagnostic"] = candidate["configuration"]
        write_json(source / "final-instructions.json", instructions)
        jobs = [
            (instruction, "final", f"{arm}-{i:02d}")
            for arm, instruction in instructions.items()
            for i in range(native.N_FINAL)
        ]
        random.Random(2026111209).shuffle(jobs)
        rows = study.run_jobs(jobs)
        write_json(source / "frozen-final-systems.json", rows)
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
        assert all(len(grid) == native.N_FINAL for grid in scores.values())
        assert len(sampler.receipts) == (137 if meta["adopted"] else 169)
        prior_seconds = 0.0
        if protocol["reused_proposals_from"]:
            prior = source.parent / protocol["reused_proposals_from"]
            start = datetime.fromisoformat(
                json.loads((prior / "protocol.json").read_text())["created_at"]
            ).timestamp()
            prior_seconds = max(
                (prior / "model-calls" / f"{r['reused_from']['number']:03d}" / "receipt.json")
                .stat()
                .st_mtime
                - start
                for r in sampler.receipts
                if "reused_from" in r
            )
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
                "wall_seconds": datetime.now(UTC).timestamp()
                - datetime.fromisoformat(protocol["created_at"]).timestamp(),
                "wall_time_includes_interruptions": True,
                "reused_model_calls": sum("reused_from" in r for r in sampler.receipts),
                "prior_generation_wall_seconds": prior_seconds,
                "native_inner_runs": 72 + len(rows),
                "native_outer_runs": 1,
                "provider_cost_usd": None,
            },
            "test_baseline_costs": [p.starting_cost for p in problems["test"]],
            "test_optimal_costs": [p.optimal_cost for p in problems["test"]],
            "recovery": [json.loads(p.read_text()) for p in sorted(recovery_dir.glob("*.json"))],
        }
        native.dump_gz(source / "report.json.gz", report)
        summary = {
            k: report[k] for k in ("means", "adoptions", "primary_contrast", "effort", "meta")
        }
        write_json(source / "summary.json", summary)
        print("COMPLETE", json.dumps(summary), flush=True)
    finally:
        write_json(source / "receipts.json", sampler.receipts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    run(parser.parse_args().source.resolve())
