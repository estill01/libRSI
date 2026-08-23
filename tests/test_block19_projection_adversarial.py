from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Claim,
    EventProjection,
    Outcome,
    OutcomeProjection,
    Run,
    RuntimeEngine,
    TargetRef,
    TargetSnapshot,
    deserialize_projection,
    outcome_for_result,
    project_event,
    project_result,
    project_transition,
    projection_from_dict,
    projection_to_dict,
    reconstruct_result,
    serialize_projection,
)
from tests.block19_support import workflow_results


def test_transport_metadata_never_changes_semantic_projection_roots() -> None:
    result = workflow_results()[2]
    embedded = project_result(result, metadata={"control_plane": "embedded", "request_id": "a"})
    managed = project_result(result, metadata={"control_plane": "managed", "request_id": "b"})

    assert embedded.projection_root == managed.projection_root
    assert embedded.result.root == managed.result.root
    assert embedded.outcome.root == managed.outcome.root
    assert serialize_projection(embedded) != serialize_projection(managed)


def test_projection_rejects_workflow_or_outcome_substitution() -> None:
    result = workflow_results()[0]
    valid = project_result(result)
    with pytest.raises(ValueError, match="workflow does not match"):
        OutcomeProjection(workflow="rsi", result=result, outcome=valid.outcome)
    forged = Outcome(
        intent=valid.outcome.intent,
        status="supported",
        target_snapshot=valid.outcome.target_snapshot,
        lineage=valid.outcome.lineage,
    )
    with pytest.raises(ValueError, match="exact result-derived outcome"):
        OutcomeProjection(workflow="validation", result=result, outcome=forged)
    with pytest.raises(TypeError, match="metadata must be a mapping"):
        project_result(result, metadata=[])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"$schema": "librsi.outcome-projection/v99"}, "unsupported projection schema"),
        ({"schema_version": 99}, "unsupported projection schema version"),
        ({"projection_root": "0" * 64}, "diverge"),
        ({"result_root": "0" * 64}, "diverge"),
        ({"workflow": "investigation"}, "workflow does not match"),
    ],
)
def test_unknown_incompatible_or_substituted_projection_fields_fail_closed(
    mutation: dict[str, object],
    message: str,
) -> None:
    payload = projection_to_dict(project_result(workflow_results()[0]))
    payload.update(mutation)
    with pytest.raises(ValueError, match=message):
        projection_from_dict(payload)


def test_embedded_record_lineage_or_currentness_cannot_be_removed() -> None:
    payload = projection_to_dict(project_result(workflow_results()[2]))
    result_payload = payload["result"]
    assert isinstance(result_payload, dict)
    result_payload["data"]["lineage"] = []
    with pytest.raises(ValueError, match="root does not match|lineage is incomplete"):
        projection_from_dict(payload)

    projection = project_result(workflow_results()[2])
    target = TargetRef(target_id="other")
    stale = TargetSnapshot(target=target, state={"version": "other"})
    with pytest.raises(ValueError, match="stale"):
        projection.require_current(stale)
    with pytest.raises(TypeError, match="exact TargetSnapshot"):
        projection.require_current(object())  # type: ignore[arg-type]
    projection.require_current(projection.outcome.target_snapshot)  # type: ignore[arg-type]


def test_event_summary_fields_cannot_diverge_from_canonical_event() -> None:
    claim = Claim(statement="event summaries are projections")
    started = RuntimeEngine.start(Run(run_id="event-summary", intent=claim.ref))
    assert started.transition is not None
    payload = projection_to_dict(project_event(started.transition.event))
    payload["kind"] = "run_completed"
    with pytest.raises(ValueError, match="diverge"):
        projection_from_dict(payload)


def test_only_exact_registered_result_and_event_classes_are_accepted() -> None:
    validation = workflow_results()[0]

    class _ResultWrapper:
        root = validation.root

    with pytest.raises(TypeError, match="supported exact workflow result"):
        project_result(_ResultWrapper())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="supported exact workflow result"):
        outcome_for_result(_ResultWrapper())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="exact canonical Event"):
        project_event(replace(validation, metadata={}))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact canonical Event"):
        EventProjection(event=validation)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact canonical Transition"):
        project_transition(validation)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact projection envelope"):
        projection_to_dict(validation)  # type: ignore[arg-type]
    started = RuntimeEngine.start(Run(run_id="x", intent=validation.ref))
    assert started.transition is not None
    event_projection = project_event(started.transition.event)
    with pytest.raises(TypeError, match="OutcomeProjection"):
        reconstruct_result(event_projection)  # type: ignore[arg-type]


def test_decoder_rejects_wrong_embedded_record_types_and_missing_workflow() -> None:
    outcome_payload = projection_to_dict(project_result(workflow_results()[0]))
    outcome_payload["result"] = Claim(statement="not a result").to_dict()
    with pytest.raises(ValueError, match="unsupported canonical records"):
        projection_from_dict(outcome_payload)

    missing_workflow = projection_to_dict(project_result(workflow_results()[0]))
    missing_workflow["workflow"] = None
    with pytest.raises(ValueError, match="workflow is required"):
        projection_from_dict(missing_workflow)

    claim = Claim(statement="not an event")
    started = RuntimeEngine.start(Run(run_id="wrong-event", intent=claim.ref))
    assert started.transition is not None
    event_payload = projection_to_dict(project_event(started.transition.event))
    event_payload["event"] = claim.to_dict()
    with pytest.raises(ValueError, match="canonical Event"):
        projection_from_dict(event_payload)

    with pytest.raises(ValueError, match="keys must be strings"):
        projection_from_dict({1: "invalid"})  # type: ignore[dict-item]


def test_non_json_and_non_object_documents_fail_closed() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        deserialize_projection("{")
    with pytest.raises(ValueError, match="JSON object"):
        deserialize_projection("[]")
    with pytest.raises(TypeError, match="must be text"):
        deserialize_projection(b"{}")  # type: ignore[arg-type]
