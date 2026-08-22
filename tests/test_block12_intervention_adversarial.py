from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    InterventionPolicy,
    InterventionSpec,
    InterventionWorkflow,
    SemanticRecord,
    TargetSnapshot,
    make_implementation_action,
    make_implementation_result,
)
from tests.block12_support import FermenterImplementer, intervention_context


class _TextSubclass(str):
    pass


def test_text_subclasses_and_policy_subclasses_cannot_change_identity_or_authority() -> None:
    context = intervention_context()
    with pytest.raises(TypeError, match="intervention kind must be text"):
        replace(context.intervention, kind=_TextSubclass("process.parameter_change"))

    class _ApplyingPolicy(InterventionPolicy):
        @staticmethod
        def apply(candidate):
            return candidate.snapshot

    with pytest.raises(ValueError, match="versioned contract"):
        _ApplyingPolicy()
    assert not hasattr(InterventionPolicy, "apply")
    assert not hasattr(InterventionWorkflow, "apply")


def test_forged_result_cannot_smuggle_authoritative_application() -> None:
    context = intervention_context()
    forged = object.__new__(type(context.result))
    object.__setattr__(forged, "request", context.request)
    object.__setattr__(forged, "disposition", "prepared")
    object.__setattr__(forged, "candidate", context.candidate)
    object.__setattr__(forged, "authoritative_snapshot", context.prospective)
    object.__setattr__(
        forged,
        "lineage",
        (
            context.request.ref,
            context.candidate.ref,
            context.prospective.ref,
            context.candidate.snapshot.ref,
            *context.candidate.evidence_refs,
            *(item.ref for item in context.candidate.artifacts),
        ),
    )
    object.__setattr__(forged, "metadata", {})
    SemanticRecord.__post_init__(forged)
    action = make_implementation_action(context.request)

    with pytest.raises(ValueError, match="cannot replace authoritative"):
        make_implementation_result(action=action, result=forged)


def test_completed_progress_cannot_swap_in_a_candidate_unrelated_to_runtime() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    completed = workflow.run_managed(
        waiting,
        implementer=FermenterImplementer(),
        current_snapshot=context.baseline,
    ).progress
    alternate_snapshot = replace(context.prospective, revision="alternate-candidate")
    alternate_candidate = InterventionPolicy.candidate(
        request=context.request,
        snapshot=alternate_snapshot,
        artifacts=(context.artifact,),
    )
    alternate_result = InterventionPolicy.result(alternate_candidate)

    with pytest.raises(ValueError, match="result has drifted"):
        replace(completed, result=alternate_result)


def test_currentness_is_reconciled_before_managed_candidate_generation() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    forged_current = TargetSnapshot(
        target=context.target,
        revision="batch-18",
        state=context.baseline.state,
    )
    implementer = FermenterImplementer()

    with pytest.raises(ValueError, match="target snapshot is stale"):
        workflow.run_managed(
            waiting,
            implementer=implementer,
            current_snapshot=forged_current,
        )
    assert implementer.calls == []


def test_domain_extensions_are_confined_to_the_specification_mapping() -> None:
    context = intervention_context()
    extended = replace(
        context.intervention,
        intervention_id="domain-extension",
        kind="agriculture.irrigation_schedule",
        specification={
            "zone": "north-field",
            "start": "05:00",
            "duration_minutes": 18,
        },
    )
    assert extended.specification["zone"] == "north-field"
    with pytest.raises(TypeError):
        InterventionSpec(  # type: ignore[call-arg]
            intervention_id="leaked-field",
            baseline=context.baseline,
            kind="agriculture.irrigation_schedule",
            specification={"zone": "north-field"},
            rationale=context.intervention.rationale,
            supporting_refs=context.intervention.supporting_refs,
            evidence=context.intervention.evidence,
            expected_effects=context.intervention.expected_effects,
            risks=context.intervention.risks,
            constraints=context.intervention.constraints,
            validation_plan=context.intervention.validation_plan,
            rollback_expectations=context.intervention.rollback_expectations,
            irrigation_zone="north-field",
            lineage=context.intervention.lineage,
        )
