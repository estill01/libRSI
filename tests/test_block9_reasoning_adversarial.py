from __future__ import annotations

from copy import deepcopy

import pytest

from librsi import (
    Action,
    ActionResult,
    CapabilityRegistry,
    CapabilityRoute,
    Goal,
    ReasoningRequest,
    ReasoningResult,
    ReasoningResultValidator,
    Run,
    RuntimeEngine,
    RuntimeFailure,
    StructuredReasoner,
    TargetRef,
    TargetSnapshot,
    make_reasoning_action,
    make_reasoning_action_result,
    make_reasoning_failure,
    reasoning_request_from_action,
    reasoning_result_from_action_result,
    require_reasoning_derivation,
    validate_reasoning_content,
)


def _fixture() -> tuple[Run, ReasoningRequest, Action, ReasoningResult]:
    target = TargetRef(target_id="adversarial-target")
    snapshot = TargetSnapshot(target=target, revision="now", state={"value": 1})
    goal = Goal(statement="Explain", target=target)
    run = Run(run_id="reasoning-adversarial", intent=goal.ref, target_snapshot=snapshot)
    request = ReasoningRequest(
        request_id="explain",
        kind="explanation",
        instruction="Explain exactly",
        input_refs=(goal.ref, snapshot.ref),
        target_snapshot=snapshot,
        lineage=(goal.ref, snapshot.ref),
    )
    action = make_reasoning_action(run=run, action_id="reason", request=request)
    result = ReasoningResult.propose(
        request=request,
        content={"explanations": [{"statement": "Exact.", "basis": ["snapshot"]}]},
    )
    return run, request, action, result


def test_action_and_adapter_type_boundaries_are_explicit() -> None:
    run, request, action, result = _fixture()
    with pytest.raises(TypeError, match="require a Run"):
        make_reasoning_action(run="run", action_id="x", request=request)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require a ReasoningRequest"):
        make_reasoning_action(run=run, action_id="x", request=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require a ReasoningResult"):
        make_reasoning_action_result(action=action, result={})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ReasoningRequest"):
        ReasoningResult.propose(request=object(), content={})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="implement ReasoningBackend"):
        StructuredReasoner(object())  # type: ignore[arg-type]

    assert reasoning_request_from_action(action) == request
    assert (
        reasoning_result_from_action_result(
            make_reasoning_action_result(action=action, result=result, resource_usage={"tokens": 3})
        )
        == result
    )


def test_action_decoding_rejects_wrong_kind_shape_record_and_lineage() -> None:
    run, request, action, _ = _fixture()
    with pytest.raises(TypeError, match="requires an Action"):
        reasoning_request_from_action({})  # type: ignore[arg-type]
    wrong_kind = Action(run=run.ref, action_id="inspect", kind="inspect")
    with pytest.raises(ValueError, match="not a structured reasoning action"):
        reasoning_request_from_action(wrong_kind)
    extra_payload = Action(
        run=run.ref,
        action_id="extra",
        kind="reason",
        payload={"request": request.to_dict(), "provider": "forbidden"},
    )
    with pytest.raises(ValueError, match="only its exact request"):
        reasoning_request_from_action(extra_payload)
    text_payload = Action(
        run=run.ref,
        action_id="text",
        kind="reason",
        payload={"request": "free form"},
    )
    with pytest.raises(TypeError, match="must be a mapping"):
        reasoning_request_from_action(text_payload)
    goal_payload = Action(
        run=run.ref,
        action_id="goal",
        kind="reason",
        payload={"request": Goal(statement="Not a request").to_dict()},
    )
    with pytest.raises(TypeError, match="decode to a ReasoningRequest"):
        reasoning_request_from_action(goal_payload)
    wrong_inputs = Action(
        run=run.ref,
        action_id="inputs",
        kind="reason",
        input_refs=request.input_refs,
        payload={"request": request.to_dict()},
    )
    with pytest.raises(ValueError, match="exact request lineage"):
        reasoning_request_from_action(wrong_inputs)
    assert reasoning_request_from_action(action) == request


def test_result_decoding_and_failure_shapes_fail_closed() -> None:
    _, request, action, proposal = _fixture()
    with pytest.raises(TypeError, match="requires an ActionResult"):
        reasoning_result_from_action_result({})  # type: ignore[arg-type]

    failure = RuntimeFailure(
        classification="execution", message="backend unavailable", retryable=True
    )
    failed = make_reasoning_failure(action=action, failure=failure, resource_usage={"tokens": 1})
    assert failed.failure == failure
    with pytest.raises(ValueError, match="do not contain proposals"):
        reasoning_result_from_action_result(failed)
    with pytest.raises(TypeError, match="require a RuntimeFailure"):
        make_reasoning_failure(action=action, failure=object())  # type: ignore[arg-type]

    missing = ActionResult(action=action, disposition="succeeded")
    with pytest.raises(ValueError, match="only its proposal"):
        reasoning_result_from_action_result(missing)
    text = ActionResult(action=action, disposition="succeeded", payload={"result": "text"})
    with pytest.raises(TypeError, match="must be a mapping"):
        reasoning_result_from_action_result(text)
    wrong_record = ActionResult(
        action=action,
        disposition="succeeded",
        payload={"result": Goal(statement="Not a result").to_dict()},
    )
    with pytest.raises(TypeError, match="decode to a ReasoningResult"):
        reasoning_result_from_action_result(wrong_record)

    other = ReasoningRequest(
        request_id="other",
        kind="explanation",
        instruction="Other",
        input_refs=request.input_refs,
        target_snapshot=request.target_snapshot,
        lineage=request.input_refs,
    )
    other_result = ReasoningResult.propose(
        request=other,
        content={"explanations": [{"statement": "Other.", "basis": ["snapshot"]}]},
    )
    mismatched = ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(other_result.ref,),
        payload={"result": other_result.to_dict()},
    )
    with pytest.raises(ValueError, match="exact dispatched request"):
        reasoning_result_from_action_result(mismatched)

    valid = make_reasoning_action_result(action=action, result=proposal)
    assert reasoning_result_from_action_result(valid) == proposal


def test_result_validator_handles_failure_and_invalid_call_types() -> None:
    run, _, action, _ = _fixture()
    state = RuntimeEngine.request(RuntimeEngine.start(run).state, action).state
    validator = ReasoningResultValidator()
    failure = RuntimeFailure(classification="execution", message="no response")
    failed = make_reasoning_failure(action=action, failure=failure)
    validator.validate(state, failed)
    with pytest.raises(TypeError, match="requires a RunState"):
        validator.validate(object(), failed)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires an ActionResult"):
        validator.validate(state, object())  # type: ignore[arg-type]

    malformed_failed = ActionResult(
        action=action,
        disposition="failed",
        payload={"narration": "not a proposal"},
        failure=failure,
    )
    with pytest.raises(ValueError, match="cannot contain proposal outputs"):
        validator.validate(state, malformed_failed)

    registry = CapabilityRegistry(
        routes=(CapabilityRoute("reason", "reasoner", "external"),),
        result_validators=(validator,),
    )
    assert registry.has_result_validator("reason")
    assert not registry.has_result_validator("inspect")
    with pytest.raises(TypeError, match="requires an action kind"):
        registry.has_result_validator(1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kind", "content", "message"),
    [
        ("reflection", {"summary": "s", "observations": []}, "missing fields"),
        (
            "reflection",
            {"summary": "s", "observations": [], "open_questions": []},
            "cannot be empty",
        ),
        ("hypothesis-generation", {"hypotheses": []}, "cannot be empty"),
        (
            "hypothesis-generation",
            {
                "hypotheses": [
                    {
                        "statement": "h",
                        "causal_model": {},
                        "predictions": [{}],
                        "confidence": True,
                    }
                ]
            },
            "must be a number",
        ),
        (
            "hypothesis-generation",
            {
                "hypotheses": [
                    {
                        "statement": "h",
                        "causal_model": {},
                        "predictions": [{}],
                        "confidence": 2.0,
                    }
                ]
            },
            "between zero and one",
        ),
        (
            "experiment-design",
            {
                "experiments": [
                    {
                        "objective": "x",
                        "design": {},
                        "criteria": {},
                        "requested_measurements": "latency",
                    }
                ]
            },
            "sequence of text",
        ),
        (
            "problem-decomposition",
            {"parts": [{"part_id": "a", "objective": "A", "depends_on": ["missing"]}]},
            "known parts",
        ),
        (
            "problem-decomposition",
            {"parts": [{"part_id": "a", "objective": "A", "depends_on": ["a"]}]},
            "depend on themselves",
        ),
        (
            "problem-decomposition",
            {
                "parts": [
                    {"part_id": "a", "objective": "A", "depends_on": []},
                    {"part_id": "a", "objective": "B", "depends_on": []},
                ]
            },
            "must be unique",
        ),
    ],
)
def test_schema_validation_reports_exact_malformed_boundaries(
    kind: str, content: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        validate_reasoning_content(kind, content)


def test_record_constructor_boundaries_and_integrity_are_strict() -> None:
    _, request, _, proposal = _fixture()
    with pytest.raises(TypeError, match="must be text"):
        ReasoningRequest(
            request_id=1,  # type: ignore[arg-type]
            kind="explanation",
            instruction="Explain",
            input_refs=request.input_refs,
            target_snapshot=request.target_snapshot,
            lineage=request.input_refs,
        )
    with pytest.raises(TypeError, match="context must be a mapping"):
        ReasoningRequest(
            request_id="bad-context",
            kind="explanation",
            instruction="Explain",
            input_refs=request.input_refs,
            target_snapshot=request.target_snapshot,
            context="provider prompt",  # type: ignore[arg-type]
            lineage=request.input_refs,
        )
    with pytest.raises(TypeError, match="exact ReasoningRequest"):
        ReasoningResult(
            request=object(),  # type: ignore[arg-type]
            kind="explanation",
            content={},
        )
    with pytest.raises(TypeError, match="content must be a mapping"):
        ReasoningResult(
            request=request,
            kind="explanation",
            content="free form",  # type: ignore[arg-type]
            lineage=(request.ref, *request.input_refs),
        )
    with pytest.raises(ValueError, match="retain the exact request"):
        ReasoningResult(
            request=request,
            kind="explanation",
            content=proposal.content,
            lineage=request.input_refs,
        )
    with pytest.raises(TypeError, match="reasoning derivation requires"):
        require_reasoning_derivation(object(), Goal(statement="x"))  # type: ignore[arg-type]


def test_tampered_serialized_result_root_is_rejected() -> None:
    _, _, action, proposal = _fixture()
    payload = deepcopy(proposal.to_dict())
    payload["root"] = "a" * 64
    tampered = ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(proposal.ref,),
        payload={"result": payload},
    )
    with pytest.raises(ValueError, match="root does not match"):
        reasoning_result_from_action_result(tampered)
