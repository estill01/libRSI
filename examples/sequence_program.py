"""Bounded search programs assembled by an LLM from audited scheduling primitives.

Configurations are JSON data, never executable model-generated Python. Every
program gets exactly 256 route-cost evaluations and retains its best valid cycle.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping
from typing import Any

from setup_sequence import SequenceProblem, cost

BUDGET = 256
BASE_PROGRAM = {"program": '{"stages":[]}'}
BASE_INSTRUCTIONS = {
    "instruction": "Use the measured planning feedback to propose two distinct bounded search programs that reduce setup costs on new workloads. Consider the choice and ordering of search operations, exploration and acceptance. Explain each hypothesis briefly."
}
PROGRAM_CONTRACT = """Design a bounded search program for repeating production sequences.
Every workload has 14 jobs and an asymmetric matrix of setup minutes. A cycle
contains each job once, begins at job 0 and returns to 0. The starting cycle is
the cheapest nearest-neighbor cycle over all starting jobs. The host keeps the
best valid cycle seen, so exploratory uphill moves cannot worsen the returned plan.
You assemble a NEW program; there is no fixed candidate-program inventory.
Return configuration {"program":"JSON TEXT"}, where the JSON text is exactly
{"stages":[stage,...]}. Use 1 to 6 stages. Every stage has exactly these fields:
  operators: nonempty distinct list drawn from ["swap","relocate","reverse"]
  sampling: "random", "expensive", or "scan"
  acceptance: "improve", "anneal", or "threshold"
  temperature: number in [0,0.2]
  cooling: number in [0,1]
  restart: "continue", "best", or "kick"
  kick: integer in [0,4] (number of random swaps when restart is kick)
  weight: integer in [1,100]
The 256 cost evaluations are divided proportionally to stage weights; the last
stage receives any remainder. Initial/current/best states and all costs are real.
Each evaluated candidate is a swap, relocation, or inclusive reversal of positions
1..13, keeping job 0 fixed. Operators cycle through their listed order.
random: two random distinct positions; scan: enumerate position pairs;
expensive: choose a moved job after a transition with probability proportional
to that transition's cost, plus a random second position.
improve accepts only lower current cost. threshold accepts delta <= T.
anneal accepts improvements, else with probability exp(-delta/T).
T = temperature * starting_cost * (1 - cooling * fraction_of_stage_completed).
restart best restores the best known cycle. restart kick first perturbs best by
kick swaps and spends the first stage evaluation on that resulting cycle.
The random seed is fixed per workload; different workloads have distinct seeds.
The baseline program has no stages and returns the starting cycle. Empty programs
are allowed only as the baseline, not as a proposed revision.
Return exactly two distinct programs with short reasons. Do not request tools,
change host primitives, increase the budget, or hardcode workload IDs or cycles.
"""


def parse_program(
    configuration: Mapping[str, Any], *, allow_baseline: bool = True
) -> dict[str, Any]:
    if set(configuration) != {"program"} or not isinstance(configuration["program"], str):
        raise ValueError("expected one program JSON string")
    if len(configuration["program"]) > 6000:
        raise ValueError("program too long")
    program = json.loads(configuration["program"])
    if not isinstance(program, dict) or set(program) != {"stages"}:
        raise ValueError("program must contain only stages")
    stages = program["stages"]
    if not isinstance(stages, list) or not (0 if allow_baseline else 1) <= len(stages) <= 6:
        raise ValueError("invalid stage count")
    fields = {
        "operators",
        "sampling",
        "acceptance",
        "temperature",
        "cooling",
        "restart",
        "kick",
        "weight",
    }
    for stage in stages:
        if not isinstance(stage, dict) or set(stage) != fields:
            raise ValueError("stage fields do not match the program contract")
        ops = stage["operators"]
        if (
            not isinstance(ops, list)
            or not ops
            or any(not isinstance(x, str) for x in ops)
            or len(set(ops)) != len(ops)
            or not set(ops) <= {"swap", "relocate", "reverse"}
        ):
            raise ValueError("invalid operators")
        for key, choices in {
            "sampling": {"random", "expensive", "scan"},
            "acceptance": {"improve", "anneal", "threshold"},
            "restart": {"continue", "best", "kick"},
        }.items():
            if stage[key] not in choices:
                raise ValueError(f"invalid {key}")
        for key, limit in (("temperature", 0.2), ("cooling", 1)):
            if (
                type(stage[key]) not in (int, float)
                or not math.isfinite(stage[key])
                or not 0 <= stage[key] <= limit
            ):
                raise ValueError(f"invalid {key}")
        for key, low, high in (("kick", 0, 4), ("weight", 1, 100)):
            if type(stage[key]) is not int or not low <= stage[key] <= high:
                raise ValueError(f"invalid {key}")
    return program


def mutate(order, operator, i, j):
    result = list(order)
    if operator == "swap":
        result[i], result[j] = result[j], result[i]
    elif operator == "relocate":
        result.insert(j, result.pop(i))
    elif operator == "reverse":
        a, b = sorted((i, j))
        result[a : b + 1] = reversed(result[a : b + 1])
    else:
        raise ValueError("invalid operator")
    return result


def execute(configuration: Mapping[str, Any], problem: SequenceProblem) -> dict[str, Any]:
    stages = parse_program(configuration)["stages"]
    seed = int.from_bytes(hashlib.sha256(problem.data["id"].encode()).digest()[:8], "big")
    rng = random.Random(seed)
    best = list(problem.starting_order)
    current = list(best)
    best_cost = current_cost = problem.starting_cost
    used = 0
    trace = []
    total_weight = sum(s["weight"] for s in stages)
    for stage_index, stage in enumerate(stages):
        count = (
            BUDGET - used
            if stage_index == len(stages) - 1
            else BUDGET * stage["weight"] // total_weight
        )
        if stage["restart"] in ("best", "kick"):
            current = list(best)
            current_cost = best_cost
        before = best_cost
        for step in range(count):
            if step == 0 and stage["restart"] == "kick":
                candidate = list(best)
                for _ in range(stage["kick"]):
                    i, j = rng.sample(range(1, problem.n), 2)
                    candidate = mutate(candidate, "swap", i, j)
            else:
                if stage["sampling"] == "scan":
                    i = 1 + (step // (problem.n - 2)) % (problem.n - 1)
                    other = [j for j in range(1, problem.n) if j != i]
                    j = other[step % len(other)]
                elif stage["sampling"] == "expensive":
                    i = rng.choices(
                        list(range(1, problem.n)),
                        weights=[
                            problem.matrix[current[k - 1]][current[k]] for k in range(1, problem.n)
                        ],
                    )[0]
                    j = rng.choice([j for j in range(1, problem.n) if j != i])
                else:
                    i, j = rng.sample(range(1, problem.n), 2)
                operator = stage["operators"][step % len(stage["operators"])]
                candidate = mutate(current, operator, i, j)
            value = cost(problem.matrix, candidate)
            used += 1
            if value < best_cost:
                best, best_cost = list(candidate), value
            delta = value - current_cost
            temperature = (
                stage["temperature"]
                * problem.starting_cost
                * (1 - stage["cooling"] * step / max(1, count - 1))
            )
            accept = delta < 0
            if stage["acceptance"] == "threshold":
                accept = delta <= temperature
            elif stage["acceptance"] == "anneal" and not accept and temperature > 0:
                accept = rng.random() < math.exp(-delta / temperature)
            if accept or (step == 0 and stage["restart"] == "kick"):
                current, current_cost = candidate, value
        trace.append(
            {
                "stage": stage_index,
                "evaluations": count,
                "cost_before": before,
                "best_cost": best_cost,
            }
        )
    assert sorted(best) == list(range(problem.n)) and best[0] == 0
    assert best_cost == cost(problem.matrix, best) and best_cost <= problem.starting_cost
    assert used == (BUDGET if stages else 0)
    return {
        "order": best,
        "cost": best_cost,
        "quality": problem.optimal_cost / best_cost,
        "cost_reduction": 1 - best_cost / problem.starting_cost,
        "evaluations": used,
        "stages": trace,
    }
