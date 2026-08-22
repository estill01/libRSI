from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    InterventionSpec,
    TargetRef,
    TargetSnapshot,
    make_implementation_handoff,
    record_from_dict,
)
from tests.block12_support import intervention_context


def test_intervention_envelope_round_trips_and_is_domain_extensible() -> None:
    context = intervention_context()
    intervention = context.intervention
    request = context.request
    candidate = context.candidate
    result = context.result

    assert intervention.specification["parameter"] == "temperature_c"
    assert intervention.baseline == result.authoritative_snapshot
    assert candidate.snapshot != result.authoritative_snapshot
    assert record_from_dict(intervention.to_dict()) == intervention
    assert record_from_dict(request.to_dict()) == request
    assert record_from_dict(candidate.to_dict()) == candidate
    assert record_from_dict(result.to_dict()) == result

    compatibility_intervention = intervention.to_intervention()
    compatibility_candidate = candidate.to_candidate()
    assert compatibility_intervention.specification == intervention.specification
    assert compatibility_candidate.target_snapshot == candidate.snapshot
    assert compatibility_candidate.intervention == compatibility_intervention.ref
    assert compatibility_candidate.status == "prepared"

    document = replace(
        intervention,
        intervention_id="revise-document",
        kind="document.revision",
        specification={"section": "methods", "replacement": "clarified text"},
    )
    assert document.specification["section"] == "methods"


def test_absent_implementer_handoff_is_complete_and_candidate_only() -> None:
    context = intervention_context()
    intervention = context.intervention
    request = context.request
    handoff = make_implementation_handoff(request)

    assert handoff.request.intervention == intervention
    assert handoff.capability_family == "implementer"
    assert handoff.authority == "candidate-only"
    assert handoff.expected_output_record_type == "implementation_result"
    assert handoff.action.run == intervention.canonical_run().ref
    assert record_from_dict(handoff.to_dict()) == handoff


def test_intervention_rejects_stale_or_incomplete_evidence_and_domain_field_leakage() -> None:
    context = intervention_context()
    target = context.target
    baseline = context.baseline
    claim = context.claim
    evidence = context.evidence
    constraint = context.constraint
    intervention = context.intervention
    with pytest.raises(ValueError, match="supporting evidence"):
        replace(intervention, evidence=())
    with pytest.raises(ValueError, match="stale or target-mismatched"):
        replace(
            intervention,
            evidence=(
                replace(
                    evidence,
                    target_snapshot=replace(baseline, revision="older"),
                ),
            ),
        )
    with pytest.raises(ValueError, match="supporting rationale"):
        replace(intervention, supporting_refs=(baseline.ref,))
    with pytest.raises(ValueError, match="another target"):
        replace(
            intervention,
            constraints=(
                replace(
                    constraint,
                    target=TargetRef(target_id="other", kind="physical-process"),
                ),
            ),
        )
    with pytest.raises(TypeError):
        InterventionSpec(  # type: ignore[call-arg]
            intervention_id="leaked-domain-field",
            baseline=baseline,
            kind="process.parameter_change",
            specification={"parameter": "temperature_c"},
            rationale=("bounded",),
            supporting_refs=(claim.ref,),
            evidence=(evidence,),
            expected_effects={"yield": "increase"},
            risks=("risk",),
            constraints=(constraint,),
            validation_plan={"measure": "yield"},
            rollback_expectations={"restore": True},
            process_parameter="temperature_c",
            lineage=intervention.lineage,
        )
    assert target == baseline.target


def test_candidate_and_result_cannot_claim_application_or_replace_authority() -> None:
    context = intervention_context()
    target = context.target
    baseline = context.baseline
    request = context.request
    prospective = context.prospective
    candidate = context.candidate
    result = context.result
    with pytest.raises(ValueError, match="unsupported candidate preparation status"):
        replace(candidate, status="applied")
    with pytest.raises(ValueError, match="differ from the authoritative baseline"):
        replace(candidate, snapshot=baseline)
    with pytest.raises(ValueError, match="another target"):
        replace(
            candidate,
            snapshot=TargetSnapshot(
                target=TargetRef(target_id="other", kind="physical-process"),
                state={"temperature_c": 32.0},
            ),
        )
    with pytest.raises(ValueError, match="evidence must match"):
        replace(candidate, evidence_refs=())
    with pytest.raises(ValueError, match="cannot replace authoritative"):
        replace(result, authoritative_snapshot=prospective)
    with pytest.raises(ValueError, match="exact request"):
        replace(
            result,
            request=replace(request, candidate_id="other-candidate"),
        )
    assert prospective.target == target
