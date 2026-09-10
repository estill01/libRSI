"""Exact reasoning requests shared by execution and historical inspection."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from ..identity import thaw
from ..reasoning import ReasoningRequest, ReasoningResult
from ..records import Observation, record_from_dict
from ..runtime import Run, RunBudget
from .learning_host import case_from_record


def _base(inputs: Observation) -> ReasoningRequest:
    baseline = inputs.target_snapshot
    assert baseline is not None
    pass_id = inputs.value["pass_id"]
    configuration = inputs.value["configuration"]
    policy = configuration["policy"]
    feedback = tuple(
        cast(Observation, record_from_dict(thaw(item))) for item in inputs.value["feedback"]
    )
    if any(not isinstance(item, Observation) for item in feedback):
        raise ValueError("pass feedback must contain exact observations")
    refs = (baseline.ref, *(item.ref for item in feedback))
    request = ReasoningRequest(
        request_id=f"{pass_id}:ideas",
        kind="hypothesis-generation",
        instruction=(
            f"Propose 2 to {policy['max_candidates']} distinct revisions to the active strategy "
            "using measured task feedback. Each causal_model must contain only configuration: "
            "a complete replacement JSON object valid for this adapter. Do not repeat the baseline."
        ),
        input_refs=refs,
        target_snapshot=baseline,
        lineage=refs,
        context={
            "configuration": baseline.state,
            "policy": policy,
            "adapter_id": configuration["adapter_id"],
            "proposer_id": configuration["proposer_id"],
            "feedback": [
                {
                    "task_id": item.value["task_id"],
                    "case": case_from_record(
                        cast(Observation, record_from_dict(thaw(item.value["case"])))
                    ).payload,
                    "output": item.value["output"],
                    "value": item.value["value"],
                    "strategy": item.target_snapshot.root if item.target_snapshot else None,
                    "feedback": item.root,
                }
                for item in feedback
            ],
        },
    )
    if "history" in inputs.value:
        historical = tuple(record_from_dict(thaw(row)) for row in inputs.value["history"])
        if any(
            not isinstance(row, Observation)
            or row.kind != "learning.attempt-feedback"
            or row.target_snapshot != baseline
            for row in historical
        ):
            raise ValueError("learning context must contain baseline-bound attempt feedback")
        refs = (*request.input_refs, *(row.ref for row in historical))
        request = replace(
            request,
            input_refs=refs,
            lineage=refs,
            context={
                **request.context,
                "history": [cast(Observation, row).value for row in historical],
                "follow_up_to": configuration.get("follow_up_to"),
            },
        )
    return request


def reflection_request(inputs: Observation) -> ReasoningRequest | None:
    request = _base(inputs)
    if not inputs.value["configuration"]["policy"].get("reflect_on_failure", False):
        return None
    if not any(
        row["disposition"] not in {"pending", "verified", "activation-disabled"}
        for row in request.context.get("history", ())
    ):
        return None
    return replace(
        request,
        request_id=f"{inputs.value['pass_id']}:reflection",
        kind="reflection",
        instruction=(
            "Inspect the recorded unsuccessful attempts and training measurements. Distinguish "
            "observations from possible explanations; identify an assumption to test differently. "
            "A rejection alone does not prove its cause. State open questions. Your reflection "
            "is a proposal, never evidence, approval, or permission to change acceptance rules."
        ),
    )


def proposal_request(
    inputs: Observation, reflection: ReasoningResult | None = None
) -> ReasoningRequest:
    request = _base(inputs)
    expected = reflection_request(inputs)
    if expected is not None:
        if reflection is None or reflection.request != expected:
            raise ValueError("proposal requires its exact completed reflection")
        refs = (*request.input_refs, reflection.ref)
        request = replace(
            request,
            input_refs=refs,
            lineage=refs,
            context={
                **request.context,
                "reflection": reflection.content,
            },
        )
    elif reflection is not None:
        raise ValueError("unexpected reflection for this learning pass")
    return request


def reasoning_run(request: ReasoningRequest) -> Run:
    return Run(
        run_id=request.request_id,
        intent=request.ref,
        target_snapshot=request.target_snapshot,
        budget=RunBudget(
            max_actions=1, max_failures=1, max_retries=0, resource_limits={"calls": 1}
        ),
        lineage=(request.ref,),
    )
