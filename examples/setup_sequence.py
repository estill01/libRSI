"""Improve production sequences under synthetic asymmetric changeover costs."""

from __future__ import annotations

import math
import random
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

BASE_INSTRUCTION = {
    "instruction": "Use the setup-cost matrix and current sequence feedback to propose two distinct production sequences with less total changeover time. Consider both cheap transitions and the complete cycle. Explain each proposal briefly."
}
CONTRACT = """Plan a repeating production cycle. Each job must occur exactly once.
The directed matrix cost[a][b] gives setup minutes when job b follows job a.
The last job returns to the first, so its transition counts. Costs need not be
symmetric or satisfy the triangle inequality. Start the listed cycle at job 0.
The objective is the sum of all directed transitions including the return to 0.
Return exactly two distinct candidates, configuration {"order":"0,3,1,..."},
with every job ID exactly once, plus a brief hypothesis as reason (<=50 words).
The host compares your two proposals with the current sequence and keeps the
lowest actual cost. You have no tools, code execution or oracle access.
Use only the supplied matrix, current sequence and its measured transitions.
"""


def workload(seed: int, family: int, *, size: int = 14) -> dict[str, Any]:
    rng = random.Random(seed)
    groups = rng.sample([i % 4 for i in range(size)], size)
    points = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(size)]
    costs = []
    for i in range(size):
        row = []
        for j in range(size):
            if i == j:
                value = 0
            elif family == 0:
                value = rng.randint(1, 99)
            elif family == 1:
                value = rng.randint(1, 20) if groups[i] == groups[j] else rng.randint(30, 99)
            elif family == 2:
                distance = math.dist(points[i], points[j])
                value = max(1, round(distance * rng.uniform(0.5, 1.5)))
            elif family == 3:
                value = rng.randint(1, 10) if rng.random() < 0.22 else rng.randint(35, 99)
            else:
                raise ValueError("unknown workload family")
            row.append(value)
        costs.append(row)
    return {"id": f"setup-{seed}", "family": family, "costs": costs}


def cost(matrix: Sequence[Sequence[int]], order: Sequence[int]) -> int:
    return sum(matrix[a][b] for a, b in zip(order, [*order[1:], order[0]], strict=True))


def greedy(matrix: Sequence[Sequence[int]]) -> list[int]:
    """Strong reference: best nearest-neighbor cycle over every starting job."""
    routes = []
    for start in range(len(matrix)):
        order = [start]
        while len(order) < len(matrix):
            order.append(
                min(
                    (j for j in range(len(matrix)) if j not in order),
                    key=lambda j: (matrix[order[-1]][j], j),
                )
            )
        offset = order.index(0)
        routes.append(order[offset:] + order[:offset])
    return min(routes, key=lambda route: (cost(matrix, route), route))


def local_search(matrix: Sequence[Sequence[int]], initial: Sequence[int]) -> list[int]:
    """Fixed deterministic relocate/swap hill-climber; benchmark control only."""
    order = list(initial)
    while True:
        best, best_cost = order, cost(matrix, order)
        for i in range(1, len(order)):
            removed = order[:i] + order[i + 1 :]
            for j in range(1, len(order)):
                candidate = removed[:j] + [order[i]] + removed[j:]
                value = cost(matrix, candidate)
                if value < best_cost:
                    best, best_cost = candidate, value
                candidate = list(order)
                candidate[i], candidate[j] = candidate[j], candidate[i]
                value = cost(matrix, candidate)
                if value < best_cost:
                    best, best_cost = candidate, value
        if best == order:
            return order
        order = best


def build_oracle(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-O2",
            str(Path(__file__).with_name("sequence_oracle.cpp")),
            "-o",
            str(output),
        ],
        check=True,
    )
    return output


class SequenceProblem:
    def __init__(self, data: Mapping[str, Any], oracle: Path) -> None:
        self.data = dict(data)
        self.matrix = data["costs"]
        self.n = len(self.matrix)
        text = str(self.n) + "\n" + "\n".join(" ".join(map(str, row)) for row in self.matrix)
        answer = subprocess.check_output([str(oracle)], input=text, text=True).splitlines()
        self.optimal_cost = int(answer[0])
        self.optimal_order = list(map(int, answer[1].split()))
        assert sorted(self.optimal_order) == list(range(self.n))
        assert cost(self.matrix, self.optimal_order) == self.optimal_cost
        self.starting_order = greedy(self.matrix)
        self.starting_cost = cost(self.matrix, self.starting_order)

    def parse(self, configuration: Mapping[str, Any]) -> list[int]:
        if set(configuration) != {"order"} or not isinstance(configuration["order"], str):
            raise ValueError("expected one order string")
        order = [int(value.strip()) for value in configuration["order"].split(",")]
        if sorted(order) != list(range(self.n)) or order[0] != 0:
            raise ValueError("order must start at zero and contain each job exactly once")
        return order

    def trace(self, order: Sequence[int]) -> list[dict[str, int]]:
        return [
            {"from": a, "to": b, "minutes": self.matrix[a][b]}
            for a, b in zip(order, [*order[1:], order[0]], strict=True)
        ]

    def prompt_data(self) -> dict[str, Any]:
        return {
            "job_ids": list(range(self.n)),
            "cost_matrix": self.matrix,
            "current_order": self.starting_order,
            "current_cost": self.starting_cost,
            "current_transitions": self.trace(self.starting_order),
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
                        "cost": cost(self.matrix, order),
                        "transitions": self.trace(order),
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
        best = min((r for r in candidates if r["valid"]), key=lambda r: r["cost"], default=None)
        if best is not None and best["cost"] < self.starting_cost:
            selected, chosen_cost = best["configuration"], best["cost"]
        else:
            selected = {"order": ",".join(map(str, self.starting_order))}
            chosen_cost = self.starting_cost
        return {
            "selected": selected,
            "cost": chosen_cost,
            "quality": self.optimal_cost / chosen_cost,
            "starting_cost": self.starting_cost,
            "optimal_cost": self.optimal_cost,
            "candidates": candidates,
        }
