from __future__ import annotations

from dataclasses import dataclass

from librsi import (
    Action,
    ActionResult,
    ArtifactRef,
    CandidateSnapshot,
    Claim,
    Constraint,
    Evidence,
    ImplementationResult,
    InterventionImplementationRequest,
    InterventionSpec,
    TargetRef,
    TargetSnapshot,
    implementation_request_from_action,
    make_implementation_result,
)


@dataclass(frozen=True)
class InterventionContext:
    target: TargetRef
    baseline: TargetSnapshot
    claim: Claim
    evidence: Evidence
    constraint: Constraint
    intervention: InterventionSpec
    request: InterventionImplementationRequest
    prospective: TargetSnapshot
    artifact: ArtifactRef
    candidate: CandidateSnapshot
    result: ImplementationResult


def intervention_context() -> InterventionContext:
    target = TargetRef(target_id="fermenter-7", kind="physical-process")
    baseline = TargetSnapshot(
        target=target,
        revision="batch-17",
        state={"temperature_c": 30.0, "yield": 0.71},
    )
    claim = Claim(
        statement="A modest temperature increase can improve yield",
        target=target,
        lineage=(baseline.ref,),
    )
    evidence = Evidence(
        evidence_type="support",
        data={"observed_delta": 0.04},
        subject_refs=(claim.ref,),
        source_refs=(baseline.ref,),
        target_snapshot=baseline,
        weight=1.0,
        lineage=(claim.ref, baseline.ref),
    )
    constraint = Constraint(
        statement="Temperature must remain below 35 C",
        target=target,
        scope={"maximum_c": 35.0},
        lineage=(baseline.ref,),
    )
    intervention = InterventionSpec.create(
        intervention_id="raise-temperature",
        baseline=baseline,
        kind="process.parameter_change",
        specification={
            "parameter": "temperature_c",
            "from": 30.0,
            "to": 32.0,
        },
        rationale=("Current evidence supports testing a bounded increase",),
        supporting_refs=(claim.ref,),
        evidence=(evidence,),
        expected_effects={"yield": {"direction": "increase"}},
        risks=("Excess temperature may reduce viability",),
        constraints=(constraint,),
        validation_plan={"measure": "yield", "minimum_batches": 2},
        rollback_expectations={"restore_temperature_c": 30.0},
    )
    request = InterventionImplementationRequest.for_intervention(
        intervention,
        candidate_id="raise-temperature:candidate",
    )
    prospective = TargetSnapshot(
        target=target,
        revision="candidate-batch-17",
        state={"temperature_c": 32.0, "yield": 0.71},
    )
    artifact = ArtifactRef(
        artifact_id="setpoint-plan",
        uri="memory://fermenter/setpoint-plan",
        content_digest="sha256:plan",
    )
    candidate = CandidateSnapshot.prepared(
        request=request,
        snapshot=prospective,
        artifacts=(artifact,),
    )
    result = ImplementationResult.prepared(candidate)
    return InterventionContext(
        target=target,
        baseline=baseline,
        claim=claim,
        evidence=evidence,
        constraint=constraint,
        intervention=intervention,
        request=request,
        prospective=prospective,
        artifact=artifact,
        candidate=candidate,
        result=result,
    )


class FermenterImplementer:
    def __init__(self) -> None:
        self.calls: list[Action] = []

    def implement(self, action: Action) -> ActionResult:
        self.calls.append(action)
        request = implementation_request_from_action(action)
        context = intervention_context()
        candidate = CandidateSnapshot.prepared(
            request=request,
            snapshot=context.prospective,
            artifacts=(context.artifact,),
        )
        return make_implementation_result(
            action=action,
            result=ImplementationResult.prepared(candidate),
        )
