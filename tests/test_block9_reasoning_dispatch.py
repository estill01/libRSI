from __future__ import annotations

from copy import deepcopy

import pytest

from librsi import (
    Action,
    ActionResult,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilityRoute,
    Goal,
    ReasoningRequest,
    ReasoningResult,
    ReasoningResultValidator,
    RSICapabilityError,
    Run,
    RunState,
    RuntimeEngine,
    StructuredReasoner,
    TargetRef,
    TargetSnapshot,
    make_reasoning_action,
    make_reasoning_action_result,
    reasoning_request_from_action,
    reasoning_result_from_action_result,
    serialize_record,
)


def _fixture():
    target = TargetRef(target_id="external-process", kind="process")
    snapshot = TargetSnapshot(target=target, revision="v7", state={"queue": 3})
    goal = Goal(statement="Explain queue growth", target=target)
    run = Run(run_id="structured-reasoning", intent=goal.ref, target_snapshot=snapshot)
    request = ReasoningRequest(
        request_id="explain-queue",
        kind="explanation",
        instruction="Explain the observed queue growth",
        input_refs=(goal.ref, snapshot.ref),
        target_snapshot=snapshot,
        lineage=(goal.ref, snapshot.ref),
    )
    action = make_reasoning_action(run=run, action_id="reason-1", request=request)
    waiting = RuntimeEngine.request(RuntimeEngine.start(run).state, action).state
    return run, request, action, waiting


class _FakeBackend:
    def __init__(self) -> None:
        self.requests: list[ReasoningRequest] = []

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        self.requests.append(request)
        return ReasoningResult.propose(
            request=request,
            content={
                "explanations": [
                    {
                        "statement": "Arrival exceeds service rate.",
                        "basis": ["exact target snapshot"],
                    }
                ]
            },
            narration="This may explain the queue; it does not validate the claim.",
        )


def _registry(*, posture: str, backend: _FakeBackend | None = None) -> CapabilityRegistry:
    implementation = () if backend is None else (StructuredReasoner(backend),)
    return CapabilityRegistry(
        routes=(CapabilityRoute("reason", "reasoner", posture),),
        implementations=implementation,
        result_validators=(ReasoningResultValidator(),),
    )


def test_managed_and_external_reasoning_use_the_same_action_result_transition() -> None:
    _, request, action, waiting = _fixture()
    managed_backend = _FakeBackend()
    managed = CapabilityDispatcher(_registry(posture="automatic", backend=managed_backend)).advance(
        waiting
    )

    external_backend = _FakeBackend()
    external_result = make_reasoning_action_result(
        action=action,
        result=external_backend.respond(reasoning_request_from_action(action)),
    )
    external_dispatcher = CapabilityDispatcher(_registry(posture="external"))
    external = external_dispatcher.submit(waiting, external_result)

    assert managed_backend.requests == [request]
    assert external_backend.requests == [request]
    assert managed.results == (external_result,)
    assert managed.transitions == (external.transition,)
    assert serialize_record(managed.state) == serialize_record(external.state)
    assert reasoning_result_from_action_result(external_result).request == request
    assert managed.state.outcome is None


def test_external_malformed_response_fails_before_state_mutation() -> None:
    _, request, action, waiting = _fixture()
    valid = ReasoningResult.propose(
        request=request,
        content={"explanations": [{"statement": "Queueing.", "basis": ["snapshot"]}]},
    )
    payload = deepcopy(valid.to_dict())
    payload["data"]["content"]["items"]["validated"] = True
    malformed = ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(valid.ref,),
        payload={"result": payload},
    )
    dispatcher = CapabilityDispatcher(_registry(posture="external"))

    with pytest.raises(ValueError, match="unsupported fields"):
        dispatcher.submit(waiting, malformed)
    assert waiting.pending_actions == (action,)
    assert waiting.results == ()


def test_direct_claim_or_evidence_promotion_is_not_a_reasoning_result() -> None:
    _, request, action, waiting = _fixture()
    proposal = ReasoningResult.propose(
        request=request,
        content={"explanations": [{"statement": "Queueing.", "basis": ["snapshot"]}]},
        narration="The claim is validated truth.",
    )
    promoted = ActionResult(
        action=action,
        disposition="succeeded",
        output_refs=(request.input_refs[0],),
        payload={"result": proposal.to_dict()},
    )
    dispatcher = CapabilityDispatcher(_registry(posture="external"))

    with pytest.raises(ValueError, match="only the exact proposal"):
        dispatcher.submit(waiting, promoted)
    assert waiting.results == ()
    assert proposal.narration == "The claim is validated truth."


def test_stale_request_and_wrong_result_request_are_rejected() -> None:
    run, request, action, _ = _fixture()
    stale = TargetSnapshot(target=run.target_snapshot.target, revision="v6", state={"queue": 2})
    stale_request = ReasoningRequest(
        request_id="stale",
        kind="explanation",
        instruction="Explain stale data",
        input_refs=(run.intent, stale.ref),
        target_snapshot=stale,
        lineage=(run.intent, stale.ref),
    )
    with pytest.raises(ValueError, match="stale or mismatched"):
        make_reasoning_action(run=run, action_id="stale", request=stale_request)

    forged_stale_action = Action(
        run=run.ref,
        action_id="forged-stale",
        kind="reason",
        input_refs=(stale_request.ref, *stale_request.input_refs),
        payload={"request": stale_request.to_dict()},
    )
    forged_waiting = RuntimeEngine.request(
        RuntimeEngine.start(run).state, forged_stale_action
    ).state
    forged_result = make_reasoning_action_result(
        action=forged_stale_action,
        result=ReasoningResult.propose(
            request=stale_request,
            content={"explanations": [{"statement": "Stale.", "basis": ["old"]}]},
        ),
    )
    with pytest.raises(ValueError, match="stale or mismatched"):
        CapabilityDispatcher(_registry(posture="external")).submit(forged_waiting, forged_result)
    assert forged_waiting.results == ()

    other = ReasoningRequest(
        request_id="other",
        kind="explanation",
        instruction="Explain something else",
        input_refs=request.input_refs,
        target_snapshot=request.target_snapshot,
        lineage=request.input_refs,
    )
    wrong = ReasoningResult.propose(
        request=other,
        content={"explanations": [{"statement": "Other.", "basis": ["snapshot"]}]},
    )
    with pytest.raises(ValueError, match="exact dispatched request"):
        make_reasoning_action_result(action=action, result=wrong)


def test_validator_configuration_and_bad_managed_backend_fail_closed() -> None:
    _, _, _, waiting = _fixture()
    with pytest.raises(ValueError, match="exact configured route"):
        CapabilityRegistry(result_validators=(ReasoningResultValidator(),))

    canonical_only = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("reason", "reasoner", "external"),),
        )
    )
    free_form = ActionResult(
        action=waiting.pending_actions[0],
        disposition="succeeded",
        payload={"anything": "free form"},
    )
    with pytest.raises(ValueError, match="only its proposal"):
        canonical_only.submit(waiting, free_form)
    assert waiting.results == ()

    class _NoOpValidator:
        action_kind = "reason"

        def validate(self, state: RunState, result: ActionResult) -> None:
            return None

    no_op = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("reason", "reasoner", "external"),),
            result_validators=(_NoOpValidator(),),
        )
    )
    with pytest.raises(ValueError, match="only its proposal"):
        no_op.submit(waiting, free_form)
    assert waiting.results == ()

    with pytest.raises(RSICapabilityError, match="exact reasoner route"):
        CapabilityDispatcher(
            CapabilityRegistry(
                routes=(CapabilityRoute("reason", "inspector", "external"),),
                result_validators=(ReasoningResultValidator(),),
            )
        )
    assert waiting.results == ()

    class _BadBackend:
        def respond(self, request: ReasoningRequest) -> object:
            return {"narration": "free form"}

    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("reason", "reasoner", "automatic"),),
            implementations=(StructuredReasoner(_BadBackend()),),  # type: ignore[arg-type]
            result_validators=(ReasoningResultValidator(),),
        )
    )
    with pytest.raises(RSICapabilityError, match="raised an exception"):
        dispatcher.advance(waiting)
    assert waiting.results == ()
