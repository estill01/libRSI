from __future__ import annotations

import pytest

from librsi import (
    Evidence,
    Goal,
    Intervention,
    ReasoningRequest,
    ReasoningResult,
    TargetRef,
    TargetSnapshot,
    require_reasoning_derivation,
)


def _proposal() -> tuple[Goal, TargetSnapshot, ReasoningResult]:
    target = TargetRef(target_id="heat-treatment", kind="physical-process")
    snapshot = TargetSnapshot(
        target=target,
        revision="cycle-4",
        state={"temperature": 42.0},
    )
    goal = Goal(statement="Reduce temperature variation", target=target)
    request = ReasoningRequest(
        request_id="intervention",
        kind="intervention-generation",
        instruction="Propose bounded controller adjustments",
        input_refs=(goal.ref, snapshot.ref),
        target_snapshot=snapshot,
        lineage=(goal.ref, snapshot.ref),
    )
    result = ReasoningResult.propose(
        request=request,
        content={
            "interventions": [
                {
                    "kind": "configuration",
                    "specification": {"gain": 0.45},
                    "rationale": {"observation": "overshoot"},
                    "expected_effects": {"variation": "decrease"},
                }
            ]
        },
    )
    return goal, snapshot, result


def test_evidence_and_intervention_decisions_retain_inputs_proposal_and_currentness() -> None:
    goal, snapshot, proposal = _proposal()
    lineage = (proposal.ref, proposal.request.ref, goal.ref, snapshot.ref)
    evidence = Evidence(
        evidence_type="observation",
        data={"temperature": 41.5},
        source_refs=(proposal.ref,),
        target_snapshot=snapshot,
        lineage=lineage,
    )
    intervention = Intervention(
        target=snapshot.target,
        kind="configuration",
        specification={"gain": 0.45},
        rationale={"proposal_root": proposal.root},
        lineage=lineage,
    )

    assert require_reasoning_derivation(proposal, evidence) is evidence
    assert require_reasoning_derivation(proposal, intervention) is intervention


def test_missing_proposal_or_input_lineage_and_stale_decisions_fail_closed() -> None:
    goal, snapshot, proposal = _proposal()
    missing_proposal = Evidence(
        evidence_type="observation",
        data={"temperature": 41.5},
        target_snapshot=snapshot,
        lineage=(goal.ref, snapshot.ref),
    )
    with pytest.raises(ValueError, match="missing reasoning proposal"):
        require_reasoning_derivation(proposal, missing_proposal)

    missing_request = Evidence(
        evidence_type="observation",
        data={"temperature": 41.5},
        target_snapshot=snapshot,
        lineage=(proposal.ref, goal.ref, snapshot.ref),
    )
    with pytest.raises(ValueError, match="missing reasoning proposal"):
        require_reasoning_derivation(proposal, missing_request)

    stale = TargetSnapshot(target=snapshot.target, revision="cycle-3", state={"temperature": 43})
    stale_evidence = Evidence(
        evidence_type="observation",
        data={"temperature": 43},
        target_snapshot=stale,
        lineage=(proposal.ref, proposal.request.ref, goal.ref, snapshot.ref),
    )
    with pytest.raises(ValueError, match="exact target snapshot"):
        require_reasoning_derivation(proposal, stale_evidence)

    other_target = TargetRef(target_id="other", kind="physical-process")
    wrong_intervention = Intervention(
        target=other_target,
        kind="configuration",
        specification={"gain": 0.45},
        lineage=(proposal.ref, proposal.request.ref, goal.ref, snapshot.ref),
    )
    with pytest.raises(ValueError, match="exact target"):
        require_reasoning_derivation(proposal, wrong_intervention)


def test_nondecision_records_cannot_masquerade_as_proposal_adoption() -> None:
    goal, _, proposal = _proposal()
    with pytest.raises(TypeError, match="Evidence or Intervention"):
        require_reasoning_derivation(proposal, goal)
