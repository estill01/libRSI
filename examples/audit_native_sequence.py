"""Replay retained-system scores, audit provenance, and export public evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
import shutil
from pathlib import Path

import numpy as np
from benchmark_document_search import write_json
from benchmark_native_sequence import BASE_INSTRUCTIONS, BASE_PROGRAM, MODEL, fresh_problem
from benchmark_setup_sequence import interval
from sequence_program import execute
from setup_sequence import build_oracle

from librsi import Observation, TargetSnapshot, record_from_dict
from librsi.identity import digest


def load_gz(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def dump_gz(path, value):
    path.write_bytes(gzip.compress(json.dumps(value, sort_keys=True).encode(), mtime=0))


def export_native(source, destination):
    raw = gzip.decompress(source.read_bytes())
    encoded = lzma.compress(raw, preset=3)
    assert lzma.decompress(encoded) == raw
    destination.write_bytes(encoded)


def audit(source, output):
    output.mkdir(parents=True, exist_ok=False)
    report = load_gz(source / "report.json.gz")
    protocol = json.loads((source / "protocol.json").read_text())
    assert report["protocol"] == protocol
    for name, expected in protocol["provenance"]["files_sha256"].items():
        path = source / "source" / name
        if not path.exists():
            # The shared provenance helper includes a static split resource.
            path = Path(__file__).resolve().parents[1] / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    runtime = hashlib.sha256()
    for path in sorted((source / "source/src/librsi").rglob("*.py")):
        runtime.update(
            path.relative_to(source / "source").as_posix().encode()
            + b"\0"
            + path.read_bytes()
            + b"\0"
        )
    assert runtime.hexdigest() == protocol["provenance"]["runtime_python_sha256"]
    receipts = json.loads((source / "receipts.json").read_text())
    expected_calls = 137 if report["meta"]["adopted"] else 169
    assert len(receipts) == expected_calls == report["effort"]["model_calls"]
    transcripts = []
    roles = set()
    test_data = json.loads((source / "workloads.json").read_text())
    ids = [r["id"] for rows in test_data.values() for r in rows]
    assert len(ids) == len(set(ids))
    for receipt in receipts:
        assert receipt["model"] == MODEL and receipt["reasoning_effort"] == "high"
        assert receipt["tool_items"] == 0 and receipt["returncode"] == 0
        assert len(receipt["usage"]) == 1
        assert receipt["role"] not in roles
        if "reused_from" in receipt:
            original = {k: v for k, v in receipt.items() if k != "reused_from"}
            original["number"] = receipt["reused_from"]["number"]
            assert digest(original) == receipt["reused_from"]["original_receipt_sha256"]
        roles.add(receipt["role"])
        call = source / "model-calls" / f"{receipt['number']:03d}"
        prompt = (call / "prompt.txt").read_text()
        assert digest(prompt) == receipt["prompt_sha256"]
        assert all(row["id"] not in prompt for row in test_data["test"])
        transcripts.append(
            {
                "receipt": receipt,
                "prompt": prompt,
                "response": json.loads((call / "response.json").read_text())
                if (call / "response.json").exists()
                else None,
            }
        )
    all_runs = [r for rows in report["development"].values() for r in rows] + report["runs"]
    assert len(all_runs) == 72 + 32 * (2 if report["meta"]["adopted"] else 3)
    assert {r["label"] for r in all_runs} == roles - {"meta-revise-improver"}
    native_dir = output / "native"
    native_dir.mkdir()
    for row in all_runs:
        evidence = load_gz(source / "native" / f"{row['label']}.json.gz")
        active = record_from_dict(evidence["active"])
        inputs = record_from_dict(evidence["inputs"])
        assert isinstance(active, TargetSnapshot) and isinstance(inputs, Observation)
        assert inputs.target_snapshot is not None
        assert active.root == row["active_root"] and dict(active.state) == row["configuration"]
        assert inputs.value["learning_version"] == 3
        assert dict(inputs.target_snapshot.state) == BASE_PROGRAM
        assert evidence["native"]["root"] == row["native_root"]
        assert row["adopted"] == (row["configuration"] != BASE_PROGRAM)
        if row["label"].startswith("after_meta-"):
            assert row["instruction"] == report["meta"]["active"]
        export_native(
            source / "native" / f"{row['label']}.json.gz", native_dir / f"{row['label']}.json.xz"
        )
    meta = load_gz(source / "native/meta.json.gz")
    assert record_from_dict(meta["active"]).root == report["meta"]["active_root"]
    assert meta["native"]["root"] == report["meta"]["native_root"]
    if not report["meta"]["adopted"]:
        assert report["meta"]["active"] == BASE_INSTRUCTIONS
    export_native(source / "native/meta.json.gz", native_dir / "meta.json.xz")
    oracle = build_oracle(output / "oracle")
    problems = {
        split: [fresh_problem(row, oracle) for row in rows]
        for split, rows in test_data.items()
        if split in ("meta_train", "meta_shadow", "meta_verify", "test")
    }
    cache = {}

    def values(config, split):
        key = (digest(config), split)
        if key not in cache:
            cache[key] = [execute(config, p)["cost_reduction"] for p in problems[split]]
        return cache[key]

    for rows in report["development"].values():
        for row in rows:
            for split, expected in row["evaluation"].items():
                assert np.isclose(
                    np.mean(values(row["configuration"], split)), expected, atol=1e-14, rtol=0
                )
    for arm, expected in report["scores"].items():
        actual = [
            values(row["configuration"], "test")
            for row in report["runs"]
            if row["label"].startswith(arm + "-")
        ]
        assert np.allclose(actual, expected, atol=1e-14, rtol=0)
        assert float(np.mean(actual)) == report["means"][arm]
        assert (
            sum(row["adopted"] for row in report["runs"] if row["label"].startswith(arm + "-"))
            == report["adoptions"][arm]
        )
    contrast = interval(
        report["scores"],
        "ordinary",
        "after_meta",
        [p.data["family"] for p in problems["test"]],
        seed=2026111210,
    )
    assert contrast == report["primary_contrast"]
    assert report["runs"] == json.loads((source / "frozen-final-systems.json").read_text())
    for name in (
        "protocol.json",
        "workloads.json",
        "report.json.gz",
        "summary.json",
        "frozen-improver.json",
        "final-instructions.json",
        "frozen-final-systems.json",
        "receipts.json",
    ):
        shutil.copyfile(source / name, output / name)
    dump_gz(output / "model-transcripts.json.gz", transcripts)
    dump_gz(
        output / "executed-sources.json.gz",
        {
            str(p.relative_to(source / "source")): p.read_text()
            for p in sorted((source / "source").rglob("*"))
            if p.is_file()
        },
    )
    if (source / "recovery").exists():
        for receipt_path in sorted((source / "recovery").glob("*.json")):
            recovery = json.loads(receipt_path.read_text())
            script = receipt_path.with_suffix(".py")
            assert hashlib.sha256(script.read_bytes()).hexdigest() == recovery["source_sha256"]
        shutil.copytree(source / "recovery", output / "recovery")
    validation = {
        "all_reasoning": f"{MODEL}, high",
        "verified_model_calls": len(receipts),
        "verified_native_inner_outcomes": len(all_runs),
        "verified_native_meta_outcomes": 1,
        "score_replay": "all development retained systems on all three outer scoring splits, all final retained systems on all 128 test workloads",
        "native_validation": "recorded active snapshot and frozen starting snapshot identities checked; every native store was reopened by runner; no substitution of candidate scores",
        "test_workloads": 128,
        "primary_bootstrap_replayed": True,
        "source_hashes_verified": True,
        "scope": "Offline audit; zero additional model calls. Raw provider event streams and credentials excluded.",
    }
    write_json(output / "validation.json", validation)
    manifest = {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*"))
        if p.is_file() and p.name != "oracle"
    }
    write_json(output / "evidence-manifest.json", manifest)
    print(json.dumps(validation), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.source, args.output)
