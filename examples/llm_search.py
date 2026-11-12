"""LLM-generated scoring formulas and proposer instructions for a bounded experiment.

This is an example backend, not the internal libRSI Codex provider. It uses the
public Codex CLI, records its usage, and gives the model no execution tools.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, cast

import numpy as np
from document_search import SearchIndex, propose, tokens

from librsi import LearningCase, ReasoningRequest, ReasoningResult, TaskMeasurement
from librsi.identity import canonical_json, digest

BASE_FORMULA = {"formula": "tf"}
BASE_INSTRUCTIONS = {
    "instruction": "Use the measured retrieval feedback to propose two distinct scoring formulas "
    "that are likely to improve MRR@5 on new queries. Explain the reason for each proposal."
}
FORMULA_CONTRACT = """You improve a lexical search engine over 5,183 scientific abstracts.
For each query term present in a document, your formula produces a contribution;
the engine sums query-term-count * contribution, then ranks documents by score.
Variables: tf = term count in title+abstract; title_tf = count in title;
idf = log(1+(N-document_frequency+0.5)/(document_frequency+0.5));
length = document token count / corpus mean token count.
No stemming or stopword removal. No embeddings, model calls or training at search time.
Allowed grammar: numeric constants of magnitude <=100, variables above, + - * /,
unary minus, log1p(x), sqrt(x), minimum(x,y), maximum(x,y).
No other Python syntax, powers, functions, names or strings. At most 800 characters
and 120 AST nodes. All contributions must be finite. Configuration is exactly
{"formula": "YOUR EXPRESSION"}. You may combine these primitives freely;
there is no prewritten candidate inventory. Return exactly two distinct proposals,
neither identical to the active formula. Each reason is a hypothesis, not a measured result.
Use only supplied training feedback. Do not use tools or access files or the web.
"""


def parse_formula(configuration: Mapping[str, Any]) -> ast.Expression:
    if set(configuration) != {"formula"} or not isinstance(configuration["formula"], str):
        raise ValueError("configuration must contain only a formula string")
    text = configuration["formula"]
    if len(text) > 800:
        raise ValueError("formula too long")
    tree = ast.parse(text, mode="eval")
    if len(list(ast.walk(tree))) > 120:
        raise ValueError("formula too complex")

    def check(node: ast.AST) -> None:
        if isinstance(node, ast.Expression):
            check(node.body)
        elif isinstance(node, ast.Constant):
            if (
                type(node.value) not in (float, int)
                or not np.isfinite(node.value)
                or abs(cast(float, node.value)) > 100
            ):
                raise ValueError("invalid constant")
        elif isinstance(node, ast.Name):
            if node.id not in {"tf", "title_tf", "idf", "length"}:
                raise ValueError("invalid variable")
        elif isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            check(node.left)
            check(node.right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            check(node.operand)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            arity = {"log1p": 1, "sqrt": 1, "minimum": 2, "maximum": 2}
            if node.func.id not in arity or len(node.args) != arity[node.func.id] or node.keywords:
                raise ValueError("invalid function")
            for arg in node.args:
                check(arg)
        else:
            raise ValueError("unsupported formula syntax")

    check(tree)
    return tree


def evaluate_formula(node: ast.AST, variables: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return evaluate_formula(node.body, variables)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return variables[node.id]
    if isinstance(node, ast.UnaryOp):
        return -evaluate_formula(node.operand, variables)
    if isinstance(node, ast.BinOp):
        left, right = (
            evaluate_formula(node.left, variables),
            evaluate_formula(node.right, variables),
        )
        operations = {
            ast.Add: np.add,
            ast.Sub: np.subtract,
            ast.Mult: np.multiply,
            ast.Div: np.divide,
        }
        return operations[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        functions = {
            "log1p": np.log1p,
            "sqrt": np.sqrt,
            "minimum": np.minimum,
            "maximum": np.maximum,
        }
        return functions[node.func.id](*(evaluate_formula(arg, variables) for arg in node.args))
    raise ValueError("unvalidated syntax")


class FormulaIndex(SearchIndex):
    @staticmethod
    def validate(configuration: Mapping[str, Any]) -> None:
        parse_formula(configuration)

    def search(self, configuration: Mapping[str, Any], query: str) -> list[str]:
        tree = parse_formula(configuration)
        self.ranked_queries += 1
        scores = np.zeros(len(self.documents))
        for term, count in Counter(tokens(query)).items():
            if term not in self.postings:
                continue
            ids = self.postings[term]
            key = (configuration["formula"], 0, term)
            if key not in self.weights:
                variables = {
                    "tf": np.asarray([self.body[i][term] for i in ids], dtype=float),
                    "title_tf": np.asarray([self.titles[i][term] for i in ids], dtype=float),
                    "idf": self.idf[term],
                    "length": np.asarray([self.lengths[i] / self.average_length for i in ids]),
                }
                with np.errstate(all="raise"):
                    weights = evaluate_formula(tree, variables)
                if not np.all(np.isfinite(weights)):
                    raise ValueError("nonfinite formula result")
                self.weights[key] = weights
            scores[ids] += count * self.weights[key]
        return [self.documents[i]["path"] for i in np.argsort(-scores, kind="stable")[:5]]

    def diagnostics(self, configuration: Mapping[str, Any], ids: Sequence[str]) -> dict[str, Any]:
        measured = self.measure(configuration, self.resolve(ids))
        titles = {row["path"]: row["text"].splitlines()[0] for row in self.documents}
        # Deterministic: show six worst training cases, then two best; no scoring labels.
        ordered = sorted(
            measured.output["queries"], key=lambda row: (row["reciprocal_rank"], row["id"])
        )
        examples = []
        for row in [*ordered[:6], *ordered[-2:]]:
            query = self.queries[row["id"]]
            examples.append(
                {
                    "query": query["query"],
                    "reciprocal_rank": row["reciprocal_rank"],
                    "top_titles": [titles[key] for key in row["ranking"][:3]],
                    "relevant_titles": [titles[key] for key in query["relevant"]],
                }
            )
        return {
            "configuration": dict(configuration),
            "mrr_at_5": measured.value,
            "training_query_count": len(ids),
            "examples": examples,
        }


class CodexSampler:
    """One isolated model turn per call; persist receipts before parsing proposals.

    No automatic retries. A failed call retains evidence and stops the experiment.
    The CLI exposes token usage, not a billed dollar amount or immutable model snapshot.
    """

    def __init__(self, directory: Path, model: str, *, max_calls: int = 24) -> None:
        self.directory, self.model, self.max_calls = directory, model, max_calls
        directory.mkdir(parents=True, exist_ok=False)
        self.receipts: list[dict[str, Any]] = []
        self._lock = Lock()
        self.version = subprocess.check_output(["codex", "--version"], text=True).strip()
        self.instructions = directory / "instructions.txt"
        self.instructions.write_text(
            "You are a stateless benchmark proposal generator. Use only supplied data. "
            "Do not use tools or access files. Return only the requested JSON object.\n"
        )

    def call(self, prompt: str, *, field: str, role: str, count: int = 2) -> list[dict[str, Any]]:
        if count not in (1, 2):
            raise ValueError("candidate count must be one or two")
        # Reserve before any provider access, including concurrent benchmark samples.
        with self._lock:
            if len(self.receipts) >= self.max_calls:
                raise RuntimeError("model-call budget exhausted")
            number = len(self.receipts) + 1
            receipt: dict[str, Any] = {}
            self.receipts.append(receipt)
        path = self.directory / f"{number:03d}"
        path.mkdir(exist_ok=False)
        schema = {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "configuration": {
                                "type": "object",
                                "properties": {field: {"type": "string"}},
                                "required": [field],
                                "additionalProperties": False,
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["configuration", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["candidates"],
            "additionalProperties": False,
        }
        (path / "schema.json").write_text(canonical_json(schema) + "\n")
        (path / "prompt.txt").write_text(prompt)
        command = [
            "codex",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--json",
            "--color",
            "never",
            "--model",
            self.model,
            "--sandbox",
            "read-only",
            "--cd",
            str(path),
            "-c",
            'model_reasoning_effort="high"',
            "-c",
            "project_doc_max_bytes=0",
            "-c",
            'web_search="disabled"',
            "-c",
            f'model_instructions_file="{self.instructions}"',
            "--output-schema",
            str(path / "schema.json"),
        ]
        for feature in (
            "shell_tool",
            "apps",
            "plugins",
            "multi_agent",
            "browser_use",
            "computer_use",
            "image_generation",
            "view_image",
            "hooks",
            "shell_snapshot",
            "skill_search",
            "goals",
            "sleep_tool",
        ):
            command += ["--disable", feature]
        command += ["-"]
        started = perf_counter()
        receipt.update(
            {
                "number": number,
                "role": role,
                "model": self.model,
                "provider": "OpenAI via Codex CLI",
                "reasoning_effort": "high",
                "cli_version": self.version,
                "prompt_sha256": digest(prompt),
                "provider_cost_usd": None,
                "candidate_count": count,
            }
        )
        (path / "receipt.json").write_text(canonical_json(receipt) + "\n")
        with (path / "events.jsonl").open("w") as out, (path / "stderr.txt").open("w") as err:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                stdout=out,
                stderr=err,
                timeout=180,
                env=os.environ.copy(),
                check=False,
            )
        receipt.update(wall_seconds=perf_counter() - started, returncode=completed.returncode)
        events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
        usage = [event["usage"] for event in events if event["type"] == "turn.completed"]
        messages = [
            event["item"]["text"]
            for event in events
            if event["type"] == "item.completed" and event["item"]["type"] == "agent_message"
        ]
        tool_items = [
            event
            for event in events
            if event["type"].startswith("item.")
            and event["item"]["type"] not in {"agent_message", "reasoning"}
        ]
        receipt.update(usage=usage, tool_items=len(tool_items))
        (path / "receipt.json").write_text(canonical_json(receipt) + "\n")
        if completed.returncode or len(usage) != 1 or not messages or tool_items:
            raise RuntimeError(
                f"model call {number} failed or used tools; inspect retained receipt"
            )
        response = json.loads(messages[-1])
        choices = response["candidates"]
        if len(choices) != count or (
            count == 2 and choices[0]["configuration"] == choices[1]["configuration"]
        ):
            raise ValueError(f"model must propose exactly {count} distinct candidates")
        (path / "response.json").write_text(canonical_json(response) + "\n")
        print(
            f"Model call {number}: {role}, {receipt['wall_seconds']:.1f}s, {usage[0]}", flush=True
        )
        return choices


class FormulaProposer:
    def __init__(
        self, sampler: CodexSampler, index: FormulaIndex, instructions: Mapping[str, Any], role: str
    ) -> None:
        validate_instructions(instructions)
        self.sampler, self.index, self.instructions, self.role = (
            sampler,
            index,
            dict(instructions),
            role,
        )

    def generate(
        self, configuration: Mapping[str, Any], ids: Sequence[str]
    ) -> list[dict[str, Any]]:
        prompt = FORMULA_CONTRACT + "\nPROPOSER STRATEGY:\n" + self.instructions["instruction"]
        prompt += "\nMEASURED TRAINING FEEDBACK:\n" + canonical_json(
            self.index.diagnostics(configuration, ids)
        )
        choices = self.sampler.call(prompt, field="formula", role=self.role)
        for choice in choices:
            parse_formula(choice["configuration"])
            if choice["configuration"] == configuration:
                raise ValueError("model repeated the active formula")
        return choices

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        ids = [key for row in request.context["feedback"] for key in row["case"]["queries"]]
        choices = self.generate(request.context["configuration"], ids)
        return propose(request, [row["configuration"] for row in choices])


def validate_instructions(configuration: Mapping[str, Any]) -> None:
    if (
        set(configuration) != {"instruction"}
        or not isinstance(configuration["instruction"], str)
        or not 1 <= len(configuration["instruction"].strip()) <= 3000
    ):
        raise ValueError(
            "proposer configuration must be one instruction string of 1..3000 characters"
        )


class InstructionProposer:
    def __init__(self, sampler: CodexSampler) -> None:
        self.sampler = sampler

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        prompt = (
            "Improve the instruction given to an LLM that proposes search scoring formulas. "
            "Return two different replacement instruction strings (<=3000 characters each). "
            "The grammar, two-candidate budget, training diagnostics, model, and evaluation "
            "remain fixed. You may change the reasoning strategy, use of diagnostics, or "
            "diversity of proposals. You cannot change the metric or see downstream test data. "
            "Use measured feedback below; a claim of improvement is only a hypothesis. "
            "Do not use tools.\nINNER TASK CONTRACT:\n"
            + FORMULA_CONTRACT
            + "\nMETA TRAINING FEEDBACK:\n"
            + canonical_json(request.context)
        )
        choices = self.sampler.call(prompt, field="instruction", role="meta-instruction-proposer")
        for row in choices:
            validate_instructions(row["configuration"])
            if row["configuration"] == request.context["configuration"]:
                raise ValueError("model repeated the active instructions")
        return propose(request, [row["configuration"] for row in choices])


class FormulaAdapter:
    adapter_id = "llm-formula-paired-search-v1"

    def __init__(self, index: FormulaIndex) -> None:
        self.index = index

    def validate_configuration(self, configuration: Mapping[str, Any]) -> None:
        parse_formula(configuration)

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        self.index.adapter_evaluations += 1
        queries = self.index.resolve(case.payload["queries"])
        scored, reference = (
            self.index.measure(configuration, queries),
            self.index.measure(BASE_FORMULA, queries),
        )
        return TaskMeasurement(
            {
                "mrr_at_5": scored.value,
                "reference_mrr_at_5": reference.value,
                "ranking_digest": digest(scored.output),
                "query_count": len(queries),
            },
            scored.value - reference.value,
        )


class InstructionAdapter:
    """A prompt's utility: generate two formulas, select on tuning, score separately.

    Freeze one actual model sample per (instruction, tuning IDs) for this run.
    Framework remeasurement repeats rankings, not paid model generation. The
    cache cannot read scoring IDs/labels. Fresh tasks get fresh model calls.
    """

    adapter_id = "llm-instruction-paired-utility-v1"

    def __init__(self, index: FormulaIndex, sampler: CodexSampler) -> None:
        self.index, self.sampler = index, sampler
        self.samples: dict[str, list[dict[str, Any]]] = {}

    validate_configuration = staticmethod(validate_instructions)

    def utility(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        key = digest({"configuration": dict(configuration), "tuning": list(case.payload["tuning"])})
        if key not in self.samples:
            proposer = FormulaProposer(
                self.sampler, self.index, configuration, "meta-inner-formula-proposer"
            )
            self.samples[key] = proposer.generate(BASE_FORMULA, case.payload["tuning"])
        choices = [BASE_FORMULA, *(row["configuration"] for row in self.samples[key])]
        tuning = self.index.resolve(case.payload["tuning"])
        values = [self.index.measure(choice, tuning).value for choice in choices]
        best = max(range(len(values)), key=values.__getitem__)
        selected = choices[best] if values[best] - values[0] >= 0.01 else BASE_FORMULA
        scoring = self.index.measure(selected, self.index.resolve(case.payload["scoring"]))
        return TaskMeasurement(
            {
                "selected": dict(selected),
                "candidate_formulas": choices,
                "tuning_mrr": values,
                "scoring_mrr": scoring.value,
                "sample_key": key,
                "ranking_digest": digest(scoring.output),
            },
            scoring.value,
        )

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        self.index.adapter_evaluations += 1
        measured, reference = (
            self.utility(configuration, case),
            self.utility(BASE_INSTRUCTIONS, case),
        )
        return TaskMeasurement(
            {"measurement": dict(measured.output), "reference": dict(reference.output)},
            measured.value - reference.value,
        )
