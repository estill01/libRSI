"""Guard cascade retention, new test partitions, and honest provider recovery."""

import csv
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import benchmark_meta_meta_sequence as cascade  # noqa: E402
import checkpoint_codex_sampler as checkpoint  # noqa: E402

from librsi import LearningCase  # noqa: E402
from librsi.identity import digest  # noqa: E402


def fake_provider(monkeypatch, *, failures):
    monkeypatch.setattr(checkpoint.subprocess, "check_output", lambda *a, **k: "test-cli")
    calls = []

    def call(self, prompt, *, field, role, count):
        number = len(self.receipts) + 1
        path = self.directory / f"{number:03d}"
        path.mkdir()
        (path / "prompt.txt").write_text(prompt)
        row = {
            "number": number,
            "role": role,
            "model": "gpt-6-astra",
            "reasoning_effort": "high",
            "candidate_count": count,
            "prompt_sha256": digest(prompt),
        }
        self.receipts.append(row)
        calls.append(role)
        if number in failures:
            row.update(status="timeout", usage=[])
            (path / "receipt.json").write_text(json.dumps(row))
            raise subprocess.TimeoutExpired("fake-model", 600)
        choices = [{"configuration": {field: str(i)}, "reason": "test"} for i in range(count)]
        row.update(returncode=0, tool_items=0, usage=[{"input_tokens": 1, "output_tokens": 2}])
        (path / "receipt.json").write_text(json.dumps(row))
        (path / "response.json").write_text(json.dumps({"candidates": choices}))
        return choices

    monkeypatch.setattr(checkpoint.CodexSampler, "call", call)
    return calls


def test_timeout_recovery_retains_both_attempts_and_resume_does_not_resample(tmp_path, monkeypatch):
    calls = fake_provider(monkeypatch, failures={1})
    sampler = checkpoint.CheckpointSampler(tmp_path / "calls", logical_limit=2, retry_limit=1)
    answer = sampler.call("exact prompt", field="instruction", role="one")
    assert calls == ["one", "one"] and len(sampler.receipts) == 2
    assert sampler.receipts[0]["status"] == "timeout"
    resumed = checkpoint.CheckpointSampler(tmp_path / "calls", logical_limit=2, retry_limit=1)
    assert resumed.call("exact prompt", field="instruction", role="one") == answer
    assert calls == ["one", "one"]
    with pytest.raises(AssertionError):
        resumed.call("changed prompt", field="instruction", role="one")


def test_second_timeout_never_triggers_third_attempt(tmp_path, monkeypatch):
    calls = fake_provider(monkeypatch, failures={1, 2})
    sampler = checkpoint.CheckpointSampler(tmp_path / "calls", logical_limit=2, retry_limit=2)
    with pytest.raises(subprocess.TimeoutExpired):
        sampler.call("exact prompt", field="instruction", role="one")
    resumed = checkpoint.CheckpointSampler(tmp_path / "calls", logical_limit=2, retry_limit=2)
    with pytest.raises(RuntimeError, match="requires diagnosis"):
        resumed.call("exact prompt", field="instruction", role="one")
    assert calls == ["one", "one"]


def test_retry_allowance_is_global_across_roles(tmp_path, monkeypatch):
    calls = fake_provider(monkeypatch, failures={1, 3})
    sampler = checkpoint.CheckpointSampler(tmp_path / "calls", logical_limit=2, retry_limit=1)
    sampler.call("first", field="instruction", role="one")
    with pytest.raises(RuntimeError, match="allowance exhausted"):
        sampler.call("second", field="instruction", role="two")
    assert calls == ["one", "one", "two"]


def test_cascade_utility_uses_retained_child_not_proposed_child():
    meta = {"instruction": "meta"}
    retained = {"instruction": "retained optimizer"}
    proposed = {"instruction": "rejected optimizer"}
    used = []

    class Study:
        def prepare(self, instruction):
            used.append(instruction)
            assert instruction != proposed
            return [
                {
                    "label": str(i),
                    "evaluation": {"meta_train": 0.2 if instruction == retained else 0.1},
                }
                for i in range(24)
            ]

    adapter = cascade.CascadeAdapter(
        Study(), {digest(meta): {"active": retained, "choices": [proposed]}}
    )
    result = adapter.evaluate(meta, LearningCase("train", {"split": "meta_train", "group": 0}))
    assert result.value == pytest.approx(0.1)
    assert used == [retained, cascade.BASE_INSTRUCTIONS]


def test_old_final_results_are_excluded_from_meta_meta_feedback(tmp_path):
    report = {
        "meta": {"disposition": "rejected", "choices": []},
        "development": {},
        "scores": "SECRET_FINAL_SCORES",
        "runs": "SECRET_FINAL_CONFIGURATIONS",
    }
    transcripts = [
        {
            "receipt": {"role": "meta-revise-improver"},
            "prompt": "original meta instruction\nPROGRAM CONTRACT:\nrest",
        }
    ]
    manifest = {}
    for name, value in (("report.json.gz", report), ("model-transcripts.json.gz", transcripts)):
        data = gzip.compress(json.dumps(value).encode())
        (tmp_path / name).write_bytes(data)
        manifest[name] = hashlib.sha256(data).hexdigest()
    (tmp_path / "evidence-manifest.json").write_text(json.dumps(manifest))
    original, feedback = cascade.prior_development(tmp_path)
    assert original == {"instruction": "original meta instruction"}
    assert "SECRET_FINAL" not in json.dumps(feedback)


def test_new_cascade_workload_partitions_are_disjoint(tmp_path, monkeypatch):
    (tmp_path / "workloads").mkdir()
    monkeypatch.setattr(cascade.native, "fresh_problem", lambda row, oracle: row)
    seen = []
    for name, seed in (
        ("development", 900000),
        ("upper", 906000),
        ("propagation", 912000),
        ("final", 918000),
    ):
        data = cascade.make_problems(tmp_path, name, seed, None, final=name == "final")
        seen.extend(row["id"] for rows in data.values() for row in rows)
    test = [cascade.workload(921000 + i, i % 4)["id"] for i in range(512)]
    assert len(seen + test) == len(set(seen + test)) == 1184


def test_final_interval_accepts_registered_panel_and_resamples_model_draws():
    # Identical workloads cannot eliminate variation between independent model draws.
    rows = np.repeat(np.linspace(0.0, 0.3, 32)[:, None], 512, axis=1)
    result = cascade.interval(
        {"a": rows, "b": rows}, "a", "b", [i % 4 for i in range(512)], seed=19
    )
    low, high = result["bootstrap_95_percentile"]
    assert low < 0 < high and result["mean_effect"] == 0
    assert result["independent_workloads"] == 512 and result["model_samples_per_arm"] == 32
    with pytest.raises(AssertionError):
        cascade.interval(
            {"a": rows[:, :128], "b": rows[:, :128]}, "a", "b", [i % 4 for i in range(128)], seed=19
        )


def test_csv_keeps_level_models_and_run_scores_together(tmp_path):
    from publish_meta_meta_sequence import export_csv

    arms = ["ordinary", "after_meta", "after_meta_meta", "forced_cascade_diagnostic"]
    report = {
        "scores": {arm: [[0.01 * (i + 1)] * 512 for i in range(32)] for arm in arms},
        "runs": [{"label": f"{arm}-{i:02d}", "adopted": True} for arm in arms for i in range(32)],
    }
    path = tmp_path / "scores.csv"
    export_csv(report, path)
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 129 and rows[0]["optimizer_model"] == "none"
    for row in rows[1:]:
        assert row["optimizer_model"] == "gpt-6-astra" and row["reasoning_effort"] == "high"
        assert (row["meta_model"] == "gpt-6-astra") == (row["case"] != "ordinary")
        assert (row["meta_meta_model"] == "gpt-6-astra") == (row["case"] in arms[2:])
        assert float(row["mean_cost_reduction_percent"]) == pytest.approx(
            int(row["optimization_run"].rsplit("-", 1)[1]) + 1
        )


@pytest.mark.slow
def test_native_meta_meta_gate_retains_improved_parent_and_reopens(tmp_path):
    for name in ("gates", "native-gates"):
        (tmp_path / name).mkdir()
    original = {"instruction": "original meta"}
    revised = {"instruction": "revised meta"}
    neutral = {"instruction": "unhelpful meta"}
    useful = {"instruction": "useful ordinary optimizer"}

    class Study:
        def prepare(self, instruction):
            return [
                {
                    "label": str(i),
                    "evaluation": {
                        split: 0.20 if instruction == useful else 0.10
                        for split in ("meta_train", "meta_shadow", "meta_verify")
                    },
                }
                for i in range(24)
            ]

    children = {
        digest(original): {"active": cascade.BASE_INSTRUCTIONS},
        digest(revised): {"active": useful},
        digest(neutral): {"active": cascade.BASE_INSTRUCTIONS},
    }
    adapter = cascade.CascadeAdapter(Study(), children)
    choices = [
        {"configuration": revised, "reason": "Measured useful child"},
        {"configuration": neutral, "reason": "Unchanged child control"},
    ]
    result = cascade.gate(tmp_path, "top", original, choices, adapter)
    assert result["adopted"] and result["active"] == revised and result["disposition"] == "verified"
    assert cascade.gate(tmp_path, "top", original, choices, adapter) == result
