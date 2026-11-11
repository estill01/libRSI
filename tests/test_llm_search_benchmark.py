"""Verify the formula boundary and meta-data isolation without paid calls."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import llm_search as workload  # noqa: E402

from librsi import LearningCase  # noqa: E402


@pytest.mark.parametrize(
    "formula",
    [
        "__import__('os')",
        "tf.__class__",
        "tf[0]",
        "2**tf",
        "sum(tf)",
        "minimum(tf)",
        "True",
        "1e99",
        "[tf]",
        "idf if tf else 0",
    ],
)
def test_expression_grammar_rejects_code_and_unbounded_operations(formula):
    with pytest.raises((ValueError, SyntaxError)):
        workload.parse_formula({"formula": formula})


def test_generated_formula_changes_ranking_and_measurement_uses_judgments():
    index = workload.FormulaIndex(
        [
            {"path": "a", "text": "# Other\napple apple apple"},
            {"path": "b", "text": "# Apple\nfruit"},
        ]
    )
    queries = [{"id": "q", "query": "apple", "relevant": ["b"]}]
    assert index.measure({"formula": "tf"}, queries).value == 0.5
    assert index.measure({"formula": "tf + 10 * title_tf"}, queries).value == 1
    assert index.ranked_queries == 2
    with pytest.raises(FloatingPointError):
        index.search({"formula": "tf / (tf - tf)"}, "apple")


def test_meta_generates_from_tuning_only_then_freezes_samples_and_selects_on_tuning():
    class Sampler:
        def __init__(self):
            self.prompts = []

        def call(self, prompt, **kwargs):
            self.prompts.append(prompt)
            return [
                {"configuration": {"formula": formula}, "reason": "hypothesis"}
                for formula in ["tf + 10 * title_tf", "idf"]
            ]

    sampler = Sampler()
    index = workload.FormulaIndex(
        [
            {"path": "a", "text": "# Other\napple apple apple"},
            {"path": "b", "text": "# Apple\nfruit"},
        ],
        {
            "t": {"id": "t", "query": "apple", "relevant": ["b"]},
            "s": {"id": "s", "query": "apple PRIVATE_SCORING_TEXT", "relevant": ["a"]},
        },
    )
    adapter = workload.InstructionAdapter(index, sampler)
    case = LearningCase("case", {"tuning": ["t"], "scoring": ["s"]})
    first = adapter.utility(workload.BASE_INSTRUCTIONS, case)
    assert first.output["selected"] == {"formula": "tf + 10 * title_tf"}
    assert first.value == 0.5  # Scoring would prefer the baseline; it cannot choose.
    adapter.utility(workload.BASE_INSTRUCTIONS, case)
    assert len(sampler.prompts) == 1
    assert "PRIVATE_SCORING_TEXT" not in sampler.prompts[0]
    assert index.ranked_queries == 9  # one diagnostic, plus 4 rankings per evaluation


def test_meta_cases_separate_generation_and_scoring_and_all_phases():
    from benchmark_llm_search import meta_cases

    cases = meta_cases([str(i) for i in range(200)], "train")
    assert len(cases) == 2
    ids = [key for case in cases for part in ("tuning", "scoring") for key in case.payload[part]]
    assert len(ids) == len(set(ids)) == 200
    assert all(len(case.payload["tuning"]) == len(case.payload["scoring"]) == 50 for case in cases)
