from __future__ import annotations

from copy import deepcopy

import pytest

from librsi import (
    REASONING_KINDS,
    Goal,
    ReasoningRequest,
    ReasoningResult,
    TargetRef,
    TargetSnapshot,
    deserialize_record,
    serialize_record,
)


def _context(kind: str) -> tuple[Goal, TargetSnapshot, ReasoningRequest]:
    target = TargetRef(target_id="reasoning-target", kind="process")
    snapshot = TargetSnapshot(target=target, revision="v1", state={"rate": 4})
    goal = Goal(statement="Understand and improve the process", target=target)
    request = ReasoningRequest(
        request_id=f"request-{kind}",
        kind=kind,
        instruction=f"Produce a structured {kind} proposal",
        input_refs=(goal.ref, snapshot.ref),
        target_snapshot=snapshot,
        context={"boundary": "proposal-only"},
        lineage=(goal.ref, snapshot.ref),
    )
    return goal, snapshot, request


VALID_CONTENT = {
    "reflection": {
        "summary": "Throughput is limited by a repeated handoff.",
        "observations": ["Queue depth rises before the handoff."],
        "open_questions": ["Is batching allowed?"],
    },
    "hypothesis-generation": {
        "hypotheses": [
            {
                "statement": "Batching reduces handoff delay.",
                "causal_model": {"cause": "fewer handoffs"},
                "predictions": [{"metric": "latency", "direction": "decrease"}],
                "confidence": 0.6,
            }
        ]
    },
    "experiment-design": {
        "experiments": [
            {
                "objective": "Measure batching latency.",
                "design": {"batch_sizes": [1, 4]},
                "criteria": {"valid_samples": 10},
                "requested_measurements": ["latency"],
            }
        ]
    },
    "explanation": {
        "explanations": [
            {
                "statement": "The queue forms at the handoff.",
                "basis": ["queue-depth observation"],
            }
        ]
    },
    "intervention-generation": {
        "interventions": [
            {
                "kind": "configuration",
                "specification": {"batch_size": 4},
                "rationale": {"mechanism": "amortize handoff"},
                "expected_effects": {"latency": "decrease"},
            }
        ]
    },
    "problem-decomposition": {
        "parts": [
            {"part_id": "measure", "objective": "Measure handoff delay", "depends_on": []},
            {
                "part_id": "compare",
                "objective": "Compare batch sizes",
                "depends_on": ["measure"],
            },
        ]
    },
    "approach-revision": {
        "revisions": [
            {
                "subject": "batching experiment",
                "problem": "insufficient valid samples",
                "proposed_change": {"samples": 20},
                "rationale": "reduce sampling uncertainty",
            }
        ]
    },
}


@pytest.mark.parametrize("kind", sorted(REASONING_KINDS))
def test_each_reasoning_kind_has_a_strict_round_trippable_request_and_result(kind: str) -> None:
    goal, snapshot, request = _context(kind)
    result = ReasoningResult.propose(
        request=request,
        content=VALID_CONTENT[kind],
        narration="This narration is explanatory, not epistemic authority.",
    )

    assert result.kind == kind
    assert request.lineage == (goal.ref, snapshot.ref)
    assert result.lineage == (request.ref, goal.ref, snapshot.ref)
    assert deserialize_record(serialize_record(request)) == request
    assert deserialize_record(serialize_record(result)) == result


def test_request_requires_exact_input_and_target_lineage() -> None:
    goal, snapshot, _ = _context("reflection")
    with pytest.raises(ValueError, match="input lineage"):
        ReasoningRequest(
            request_id="missing",
            kind="reflection",
            instruction="Reflect",
            input_refs=(),
        )
    with pytest.raises(ValueError, match="target snapshot"):
        ReasoningRequest(
            request_id="missing-snapshot",
            kind="reflection",
            instruction="Reflect",
            input_refs=(goal.ref,),
            target_snapshot=snapshot,
            lineage=(goal.ref,),
        )
    with pytest.raises(ValueError, match="exactly match"):
        ReasoningRequest(
            request_id="mismatched-lineage",
            kind="reflection",
            instruction="Reflect",
            input_refs=(goal.ref, snapshot.ref),
            target_snapshot=snapshot,
            lineage=(goal.ref,),
        )


@pytest.mark.parametrize("kind", sorted(REASONING_KINDS))
def test_malformed_or_authority_bearing_payloads_fail_closed(kind: str) -> None:
    _, _, request = _context(kind)
    malformed = deepcopy(VALID_CONTENT[kind])
    malformed["validated"] = True
    with pytest.raises(ValueError, match="unsupported fields"):
        ReasoningResult.propose(request=request, content=malformed)


def test_kind_mismatch_unsupported_kind_and_dependency_cycles_are_rejected() -> None:
    _, _, request = _context("reflection")
    with pytest.raises(ValueError, match="must match"):
        ReasoningResult(
            request=request,
            kind="explanation",
            content=VALID_CONTENT["explanation"],
            lineage=(request.ref, *request.input_refs),
        )
    with pytest.raises(ValueError, match="unsupported reasoning kind"):
        ReasoningRequest(
            request_id="unsupported",
            kind="provider-chat",
            instruction="Chat",
            input_refs=request.input_refs,
            target_snapshot=request.target_snapshot,
            lineage=request.input_refs,
        )

    _, _, decomposition = _context("problem-decomposition")
    cyclic = {
        "parts": [
            {"part_id": "a", "objective": "A", "depends_on": ["b"]},
            {"part_id": "b", "objective": "B", "depends_on": ["a"]},
        ]
    }
    with pytest.raises(ValueError, match="acyclic"):
        ReasoningResult.propose(request=decomposition, content=cyclic)
