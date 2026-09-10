"""Exact reasoning requests shared by execution and historical inspection."""

from __future__ import annotations

from typing import cast

from ..identity import thaw
from ..reasoning import ReasoningRequest
from ..records import Observation, record_from_dict
from ..runtime import Run, RunBudget
from .learning_host import case_from_record


def proposal_request(inputs: Observation) -> ReasoningRequest:
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
