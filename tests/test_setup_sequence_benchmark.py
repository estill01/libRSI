"""Check the exact oracle, directed-cycle scoring, sampling isolation and analysis."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import benchmark_setup_sequence as benchmark  # noqa: E402
import llm_search  # noqa: E402
from sequence_intent import operationalize, validate_plan  # noqa: E402
from sequence_program import BASE_INSTRUCTIONS, BASE_PROGRAM, execute, parse_program  # noqa: E402
from setup_sequence import (  # noqa: E402
    SequenceProblem,
    build_oracle,
    cost,
    greedy,
    local_search,
    workload,
)


@pytest.fixture(scope="module")
def oracle(tmp_path_factory):
    return build_oracle(tmp_path_factory.mktemp("sequence-oracle") / "oracle")


@pytest.mark.parametrize("family", range(4))
def test_exact_oracle_matches_exhaustive_directed_cycles(oracle, family):
    p = SequenceProblem(workload(1234 + family, family, size=7), oracle)
    exhaustive = min(cost(p.matrix, [0, *rest]) for rest in itertools.permutations(range(1, 7)))
    assert p.optimal_cost == exhaustive
    assert cost(p.matrix, local_search(p.matrix, p.starting_order)) <= p.starting_cost
    assert p.starting_order == greedy(p.matrix)
    assert cost(p.matrix, p.optimal_order) == p.optimal_cost


def test_directed_return_edge_and_invalid_candidate_fallback(oracle):
    p = SequenceProblem(
        {"id": "fixture", "family": 0, "costs": [[0, 1, 40], [30, 0, 2], [3, 20, 0]]}, oracle
    )
    assert cost(p.matrix, [0, 1, 2]) == 6
    assert cost(p.matrix, [0, 2, 1]) == 90
    result = p.evaluate([{"configuration": {"order": "0,1,1"}}])
    assert result["candidates"][0]["valid"] is False
    assert result["cost"] == p.starting_cost
    assert result["quality"] <= 1
    assert "optimal" not in json.dumps(p.prompt_data())


def program():
    return {
        "program": json.dumps(
            {
                "stages": [
                    {
                        "operators": ["swap", "relocate"],
                        "sampling": "scan",
                        "acceptance": "improve",
                        "temperature": 0,
                        "cooling": 1,
                        "restart": "continue",
                        "kick": 0,
                        "weight": 1,
                    }
                ]
            }
        )
    }


def test_bounded_program_is_deterministic_preserves_coverage_and_budget(oracle):
    p = SequenceProblem(workload(1234, 0, size=7), oracle)
    first = execute(program(), p)
    assert first == execute(program(), p)
    assert first["evaluations"] == 256
    assert sorted(first["order"]) == list(range(7))
    assert first["cost"] <= p.starting_cost
    assert first["cost"] == cost(p.matrix, first["order"])
    assert execute(BASE_PROGRAM, p)["evaluations"] == 0
    invalid = json.loads(program()["program"])
    invalid["stages"][0]["temperature"] = float("inf")
    with pytest.raises(ValueError):
        parse_program({"program": json.dumps(invalid)})
    with pytest.raises(ValueError):
        parse_program(BASE_PROGRAM, allow_baseline=False)


def test_proposals_are_bound_to_policy_phase_and_draw(oracle, tmp_path):
    p = SequenceProblem(workload(1234, 0, size=7), oracle)

    class Sampler:
        def call(self, prompt, **kwargs):
            assert "PROPOSER STRATEGY" in prompt
            assert "cost_matrix" in prompt
            assert "optimal_order" not in prompt
            return [{"configuration": program(), "reason": "hypothesis"}]

    study = benchmark.ProgramStudy(tmp_path, {"generation": [p]}, Sampler(), {"metric": "quality"})
    rows = study.prepare(BASE_INSTRUCTIONS, count=2)
    assert len(rows) == 2
    assert rows[0]["sample"] != rows[1]["sample"]
    assert rows[0]["instruction"] == BASE_INSTRUCTIONS
    assert rows[0]["selected"] == program() or rows[0]["selected"] == BASE_PROGRAM
    assert rows[0]["role"] != rows[1]["role"]
    study.final_frozen = True
    with pytest.raises(RuntimeError, match="frozen"):
        study.generate(BASE_INSTRUCTIONS, "final", 0)


def test_bootstrap_uses_workloads_and_preserves_family_balance():
    families = [i % 4 for i in range(128)]
    a = np.tile(np.asarray(families) * 0.02, (32, 1))
    result = benchmark.interval({"a": a, "b": a + 0.03}, "a", "b", families)
    assert result["independent_workloads"] == 128
    assert result["model_samples_per_arm"] == 32
    assert result["mean_effect"] == pytest.approx(0.03)
    assert result["bootstrap_95_percentile"] == pytest.approx([0.03, 0.03])


def test_model_interpretation_creates_native_proposal_and_cannot_change_bounds(tmp_path):
    plan = {
        "objective": "Improve normalized schedule quality",
        "metric": "quality",
        "minimum_effect": 0.02,
        "null_hypothesis": "mean_gain <= minimum_effect",
        "baseline": "current_nearest_neighbor",
        "hypotheses": [
            {"claim": "Explore", "mechanism": "Escapes local minima", "experiment": "Mix moves"},
            {
                "claim": "Focus",
                "mechanism": "Fix expensive transitions",
                "experiment": "Focus sampling",
            },
        ],
        "confirmation": "Use independent workloads and model draws",
    }

    class Sampler:
        def call(self, prompt, **kwargs):
            assert "broad goal" in prompt
            return [{"configuration": {"plan": json.dumps(plan)}}]

    proposed, accepted = operationalize(Sampler(), tmp_path, 0.8)
    assert proposed == plan and accepted.proposal is not None
    assert accepted.contract.objectives[0].minimum_effect == 0.02
    assert accepted.contract.baseline.measurements["quality"] == 0.8
    with pytest.raises(ValueError):
        validate_plan({**plan, "minimum_effect": 0})


def test_requested_reasoning_effort_reaches_cli_and_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_search.subprocess, "check_output", lambda *a, **k: "codex-cli test")

    def run(command, **kwargs):
        assert 'model_reasoning_effort="low"' in command
        response = {
            "candidates": [{"configuration": {"instruction": "test"}, "reason": "hypothesis"}]
        }
        events = [
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps(response)},
            },
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
        ]
        kwargs["stdout"].write("\n".join(json.dumps(row) for row in events) + "\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(llm_search.subprocess, "run", run)
    sampler = llm_search.CodexSampler(
        tmp_path / "calls", "test", max_calls=1, reasoning_effort="low"
    )
    sampler.call("test", field="instruction", role="test", count=1)
    assert sampler.receipts[0]["reasoning_effort"] == "low"
