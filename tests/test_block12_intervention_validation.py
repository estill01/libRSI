from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from librsi import (
    ActionResult,
    CandidateSnapshot,
    Constraint,
    ImplementationHandoff,
    ImplementationResult,
    ImplementationResultValidator,
    InterventionImplementationRequest,
    InterventionPolicy,
    InterventionProgress,
    InterventionUpdate,
    InterventionWorkflow,
    RuntimeEngine,
    RuntimeFailure,
    implementation_request_from_action,
    implementation_result_from_action_result,
    make_implementation_action,
    make_implementation_failure,
    make_implementation_handoff,
    make_implementation_result,
)
from tests.block12_support import FermenterImplementer, intervention_context


@pytest.mark.parametrize(
    "change",
    [
        {"intervention_id": " "},
        {"baseline": object()},
        {"specification": {}},
        {"rationale": "not-a-sequence"},
        {"rationale": ()},
        {"rationale": ("same", "same")},
        {"supporting_refs": "not-a-sequence"},
        {"supporting_refs": (object(),)},
        {"supporting_refs": ()},
        {"evidence": "not-a-sequence"},
        {"evidence": (object(),)},
        {"evidence": ()},
        {"expected_effects": {}},
        {"risks": "not-a-sequence"},
        {"risks": ()},
        {"risks": ("same", "same")},
        {"constraints": "not-a-sequence"},
        {"constraints": (object(),)},
        {"validation_plan": {}},
        {"rollback_expectations": {}},
        {"lineage": ()},
    ],
)
def test_intervention_envelope_rejects_malformed_universal_fields(
    change: dict[str, Any],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(intervention_context().intervention, **change)


def test_intervention_rejects_duplicate_and_semantically_incomplete_dependencies() -> None:
    context = intervention_context()
    no_source = replace(context.evidence, source_refs=())
    unsupported = replace(context.evidence, evidence_type="unsupported-relationship")
    unweighted = replace(context.evidence, weight=None)
    unrelated = replace(context.evidence, subject_refs=(context.baseline.ref,))
    unbound_constraint = Constraint(statement="A host-global guardrail")

    assert replace(
        context.intervention,
        constraints=(unbound_constraint,),
        lineage=(
            context.baseline.ref,
            *context.intervention.supporting_refs,
            *(item.ref for item in context.intervention.evidence),
            unbound_constraint.ref,
        ),
    ).constraints == (unbound_constraint,)
    for evidence, message in (
        (no_source, "exact provenance"),
        (unsupported, "relationship is unsupported"),
        (unweighted, "explicit weight"),
        (unrelated, "supporting rationale"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(context.intervention, evidence=(evidence,))
    with pytest.raises(ValueError, match="evidence must be unique"):
        replace(context.intervention, evidence=(context.evidence, context.evidence))
    with pytest.raises(ValueError, match="constraints must be unique"):
        replace(context.intervention, constraints=(context.constraint, context.constraint))
    with pytest.raises(ValueError, match="references must be unique"):
        replace(
            context.intervention,
            supporting_refs=(context.claim.ref, context.claim.ref),
        )


def test_request_candidate_result_and_handoff_validate_every_owned_edge() -> None:
    context = intervention_context()
    action = make_implementation_action(context.request)
    handoff = make_implementation_handoff(context.request)
    other_request = InterventionImplementationRequest.for_intervention(
        context.intervention,
        candidate_id="other-candidate",
    )
    other_candidate = CandidateSnapshot.prepared(
        request=other_request,
        snapshot=context.prospective,
    )

    invalid_factories = (
        lambda: InterventionImplementationRequest(
            intervention=object(),  # type: ignore[arg-type]
            candidate_id="candidate",
        ),
        lambda: replace(context.request, candidate_id=" "),
        lambda: replace(context.request, lineage=()),
        lambda: InterventionImplementationRequest.for_intervention(  # type: ignore[arg-type]
            object(), candidate_id="candidate"
        ),
        lambda: replace(context.candidate, request=object()),
        lambda: replace(context.candidate, snapshot=object()),
        lambda: replace(context.candidate, status=" "),
        lambda: replace(context.candidate, artifacts="not-a-sequence"),
        lambda: replace(context.candidate, artifacts=(object(),)),
        lambda: replace(
            context.candidate,
            artifacts=(context.artifact, context.artifact),
        ),
        lambda: replace(context.candidate, lineage=()),
        lambda: CandidateSnapshot.prepared(  # type: ignore[arg-type]
            request=object(), snapshot=context.prospective
        ),
        lambda: replace(context.result, request=object()),
        lambda: replace(context.result, disposition=" "),
        lambda: replace(context.result, disposition="applied"),
        lambda: replace(context.result, candidate=object()),
        lambda: replace(context.result, candidate=other_candidate),
        lambda: replace(context.result, authoritative_snapshot=object()),
        lambda: replace(context.result, lineage=()),
        lambda: ImplementationResult.prepared(object()),  # type: ignore[arg-type]
        lambda: replace(handoff, request=object()),
        lambda: replace(handoff, action=object()),
        lambda: replace(handoff, action=replace(action, action_id="other-action")),
        lambda: replace(handoff, capability_family="applier"),
        lambda: replace(handoff, authority="target-application"),
        lambda: replace(handoff, expected_output_record_type="candidate"),
        lambda: replace(handoff, lineage=()),
    )
    for factory in invalid_factories:
        with pytest.raises((TypeError, ValueError)):
            factory()
    assert handoff.action == action


def test_action_codecs_reject_wrong_types_and_nonrecord_payloads() -> None:
    context = intervention_context()
    action = make_implementation_action(context.request)
    waiting = RuntimeEngine.request(
        RuntimeEngine.start(context.intervention.canonical_run()).state,
        action,
    ).state
    failure = RuntimeFailure(
        classification="execution",
        message="bounded preparation failed",
    )
    failed = make_implementation_failure(action=action, failure=failure)

    with pytest.raises(TypeError, match="implementation actions require"):
        make_implementation_action(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="decoding requires an Action"):
        implementation_request_from_action(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="request payload must be a mapping"):
        implementation_request_from_action(replace(action, payload={"request": 1}))
    with pytest.raises(TypeError, match="must decode to an InterventionImplementationRequest"):
        implementation_request_from_action(
            replace(action, payload={"request": context.intervention.to_dict()})
        )
    with pytest.raises(TypeError, match="require an ImplementationResult"):
        make_implementation_result(action=action, result=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require a RuntimeFailure"):
        make_implementation_failure(action=action, failure=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires an ActionResult"):
        implementation_result_from_action_result(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="do not contain a candidate"):
        implementation_result_from_action_result(failed)
    with pytest.raises(TypeError, match="result payload must be a mapping"):
        implementation_result_from_action_result(
            ActionResult(
                action=action,
                disposition="succeeded",
                payload={"result": 1},
            )
        )
    with pytest.raises(TypeError, match="must decode to an ImplementationResult"):
        implementation_result_from_action_result(
            ActionResult(
                action=action,
                disposition="succeeded",
                payload={"result": context.request.to_dict()},
            )
        )
    with pytest.raises(TypeError, match="validation requires a RunState"):
        ImplementationResultValidator().validate(object(), failed)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="validation requires an ActionResult"):
        ImplementationResultValidator().validate(waiting, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="currentness requires a RunState"):
        ImplementationResultValidator().require_current_frontier(  # type: ignore[arg-type]
            object(), action, context.baseline
        )
    with pytest.raises(TypeError, match="currentness requires an Action"):
        ImplementationResultValidator().require_current_frontier(  # type: ignore[arg-type]
            waiting, object(), context.baseline
        )


def test_policy_and_workflow_public_boundaries_reject_wrong_types() -> None:
    context = intervention_context()
    policy = InterventionPolicy()
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

    assert (
        policy.candidate(
            request=context.request,
            snapshot=context.prospective,
            artifacts=(context.artifact,),
        )
        == context.candidate
    )
    assert policy.result(context.candidate) == context.result
    assert (
        workflow.run_managed(
            completed,
            implementer=FermenterImplementer(),
            current_snapshot=context.baseline,
        ).progress
        == completed
    )

    invalid_calls = (
        lambda: policy.require_current(object(), context.baseline),
        lambda: policy.require_current(context.intervention, object()),
        lambda: workflow.start(object(), current_snapshot=context.baseline),
        lambda: workflow.resume(object(), waiting.state, current_snapshot=context.baseline),
        lambda: workflow.resume(context.intervention, object(), current_snapshot=context.baseline),
        lambda: workflow.submit(
            object(),  # type: ignore[arg-type]
            waiting.state.results,
            current_snapshot=context.baseline,
        ),
        lambda: workflow.submit(
            waiting,
            object(),  # type: ignore[arg-type]
            current_snapshot=context.baseline,
        ),
        lambda: workflow.run_managed(
            waiting,
            implementer=object(),  # type: ignore[arg-type]
            current_snapshot=context.baseline,
        ),
        lambda: InterventionProgress(
            intervention=object(),  # type: ignore[arg-type]
            current_snapshot=context.baseline,
            state=waiting.state,
        ),
        lambda: InterventionProgress(
            intervention=context.intervention,
            current_snapshot=object(),  # type: ignore[arg-type]
            state=waiting.state,
        ),
        lambda: InterventionProgress(
            intervention=context.intervention,
            current_snapshot=context.baseline,
            state=object(),  # type: ignore[arg-type]
        ),
        lambda: InterventionUpdate(progress=object(), transitions=()),  # type: ignore[arg-type]
        lambda: InterventionUpdate(progress=waiting, transitions=(object(),)),  # type: ignore[arg-type]
    )
    for call in invalid_calls:
        with pytest.raises((TypeError, ValueError)):
            call()


def test_handoff_constructor_requires_exact_action_lineage() -> None:
    context = intervention_context()
    action = make_implementation_action(context.request)
    with pytest.raises(ValueError, match="lineage is incomplete"):
        ImplementationHandoff(
            request=context.request,
            action=action,
            lineage=(context.request.ref,),
        )


def test_duplicate_success_and_failure_shapes_remain_outside_workflow_authority() -> None:
    context = intervention_context()
    workflow = InterventionWorkflow()
    waiting = workflow.start(
        context.intervention,
        current_snapshot=context.baseline,
    ).progress
    action = waiting.state.pending_actions[0]
    success = make_implementation_result(action=action, result=context.result)
    submitted = RuntimeEngine.submit(waiting.state, success).state
    with pytest.raises(ValueError, match="requires one exact pending handoff"):
        workflow.submit(
            workflow.resume(
                context.intervention,
                submitted,
                current_snapshot=context.baseline,
            ).progress,
            success,
            current_snapshot=context.baseline,
        )
