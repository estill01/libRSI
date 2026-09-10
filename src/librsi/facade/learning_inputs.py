"""Freeze learning context and bounded follow-up admission before host calls."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from ..identity import digest, thaw
from ..records import Observation, record_from_dict
from .learning_history import attempt, ordered_inputs
from .learning_host import case_from_record
from .learning_records import LearningCase, LearningPolicy
from .learning_store import LearningStore

_DEFAULTS = {"history_limit": 2, "reflect_on_failure": False, "max_followups": 1}
_UNSUCCESSFUL = frozenset(
    {
        "failed",
        "no-supported-revision",
        "no-useful-improvement",
        "governance-rejected",
        "governance-failed",
        "rolled-back",
        "application-failed",
    }
)


def cases(policy: LearningPolicy, values: Sequence[LearningCase]) -> tuple[LearningCase, ...]:
    if not isinstance(values, Sequence):
        raise TypeError("evaluation cases require a finite sequence")
    if not 2 <= len(values) <= policy.max_cases:
        raise ValueError("evaluation case count must be between 2 and max_cases")
    items = tuple(values)
    if any(not isinstance(item, LearningCase) for item in items):
        raise TypeError("evaluation cases must be LearningCase values")
    if len({item.case_id for item in items}) != len(items):
        raise ValueError("evaluation case ids must be unique")
    if len({digest(item.payload) for item in items}) != len(items):
        raise ValueError("evaluation cases must contain distinct payloads")
    return items


def _disjoint(new: Sequence[LearningCase], old: Sequence[LearningCase]) -> None:
    if {case.case_id for case in new} & {case.case_id for case in old} or {
        digest(case.payload) for case in new
    } & {digest(case.payload) for case in old}:
        raise ValueError("evaluation cases must be fresh held-out ids and payloads")


def _records(inputs: Observation, key: str) -> tuple[Observation, ...]:
    return tuple(cast(Observation, record_from_dict(thaw(row))) for row in inputs.value[key])


def prepare(
    store: LearningStore,
    *,
    policy: LearningPolicy,
    adapter_id: str,
    proposer_id: str,
    reviewer_id: str,
    pass_id: str,
    shadow: tuple[LearningCase, ...],
    verification: tuple[LearningCase, ...],
    activate: bool,
    follow_up_to: str | None,
) -> Observation | None:
    if not isinstance(pass_id, str) or not pass_id.strip() or type(activate) is not bool:
        raise ValueError("learning requires a pass id and boolean activation choice")
    if follow_up_to is not None and (
        not isinstance(follow_up_to, str) or not follow_up_to.strip() or follow_up_to == pass_id
    ):
        raise ValueError("follow-up requires a different predecessor pass id")
    configuration: dict[str, Any] = {
        "policy": policy.to_dict(),
        "adapter_id": adapter_id,
        "proposer_id": proposer_id,
        "reviewer_id": reviewer_id,
        "activate": activate,
        "follow_up_to": follow_up_to,
        "shadow": [item.record.to_dict() for item in shadow],
        "verification": [item.record.to_dict() for item in verification],
    }
    existing = store.pass_input(pass_id)
    if existing is not None:
        # Old passes retain their original request shape. Only newly introduced
        # default options are elided; enabling/changing one rejects exact replay.
        saved = existing.value["configuration"]
        for key, default in _DEFAULTS.items():
            if key not in saved["policy"] and configuration["policy"][key] == default:
                configuration["policy"].pop(key)
        if "follow_up_to" not in saved and follow_up_to is None:
            configuration.pop("follow_up_to")
        if digest(saved) != digest(configuration):
            raise ValueError("pass id already names different configuration or cases")
        return existing
    if store.pending_pass is not None:
        raise RuntimeError("another learning pass is pending")
    previous = ordered_inputs(store)
    baseline = store.active
    compatible = tuple(
        row
        for row in previous
        if row.target_snapshot == baseline
        and row.value["configuration"]["adapter_id"] == adapter_id
        and digest(row.value["configuration"]["policy"]["metric"])
        == digest(policy.metric.to_dict())
        and row.value["configuration"]["policy"]["objective"] == policy.objective
        and row.value["configuration"]["policy"]["minimum_effect"] == policy.minimum_effect
    )
    selected = list(compatible[-policy.history_limit :]) if policy.history_limit else []
    inspected = {}
    depth = 0
    if follow_up_to is not None:
        predecessor = next(
            (row for row in compatible if row.value["pass_id"] == follow_up_to), None
        )
        if predecessor is None:
            raise ValueError("follow-up baseline or scoring differs from its predecessor")
        prior = attempt(store, predecessor)
        inspected[predecessor.root] = prior
        if prior.disposition not in _UNSUCCESSFUL:
            raise ValueError("follow-up requires a completed unsuccessful predecessor")
        depth = predecessor.value.get("follow_up_depth", 0) + 1
        allowance = min(policy.max_followups, predecessor.value.get("follow_up_allowance", 1))
        if depth > allowance:
            raise ValueError("follow-up allowance exhausted")
        if any(row.value["configuration"].get("follow_up_to") == follow_up_to for row in previous):
            raise ValueError("predecessor already has a follow-up; resume it")
        if not policy.history_limit:
            raise ValueError("follow-up requires retained history")
        selected = (
            [row for row in selected if row != predecessor][-(policy.history_limit - 1) :]
            if policy.history_limit > 1
            else []
        )
        selected.append(predecessor)
        feedback = _records(predecessor, "feedback")
    else:
        allowance = policy.max_followups
        consumed = {item["root"] for row in previous for item in row.value["feedback"]}
        feedback = tuple(row for row in store.feedback() if row.root not in consumed)
        if len(feedback) < policy.min_new_feedback:
            return None
        feedback = feedback[-min(policy.max_feedback, policy.max_cases) :]
    if any(
        row.value["adapter_id"] != adapter_id or row.value["metric_root"] != policy.metric.root
        for row in feedback
    ):
        raise ValueError("feedback scoring semantics changed; use a separate profile")
    training = cases(
        policy,
        tuple(
            case_from_record(cast(Observation, record_from_dict(thaw(row.value["case"]))))
            for row in feedback
        ),
    )
    _disjoint(shadow, training)
    _disjoint(verification, training)
    # Historical outcomes influence the next proposal even without revealing
    # held-out payloads. Reusing any previously assessed set is not fresh proof.
    old_heldout = tuple(
        case_from_record(row)
        for inputs in previous
        for key in ("shadow", "verification")
        for row in _records(inputs, key)
    )
    _disjoint(training, old_heldout)
    _disjoint(
        tuple(case_from_record(row) for inputs in selected for row in _records(inputs, "training")),
        old_heldout,
    )
    old_cases = (
        *old_heldout,
        *(case_from_record(row) for inputs in previous for row in _records(inputs, "training")),
    )
    _disjoint(shadow, old_cases)
    _disjoint(verification, old_cases)
    historical = tuple(
        (inspected[row.root] if row.root in inspected else attempt(store, row)).feedback
        for row in selected
    )
    inputs = Observation(
        kind="learning.pass",
        target_snapshot=baseline,
        value={
            "pass_id": pass_id,
            "learning_version": 2,
            "sequence": 1 + max((row.value.get("sequence", 0) for row in previous), default=0),
            "configuration": configuration,
            "feedback": [row.to_dict() for row in feedback],
            "training": [case.record.to_dict() for case in training],
            "shadow": configuration["shadow"],
            "verification": configuration["verification"],
            "history": [row.to_dict() for row in historical],
            "follow_up_depth": depth,
            "follow_up_allowance": allowance,
        },
        source_refs=(
            baseline.ref,
            *(row.ref for row in feedback),
            *(row.ref for row in historical),
        ),
    )
    store.begin_pass(inputs)
    return inputs
