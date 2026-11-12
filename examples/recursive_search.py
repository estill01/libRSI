"""Measured recursive prompt cascades; five independent samples per policy.

Depth 1: instructions -> formulas.
Depth 2: meta instructions -> proposer instructions -> formulas.
Depth 3: meta-meta instructions -> meta instructions -> proposer instructions -> formulas.

A native libRSI pass optimizes the instruction at the chosen depth. Candidate
policies are evaluated by propagating their actual generated children downward.
The nested utility is a proxy; it does not run a complete adoption loop per child.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from benchmark_document_search import write_json
from document_search import propose
from llm_search import (
    BASE_FORMULA,
    BASE_INSTRUCTIONS,
    FORMULA_CONTRACT,
    CodexSampler,
    FormulaIndex,
    parse_formula,
    validate_instructions,
)

from librsi import LearningCase, ReasoningRequest, ReasoningResult, TaskMeasurement
from librsi.identity import canonical_json, digest

REPLICATES = 5
WORKERS = 3
DEFAULTS = {
    1: BASE_INSTRUCTIONS,
    2: {
        "instruction": "Use the measured retrieval feedback to improve the instruction given to "
        "a formula proposer. Produce one practical replacement that should generate more useful "
        "scoring formulas on unseen queries."
    },
    3: {
        "instruction": "Use the measured feedback to improve the strategy used to revise a formula "
        "proposer's instructions. Produce one replacement instruction for that meta proposer."
    },
}


def instruction_task(depth: int) -> str:
    return {
        1: "a formula proposer that emits two scoring expressions",
        2: "a meta proposer that emits one revised instruction for the formula proposer",
        3: "a meta-meta proposer that emits one revised instruction for the meta proposer",
    }[depth]


class CascadeCache:
    """Generate independent chains once; reuse them for held-out remeasurement.

    Every generated instruction is used in the next model call, never merely
    described. Scoring labels are absent from all generation prompts. The cache
    freezes before final test scoring and refuses any subsequent model access.
    """

    def __init__(
        self,
        index: FormulaIndex,
        sampler: CodexSampler,
        directory: Path,
        generation_ids: Sequence[str],
        child_seeds: Mapping[int, Mapping[str, Any]],
    ) -> None:
        self.index, self.sampler, self.directory = index, sampler, directory
        directory.mkdir(exist_ok=False)
        self.generation_ids = list(generation_ids)
        self.child_seeds = {key: dict(value) for key, value in child_seeds.items()}
        self.diagnostics = index.diagnostics(BASE_FORMULA, generation_ids)
        self.samples: dict[str, list[dict[str, Any]]] = {}
        self.frozen = False

    def key(self, depth: int, configuration: Mapping[str, Any]) -> str:
        return digest(
            {
                "depth": depth,
                "configuration": dict(configuration),
                "generation_ids": self.generation_ids,
                "children": {str(k): v for k, v in self.child_seeds.items() if k < depth},
            }
        )

    def generate(
        self, depth: int, configuration: Mapping[str, Any], replicate: int
    ) -> dict[str, Any]:
        current = dict(configuration)
        chain = []
        key = self.key(depth, configuration)
        for current_depth in range(depth, 1, -1):
            prompt = (
                f"You are {instruction_task(current_depth)}. Execute the strategy below. "
                'Return exactly ONE candidate, configuration {"instruction": "text"}, '
                "with a reason. The instruction should be <=1200 characters. You can change "
                "reasoning strategy and proposal diversity, not the formula grammar, metrics, "
                "data, model, or candidate budget. Use only supplied generation feedback; "
                "do not use tools.\nDOWNSTREAM CONTRACT:\n"
                + FORMULA_CONTRACT
                + "\nSTRATEGY TO EXECUTE:\n"
                + current["instruction"]
                + "\nINSTRUCTION TO REVISE:\n"
                + canonical_json(self.child_seeds[current_depth - 1])
                + "\nMEASURED GENERATION FEEDBACK:\n"
                + canonical_json(self.diagnostics)
            )
            child = self.sampler.call(
                prompt,
                field="instruction",
                count=1,
                role=f"cascade-d{depth}:{key[:12]}:sample{replicate}:instruction-d{current_depth - 1}",
            )[0]
            validate_instructions(child["configuration"])
            chain.append(
                {
                    "depth": current_depth,
                    "input_instruction": current,
                    "output_instruction": child["configuration"],
                    "reason": child["reason"],
                }
            )
            current = dict(child["configuration"])
        prompt = (
            FORMULA_CONTRACT
            + "\nPROPOSER STRATEGY:\n"
            + current["instruction"]
            + "\nMEASURED GENERATION FEEDBACK:\n"
            + canonical_json(self.diagnostics)
        )
        choices = self.sampler.call(
            prompt, field="formula", role=f"cascade-d{depth}:{key[:12]}:sample{replicate}:formulas"
        )
        for choice in choices:
            parse_formula(choice["configuration"])
            if choice["configuration"] == BASE_FORMULA:
                raise ValueError("model repeated the baseline formula")
        result = {
            "sample": replicate,
            "root_depth": depth,
            "root_configuration": dict(configuration),
            "chain": chain,
            "formula_instructions": current,
            "candidates": choices,
        }
        write_json(self.directory / f"{key}-{replicate}-generated.json", result)
        return result

    def prepare(self, depth: int, configuration: Mapping[str, Any]) -> list[dict[str, Any]]:
        validate_instructions(configuration)
        key = self.key(depth, configuration)
        if key in self.samples:
            return self.samples[key]
        if self.frozen:
            raise RuntimeError("cannot generate a model sample after final freeze")
        # Independent inference turns run in parallel; scoring and native writes remain serial.
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [
                pool.submit(self.generate, depth, configuration, i) for i in range(REPLICATES)
            ]
            generated = [future.result() for future in futures]
        for row in generated:
            configs = [BASE_FORMULA, *(choice["configuration"] for choice in row["candidates"])]
            values = [
                self.index.measure(config, self.index.resolve(self.generation_ids)).value
                for config in configs
            ]
            best = max(range(len(values)), key=values.__getitem__)
            row["tuning_mrr"] = values
            row["selected"] = dict(
                configs[best] if values[best] - values[0] >= 0.01 else BASE_FORMULA
            )
            row["sample_key"] = key
            write_json(self.directory / f"{key}-{row['sample']}-selected.json", row)
        self.samples[key] = generated
        return generated

    def measure(
        self,
        depth: int,
        configuration: Mapping[str, Any],
        replicate: int,
        scoring_ids: Sequence[str],
    ) -> TaskMeasurement:
        row = self.prepare(depth, configuration)[replicate]
        measured = self.index.measure(row["selected"], self.index.resolve(scoring_ids))
        return TaskMeasurement(
            {
                "sample": replicate,
                "sample_key": row["sample_key"],
                "selected": row["selected"],
                "tuning_mrr": row["tuning_mrr"],
                "mrr_at_5": measured.value,
                "ranking_digest": digest(measured.output),
            },
            measured.value,
        )


class CascadeAdapter:
    adapter_id = "recursive-five-sample-paired-utility-v1"
    validate_configuration = staticmethod(validate_instructions)

    def __init__(self, cache: CascadeCache, depth: int, baseline: Mapping[str, Any]) -> None:
        self.cache, self.depth, self.baseline = cache, depth, dict(baseline)

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        self.cache.index.adapter_evaluations += 1
        sample, ids = case.payload["sample"], case.payload["scoring"]
        measured = self.cache.measure(self.depth, configuration, sample, ids)
        reference = self.cache.measure(self.depth, self.baseline, sample, ids)
        return TaskMeasurement(
            {"measurement": dict(measured.output), "reference": dict(reference.output)},
            measured.value - reference.value,
        )


class CascadePolicyProposer:
    def __init__(self, cache: CascadeCache, depth: int, prior: Sequence[Mapping[str, Any]]) -> None:
        self.cache, self.depth, self.prior = cache, depth, list(prior)

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        baseline = request.context["configuration"]
        traces = self.cache.prepare(self.depth, baseline)
        prompt = (
            f"Improve the strategy instruction for {instruction_task(self.depth)}. "
            "Return exactly TWO distinct replacement instructions, neither identical to the "
            "current instruction, each <=1200 characters. Configuration has only instruction. "
            "A libRSI experiment will propagate each instruction down to actual scoring formulas "
            "on five independent model samples. Each rewrite emits one child instruction; "
            "the final proposer emits two formulas. Optimize reliable out-of-sample MRR@5, "
            "not self-reported quality. You cannot change metrics, grammar, budgets, model, "
            "or acceptance. Use only training evidence below. No tools.\nFORMULA CONTRACT:\n"
            + FORMULA_CONTRACT
            + "\nNATIVE TRAINING FEEDBACK:\n"
            + canonical_json(request.context)
            + "\nEXAMPLE GENERATED CHAINS (FIRST TWO OF FIVE):\n"
            + canonical_json(traces[:2])
            + "\nEARLIER LEVELS (NO OFFICIAL TEST SCORES):\n"
            + canonical_json(self.prior)
        )
        choices = self.cache.sampler.call(
            prompt, field="instruction", role=f"optimize-instruction-depth-{self.depth}"
        )
        for choice in choices:
            validate_instructions(choice["configuration"])
            if choice["configuration"] == baseline:
                raise ValueError("root proposer repeated the active instruction")
        return propose(request, [choice["configuration"] for choice in choices])


class AuditAdapter:
    """Native tasks consume frozen cascades; the metric is raw audit MRR@5."""

    adapter_id = "recursive-frozen-cascade-audit-v1"
    validate_configuration = staticmethod(validate_instructions)

    def __init__(self, cache: CascadeCache, depth: int) -> None:
        self.cache, self.depth = cache, depth

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        if not self.cache.frozen:
            raise RuntimeError("audit requires frozen model samples")
        return self.cache.measure(
            self.depth, configuration, case.payload["sample"], case.payload["scoring"]
        )
