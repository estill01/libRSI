from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    ActionResult,
    ImplementationResultValidator,
    RuntimeEngine,
    RuntimeFailure,
    implementation_request_from_action,
    implementation_result_from_action_result,
    make_implementation_action,
    make_implementation_failure,
    make_implementation_result,
)
from tests.block12_support import intervention_context


def _waiting():
    context = intervention_context()
    action = make_implementation_action(context.request)
    state = RuntimeEngine.request(
        RuntimeEngine.start(context.intervention.canonical_run()).state,
        action,
    ).state
    return context, action, state


def test_implementation_action_and_success_result_are_exactly_correlated() -> None:
    context, action, waiting = _waiting()
    envelope = make_implementation_result(action=action, result=context.result)

    assert implementation_request_from_action(action) == context.request
    assert implementation_result_from_action_result(envelope) == context.result
    assert envelope.output_refs == (context.result.ref, context.candidate.ref)
    ImplementationResultValidator().validate(waiting, envelope)


@pytest.mark.parametrize("field", ["action_id", "kind", "input_refs", "payload"])
def test_action_decoder_rejects_any_noncanonical_request_projection(field: str) -> None:
    context = intervention_context()
    action = make_implementation_action(context.request)
    replacement = {
        "action_id": "other",
        "kind": "reason",
        "input_refs": (context.request.ref,),
        "payload": {"request": context.request.to_dict(), "domain": "smuggled"},
    }[field]
    forged = replace(action, **{field: replacement})

    with pytest.raises(ValueError):
        implementation_request_from_action(forged)


def test_result_decoder_rejects_payload_and_output_reference_drift() -> None:
    context, action, _ = _waiting()
    valid = make_implementation_result(action=action, result=context.result)

    with pytest.raises(ValueError, match="only its exact result"):
        implementation_result_from_action_result(
            replace(valid, payload={"result": context.result.to_dict(), "applied": True})
        )
    with pytest.raises(ValueError, match="exact result and candidate"):
        implementation_result_from_action_result(
            replace(valid, output_refs=(context.candidate.ref, context.result.ref))
        )


def test_structured_implementation_failure_has_no_candidate_output() -> None:
    _, action, waiting = _waiting()
    failure = RuntimeFailure(
        classification="execution",
        message="No bounded implementer is connected",
        retryable=False,
    )
    result = make_implementation_failure(action=action, failure=failure)

    assert result.output_refs == ()
    assert not result.payload
    ImplementationResultValidator().validate(waiting, result)
    with pytest.raises(ValueError, match="cannot contain candidate outputs"):
        ImplementationResultValidator().validate(
            waiting,
            ActionResult(
                action=action,
                disposition="failed",
                output_refs=(failure.ref,),
                failure=failure,
            ),
        )


def test_result_validator_rejects_stale_or_unrequested_actions() -> None:
    context, action, waiting = _waiting()
    envelope = make_implementation_result(action=action, result=context.result)
    initial = RuntimeEngine.start(context.intervention.canonical_run()).state

    with pytest.raises(ValueError, match="not for a pending action"):
        ImplementationResultValidator().validate(initial, envelope)
    other = replace(context.intervention, intervention_id="other-intervention")
    other_state = RuntimeEngine.start(other.canonical_run()).state
    with pytest.raises(ValueError, match="stale or mismatched"):
        ImplementationResultValidator().validate(other_state, envelope)
    assert waiting.results == ()
