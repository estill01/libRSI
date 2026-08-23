from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from librsi import (
    EVENT_PROJECTION_JSON_SCHEMA,
    EVENT_PROJECTION_SCHEMA,
    OUTCOME_PROJECTION_JSON_SCHEMA,
    OUTCOME_PROJECTION_SCHEMA,
    PROJECTION_SCHEMA_VERSION,
    Claim,
    EventProjection,
    Evidence,
    OutcomeProjection,
    ResultRecord,
    Run,
    RuntimeEngine,
    deserialize_projection,
    outcome_for_result,
    project_event,
    project_result,
    project_transition,
    projection_schema,
    projection_to_dict,
    reconstruct_result,
    serialize_projection,
    validate,
)
from tests.block19_support import workflow_results

_GOLDEN = Path(__file__).parent / "fixtures" / "block19_projection_contract.json"


@pytest.mark.parametrize(
    ("position", "workflow"),
    [(0, "validation"), (1, "investigation"), (2, "improvement"), (3, "rsi")],
)
def test_every_workflow_result_has_one_complete_versioned_round_trip(
    position: int,
    workflow: str,
) -> None:
    result = workflow_results()[position]
    projection = project_result(result, metadata={"control_plane": "embedded"})

    assert type(projection) is OutcomeProjection
    assert projection.workflow == workflow
    assert projection.outcome == outcome_for_result(result)
    assert projection.outcome.lineage[0] == result.ref
    assert projection.outcome.target_snapshot is not None or workflow in {
        "validation",
        "investigation",
    }
    assert projection.SCHEMA_VERSION == PROJECTION_SCHEMA_VERSION

    serialized = serialize_projection(projection)
    decoded = deserialize_projection(serialized)
    assert decoded == projection
    assert serialize_projection(decoded) == serialized
    assert reconstruct_result(decoded) == result
    assert json.loads(serialized)["result_root"] == result.root


def test_event_and_transition_projection_share_the_exact_runtime_event() -> None:
    claim = Claim(statement="runtime events remain authoritative")
    started = RuntimeEngine.start(
        Run(run_id="block19-event", intent=claim.ref, lineage=(claim.ref,))
    )
    assert started.transition is not None

    direct = project_event(started.transition.event, metadata={"session": "external"})
    carried = project_transition(started.transition, metadata={"session": "external"})

    assert type(direct) is EventProjection
    assert direct == carried
    assert direct.event == started.transition.event
    assert direct.event.run == started.state.run.ref
    assert deserialize_projection(serialize_projection(direct)) == direct
    document = projection_to_dict(direct)
    assert document["kind"] == "run_started"
    assert document["event_root"] == direct.event.root
    assert document["run_root"] == direct.event.run.root


def test_published_schemas_are_explicit_and_closed() -> None:
    assert projection_schema(OUTCOME_PROJECTION_SCHEMA) is OUTCOME_PROJECTION_JSON_SCHEMA
    assert projection_schema(EVENT_PROJECTION_SCHEMA) is EVENT_PROJECTION_JSON_SCHEMA
    assert OUTCOME_PROJECTION_JSON_SCHEMA["additionalProperties"] is False
    assert EVENT_PROJECTION_JSON_SCHEMA["additionalProperties"] is False
    assert "result" in OUTCOME_PROJECTION_JSON_SCHEMA["properties"]
    assert "event" in EVENT_PROJECTION_JSON_SCHEMA["properties"]
    outcome_properties = OUTCOME_PROJECTION_JSON_SCHEMA["properties"]
    event_properties = EVENT_PROJECTION_JSON_SCHEMA["properties"]
    assert outcome_properties["result"]["properties"]["record_type"] == {
        "enum": (
            "validation_result",
            "investigation_result",
            "improvement_result",
            "rsi_result",
        )
    }
    assert outcome_properties["outcome"]["properties"]["record_type"] == {"const": "outcome"}
    assert event_properties["event"]["properties"]["record_type"] == {"const": "event"}
    with pytest.raises(ValueError, match="unsupported projection schema"):
        projection_schema("librsi.unknown/v1")


@pytest.mark.parametrize(
    ("evidence_type", "expected_status", "prefix"),
    [
        ("counterexample", "contradicted", "Contradicted:"),
        ("boundary", "bounded", "Bounded:"),
    ],
)
def test_validation_outcome_projection_covers_public_decisive_dispositions(
    evidence_type: str,
    expected_status: str,
    prefix: str,
) -> None:
    claim = Claim(statement="The projected claim is decisive")
    count = 2 if evidence_type == "counterexample" else 1
    result = validate(
        claim=claim,
        validation_id=f"projection-{expected_status}",
        evidence=tuple(
            Evidence(
                evidence_type=evidence_type,
                data={"sample": sample},
                subject_refs=(claim.ref,),
                source_refs=(claim.ref,),
                weight=1.0,
            )
            for sample in range(count)
        ),
    )
    outcome = outcome_for_result(result)
    assert outcome.status == expected_status
    assert outcome.conclusions[0].startswith(prefix)


def test_projection_roots_and_canonical_bytes_match_the_golden_v1_contract() -> None:
    contract = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert contract["schema_version"] == PROJECTION_SCHEMA_VERSION
    for workflow, result in zip(
        ("validation", "investigation", "improvement", "rsi"),
        workflow_results(),
        strict=True,
    ):
        projection = project_result(cast(ResultRecord, result))
        expected = contract["workflows"][workflow]
        assert result.root == expected["result_root"]
        assert projection.outcome.root == expected["outcome_root"]
        assert projection.projection_root == expected["projection_root"]
        assert (
            hashlib.sha256(serialize_projection(projection).encode()).hexdigest()
            == expected["serialized_sha256"]
        )

    claim = Claim(statement="events persist as projections")
    started = RuntimeEngine.start(Run(run_id="block19-golden-event", intent=claim.ref))
    assert started.transition is not None
    event = project_event(started.transition.event)
    assert event.event.root == contract["event"]["event_root"]
    assert event.projection_root == contract["event"]["projection_root"]
    assert (
        hashlib.sha256(serialize_projection(event).encode()).hexdigest()
        == contract["event"]["serialized_sha256"]
    )
