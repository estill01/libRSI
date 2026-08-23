from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Action,
    ActionResult,
    CapabilityRegistry,
    CapabilityRoute,
    Claim,
    Evidence,
    InvestigationRequest,
    InvestigationWorkflow,
    LibRSI,
    Question,
    RuntimeFailure,
    ValidationEvidenceBatch,
    ValidationRequest,
    ValidationWorkflow,
    deserialize_projection,
    make_reasoning_failure,
    make_validation_evidence_failure,
    make_validation_evidence_result,
    outcome_for_result,
    project_result,
    serialize_projection,
    validation_evidence_request_from_action,
)


class _SequencedExperimenter:
    """Return one deterministic support item for each exact validation action."""

    def experiment(self, action: Action) -> ActionResult:
        request = validation_evidence_request_from_action(action)
        evidence = Evidence(
            evidence_type="support",
            data={"sequence": request.sequence},
            subject_refs=(request.validation.claim.ref,),
            source_refs=(request.ref,),
            target_snapshot=request.validation.target_snapshot,
            weight=1.0,
        )
        return make_validation_evidence_result(
            action=action,
            batch=ValidationEvidenceBatch.collected(
                request=request,
                evidence=(evidence,),
            ),
        )


def _validation_request() -> ValidationRequest:
    return ValidationRequest.for_claim(
        validation_id="block19-control-equivalence",
        claim=Claim(statement="Two independent observations support the claim"),
        max_evidence_actions=2,
    )


def test_managed_external_and_hybrid_executions_project_the_same_outcome() -> None:
    request = _validation_request()

    managed_provider = _SequencedExperimenter()
    managed_registry = CapabilityRegistry(
        routes=(CapabilityRoute("validation-evidence", "experimenter", "automatic"),),
        implementations=(managed_provider,),
    )
    managed = LibRSI(capability_registry=managed_registry).start(request)
    managed.run()

    external_provider = _SequencedExperimenter()
    external = LibRSI(
        routes=(CapabilityRoute("validation-evidence", "experimenter", "external"),)
    ).start(request)
    while not external.terminal:
        action = external.next()
        assert action is not None
        external.submit(external_provider.experiment(action), authority="external")

    hybrid_provider = _SequencedExperimenter()
    hybrid_registry = CapabilityRegistry(
        routes=(CapabilityRoute("validation-evidence", "experimenter", "automatic"),),
        implementations=(hybrid_provider,),
    )
    hybrid = LibRSI(capability_registry=hybrid_registry).start(request)
    automatic = hybrid.plan.resolutions[0]
    hybrid.submit(hybrid_registry.execute(automatic), authority="automatic")
    action = hybrid.next()
    assert action is not None
    hybrid.submit(hybrid_provider.experiment(action), authority="external")

    assert managed.result is not None
    assert managed.result == external.result == hybrid.result
    projections = tuple(
        project_result(result)
        for result in (managed.result, external.result, hybrid.result)
        if result is not None
    )
    assert len(projections) == 3
    assert projections[0] == projections[1] == projections[2]
    assert len({projection.projection_root for projection in projections}) == 1


def test_failed_validation_projection_retains_runtime_settlement() -> None:
    request = ValidationRequest.for_claim(
        validation_id="block19-failure-settlement",
        claim=Claim(statement="The collector is available"),
    )
    workflow = ValidationWorkflow()

    unavailable_start = workflow.start(request)
    unavailable_action = unavailable_start.progress.state.pending_actions[0]
    evidence_request = validation_evidence_request_from_action(unavailable_action)
    unavailable = workflow.submit(
        unavailable_start.progress,
        make_validation_evidence_result(
            action=unavailable_action,
            batch=ValidationEvidenceBatch.unavailable(
                request=evidence_request,
                reason="collector returned no evidence",
            ),
        ),
    )

    failed_start = workflow.start(request)
    failed_action = failed_start.progress.state.pending_actions[0]
    failed = workflow.submit(
        failed_start.progress,
        make_validation_evidence_failure(
            action=failed_action,
            failure=RuntimeFailure(
                classification="execution",
                message="collector crashed",
            ),
        ),
    )

    unavailable_result = unavailable.progress.result
    failed_result = failed.progress.result
    assert unavailable_result is not None and failed_result is not None
    assert unavailable_result.disposition == failed_result.disposition == "inconclusive"
    assert failed_result.terminal_status == "failed"
    assert failed_result.terminal_result == failed.progress.state.results[-1]
    assert failed_result.terminal_failure == failed.progress.state.failures[-1]
    assert failed_result.root != unavailable_result.root

    projection = project_result(failed_result)
    assert projection.outcome == failed.progress.state.outcome
    assert projection.outcome.status == "failed"
    assert projection.outcome.lineage == (
        failed_result.terminal_result.ref,
        failed_result.terminal_failure.ref,
    )
    assert deserialize_projection(serialize_projection(projection)) == projection

    forged_action = replace(failed_result.terminal_result.action, kind="unrelated-provider-action")
    forged_result = replace(failed_result.terminal_result, action=forged_action)
    with pytest.raises(ValueError, match="validation evidence action"):
        replace(
            failed_result,
            terminal_result=forged_result,
            lineage=(*failed_result.lineage[:-2], forged_result.ref, failed_result.lineage[-1]),
        )

    fabricated_payload = replace(
        failed_result.terminal_result,
        payload={"fabricated": "semantic output"},
    )
    with pytest.raises(ValueError, match="cannot contain batch outputs"):
        replace(
            failed_result,
            terminal_result=fabricated_payload,
            lineage=(
                *failed_result.lineage[:-2],
                fabricated_payload.ref,
                failed_result.lineage[-1],
            ),
        )

    arbitrary_budget_failure = RuntimeFailure(
        classification="budget-exhausted",
        message="fabricated budget settlement",
        details={"limit": 999},
    )
    with pytest.raises(ValueError, match="result and failure have drifted"):
        replace(
            failed_result,
            terminal_failure=arbitrary_budget_failure,
            lineage=(
                *failed_result.lineage[:-1],
                arbitrary_budget_failure.ref,
            ),
        )


def test_cancelled_validation_projection_remains_distinct_from_failure() -> None:
    request = ValidationRequest.for_claim(
        validation_id="block19-cancelled-settlement",
        claim=Claim(statement="The caller still wants this validation"),
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    cancellation = RuntimeFailure(
        classification="cancelled",
        message="caller withdrew the request",
    )
    cancelled = workflow.submit(
        started.progress,
        ActionResult(
            action=started.progress.state.pending_actions[0],
            disposition="cancelled",
            failure=cancellation,
        ),
    )

    result = cancelled.progress.result
    assert result is not None
    assert result.disposition == "inconclusive"
    assert result.terminal_status == "cancelled"
    assert result.terminal_failure == cancellation
    assert outcome_for_result(result) == cancelled.progress.state.outcome
    assert project_result(result).outcome.status == "cancelled"


def test_failed_investigation_projection_uses_the_runtime_failure_outcome() -> None:
    request = InvestigationRequest.for_question(
        investigation_id="block19-investigation-failure",
        question=Question(prompt="Which explanation survives?"),
        max_hypotheses=2,
    )
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    failed = workflow.submit(
        started.progress,
        make_reasoning_failure(
            action=started.progress.state.pending_actions[0],
            failure=RuntimeFailure(
                classification="execution",
                message="reasoner crashed",
            ),
        ),
    )

    result = failed.progress.result
    assert result is not None
    assert result.terminal_status == "failed"
    assert result.terminal_failure == failed.progress.state.failures[-1]
    assert outcome_for_result(result) == failed.progress.state.outcome
    assert project_result(result).outcome.status == "failed"

    assert result.failure_result is not None
    fabricated = replace(result.failure_result, payload={"proposal": "fabricated"})
    with pytest.raises(ValueError, match="cannot contain proposal outputs"):
        replace(
            result,
            failure_result=fabricated,
            lineage=(*result.lineage[:-2], fabricated.ref, result.lineage[-1]),
        )
