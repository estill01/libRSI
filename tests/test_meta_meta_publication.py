"""README publication must label models and distinguish retention from improvement."""

import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install_meta_meta_results as publication  # noqa: E402


def fixture(tmp_path):
    arms = {"ordinary": 0.10, "after_meta": 0.11, "after_meta_meta": 0.12}
    original = {"instruction": "original"}
    gate = {"active": original, "initial": original, "adopted": False}
    report = {
        "protocol": {"model": "gpt-6-astra", "reasoning_effort": "high"},
        "scores": {arm: [[value] * 512] * 32 for arm, value in arms.items()},
        "means": arms,
        "primary_contrast": {"mean_effect": 0.01, "bootstrap_95_percentile": [-0.01, 0.03]},
        "instructions": {arm: original for arm in arms},
        "meta_meta": gate,
        "propagation": {"original_meta": gate, "retained_meta": gate},
        "effort": {
            "native_inner_runs": 96,
            "attempts": 100,
            "logical_calls": 100,
            "timeout_attempts": 0,
            "usage": {"input_tokens": 1000, "output_tokens": 100},
        },
    }
    proof = {
        "model": "gpt-6-astra",
        "reasoning_effort": "high",
        "verified_inner_runs": 96,
        "complete_store_archive_hashes_verified": 96,
        "verified_attempts": 100,
    }
    proof.update(
        {
            key: True
            for key in (
                "development_and_final_scores_replayed",
                "primary_bootstrap_replayed",
                "source_hashes_verified",
                "downward_active_instruction_bindings_verified",
            )
        }
    )
    (tmp_path / "report.json.gz").write_bytes(gzip.compress(json.dumps(report).encode()))
    (tmp_path / "validation.json").write_text(json.dumps(proof))
    (tmp_path / "figure-values.json").write_text(
        json.dumps({"means_percent": [0, *[v * 100 for v in arms.values()]]})
    )
    with (tmp_path / "run-scores.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "case",
                "optimizer_model",
                "meta_model",
                "meta_meta_model",
                "reasoning_effort",
            ],
        )
        writer.writeheader()
        writer.writerow({"case": "base", "optimizer_model": "none"})
        for arm in arms:
            for _ in range(32):
                writer.writerow(
                    {
                        "case": arm,
                        "optimizer_model": "gpt-6-astra",
                        "meta_model": "none" if arm == "ordinary" else "gpt-6-astra",
                        "meta_meta_model": "gpt-6-astra" if arm == "after_meta_meta" else "none",
                        "reasoning_effort": "high",
                    }
                )
    refresh_manifest(tmp_path)
    return report


def refresh_manifest(path):
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.iterdir()
        if p.is_file() and p.name != "evidence-manifest.json"
    }
    (path / "evidence-manifest.json").write_text(json.dumps(manifest))


def test_completed_package_labels_all_levels_without_claiming_rejected_meta_gain(tmp_path):
    report = fixture(tmp_path)
    assert publication.load_publication(tmp_path) == report
    text = publication.comparison(report)
    assert "0.00%" in text and "10.00%" in text and "11.00%" in text and "12.00%" in text
    assert "high at all three levels" in text and "high at both levels" in text
    assert "retained the original meta optimizer" in text
    assert "does not demonstrate a learned meta-meta improvement" in text
    assert "[-1.00, +3.00]" in text


def test_publication_refuses_tampered_evidence(tmp_path):
    fixture(tmp_path)
    (tmp_path / "validation.json").write_text("{}")
    with pytest.raises(AssertionError):
        publication.load_publication(tmp_path)


def test_publication_refuses_incomplete_samples_even_with_updated_file_hash(tmp_path):
    report = fixture(tmp_path)
    report["scores"]["after_meta_meta"] = report["scores"]["after_meta_meta"][:4]
    (tmp_path / "report.json.gz").write_bytes(gzip.compress(json.dumps(report).encode()))
    refresh_manifest(tmp_path)
    with pytest.raises(AssertionError):
        publication.load_publication(tmp_path)


def test_publication_refuses_changed_mean_and_false_adoption(tmp_path):
    report = fixture(tmp_path)
    report["means"]["after_meta_meta"] = 0.95
    (tmp_path / "report.json.gz").write_bytes(gzip.compress(json.dumps(report).encode()))
    refresh_manifest(tmp_path)
    with pytest.raises(AssertionError):
        publication.load_publication(tmp_path)
    report = fixture(tmp_path)
    report["meta_meta"]["active"] = {"instruction": "unaccepted change"}
    (tmp_path / "report.json.gz").write_bytes(gzip.compress(json.dumps(report).encode()))
    refresh_manifest(tmp_path)
    with pytest.raises(AssertionError):
        publication.load_publication(tmp_path)
