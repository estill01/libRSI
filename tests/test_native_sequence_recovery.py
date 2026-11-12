"""Interrupted native studies retain exact provider draws and count each once."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import resume_native_sequence as recovery  # noqa: E402

from librsi.identity import digest  # noqa: E402


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery.subprocess, "check_output", lambda *a, **k: "codex test")
    calls = tmp_path / "model-calls"
    call = calls / "001"
    call.mkdir(parents=True)
    (calls / "instructions.txt").write_text("fixed instructions")
    (call / "prompt.txt").write_text("exact prompt")
    choices = [{"configuration": {"program": "a"}}, {"configuration": {"program": "b"}}]
    (call / "response.json").write_text(json.dumps({"candidates": choices}))
    receipt = {
        "number": 1,
        "role": "ordinary-00",
        "model": "gpt-6-astra",
        "reasoning_effort": "high",
        "returncode": 0,
        "tool_items": 0,
        "candidate_count": 2,
        "prompt_sha256": digest("exact prompt"),
        "usage": [{"input_tokens": 5, "output_tokens": 6}],
    }
    (call / "receipt.json").write_text(json.dumps(receipt))
    protocol = {
        "model": "gpt-6-astra",
        "reasoning_effort": "high",
        "model_call_limit": 169,
        "model_timeout_seconds": 600,
    }
    return call, choices, receipt, protocol


def test_resume_reuses_exact_response_once_and_refuses_changed_prompt(tmp_path, monkeypatch):
    _call, choices, receipt, protocol = fixture(tmp_path, monkeypatch)
    sampler = recovery.ExistingSampler(tmp_path, protocol)
    assert sampler.call("exact prompt", field="program", role="ordinary-00") == choices
    assert sampler.receipts == [receipt]
    with pytest.raises(AssertionError):
        sampler.call("different prompt", field="program", role="ordinary-00")
    assert sampler.receipts == [receipt]


def test_resume_refuses_unfinished_provider_call(tmp_path, monkeypatch):
    call, _choices, receipt, protocol = fixture(tmp_path, monkeypatch)
    receipt.pop("returncode")
    (call / "receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="unfinished provider call"):
        recovery.ExistingSampler(tmp_path, protocol)
