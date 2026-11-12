"""Guard the actual-system meta objective and held-out split isolation."""

import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import benchmark_native_sequence as benchmark  # noqa: E402
from recorded_codex_sampler import RecordedCodexSampler  # noqa: E402

from librsi import LearningCase  # noqa: E402
from librsi.identity import FrozenMap, digest  # noqa: E402


def test_outer_cases_use_distinct_inner_runs_and_retained_system_scores():
    used = []

    class Study:
        def prepare(self, instruction):
            baseline = instruction == benchmark.BASE_INSTRUCTIONS
            return [
                {
                    "label": str(i),
                    "evaluation": {
                        split: (0 if baseline else i / 100)
                        for split in ("meta_train", "meta_shadow", "meta_verify")
                    },
                }
                for i in range(24)
            ]

    adapter = benchmark.MetaAdapter(Study())
    for stage, split in enumerate(("meta_train", "meta_shadow", "meta_verify")):
        for group in range(2):
            result = adapter.evaluate(
                {"instruction": "revised"},
                LearningCase(f"{split}-{group}", {"split": split, "group": group}),
            )
            expected = list(range(stage * 8 + group * 4, stage * 8 + (group + 1) * 4))
            assert result.value == pytest.approx(sum(expected) / 400)
            assert list(result.output["native_runs"]) == list(map(str, expected))
            used.extend(expected)
    assert used == list(range(24))


def test_scheduler_generation_sees_only_training_data_and_invalid_response_spends_slot(tmp_path):
    calls = []

    class Sampler:
        def call(self, prompt, **kwargs):
            calls.append((prompt, kwargs))
            assert "TRAINING_SENTINEL" in prompt
            assert "SECRET_TEST" not in prompt
            raise ValueError("malformed response")

    problems = {
        "final_train": [SimpleNamespace(prompt_data=lambda: "TRAINING_SENTINEL")],
        "test": [SimpleNamespace(prompt_data=lambda: "SECRET_TEST")],
    }
    study = benchmark.Study(tmp_path, problems, Sampler())
    result = study.propose(benchmark.BASE_INSTRUCTIONS, "final", "ordinary-00")
    assert len(calls) == 1
    assert all("invalid_output" in choice["configuration"] for choice in result)


def test_corrected_baseline_is_single_start_and_contract_describes_it():
    assert "a nearest-neighbor cycle starting at job 0" in benchmark.CONTRACT
    assert "over all starting jobs" not in benchmark.CONTRACT
    assert len(set(benchmark.SEEDS.values())) == len(benchmark.SEEDS)


def test_native_worker_payload_serializes_immutable_instruction(tmp_path):
    (tmp_path / "proposals").mkdir()
    study = benchmark.Study(tmp_path, {}, None)
    study.propose = lambda *args: []
    job = study.generate(FrozenMap(benchmark.BASE_INSTRUCTIONS), "development", "test")
    assert type(job[3]) is dict
    assert pickle.loads(pickle.dumps(job)) == job


def test_exact_recorded_response_reuses_usage_and_rejects_changed_prompt(tmp_path, monkeypatch):
    import llm_search

    monkeypatch.setattr(llm_search.subprocess, "check_output", lambda *args, **kw: "test-cli")
    previous = tmp_path / "previous"
    call = previous / "model-calls" / "001"
    call.mkdir(parents=True)
    prompt = "original prompt"
    receipt = {
        "number": 1,
        "model": benchmark.MODEL,
        "reasoning_effort": "high",
        "role": "draw",
        "candidate_count": 1,
        "prompt_sha256": digest(prompt),
        "returncode": 0,
        "tool_items": 0,
        "usage": [{"input_tokens": 10, "output_tokens": 2}],
    }
    response = {
        "candidates": [
            {"configuration": {"instruction": "original answer"}, "reason": "hypothesis"}
        ]
    }
    (call / "prompt.txt").write_text(prompt)
    (call / "receipt.json").write_text(json.dumps(receipt))
    (call / "response.json").write_text(json.dumps(response))
    sampler = RecordedCodexSampler(tmp_path / "current", benchmark.MODEL, reuse=previous)
    with pytest.raises(ValueError, match="exact request"):
        sampler.call("changed prompt", field="instruction", role="draw", count=1)
    assert not sampler.receipts
    assert sampler.call(prompt, field="instruction", role="draw", count=1) == response["candidates"]
    assert sampler.receipts[0]["usage"] == receipt["usage"]
    assert sampler.receipts[0]["reused_from"]["run"] == "previous"
