"""A real LLM intake factory for two kinds of caller-supplied, measured targets.

Run with LIBRSI_INTAKE_MODEL and OPENAI_API_KEY configured:
  librsi-http --factory examples.goal_intake_service:create_service --data-dir /path/to/data

This sample registers external execution routes. An agent consumes the resulting
run's next actions and submits actual experiment results via the existing API.
It does not fabricate experiments or claim the supplied measurements are authenticated.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from statistics import fmean

from librsi import CapabilityBinding, Metric, TargetRef, TargetSnapshot
from librsi.identity import digest
from librsi.intake import IntakeAdapter, IntakeContext, IntakeMetric, IntakeNeedsInformation
from librsi.providers import OpenAIResponsesBackend, OpenAIResponsesConfig
from librsi.service import LibRSIService


def _collect(request, *, kind):
    context = request.context
    configuration = context.get("configuration")
    examples = context.get("examples")
    target_id = context.get("target_id")
    if (
        not isinstance(configuration, Mapping)
        or not configuration
        or not isinstance(target_id, str)
        or not target_id.strip()
    ):
        raise IntakeNeedsInformation("Supply target_id and the current configuration object.")
    if not isinstance(examples, tuple) or len(examples) < 2:
        raise IntakeNeedsInformation(
            "Supply at least two measured examples, including their inputs and outputs."
        )
    if any(
        not isinstance(row, Mapping) or "input" not in row or "output" not in row
        for row in examples
    ):
        raise IntakeNeedsInformation("Include input and output in every measured example.")
    if kind == "prompt":
        if any(type(row.get("passed")) is not bool for row in examples):
            raise IntakeNeedsInformation(
                "Include a measured passed boolean for each prompt example."
            )
        scores = [float(row["passed"]) for row in examples]
        metric_id, description = "pass_rate", "Fraction passing the caller's fixed task evaluator"
    else:
        if any(
            row.get("relevant_rank") is not None
            and (type(row["relevant_rank"]) is not int or row["relevant_rank"] < 1)
            for row in examples
        ):
            raise IntakeNeedsInformation(
                "Use a positive relevant_rank or null for each search example."
            )
        if any("relevant_rank" not in row for row in examples):
            raise IntakeNeedsInformation("Supply measured relevant_rank for each search example.")
        scores = [
            0.0 if row["relevant_rank"] is None else 1.0 / row["relevant_rank"] for row in examples
        ]
        metric_id, description = "mrr", "Mean reciprocal rank using the caller's relevance labels"
    snapshot = TargetSnapshot(
        target=TargetRef(target_id=target_id, kind=kind),
        revision=digest(configuration),
        state=configuration,
    )
    return IntakeContext(
        snapshot=snapshot,
        metrics=(
            IntakeMetric(
                Metric(
                    metric_id=metric_id, direction="increase", role="objective", unit="fraction"
                ),
                fmean(scores),
                0.01,
                description,
            ),
        ),
        facts={"examples": examples, "measurement_source": "caller supplied"},
    )


def create_service(*, data_directory, limits):
    from openai import OpenAI

    model = os.environ.get("LIBRSI_INTAKE_MODEL")
    if not model:
        raise ValueError("set LIBRSI_INTAKE_MODEL explicitly")
    backend = OpenAIResponsesBackend(
        OpenAIResponsesConfig(model=model), client=OpenAI(timeout=60, max_retries=0)
    )
    bindings = (
        CapabilityBinding(action_kind="improvement-cycle", family="reasoner", posture="external"),
        CapabilityBinding(
            action_kind="investigation-reason", family="reasoner", posture="external"
        ),
        CapabilityBinding(
            action_kind="investigation-experiment", family="experimenter", posture="external"
        ),
    )
    return LibRSIService.local(
        data_directory,
        limits=limits,
        intake_backend=backend,
        intake_adapters=(
            IntakeAdapter(
                "prompts-v1",
                "Improve prompts or investigate prompt failures",
                lambda request: _collect(request, kind="prompt"),
                bindings,
            ),
            IntakeAdapter(
                "search-v1",
                "Improve document search ranking or investigate retrieval failures",
                lambda request: _collect(request, kind="search"),
                bindings,
            ),
        ),
    )
