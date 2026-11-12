"""Check recursive propagation, holdout isolation and concurrent call bounds."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import llm_search  # noqa: E402
import recursive_search as recursive  # noqa: E402


class Sampler:
    def __init__(self):
        self.prompts = []

    def call(self, prompt, *, field, role, count=2):
        self.prompts.append((prompt, field, role, count))
        if field == "instruction":
            value = "CHILD_POLICY_B" if "CHILD_POLICY_A" in prompt else "CHILD_POLICY_A"
            return [{"configuration": {"instruction": value}, "reason": "hypothesis"}]
        return [
            {"configuration": {"formula": formula}, "reason": "hypothesis"}
            for formula in ("tf + 10 * title_tf", "idf")
        ]


def make_index():
    return llm_search.FormulaIndex(
        [
            {"path": "a", "text": "# Other\napple apple apple"},
            {"path": "b", "text": "# Apple\nfruit"},
        ],
        {
            "train": {"id": "train", "query": "apple", "relevant": ["b"]},
            "test": {"id": "test", "query": "apple SECRET_SCORING_QUERY", "relevant": ["a"]},
        },
    )


def test_three_level_cascade_really_consumes_each_generated_child(tmp_path):
    sampler = Sampler()
    cache = recursive.CascadeCache(
        make_index(), sampler, tmp_path / "cache", ["train"], recursive.DEFAULTS
    )
    rows = cache.prepare(3, recursive.DEFAULTS[3])
    assert len(rows) == 5 and len(sampler.prompts) == 15
    for row in rows:
        assert row["chain"][0]["output_instruction"] == row["chain"][1]["input_instruction"]
        assert row["chain"][1]["output_instruction"] == row["formula_instructions"]
        assert row["formula_instructions"] == {"instruction": "CHILD_POLICY_B"}
        assert row["selected"] == {"formula": "tf + 10 * title_tf"}
    assert all(
        "CHILD_POLICY_B" in prompt for prompt, field, _, _ in sampler.prompts if field == "formula"
    )
    assert all("SECRET_SCORING_QUERY" not in prompt for prompt, _, _, _ in sampler.prompts)
    assert cache.measure(3, recursive.DEFAULTS[3], 0, ["test"]).value == 0.5
    assert len(sampler.prompts) == 15


def test_freeze_prevents_new_model_samples_and_child_seed_changes_identity(tmp_path):
    sampler = Sampler()
    cache = recursive.CascadeCache(
        make_index(), sampler, tmp_path / "cache", ["train"], recursive.DEFAULTS
    )
    cache.prepare(1, recursive.DEFAULTS[1])
    cache.frozen = True
    assert cache.prepare(1, recursive.DEFAULTS[1])
    with pytest.raises(RuntimeError, match="after final freeze"):
        cache.prepare(1, {"instruction": "a changed policy"})
    key = cache.key(2, recursive.DEFAULTS[2])
    cache.child_seeds[1] = {"instruction": "changed child"}
    assert cache.key(2, recursive.DEFAULTS[2]) != key


def test_concurrent_sampler_never_exceeds_budget_or_reuses_call_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_search.subprocess, "check_output", lambda *a, **k: "codex-cli test")

    def run(command, **kwargs):
        response = {
            "candidates": [{"configuration": {"instruction": "generated"}, "reason": "hypothesis"}]
        }
        events = [
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps(response)},
            },
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
        ]
        kwargs["stdout"].write("\n".join(json.dumps(event) for event in events) + "\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(llm_search.subprocess, "run", run)
    sampler = llm_search.CodexSampler(tmp_path / "calls", "test-model", max_calls=4)

    def call(_):
        try:
            sampler.call("One candidate", field="instruction", role="test", count=1)
            return True
        except RuntimeError as exc:
            assert "budget exhausted" in str(exc)
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        succeeded = list(pool.map(call, range(8)))
    assert sum(succeeded) == len(sampler.receipts) == 4
    assert sorted(row["number"] for row in sampler.receipts) == [1, 2, 3, 4]
    assert all(
        row["usage"] == [{"input_tokens": 10, "output_tokens": 2}] for row in sampler.receipts
    )
