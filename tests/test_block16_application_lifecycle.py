from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    APPLY_CANDIDATE_ACTION_KIND,
    ActionResult,
    ApplicationActionResultValidator,
    ApplicationCommand,
    ApplicationPolicy,
    ApplicationProgress,
    ApplicationRequest,
    ApplicationResult,
    ApplicationWorkflow,
    CapabilityRegistry,
    CapabilityRoute,
    Evidence,
    Outcome,
    RSITransitionError,
    Run,
    RuntimeEngine,
    RuntimeFailure,
    TargetSnapshot,
    application_command_from_action,
    application_receipt_from_result,
    apply_improvement,
    deserialize_record,
    make_application_failure,
    make_application_success,
    make_apply_action,
    make_rollback_action,
    make_rollback_success,
    make_verification_result,
    make_verify_action,
    rollback_input_from_action,
    rollback_receipt_from_result,
    serialize_record,
    verification_from_result,
    verification_input_from_action,
)
from tests.block14_support import ComparisonContext, comparison_context
from tests.block15_support import DeterministicCycleProvider, improvement_request
from tests.block16_support import DeterministicApplicationTarget, application_registry


@pytest.fixture(scope="module")
def context() -> ComparisonContext:
    return comparison_context()


@pytest.fixture(scope="module")
def improvement(context: ComparisonContext):
    from librsi import improve

    return improve(
        improvement_request(context),
        provider=DeterministicCycleProvider(context, (True,)),
        current_snapshot=context.baseline_snapshot,
    )


def application_request(improvement, *, apply: bool = True) -> ApplicationRequest:
    return ApplicationRequest.create(
        application_id="bounded-application",
        improvement=improvement,
        current_snapshot=improvement.request.baseline,
        apply=apply,
    )


@pytest.fixture(scope="module")
def rejected_result(improvement, context: ComparisonContext) -> ApplicationResult:
    result = apply_improvement(
        improvement,
        current_snapshot=context.baseline_snapshot,
        apply=True,
        registry=application_registry(
            DeterministicApplicationTarget(
                context.baseline_snapshot,
                verification="rejected",
            )
        ),
        application_id="contract-fixture",
    )
    assert isinstance(result, ApplicationResult)
    return result


@pytest.fixture(scope="module")
def verified_result(improvement, context: ComparisonContext) -> ApplicationResult:
    result = apply_improvement(
        improvement,
        current_snapshot=context.baseline_snapshot,
        apply=True,
        registry=application_registry(DeterministicApplicationTarget(context.baseline_snapshot)),
        application_id="verified-contract-fixture",
    )
    assert isinstance(result, ApplicationResult)
    return result


def stale(snapshot: TargetSnapshot) -> TargetSnapshot:
    return replace(
        snapshot,
        state={**snapshot.state, "concurrent_change": True},
        revision=f"stale-{snapshot.revision}",
    )


def test_disabled_application_returns_consumable_result_without_effects(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)

    result = apply_improvement(
        improvement,
        current_snapshot=context.baseline_snapshot,
        apply=False,
        registry=application_registry(target),
    )

    assert isinstance(result, ApplicationResult)
    assert result.disposition == "application-disabled"
    assert result.authoritative_snapshot == context.baseline_snapshot
    assert result.application is None
    assert target.apply_calls == []
    assert target.verify_calls == []


@pytest.mark.parametrize("target_kind", ["physical-process", "software-repository"])
def test_authorized_application_verifies_the_actual_host_state(target_kind: str) -> None:
    local_context = comparison_context(target_kind=target_kind)
    from librsi import improve

    improvement = improve(
        improvement_request(local_context),
        provider=DeterministicCycleProvider(local_context, (True,)),
        current_snapshot=local_context.baseline_snapshot,
    )
    target = DeterministicApplicationTarget(local_context.baseline_snapshot)

    result = apply_improvement(
        improvement,
        current_snapshot=local_context.baseline_snapshot,
        apply=True,
        registry=application_registry(target),
    )

    assert isinstance(result, ApplicationResult)
    assert result.disposition == "verified"
    assert result.application is not None
    assert result.verification is not None
    assert result.verification.disposition == "verified"
    assert result.verification.assessment is not None
    assert result.verification.assessment.disposition == "accepted"
    assert result.verification.assessment.batch.candidate.snapshot == target.snapshot
    assert result.application.produced_snapshot == target.snapshot
    assert result.authoritative_snapshot == target.snapshot
    assert (
        result.authoritative_snapshot
        != improvement.handoff.selection.assessments[0].batch.candidate.snapshot
    )
    assert result.authoritative_snapshot.state["host_applied"] == "actual"
    assert [action.kind for action in target.apply_calls] == [APPLY_CANDIDATE_ACTION_KIND]
    assert len(target.verify_calls) == 1


def test_rejected_actual_state_rolls_back_to_exact_prior_snapshot(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        verification="rejected",
    )

    result = apply_improvement(
        improvement,
        current_snapshot=context.baseline_snapshot,
        apply=True,
        registry=application_registry(target),
    )

    assert isinstance(result, ApplicationResult)
    assert result.disposition == "rolled-back"
    assert result.verification is not None
    assert result.verification.disposition == "rejected"
    assert result.verification.assessment is not None
    assert result.verification.assessment.disposition == "rejected"
    assert any(
        criterion.disposition == "failed" for criterion in result.verification.assessment.criteria
    )
    assert result.rollback is not None
    assert result.rollback.restored_snapshot == context.baseline_snapshot
    assert result.authoritative_snapshot == context.baseline_snapshot
    assert target.snapshot == context.baseline_snapshot
    assert [action.kind for action in target.apply_calls] == [
        "apply-selected-candidate",
        "rollback-applied-target",
    ]


def test_verifier_infrastructure_failure_is_operational_and_rolls_back(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        verification="unavailable",
    )

    result = apply_improvement(
        improvement,
        current_snapshot=context.baseline_snapshot,
        apply=True,
        registry=application_registry(target),
    )

    assert isinstance(result, ApplicationResult)
    assert result.disposition == "rolled-back"
    assert result.verification is not None
    assert result.verification.disposition == "unavailable"
    assert len(result.operational_failures) == 1
    assert isinstance(result.operational_failures[0], RuntimeFailure)
    assert not isinstance(result.operational_failures[0], Evidence)
    assert result.request.improvement == improvement
    assert target.snapshot == context.baseline_snapshot


def test_application_failure_does_not_mutate_epistemic_result(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        fail_application=True,
    )

    result = apply_improvement(
        improvement,
        current_snapshot=context.baseline_snapshot,
        apply=True,
        registry=application_registry(target),
    )

    assert isinstance(result, ApplicationResult)
    assert result.disposition == "application-failed"
    assert result.authoritative_snapshot == context.baseline_snapshot
    assert result.application is None
    assert result.request.improvement == improvement
    assert result.request.improvement.disposition == "improved"
    assert len(result.operational_failures) == 1


def test_failed_rollback_never_claims_an_authoritative_state(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        verification="rejected",
        fail_rollback=True,
    )

    result = apply_improvement(
        improvement,
        current_snapshot=context.baseline_snapshot,
        apply=True,
        registry=application_registry(target),
    )

    assert isinstance(result, ApplicationResult)
    assert result.disposition == "rollback-failed"
    assert result.authoritative_snapshot is None
    assert result.application is not None
    assert result.verification is not None
    assert result.rollback is None
    assert len(result.operational_failures) == 1


@pytest.mark.parametrize(
    ("registry", "posture"),
    [
        (application_registry(None), "unavailable"),
        (
            application_registry(
                DeterministicApplicationTarget(comparison_context().baseline_snapshot),
                apply_posture="unavailable",
            ),
            "unavailable",
        ),
        (
            application_registry(
                DeterministicApplicationTarget(comparison_context().baseline_snapshot),
                apply_posture="human-reserved",
            ),
            "human-reserved",
        ),
    ],
)
def test_absent_unavailable_and_reserved_appliers_never_execute(
    improvement,
    context: ComparisonContext,
    registry: CapabilityRegistry,
    posture: str,
) -> None:
    request = application_request(improvement)
    workflow = ApplicationWorkflow(registry)
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)

    update = workflow.run_managed(
        started.progress,
        current_snapshot=context.baseline_snapshot,
    )

    assert update.progress.state.status == "waiting"
    assert update.progress.result is None
    assert update.plan.resolutions[0].posture == posture


def test_external_authority_can_submit_each_exact_pre_and_post_effect_state(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = ApplicationWorkflow(
        application_registry(
            target,
            apply_posture="external",
            verify_posture="external",
        )
    )
    started = workflow.start(
        application_request(improvement),
        current_snapshot=context.baseline_snapshot,
    )
    apply_result = target.apply(started.progress.state.pending_actions[0])
    applied = workflow.submit(
        started.progress,
        apply_result,
        prior_snapshot=context.baseline_snapshot,
        current_snapshot=target.snapshot,
        authority="external",
    )
    applied_snapshot = target.snapshot
    verification_result = target.verify(applied.progress.state.pending_actions[0])

    completed = workflow.submit(
        applied.progress,
        verification_result,
        prior_snapshot=applied_snapshot,
        current_snapshot=applied_snapshot,
        authority="external",
    )

    assert completed.progress.result is not None
    assert completed.progress.result.disposition == "verified"
    assert completed.progress.result.authoritative_snapshot == applied_snapshot


def test_stale_start_rejects_before_any_provider_effect(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = ApplicationWorkflow(application_registry(target))

    with pytest.raises(ValueError, match="drifted"):
        workflow.start(
            application_request(improvement),
            current_snapshot=stale(context.baseline_snapshot),
        )
    assert target.apply_calls == []


def test_wrong_post_effect_snapshot_is_rejected_before_runtime_mutation(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = ApplicationWorkflow(application_registry(target))
    started = workflow.start(
        application_request(improvement),
        current_snapshot=context.baseline_snapshot,
    )
    result = target.apply(started.progress.state.pending_actions[0])

    with pytest.raises(ValueError, match="drifted"):
        workflow.submit(
            started.progress,
            result,
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="automatic",
        )
    assert started.progress.state.results == ()


def test_repeated_managed_run_does_not_duplicate_application(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = ApplicationWorkflow(application_registry(target))
    started = workflow.start(
        application_request(improvement),
        current_snapshot=context.baseline_snapshot,
    )
    completed = workflow.run_managed(
        started.progress,
        current_snapshot=context.baseline_snapshot,
    )
    assert completed.progress.result is not None

    repeated = workflow.run_managed(
        completed.progress,
        current_snapshot=target.snapshot,
    )

    assert repeated.progress == completed.progress
    assert completed.progress.state.outcome is not None
    assert completed.progress.state.outcome.target_snapshot == target.snapshot
    assert (
        completed.progress.state.run.target_transition_authority == completed.progress.request.ref
    )
    assert len(target.apply_calls) == 1
    assert len(target.verify_calls) == 1


def test_failed_verifier_envelope_cannot_become_counterevidence(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = ApplicationWorkflow(application_registry(target))
    started = workflow.start(
        application_request(improvement),
        current_snapshot=context.baseline_snapshot,
    )
    application_result = target.apply(started.progress.state.pending_actions[0])
    applied = workflow.submit(
        started.progress,
        application_result,
        prior_snapshot=context.baseline_snapshot,
        current_snapshot=target.snapshot,
        authority="automatic",
    )
    action = applied.progress.state.pending_actions[0]
    failed = make_application_failure(
        action=action,
        failure=RuntimeFailure(
            classification="execution",
            message="verifier host failed",
        ),
    )

    with pytest.raises(ValueError, match="typed unavailable report"):
        workflow.submit(
            applied.progress,
            failed,
            prior_snapshot=target.snapshot,
            current_snapshot=target.snapshot,
            authority="automatic",
        )
    assert applied.progress.state.results == (application_result,)


def test_result_codecs_and_persisted_replay_round_trip_exactly(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    result = apply_improvement(
        improvement,
        current_snapshot=context.baseline_snapshot,
        apply=True,
        registry=application_registry(target),
    )
    assert isinstance(result, ApplicationResult)

    restored = deserialize_record(serialize_record(result))

    assert type(restored) is ApplicationResult
    assert restored == result
    resumed = ApplicationWorkflow(application_registry(target)).resume(
        result.request,
        result.settled_state,
        current_snapshot=target.snapshot,
    )
    assert resumed.progress.result == result


def test_tampered_result_payload_and_observed_snapshot_fail_closed(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = ApplicationWorkflow(application_registry(target))
    started = workflow.start(
        application_request(improvement),
        current_snapshot=context.baseline_snapshot,
    )
    action = started.progress.state.pending_actions[0]
    valid = target.apply(action)
    receipt = application_receipt_from_result(valid)
    tampered = replace(valid, output_refs=(receipt.ref, context.baseline_snapshot.ref))

    with pytest.raises(ValueError, match="exact receipt and produced state"):
        workflow.submit(
            started.progress,
            tampered,
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=target.snapshot,
            authority="automatic",
        )

    applied = workflow.submit(
        started.progress,
        valid,
        prior_snapshot=context.baseline_snapshot,
        current_snapshot=target.snapshot,
        authority="automatic",
    )
    valid_verification = verification_from_result(
        target.verify(applied.progress.state.pending_actions[0])
    )
    with pytest.raises(ValueError, match="exact produced"):
        replace(valid_verification, observed_snapshot=stale(target.snapshot))


def test_forged_persisted_action_history_is_rejected_before_provider_effects(
    improvement,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = ApplicationWorkflow(application_registry(target))
    started = workflow.start(
        application_request(improvement),
        current_snapshot=context.baseline_snapshot,
    )
    canonical = started.progress.state.pending_actions[0]
    forged = replace(canonical, action_id="forged-direct-application")
    run_started = RuntimeEngine.start(started.progress.request.canonical_run()).state
    forged_state = RuntimeEngine.request(run_started, forged).state
    with pytest.raises(ValueError, match="exact lifecycle-derived frontier"):
        replace(started.progress, state=forged_state)
    assert target.apply_calls == []


def test_route_family_and_submission_authority_cannot_be_substituted(
    improvement,
    context: ComparisonContext,
) -> None:
    with pytest.raises(Exception, match="exact applier route"):
        ApplicationWorkflow(
            CapabilityRegistry(
                routes=(
                    CapabilityRoute(
                        APPLY_CANDIDATE_ACTION_KIND,
                        "verifier",
                        "external",
                    ),
                )
            )
        )

    workflow = ApplicationWorkflow(
        application_registry(
            DeterministicApplicationTarget(context.baseline_snapshot),
            apply_posture="external",
        )
    )
    started = workflow.start(
        application_request(improvement),
        current_snapshot=context.baseline_snapshot,
    )
    candidate = started.progress.request.candidate
    assert candidate is not None
    fabricated = make_application_success(
        action=started.progress.state.pending_actions[0],
        produced_snapshot=candidate.snapshot,
    )
    with pytest.raises(Exception, match="authority does not match"):
        workflow.submit(
            started.progress,
            fabricated,
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=candidate.snapshot,
            authority="automatic",
        )


def test_direct_nonprojected_application_result_is_rejected(
    improvement,
    context: ComparisonContext,
) -> None:
    request = application_request(improvement, apply=False)
    workflow = ApplicationWorkflow()
    completed = workflow.start(request, current_snapshot=context.baseline_snapshot)
    result = completed.progress.result
    assert result is not None

    with pytest.raises(ValueError, match="runtime-derived projection"):
        replace(result, disposition="verified")


def test_application_progress_cannot_wrap_a_noncanonical_state(
    improvement,
    context: ComparisonContext,
) -> None:
    request = application_request(improvement)
    state = RuntimeEngine.start(request.canonical_run()).state
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = ApplicationWorkflow(application_registry(target))
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    result = target.apply(started.progress.state.pending_actions[0])
    applied = workflow.submit(
        started.progress,
        result,
        prior_snapshot=context.baseline_snapshot,
        current_snapshot=target.snapshot,
        authority="automatic",
    )
    with pytest.raises(ValueError, match="projection"):
        ApplicationProgress(
            request=request,
            state=state,
            projection=applied.progress.projection,
        )


def test_terminal_progress_rejects_result_from_another_exact_application_state(
    improvement,
    context: ComparisonContext,
) -> None:
    request = application_request(improvement)
    first_target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        actual_label="first",
    )
    second_target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        actual_label="second",
    )

    def complete(target: DeterministicApplicationTarget):
        workflow = ApplicationWorkflow(application_registry(target))
        started = workflow.start(request, current_snapshot=context.baseline_snapshot)
        return workflow.run_managed(
            started.progress,
            current_snapshot=context.baseline_snapshot,
        )

    first = complete(first_target)
    second = complete(second_target)
    assert first.progress.result is not None
    assert second.progress.result is not None
    assert first.progress.result.settled_state != second.progress.result.settled_state

    with pytest.raises(ValueError, match="another exact state"):
        ApplicationProgress(
            request=request,
            state=second.progress.state,
            projection=second.progress.projection,
            result=first.progress.result,
        )
    with pytest.raises(ValueError, match="requires its exact result"):
        replace(second.progress, result=None)


def test_runtime_target_transition_authority_is_explicit_and_same_target_only(
    improvement,
    context: ComparisonContext,
) -> None:
    request = application_request(improvement)
    run = request.canonical_run()
    assert run.target_snapshot == context.baseline_snapshot
    assert run.target_transition_authority == request.ref
    started = RuntimeEngine.start(run).state
    same_target = stale(context.baseline_snapshot)
    completed = RuntimeEngine.complete(
        started,
        Outcome(
            intent=request.ref,
            status="completed",
            target_snapshot=same_target,
            lineage=(request.ref,),
        ),
    )
    assert completed.state.outcome is not None
    assert completed.state.outcome.target_snapshot == same_target

    other_target = comparison_context(target_kind="software-repository").baseline_snapshot
    with pytest.raises(RSITransitionError, match="target snapshot"):
        RuntimeEngine.complete(
            started,
            Outcome(
                intent=request.ref,
                status="completed",
                target_snapshot=other_target,
                lineage=(request.ref,),
            ),
        )
    with pytest.raises(ValueError, match="initial target snapshot"):
        Run(
            run_id="invalid-transition-authority",
            intent=request.ref,
            target_transition_authority=request.ref,
        )
    with pytest.raises(TypeError, match="RecordRef"):
        replace(run, target_transition_authority="authority")


def test_failed_application_result_cannot_carry_semantic_outputs(
    improvement,
    context: ComparisonContext,
) -> None:
    request = application_request(improvement)
    workflow = ApplicationWorkflow(
        application_registry(
            DeterministicApplicationTarget(context.baseline_snapshot),
            apply_posture="external",
        )
    )
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    failure = RuntimeFailure(classification="execution", message="failed")
    smuggled = ActionResult(
        action=action,
        disposition="failed",
        output_refs=(request.improvement.ref,),
        payload={"counterevidence": request.improvement.to_dict()},
        failure=failure,
        lineage=(action.ref, failure.ref),
    )

    with pytest.raises(ValueError, match="cannot contain semantic outputs"):
        workflow.submit(
            started.progress,
            smuggled,
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="external",
        )


def test_apply_command_and_result_codecs_reject_every_malformed_envelope(
    improvement,
    context: ComparisonContext,
) -> None:
    request = application_request(improvement)
    action = make_apply_action(request)
    command = application_command_from_action(action)
    produced = stale(context.baseline_snapshot)
    success = make_application_success(action=action, produced_snapshot=produced)
    failure = RuntimeFailure(classification="execution", message="failed")

    with pytest.raises(ValueError, match="enabled"):
        make_apply_action(application_request(improvement, apply=False))
    with pytest.raises((TypeError, ValueError)):
        make_apply_action("request")  # type: ignore[arg-type]
    for malformed, error in (
        ("action", TypeError),
        (replace(action, kind="inspect"), ValueError),
        (replace(action, payload={"extra": 1}), ValueError),
        (replace(action, payload={"command": 1}), TypeError),
        (
            replace(action, payload={"command": context.baseline_snapshot.to_dict()}),
            TypeError,
        ),
        (replace(action, action_id="wrong"), ValueError),
    ):
        with pytest.raises(error):
            application_command_from_action(malformed)  # type: ignore[arg-type]

    for malformed, error in (
        ("result", TypeError),
        (
            make_application_failure(action=action, failure=failure),
            ValueError,
        ),
        (replace(success, payload={"extra": 1}), ValueError),
        (replace(success, payload={"receipt": 1}), TypeError),
        (
            replace(success, payload={"receipt": context.baseline_snapshot.to_dict()}),
            ValueError,
        ),
        (
            replace(success, output_refs=(application_receipt_from_result(success).ref,)),
            ValueError,
        ),
    ):
        with pytest.raises(error):
            application_receipt_from_result(malformed)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="references"):
        replace(command, request=context.baseline_snapshot.ref)
    with pytest.raises(TypeError, match="CandidateSnapshot"):
        replace(command, candidate=context.baseline_snapshot)
    with pytest.raises(TypeError, match="prior TargetSnapshot"):
        replace(command, prior_snapshot="snapshot")
    with pytest.raises(ValueError, match="lineage"):
        replace(command, lineage=())


def test_verification_codecs_reject_wrong_types_payloads_and_correlations(
    rejected_result: ApplicationResult,
    context: ComparisonContext,
) -> None:
    application = rejected_result.application
    verification = rejected_result.verification
    assert application is not None
    assert verification is not None
    action = verification.action
    valid = rejected_result.settled_state.results[1]
    failure = RuntimeFailure(classification="execution", message="failed")

    with pytest.raises(TypeError, match="ApplicationReceipt"):
        make_verify_action("receipt")  # type: ignore[arg-type]
    for malformed, error in (
        ("action", TypeError),
        (replace(action, kind="inspect"), ValueError),
        (replace(action, payload={"extra": 1}), ValueError),
        (replace(action, payload={"application": 1}), TypeError),
        (
            replace(action, payload={"application": context.baseline_snapshot.to_dict()}),
            TypeError,
        ),
        (replace(action, action_id="wrong"), ValueError),
    ):
        with pytest.raises(error):
            verification_input_from_action(malformed)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="CandidateTrialBatch"):
        make_verification_result(
            action=action,
            observed_snapshot=application.produced_snapshot,
        )
    with pytest.raises(TypeError, match="unexpected keyword"):
        make_verification_result(  # type: ignore[call-arg]
            action=action,
            observed_snapshot=application.produced_snapshot,
            verified=True,
        )
    assert verification.assessment is not None
    selected_assessment = next(
        item
        for item in rejected_result.request.handoff.selection.assessments
        if item.candidate_ref in rejected_result.request.handoff.selection.selected
    )
    with pytest.raises(ValueError, match="exact applied target"):
        make_verification_result(
            action=action,
            observed_snapshot=application.produced_snapshot,
            batch=selected_assessment.batch,
        )
    with pytest.raises(ValueError, match="cannot contain a trial batch"):
        make_verification_result(
            action=action,
            observed_snapshot=application.produced_snapshot,
            batch=verification.assessment.batch,
            operational_failure=failure,
        )
    for malformed, error in (
        ("result", TypeError),
        (make_application_failure(action=action, failure=failure), ValueError),
        (replace(valid, payload={"extra": 1}), ValueError),
        (replace(valid, payload={"verification": 1}), TypeError),
        (
            replace(valid, payload={"verification": context.baseline_snapshot.to_dict()}),
            ValueError,
        ),
        (replace(valid, output_refs=(verification.ref,)), ValueError),
    ):
        with pytest.raises(error):
            verification_from_result(malformed)  # type: ignore[arg-type]


def test_rollback_codecs_reject_wrong_types_payloads_and_restoration(
    rejected_result: ApplicationResult,
    verified_result: ApplicationResult,
    context: ComparisonContext,
) -> None:
    application = rejected_result.application
    verification = rejected_result.verification
    rollback = rejected_result.rollback
    assert application is not None
    assert verification is not None
    assert rollback is not None
    action = rollback.action
    valid = rejected_result.settled_state.results[2]
    failure = RuntimeFailure(classification="execution", message="failed")

    with pytest.raises(TypeError, match="ApplicationReceipt"):
        make_rollback_action("receipt", verification)  # type: ignore[arg-type]
    verified = verified_result.verification
    assert verified is not None
    with pytest.raises(ValueError, match="nonverified"):
        make_rollback_action(application, verified)
    for malformed, error in (
        ("action", TypeError),
        (replace(action, kind="inspect"), ValueError),
        (replace(action, payload={"extra": 1}), ValueError),
        (replace(action, payload={"verification": 1}), TypeError),
        (
            replace(action, payload={"verification": context.baseline_snapshot.to_dict()}),
            TypeError,
        ),
        (replace(action, action_id="wrong"), ValueError),
    ):
        with pytest.raises(error):
            rollback_input_from_action(malformed)  # type: ignore[arg-type]

    for malformed, error in (
        ("result", TypeError),
        (make_application_failure(action=action, failure=failure), ValueError),
        (replace(valid, payload={"extra": 1}), ValueError),
        (replace(valid, payload={"rollback": 1}), TypeError),
        (
            replace(valid, payload={"rollback": context.baseline_snapshot.to_dict()}),
            ValueError,
        ),
        (replace(valid, output_refs=(rollback.ref,)), ValueError),
    ):
        with pytest.raises(error):
            rollback_receipt_from_result(malformed)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact prior"):
        make_rollback_success(
            action=action,
            restored_snapshot=stale(context.baseline_snapshot),
        )


def test_application_records_reject_noncanonical_direct_construction(
    rejected_result: ApplicationResult,
    context: ComparisonContext,
) -> None:
    application = rejected_result.application
    verification = rejected_result.verification
    rollback = rejected_result.rollback
    assert application is not None
    assert verification is not None
    assert rollback is not None
    failure = RuntimeFailure(classification="execution", message="failed")

    for mutation, pattern in (
        ({"request": context.baseline_snapshot.ref}, "ApplicationRequest reference"),
        (
            {
                "produced_snapshot": comparison_context(
                    target_kind="software-repository"
                ).baseline_snapshot
            },
            "another target",
        ),
        ({"lineage": ()}, "lineage"),
    ):
        with pytest.raises((TypeError, ValueError), match=pattern):
            replace(application, **mutation)

    for mutation, pattern in (
        ({"request": context.baseline_snapshot.ref}, "ApplicationRequest reference"),
        ({"observed_snapshot": stale(application.produced_snapshot)}, "exact produced"),
        ({"disposition": "unknown"}, "unsupported"),
        ({"disposition": "unavailable"}, "assessment-derived"),
        ({"assessment": None}, "requires a candidate assessment"),
        ({"operational_failure": failure}, "cannot contain an assessment"),
        ({"reason": "forged"}, "reason is not assessment-derived"),
        ({"lineage": ()}, "lineage"),
    ):
        with pytest.raises((TypeError, ValueError), match=pattern):
            replace(verification, **mutation)

    for mutation, pattern in (
        ({"request": context.baseline_snapshot.ref}, "ApplicationRequest reference"),
        ({"restored_snapshot": stale(context.baseline_snapshot)}, "exact prior"),
        ({"lineage": ()}, "lineage"),
    ):
        with pytest.raises((TypeError, ValueError), match=pattern):
            replace(rollback, **mutation)

    for mutation, pattern in (
        ({"request": "request"}, "ApplicationRequest"),
        ({"disposition": "unknown"}, "unsupported"),
        ({"settled_state": "state"}, "RunState"),
        ({"operational_failures": "failure"}, "sequence"),
        ({"operational_failures": (failure, failure)}, "unique"),
        ({"operational_failures": (context.baseline_snapshot,)}, "RuntimeFailure"),
        ({"lineage": ()}, "lineage"),
    ):
        with pytest.raises((TypeError, ValueError), match=pattern):
            replace(rejected_result, **mutation)


def test_failure_and_validator_guards_are_fail_closed(
    improvement,
    context: ComparisonContext,
) -> None:
    request = application_request(improvement)
    workflow = ApplicationWorkflow(
        application_registry(
            DeterministicApplicationTarget(context.baseline_snapshot),
            apply_posture="external",
        )
    )
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    failure = RuntimeFailure(classification="execution", message="failed")
    valid = make_application_failure(action=action, failure=failure)
    validator = ApplicationActionResultValidator()

    with pytest.raises(ValueError, match="lifecycle action"):
        make_application_failure(action=replace(action, kind="inspect"), failure=failure)
    with pytest.raises(TypeError, match="RuntimeFailure"):
        make_application_failure(action=action, failure="failure")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RunState"):
        validator.validate("state", valid)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ActionResult"):
        validator.validate(started.progress.state, "result")  # type: ignore[arg-type]

    another = replace(request, application_id="another-application")
    other_state = (
        ApplicationWorkflow()
        .start(
            another,
            current_snapshot=context.baseline_snapshot,
        )
        .progress.state
    )
    with pytest.raises(ValueError, match="pending action"):
        validator.validate(other_state, valid)

    unknown = replace(action, kind="unknown-application-action")
    active = RuntimeEngine.start(request.canonical_run()).state
    waiting = RuntimeEngine.request(active, unknown).state
    unknown_result = ActionResult(
        action=unknown,
        disposition="failed",
        failure=failure,
    )
    with pytest.raises(ValueError, match="lifecycle action"):
        validator.validate(waiting, unknown_result)


def test_workflow_public_guards_reject_bad_host_inputs(
    improvement,
    context: ComparisonContext,
) -> None:
    with pytest.raises(TypeError, match="CapabilityRegistry"):
        ApplicationWorkflow("registry")  # type: ignore[arg-type]
    workflow = ApplicationWorkflow(application_registry(None))
    request = application_request(improvement)
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)

    with pytest.raises(TypeError, match="ApplicationProgress"):
        workflow.submit(  # type: ignore[arg-type]
            "progress",
            "result",
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="external",
        )
    with pytest.raises(ValueError, match="exact pending action"):
        workflow.submit(
            started.progress,
            "result",  # type: ignore[arg-type]
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="external",
        )
    failure = RuntimeFailure(classification="execution", message="failed")
    result = make_application_failure(
        action=started.progress.state.pending_actions[0],
        failure=failure,
    )
    with pytest.raises(Exception, match="unavailable application capabilities"):
        workflow.submit(
            started.progress,
            result,
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="external",
        )


def test_request_policy_and_remaining_record_guards_are_explicit(
    improvement,
    rejected_result: ApplicationResult,
    verified_result: ApplicationResult,
    context: ComparisonContext,
) -> None:
    from librsi.application.replay import ApplicationProjection

    request = application_request(improvement)
    disabled = application_request(improvement, apply=False)
    application = rejected_result.application
    verification = rejected_result.verification
    rollback = rejected_result.rollback
    assert application is not None
    assert verification is not None
    assert rollback is not None

    assert disabled.candidate is not None
    with pytest.raises(ValueError, match="explicit handoff"):
        ApplicationRequest.create(
            application_id="bad",
            improvement="improvement",  # type: ignore[arg-type]
            current_snapshot=context.baseline_snapshot,
        )
    for mutation, pattern in (
        ({"application_id": 1}, "must be text"),
        ({"application_id": " "}, "required"),
        ({"improvement": "improvement"}, "ImprovementResult"),
        ({"current_snapshot": "snapshot"}, "TargetSnapshot"),
        ({"current_snapshot": stale(context.baseline_snapshot)}, "stale"),
        ({"apply": 1}, "boolean"),
        ({"lineage": ()}, "lineage"),
    ):
        with pytest.raises((TypeError, ValueError), match=pattern):
            replace(request, **mutation)

    with pytest.raises(ValueError, match="enabled"):
        ApplicationCommand.from_request(disabled)
    with pytest.raises(ValueError, match="enabled"):
        ApplicationCommand.from_request("request")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="produced TargetSnapshot"):
        replace(application, produced_snapshot="snapshot")
    with pytest.raises(ValueError, match="exact command"):
        replace(application, prior_snapshot=stale(application.prior_snapshot))

    with pytest.raises(ValueError, match="exact application receipt"):
        replace(verification, application="receipt")
    with pytest.raises(ValueError, match="required"):
        replace(verification, reason=" ")
    with pytest.raises(ValueError, match="canonical verify action"):
        replace(verification, action=replace(verification.action, action_id="wrong"))

    verified = verified_result.verification
    assert verified is not None
    with pytest.raises(ValueError, match="exact application receipt"):
        replace(rollback, application="receipt")
    with pytest.raises(ValueError, match="nonverified"):
        replace(rollback, verification=verified)
    with pytest.raises(ValueError, match="canonical rollback action"):
        replace(rollback, action=replace(rollback.action, action_id="wrong"))
    with pytest.raises(ValueError, match="handoff differs"):
        replace(rejected_result, handoff="handoff")

    with pytest.raises(TypeError, match="ApplicationRequest"):
        ApplicationPolicy.validate_request("request")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="explicit current snapshot"):
        ApplicationPolicy.require_current(
            request,
            ApplicationProjection(),
            "snapshot",  # type: ignore[arg-type]
        )
    other_target = comparison_context(target_kind="software-repository").baseline_snapshot
    with pytest.raises(ValueError, match="another target"):
        ApplicationPolicy.require_current(request, ApplicationProjection(), other_target)
