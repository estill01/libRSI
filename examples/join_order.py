"""Synthetic join-order planning with an exact, inspectable cost oracle.

These are generated cost-model workloads, not database execution timings or JOB.
Every proposer receives the complete same cardinality/selectivity information.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

BASE_INSTRUCTION = {
    "instruction": "Use the query statistics and measured starting-plan feedback to propose "
    "two distinct join orders with lower total estimated cost. Consider selectivity and "
    "intermediate result sizes. Explain the reason for each proposal."
}

CONTRACT = """Optimize a left-deep sequence of hash joins under this exact synthetic cost model.
All tables must appear exactly once. Cross products are legal but often costly.
For a subset S of tables, C(S) = max(1, product(rows[t] for t in S) *
product(selectivity[a,b] for every edge whose BOTH endpoints are in S)).
Missing edges have selectivity 1. Compute this from the full subset, not by
repeatedly rounding intermediate cardinalities. A singleton has its given rows.
For order t1,...,tn, cost = sum(C({t1,...,ti}) for i=1,...,n-1).
The final output is constant across orders and excluded; cost measures the
intermediate rows materialized before the last join, not real elapsed time.
Return exactly two distinct candidates, each configuration {"order":"A,B,..."},
using the supplied table names exactly once. Include a brief hypothesis as reason.
You may reason and calculate, but have no execution tools or oracle calls.
The host evaluates both plans and retains the cheapest of them and the starting
plan. The proposal budget is two plans per call for every instruction policy.
"""


def workload(seed: int, family: int, *, size: int = 10, regime: str = "filtered") -> dict[str, Any]:
    """Four graph families; table labels and all numbers vary independently."""
    rng = random.Random(seed)
    names = [chr(65 + i) for i in range(size)]
    if regime not in {"filtered", "many_to_many"}:
        raise ValueError("unknown workload regime")
    low, high, filtering, fanout = (3, 6, 3, 0.7) if regime == "filtered" else (2, 5, 1, 3)
    original = [10 ** rng.uniform(low, high) for _ in names]
    rows = [max(1, round(n * 10 ** rng.uniform(-filtering, 0))) for n in original]
    permutation = rng.sample(range(size), size)
    if family == 0:
        edges = {(permutation[i - 1], permutation[i]) for i in range(1, size)}
    elif family == 1:
        edges = {(permutation[0], permutation[i]) for i in range(1, size)}
    elif family == 2:
        edges = {(permutation[rng.randrange(i)], permutation[i]) for i in range(1, size)}
    else:
        edges = {(permutation[i - 1], permutation[i]) for i in range(1, size)}
        edges.update((i, j) for i in range(size) for j in range(i + 1, size) if rng.random() < 0.22)
    pairs = sorted({tuple(sorted(edge)) for edge in edges})
    selectivities = [
        {
            "a": names[a],
            "b": names[b],
            "selectivity": float(
                f"{min(1.0, 10 ** rng.uniform(-0.3, fanout) / max(original[a], original[b])):.6g}"
            ),
        }
        for a, b in pairs
    ]
    return {
        "id": f"q-{seed}",
        "family": family,
        "regime": regime,
        "rows": dict(zip(names, rows, strict=True)),
        "edges": selectivities,
    }


class JoinProblem:
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.data = dict(data)
        self.names = sorted(data["rows"])
        self.n = len(self.names)
        positions = {name: i for i, name in enumerate(self.names)}
        logs = [math.log(data["rows"][name]) for name in self.names]
        edges = [
            (positions[e["a"]], positions[e["b"]], math.log(e["selectivity"]))
            for e in data["edges"]
        ]
        self.cardinalities = [0.0] * (1 << self.n)
        for mask in range(1, 1 << self.n):
            log_size = sum(logs[i] for i in range(self.n) if mask & (1 << i))
            log_size += sum(value for a, b, value in edges if mask & (1 << a) and mask & (1 << b))
            self.cardinalities[mask] = max(1.0, math.exp(log_size))
        self.optimal_cost, self.optimal_order = self.optimum()
        self.starting_order = list(self.names)
        self.starting_cost = self.cost(self.starting_order)

    def parse(self, configuration: Mapping[str, Any]) -> list[str]:
        if set(configuration) != {"order"} or not isinstance(configuration["order"], str):
            raise ValueError("expected an order string")
        order = [name.strip() for name in configuration["order"].split(",")]
        if sorted(order) != self.names:
            raise ValueError("plan must contain each table exactly once")
        return order

    def trace(self, order: Sequence[str]) -> list[dict[str, Any]]:
        mask = 0
        result: list[dict[str, Any]] = []
        for name in order[:-1]:
            mask |= 1 << self.names.index(name)
            result.append(
                {"prefix": list(order[: len(result) + 1]), "rows": self.cardinalities[mask]}
            )
        return result

    def cost(self, order: Sequence[str]) -> float:
        return sum(row["rows"] for row in self.trace(order))

    def optimum(self) -> tuple[float, list[str]]:
        # DP[S] includes C(S); omit the full-set constant when reporting cost.
        values = [0.0] + [math.inf] * ((1 << self.n) - 1)
        orders: list[list[str]] = [[] for _ in values]
        for mask in range(1, len(values)):
            options = [(values[mask ^ (1 << i)], i) for i in range(self.n) if mask & (1 << i)]
            previous, i = min(options)
            values[mask] = previous + self.cardinalities[mask]
            orders[mask] = [*orders[mask ^ (1 << i)], self.names[i]]
        order = orders[-1]
        return self.cost(order), order

    def greedy(self) -> list[str]:
        mask = 0
        order: list[str] = []
        while len(order) < self.n:
            _, i = min(
                (self.cardinalities[mask | (1 << i)], i)
                for i in range(self.n)
                if not mask & (1 << i)
            )
            mask |= 1 << i
            order.append(self.names[i])
        return order

    def prompt_data(self) -> dict[str, Any]:
        return {
            "rows": self.data["rows"],
            "edges": self.data["edges"],
            "starting_plan": self.starting_order,
            "starting_cost": self.starting_cost,
            "starting_prefix_rows": self.trace(self.starting_order),
        }

    def evaluate(self, choices: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for choice in choices:
            try:
                order = self.parse(choice["configuration"])
                candidates.append(
                    {
                        "configuration": dict(choice["configuration"]),
                        "valid": True,
                        "cost": self.cost(order),
                        "prefix_rows": self.trace(order),
                    }
                )
            except (ValueError, TypeError, KeyError) as error:
                candidates.append(
                    {
                        "configuration": dict(choice.get("configuration", {})),
                        "valid": False,
                        "error": str(error),
                    }
                )
        valid = [row for row in candidates if row["valid"]]
        best = min(valid, key=lambda row: row["cost"], default=None)
        if best is not None and best["cost"] < self.starting_cost:
            selected, cost = best["configuration"], best["cost"]
        else:
            selected, cost = {"order": ",".join(self.starting_order)}, self.starting_cost
        return {
            "selected": selected,
            "cost": cost,
            "quality": min(1.0, self.optimal_cost / cost),
            "starting_cost": self.starting_cost,
            "optimal_cost": self.optimal_cost,
            "candidates": candidates,
        }
