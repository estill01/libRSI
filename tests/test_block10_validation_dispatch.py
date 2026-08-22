from __future__ import annotations

import pytest

from librsi import (
    Action,
    ActionResult,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilityRoute,
    Claim,
    Evidence,
    RSICapabilityError,
    RunState,
    SemanticRecord,
    ValidationEvidenceBatch,
    ValidationRequest,
    ValidationWorkflow,
    make_validation_evidence_result,
    serialize_record,
    validation_evidence_request_from_action,
)


def _waiting():
    claim = Claim(statement="The process is repeatable", kind="behavioral")
    request = ValidationRequest.for_claim(
        validation_id="dispatch-validation",
        claim=claim,
    )
    update = ValidationWorkflow().start(request)
    return claim, request, update.progress


class _EvidenceExperimenter:
    def __init__(self, claim: Claim) -> None:
        self.claim = claim
        self.calls: list[Action] = []

    def experiment(self, action: Action) -> ActionResult:
        self.calls.append(action)
        request = validation_evidence_request_from_action(action)
        evidence = tuple(
            Evidence(
                evidence_type="support",
                data={"sample": index},
                subject_refs=(self.claim.ref,),
                source_refs=(request.ref,),
                weight=1.0,
            )
            for index in (1, 2)
        )
        return make_validation_evidence_result(
            action=action,
            batch=ValidationEvidenceBatch.collected(request=request, evidence=evidence),
        )


def test_managed_and_external_validation_produce_identical_runtime_and_result() -> None:
    claim, _, waiting = _waiting()
    workflow = ValidationWorkflow()
    managed_capability = _EvidenceExperimenter(claim)
    managed = workflow.run_managed(waiting, managed_capability)

    external_capability = _EvidenceExperimenter(claim)
    action = waiting.state.pending_actions[0]
    external = workflow.submit(waiting, external_capability.experiment(action))

    assert managed.progress.result == external.progress.result
    assert serialize_record(managed.progress.state) == serialize_record(external.progress.state)
    assert managed.transitions == external.transitions
    assert managed.progress.result is not None
    assert managed.progress.result.disposition == "supported"
    assert managed.progress.state.run.intent == claim.ref
    assert managed.progress.state.outcome is not None
    assert managed.progress.state.outcome.intervention_refs == ()
    assert managed_capability.calls == [action]


def test_dispatcher_result_state_reconciles_through_the_exact_workflow_transition() -> None:
    claim, _, waiting = _waiting()
    action = waiting.state.pending_actions[0]
    result = _EvidenceExperimenter(claim).experiment(action)
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("validation-evidence", "experimenter", "external"),)
        )
    )

    dispatched = dispatcher.submit(waiting.state, result)
    assert dispatched.transition is not None
    assert dispatched.state.status == "active"
    reconciled = ValidationWorkflow().resume(waiting.validation, dispatched.state)
    direct = ValidationWorkflow().submit(waiting, result)

    assert reconciled.progress == direct.progress
    assert reconciled.transitions == direct.transitions[1:]
    assert (dispatched.transition, *reconciled.transitions) == direct.transitions


def test_dispatcher_canonical_validation_cannot_be_bypassed_by_host_validator() -> None:
    _, _, waiting = _waiting()
    action = waiting.state.pending_actions[0]

    class _NoOpValidator:
        action_kind = "validation-evidence"

        def validate(self, state: RunState, result: ActionResult) -> None:
            return None

    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("validation-evidence", "experimenter", "external"),),
            result_validators=(_NoOpValidator(),),
        )
    )
    malformed = ActionResult(
        action=action,
        disposition="succeeded",
        payload={"narrative": "tests passed, therefore the claim is true"},
    )

    with pytest.raises(ValueError, match="only its evidence batch"):
        dispatcher.submit(waiting.state, malformed)
    assert waiting.state.results == ()
    assert waiting.state.pending_actions == (action,)


@pytest.mark.parametrize(
    ("evidence_type", "weight", "data", "message"),
    [
        ("support", 1.0, {"valid": False}, "invalid or infrastructure-failed"),
        ("support", 1.5, {"sample": 1}, "between zero and one"),
        ("null", 0.5, {"sample": 1}, "must have zero weight"),
    ],
)
def test_dispatcher_rejects_epistemically_invalid_success_before_runtime_mutation(
    evidence_type: str,
    weight: float,
    data: dict[str, object],
    message: str,
) -> None:
    claim, _, waiting = _waiting()
    action = waiting.state.pending_actions[0]
    request = validation_evidence_request_from_action(action)
    evidence = Evidence(
        evidence_type=evidence_type,
        data=data,
        subject_refs=(claim.ref,),
        source_refs=(request.ref,),
        weight=weight,
    )
    forged = object.__new__(ValidationEvidenceBatch)
    object.__setattr__(forged, "request", request)
    object.__setattr__(forged, "disposition", "collected")
    object.__setattr__(forged, "evidence", (evidence,))
    object.__setattr__(forged, "reason", None)
    object.__setattr__(
        forged,
        "lineage",
        (request.ref, *request.lineage, evidence.ref),
    )
    object.__setattr__(forged, "metadata", {})
    SemanticRecord.__post_init__(forged)
    result = make_validation_evidence_result(action=action, batch=forged)
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("validation-evidence", "experimenter", "external"),)
        )
    )

    with pytest.raises(ValueError, match=message):
        dispatcher.submit(waiting.state, result)
    assert waiting.state.results == ()
    assert waiting.state.pending_actions == (action,)


def test_wrong_capability_family_and_malformed_managed_result_fail_closed() -> None:
    claim, _, waiting = _waiting()
    with pytest.raises(RSICapabilityError, match="exact experimenter route"):
        CapabilityDispatcher(
            CapabilityRegistry(
                routes=(CapabilityRoute("validation-evidence", "reasoner", "external"),)
            )
        )

    class _NarrativeExperimenter:
        def experiment(self, action: Action) -> ActionResult:
            return ActionResult(
                action=action,
                disposition="succeeded",
                payload={"narrative": "looks valid"},
            )

    with pytest.raises(ValueError, match="only its evidence batch"):
        ValidationWorkflow().run_managed(waiting, _NarrativeExperimenter())
    assert waiting.state.results == ()
    assert claim.ref == waiting.state.run.intent


def test_run_managed_rejects_non_capability_and_external_result_mismatch() -> None:
    claim, _, waiting = _waiting()
    with pytest.raises(TypeError, match="requires an Experimenter"):
        ValidationWorkflow().run_managed(waiting, object())  # type: ignore[arg-type]
    other_claim = Claim(statement="Another claim", kind="behavioral")
    with pytest.raises(ValueError, match="exact claim"):
        _EvidenceExperimenter(other_claim).experiment(waiting.state.pending_actions[0])
    assert claim != other_claim
