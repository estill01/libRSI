from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator, ValidationError

from librsi import (
    CapabilityBinding,
    Evidence,
    RunAdmissionBinding,
    TargetRef,
    TargetSnapshot,
    action_result_schema,
    deserialize_record,
    external_response_schema,
    serialize_record,
    target_admission_schema,
)
from librsi.identity import canonical_json
from librsi.protocol import error_document, response_document, serialize_response
from librsi.runtime import ActionResult, RuntimeFailure
from librsi.validation import ValidationWorkflow
from tests.block20_support import target_admission, validation_request, validation_result


def test_target_admission_is_complete_canonical_and_round_trips() -> None:
    admission = target_admission()

    assert deserialize_record(serialize_record(admission)) == admission
    assert admission.binding_for("validation-evidence").route().posture == "external"
    assert admission.lineage == (
        admission.target_snapshot.ref,
        admission.objective.ref,
        admission.evaluation_contract.ref,
        *(item.ref for item in admission.capabilities),
        admission.application_requirement.ref,
    )
    assert set(admission.resource_limits) >= {
        "max_actions",
        "max_failures",
        "max_retries",
    }


def test_run_admission_binding_is_an_exact_immutable_relationship_record() -> None:
    admission = target_admission()
    request = validation_request()
    binding = RunAdmissionBinding.create(
        run_id=request.validation_id,
        workflow="validation",
        request=request,
        admission=admission,
        initial_snapshot=admission.target_snapshot,
    )

    assert deserialize_record(serialize_record(binding)) == binding
    assert binding.lineage == (
        request.ref,
        admission.ref,
        admission.target_snapshot.ref,
    )
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(binding, lineage=())
    with pytest.raises(ValueError, match="unsupported bound workflow"):
        replace(binding, workflow="future")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("capabilities", (), "requires CapabilityBinding"),
        ("resource_limits", {"max_actions": 1}, "resource limits require"),
        ("lineage", (), "lineage is incomplete"),
    ],
)
def test_target_admission_rejects_incomplete_contracts(field, value, message: str) -> None:
    admission = target_admission()
    with pytest.raises((TypeError, ValueError), match=message):
        replace(admission, **{field: value})


def test_target_admission_rejects_snapshot_and_application_drift() -> None:
    admission = target_admission()
    other = TargetSnapshot(
        target=admission.target_snapshot.target,
        revision="batch-19",
        state=admission.target_snapshot.state,
    )
    with pytest.raises(ValueError, match="objective and contract"):
        replace(admission, target_snapshot=other)
    wrong_target = TargetSnapshot(
        target=TargetRef(target_id="other", kind="physical-process"),
        revision="batch-18",
        state={},
    )
    with pytest.raises(ValueError, match="application governance"):
        replace(
            admission,
            application_requirement=replace(
                admission.application_requirement,
                target_snapshot=wrong_target,
                lineage=(wrong_target.ref, *admission.application_requirement.governing_refs),
            ),
        )


def test_capability_bindings_reject_unknown_or_duplicate_authority() -> None:
    with pytest.raises(ValueError, match="unsupported capability family"):
        CapabilityBinding(action_kind="x", family="oracle", posture="external")
    with pytest.raises(ValueError, match="unsupported capability posture"):
        CapabilityBinding(action_kind="x", family="reasoner", posture="implicit")
    route = CapabilityBinding(
        action_kind="validation-evidence", family="experimenter", posture="external"
    )
    with pytest.raises(ValueError, match="must be unique"):
        target_admission(capabilities=(route, route))


def test_pending_result_schema_is_closed_and_bound_to_the_exact_action() -> None:
    action = ValidationWorkflow().start(validation_request()).progress.state.pending_actions[0]
    schema = action_result_schema(action)

    assert schema["additionalProperties"] is False
    action_schema = schema["properties"]["data"]["properties"]["action"]
    assert action_schema == {"const": action.to_dict()}
    assert schema["$id"].endswith(action.root)

    with pytest.raises(TypeError, match="exact Action"):
        action_result_schema(object())  # type: ignore[arg-type]


def test_public_protocol_schemas_are_closed_and_bind_canonical_types() -> None:
    response = external_response_schema()
    record = target_admission()
    admission = target_admission_schema(record)

    assert response["$id"] == "librsi.external-agent/v1"
    assert response["additionalProperties"] is False
    assert admission["$id"].endswith(record.root)
    assert admission["const"] == record.to_dict()
    Draft202012Validator.check_schema(admission)
    Draft202012Validator(admission).validate(record.to_dict())
    with pytest.raises(TypeError, match="exact TargetAdmission"):
        target_admission_schema(object())  # type: ignore[arg-type]


def test_result_schema_validates_canonical_success_and_failure_documents() -> None:
    action = ValidationWorkflow().start(validation_request()).progress.state.pending_actions[0]
    success = validation_result(action).to_dict()
    failed = replace(
        validation_result(action),
        disposition="failed",
        output_refs=(),
        payload={},
        failure=RuntimeFailure(
            classification="execution",
            message="external experiment failed",
            retryable=False,
            lineage=(action.ref,),
        ),
        lineage=(action.ref,),
    ).to_dict()
    schema = action_result_schema(action)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    validator.validate(success)
    validator.validate(failed)


@pytest.mark.parametrize(
    ("mutation",),
    [
        (lambda document: document["data"].__setitem__("unexpected", True),),
        (lambda document: document["data"].__setitem__("output_refs", "not-a-list"),),
        (lambda document: document["data"].__setitem__("payload", {"plain": True}),),
        (
            lambda document: document["data"].__setitem__(
                "resource_usage",
                {"$schema": "librsi.map/v1", "items": {"units": -1}},
            ),
        ),
        (lambda document: document["data"]["action"].__setitem__("root", "0" * 64),),
        (lambda document: document["data"].__setitem__("failure", {}),),
        (lambda document: document["data"].pop("lineage"),),
    ],
)
def test_result_schema_rejects_structurally_malformed_documents(mutation) -> None:
    action = ValidationWorkflow().start(validation_request()).progress.state.pending_actions[0]
    document = deepcopy(validation_result(action).to_dict())
    mutation(document)

    with pytest.raises(ValidationError):
        Draft202012Validator(action_result_schema(action)).validate(document)


def test_validation_schema_rejects_generic_empty_success_accepted_by_record_decoder() -> None:
    action = ValidationWorkflow().start(validation_request()).progress.state.pending_actions[0]
    generic = ActionResult(action=action, disposition="succeeded").to_dict()

    with pytest.raises(ValidationError):
        Draft202012Validator(action_result_schema(action)).validate(generic)


def test_target_schema_rejects_every_change_to_the_bound_admission() -> None:
    admission = target_admission()
    document = deepcopy(admission.to_dict())
    document["data"]["resource_limits"]["items"]["max_actions"] = -1

    with pytest.raises(ValidationError):
        Draft202012Validator(target_admission_schema(admission)).validate(document)


def test_canonical_json_is_deterministic_and_stack_safe_for_deep_records() -> None:
    nested: dict = {}
    for _ in range(1_500):
        nested = {"next": nested}

    encoded = canonical_json(nested)

    assert encoded.startswith('{"next":{"next":')
    assert encoded.endswith("}" * 1_501)
    assert canonical_json({"b": [True, None], "a": "é"}) == '{"a":"é","b":[true,null]}'

    cyclic: dict = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="cannot contain cycles"):
        canonical_json(cyclic)


def test_canonical_json_ignores_numeric_subclass_string_overrides() -> None:
    class MisleadingInteger(int):
        def __str__(self) -> str:
            return "INVALID"

    evidence = Evidence(
        evidence_type="observation",
        data={"sample_count": MisleadingInteger(7)},
    )
    serialized = serialize_record(evidence)

    assert '"sample_count":7' in serialized
    assert deserialize_record(serialized) == evidence


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("action_kind", object(), "must be text"),
        ("action_kind", " ", "is required"),
        ("lineage", (TargetRef(target_id="x", kind="test").ref,), "do not accept"),
    ],
)
def test_capability_binding_rejects_noncanonical_text_and_lineage(
    field, value, message: str
) -> None:
    values = {
        "action_kind": "validation-evidence",
        "family": "experimenter",
        "posture": "external",
    }
    values[field] = value
    with pytest.raises((TypeError, ValueError), match=message):
        CapabilityBinding(**values)  # type: ignore[arg-type]


def test_target_admission_rejects_invalid_evidence_and_limits() -> None:
    admission = target_admission()
    unsourced = Evidence(
        evidence_type="support",
        data={"sample": 1},
        subject_refs=(admission.objective.ref,),
        source_refs=(),
        target_snapshot=admission.target_snapshot,
        weight=1.0,
    )
    with pytest.raises(ValueError, match="current and exactly sourced"):
        type(admission).create(
            admission_id="unsourced",
            target_snapshot=admission.target_snapshot,
            objective=admission.objective,
            evaluation_contract=admission.evaluation_contract,
            capabilities=admission.capabilities,
            evidence_baseline=(unsourced,),
            application_requirement=admission.application_requirement,
            resource_limits=admission.resource_limits,
        )
    with pytest.raises(TypeError, match="evidence must be a sequence"):
        replace(admission, evidence_baseline="bad")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="contain Evidence"):
        replace(admission, evidence_baseline=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be unique"):
        replace(admission, evidence_baseline=(unsourced, unsourced))

    for limits, error in (
        (object(), TypeError),
        ({"max_actions": True, "max_failures": 1, "max_retries": 1}, TypeError),
        ({"max_actions": float("nan"), "max_failures": 1, "max_retries": 1}, ValueError),
        ({"max_actions": -1, "max_failures": 1, "max_retries": 1}, ValueError),
    ):
        with pytest.raises(error):
            replace(admission, resource_limits=limits)  # type: ignore[arg-type]


def test_target_admission_rejects_wrong_record_types_and_missing_binding() -> None:
    admission = target_admission()
    for field, value, message in (
        ("target_snapshot", object(), "exact TargetSnapshot"),
        ("objective", object(), "exact Objective"),
        ("evaluation_contract", object(), "exact EvaluationContract"),
        ("application_requirement", object(), "application governance"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            replace(admission, **{field: value})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="capabilities must be a sequence"):
        replace(admission, capabilities="bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="does not bind"):
        admission.binding_for("missing")


def test_protocol_envelope_helpers_reject_unstructured_inputs() -> None:
    with pytest.raises(ValueError, match="operation is required"):
        response_document(" ", data={})
    with pytest.raises(TypeError, match="data must be a mapping"):
        response_document("status", data=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a mapping"):
        serialize_response(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require an Exception"):
        error_document(object())  # type: ignore[arg-type]
