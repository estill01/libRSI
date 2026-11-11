"""Offline search workload and bounded proposal policies for the README benchmark.

NumPy accelerates ranking; libRSI's core remains dependency-free. No model is used.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from librsi import LearningCase, ReasoningRequest, ReasoningResult, TaskMeasurement
from librsi.identity import digest

BASE_RANKER = {"method": "tf", "title_weight": 0}
BASE_PROPOSER = {"portfolio": "term-frequency"}
MINIMUM_EFFECT = 0.01
# Each policy spends exactly two candidate slots. These are engineering choices,
# not algorithms invented by libRSI. Keep the inventory fixed before evaluation.
PORTFOLIOS = {
    "term-frequency": (
        {"method": "logtf", "title_weight": 2},
        {"method": "logtf", "title_weight": 8},
    ),
    "normalization": (
        {"method": "tfidf", "title_weight": 2},
        {"method": "bm25", "title_weight": 2},
    ),
    "mixed": (
        {"method": "logtf", "title_weight": 8},
        {"method": "bm25", "title_weight": 8},
    ),
}


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text).lower())


class SearchIndex:
    """Search actual Markdown documents; record every ranked query, including repeats."""

    def __init__(
        self, documents: Sequence[Mapping[str, Any]], queries: Mapping[str, Any] | None = None
    ) -> None:
        self.queries = queries or {}
        self.documents = sorted(documents, key=lambda row: row["path"])
        self.body = [Counter(tokens(row["text"])) for row in self.documents]
        self.titles = [
            Counter(tokens(row["text"].splitlines()[0].lstrip("# "))) for row in self.documents
        ]
        self.lengths = [sum(row.values()) for row in self.body]
        self.average_length = sum(self.lengths) / len(self.lengths)
        frequency: Counter[str] = Counter()
        for row in self.body:
            frequency.update(row.keys())
        self.idf = {
            term: math.log(1 + (len(self.documents) - count + 0.5) / (count + 0.5))
            for term, count in frequency.items()
        }
        self.norms = [
            math.sqrt(sum(((1 + math.log(n)) * self.idf[t]) ** 2 for t, n in row.items()))
            for row in self.body
        ]
        postings: dict[str, list[int]] = {}
        for i, body in enumerate(self.body):
            for term in body:
                postings.setdefault(term, []).append(i)
        self.postings = {term: np.asarray(ids, dtype=np.int32) for term, ids in postings.items()}
        self.weights: dict[tuple[str, int, str], Any] = {}
        self.ranked_queries = 0
        self.measurements = 0
        self.adapter_evaluations = 0

    @staticmethod
    def validate(configuration: Mapping[str, Any]) -> None:
        if (
            set(configuration) != {"method", "title_weight"}
            or configuration["method"] not in {"tf", "logtf", "tfidf", "bm25"}
            or type(configuration["title_weight"]) is not int
            or configuration["title_weight"] not in {0, 2, 8}
        ):
            raise ValueError("invalid search configuration")

    def search(self, configuration: Mapping[str, Any], query: str) -> list[str]:
        self.validate(configuration)
        self.ranked_queries += 1
        query_terms = Counter(tokens(query))
        scores = np.zeros(len(self.documents))
        for term, count in query_terms.items():
            if term not in self.postings:
                continue
            ids = self.postings[term]
            method, title_weight = configuration["method"], configuration["title_weight"]
            key = (method, title_weight, term)
            if key not in self.weights:
                tf = np.asarray([self.body[i][term] for i in ids], dtype=float)
                idf = self.idf[term]
                if method == "tf":
                    weights = tf
                elif method == "logtf":
                    weights = 1 + np.log(tf)
                elif method == "tfidf":
                    weights = (1 + np.log(tf)) * idf**2 / np.asarray([self.norms[i] for i in ids])
                else:
                    lengths = np.asarray([self.lengths[i] for i in ids])
                    weights = (
                        idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lengths / self.average_length))
                    )
                title_scale = 0.01 if method == "tfidf" else 1.0
                title_idf = idf if method in {"tfidf", "bm25"} else 1.0
                weights = weights + title_weight * title_scale * title_idf * np.asarray(
                    [bool(self.titles[i][term]) for i in ids]
                )
                # Cache fixed index weights, never query rankings or measurements.
                self.weights[key] = weights
            scores[ids] += count * self.weights[key]
        order = np.argsort(-scores, kind="stable")[:5]
        return [self.documents[i]["path"] for i in order]

    def resolve(self, ids: Sequence[str]) -> list[Mapping[str, Any]]:
        return [self.queries[key] for key in ids]

    def measure(
        self, configuration: Mapping[str, Any], queries: Sequence[Mapping[str, Any]]
    ) -> TaskMeasurement:
        if not queries:
            raise ValueError("cannot score an empty query set")
        self.measurements += 1
        rows = []
        for query in queries:
            ranking = self.search(configuration, query["query"])
            rank = next((i for i, path in enumerate(ranking, 1) if path in query["relevant"]), None)
            rows.append(
                {
                    "id": query["id"],
                    "ranking": ranking,
                    "reciprocal_rank": 1 / rank if rank else 0.0,
                }
            )
        return TaskMeasurement(
            {"queries": rows, "configuration": dict(configuration)},
            sum(row["reciprocal_rank"] for row in rows) / len(rows),
        )


class SearchAdapter:
    adapter_id = "scifact-paired-search-v1"

    def __init__(self, index: SearchIndex) -> None:
        self.index = index

    def validate_configuration(self, configuration: Mapping[str, Any]) -> None:
        self.index.validate(configuration)

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        self.index.adapter_evaluations += 1
        queries = self.index.resolve(case.payload["queries"])
        measured = self.index.measure(configuration, queries)
        reference = self.index.measure(BASE_RANKER, queries)
        return TaskMeasurement(
            {
                "mrr_at_5": measured.value,
                "reference_mrr_at_5": reference.value,
                "ranking_digest": digest(measured.output),
                "reference_digest": digest(reference.output),
                "query_count": len(queries),
            },
            measured.value - reference.value,
        )


def candidates(configuration: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    if set(configuration) != {"portfolio"} or configuration["portfolio"] not in PORTFOLIOS:
        raise ValueError("invalid proposal policy")
    return tuple(dict(item) for item in PORTFOLIOS[configuration["portfolio"]])


def propose(request: ReasoningRequest, choices: Sequence[Mapping[str, Any]]) -> ReasoningResult:
    return ReasoningResult.propose(
        request=request,
        content={
            "hypotheses": [
                {
                    "statement": f"Improve document retrieval using {dict(configuration)}",
                    "causal_model": {"configuration": dict(configuration)},
                    "predictions": [{"mrr_at_5": "increase"}],
                    "confidence": 0.5,
                }
                for configuration in choices
            ]
        },
    )


class SearchProposer:
    """The improver's tunable policy; proposes two configurations, never scores holdouts."""

    def __init__(self, configuration: Mapping[str, Any]) -> None:
        self.configuration = dict(configuration)
        candidates(self.configuration)

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        return propose(request, candidates(self.configuration))


class PortfolioProposer:
    """Outer-loop engineering hypotheses about where to spend the same two slots."""

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        return propose(request, [{"portfolio": "normalization"}, {"portfolio": "mixed"}])


class ProposalAdapter:
    """Measure proposal utility on small tasks before paying for full inner workflows.

    This is a proxy experiment, not a nested libRSI run: choose a candidate using
    tuning queries, then measure it on separate scoring queries. The final transfer
    comparison runs both policies through the actual AdaptiveLoop, including review,
    activation and verification. Every baseline/candidate query execution is counted.
    """

    adapter_id = "scifact-paired-proposal-utility-v1"

    def __init__(self, index: SearchIndex) -> None:
        self.index = index

    def validate_configuration(self, configuration: Mapping[str, Any]) -> None:
        candidates(configuration)

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        self.index.adapter_evaluations += 1
        measured = self.utility(configuration, case)
        reference = self.utility(BASE_PROPOSER, case)
        return TaskMeasurement(
            {
                "selected": measured.output["selected"],
                "mrr_at_5": measured.value,
                "reference_mrr_at_5": reference.value,
                "measurement": dict(measured.output),
                "reference": dict(reference.output),
            },
            measured.value - reference.value,
        )

    def utility(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        choices = candidates(configuration)
        tuning = self.index.resolve(case.payload["tuning"])
        scoring = self.index.resolve(case.payload["scoring"])
        baseline = self.index.measure(BASE_RANKER, tuning)
        trials = [self.index.measure(item, tuning) for item in choices]
        best = max(range(len(trials)), key=lambda i: trials[i].value)
        selected = (
            choices[best] if trials[best].value - baseline.value >= MINIMUM_EFFECT else BASE_RANKER
        )
        scored = self.index.measure(selected, scoring)
        return TaskMeasurement(
            {
                "selected": dict(selected),
                "baseline_tuning_mrr": baseline.value,
                "candidate_tuning_mrr": [row.value for row in trials],
                "ranking_digest": digest(scored.output),
            },
            scored.value,
        )
