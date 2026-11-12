"""Validate measurement and isolation without rerunning costly native workflows."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from librsi import LearningCase

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SPEC = importlib.util.spec_from_file_location(
    "document_search_benchmark_workload", EXAMPLES / "document_search.py"
)
assert SPEC is not None and SPEC.loader is not None
WORKLOAD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WORKLOAD
SPEC.loader.exec_module(WORKLOAD)


def test_scores_follow_actual_rankings_and_count_repeated_work():
    index = WORKLOAD.SearchIndex(
        [
            {"path": "a.md", "text": "# Apples\napples apples fruit"},
            {"path": "b.md", "text": "# Oranges\noranges citrus"},
        ]
    )
    queries = [{"id": "q", "query": "apples", "relevant": ["a.md"]}]
    assert index.measure(WORKLOAD.BASE_RANKER, queries).value == 1
    queries[0]["relevant"] = ["b.md"]
    assert index.measure(WORKLOAD.BASE_RANKER, queries).value == 0.5
    assert index.ranked_queries == 2 and index.measurements == 2


def test_proposal_proxy_selects_using_tuning_only_and_counts_all_trials():
    class StubIndex:
        def __init__(self):
            self.calls = []
            self.adapter_evaluations = 0

        def resolve(self, ids):
            return [{"id": key} for key in ids]

        def measure(self, configuration, queries):
            from librsi import TaskMeasurement

            self.calls.append((dict(configuration), queries[0]["id"]))
            # Tuning prefers weight 2. Scoring would prefer 8, but must never select it.
            tuning = queries[0]["id"] == "tuning"
            value = {0: 0.0, 2: 1.0 if tuning else 0.0, 8: 0.5 if tuning else 1.0}
            return TaskMeasurement({}, value[configuration["title_weight"]])

    index = StubIndex()
    case = LearningCase("proxy", {"tuning": ["tuning"], "scoring": ["scoring"]})
    result = WORKLOAD.ProposalAdapter(index).evaluate(WORKLOAD.BASE_PROPOSER, case)
    assert result.value == 0.0
    assert result.output["selected"]["title_weight"] == 2
    assert [kind for _, kind in index.calls] == ["tuning", "tuning", "tuning", "scoring"] * 2
    assert index.calls[3][0] == index.calls[1][0]


def test_frozen_splits_are_disjoint_and_keep_official_test_separate():
    manifest = json.loads((EXAMPLES / "data/scifact-split.json").read_text())
    splits = manifest["splits"]
    rows = [key for split in splits.values() for key in split]
    assert len(rows) == len(set(rows)) == 1109
    assert len(splits["test"]) == 300
    assert len(splits["unused_train"]) == 29
    assert all(len(splits[f"meta_{part}"]) == 200 for part in ["train", "shadow", "verification"])
    assert all(
        len(splits[f"ordinary_{part}"]) == 60 for part in ["train", "shadow", "verification"]
    )


def test_every_policy_has_the_same_candidate_budget():
    for name in WORKLOAD.PORTFOLIOS:
        choices = WORKLOAD.candidates({"portfolio": name})
        assert len(choices) == 2
        assert choices[0] != choices[1]
        assert WORKLOAD.BASE_RANKER not in choices
        for choice in choices:
            WORKLOAD.SearchIndex.validate(choice)


@pytest.mark.parametrize(
    "configuration",
    [
        {"method": "unknown", "title_weight": 2},
        {"method": "tf", "title_weight": True},
        {"method": "tf", "title_weight": 2, "test_answers": []},
    ],
)
def test_invalid_rankers_reject(configuration):
    with pytest.raises(ValueError):
        WORKLOAD.SearchIndex.validate(configuration)
