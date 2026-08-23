from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar

import pytest

from librsi import (
    ActionResult,
    ApplicationGovernanceAuthority,
    CandidateReview,
    CandidateTrialBatch,
    RiskPolicy,
    RSIProgress,
    RSIRequest,
    RSIResult,
    RSITransitionError,
    RSIWorkflow,
    RuntimeFailure,
    SelectorPolicy,
    SelfChangeGovernancePolicy,
    SelfChangeRule,
    deserialize_record,
    evaluation_command_from_action,
    evaluation_from_result,
    make_evaluation_result,
    make_review_result,
    make_self_change_failure,
    recurse,
    review_command_from_action,
    serialize_record,
)
from tests.block14_support import ComparisonContext, comparison_context
from tests.block16_support import DeterministicApplicationTarget
from tests.block17_support import (
    DeterministicGovernanceProvider,
    self_change_registry,
    self_change_request,
)


@dataclass(frozen=True, kw_only=True)
class ForgedSelfChangeApproval(ApplicationGovernanceAuthority):
    """Adversarial unregistered authority with the canonical record-type string."""

    RECORD_TYPE: ClassVar[str] = "self_change_approval"


@dataclass(frozen=True, kw_only=True, eq=False)
class EqualitySpoofSelfChangeApproval(ApplicationGovernanceAuthority):
    """Adversarial authority that also claims equality with every object."""

    RECORD_TYPE: ClassVar[str] = "self_change_approval"

    def __eq__(self, other: object) -> bool:
        return True


@pytest.fixture(scope="module")
def context() -> ComparisonContext:
    return comparison_context(target_kind="improvement-policy-bundle")


@pytest.fixture(scope="module")
def disabled_request(context: ComparisonContext) -> RSIRequest:
    return self_change_request(context)


@pytest.fixture(scope="module")
def enabled_request(context: ComparisonContext) -> RSIRequest:
    return self_change_request(context, activate=True)


def test_explicit_meta_target_and_strict_policy_are_canonical(
    disabled_request: RSIRequest,
) -> None:
    assert disabled_request.declaration.change_classes == ("selection-policy",)
    assert disabled_request.governance.rules == tuple(
        sorted(disabled_request.governance.rules, key=lambda item: item.change_class)
    )
    assert disabled_request.governance.risk_policy.require_independent_review is False
    assert disabled_request.candidate.request.intervention.baseline == (
        disabled_request.declaration.target_snapshot
    )


def test_activation_disabled_runs_every_gate_without_target_effect(
    disabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    provider = DeterministicGovernanceProvider(context)
    target = DeterministicApplicationTarget(context.baseline_snapshot)

    result = recurse(
        disabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(provider, target),
    )

    assert isinstance(result, RSIResult)
    assert result.disposition == "activation-disabled"
    assert result.governance.disposition == "accepted"
    assert result.approval is None
    assert result.application is None
    assert result.authoritative_snapshot == context.baseline_snapshot
    assert [evaluation_command_from_action(item).stage for item in provider.experiment_actions] == [
        "historical",
        "forward-shadow",
    ]
    assert len(provider.review_actions) == 1
    assert target.apply_calls == []


def test_accepted_self_change_uses_approval_bound_ordinary_application(
    enabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    provider = DeterministicGovernanceProvider(context)
    target = DeterministicApplicationTarget(context.baseline_snapshot)

    result = recurse(
        enabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(provider, target),
    )

    assert isinstance(result, RSIResult)
    assert result.disposition == "verified"
    assert result.approval is not None
    assert result.approval.risk_tier == "critical"
    assert result.application is not None
    assert result.application.request.governance_authority == result.approval
    assert result.application.authoritative_snapshot == target.snapshot
    assert result.authoritative_snapshot == target.snapshot
    assert result.authoritative_snapshot != enabled_request.candidate.snapshot


def test_failed_post_activation_verification_rolls_back_exactly(
    enabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        verification="rejected",
    )
    result = recurse(
        enabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(DeterministicGovernanceProvider(context), target),
    )

    assert isinstance(result, RSIResult)
    assert result.disposition == "rolled-back"
    assert result.application is not None
    assert result.application.disposition == "rolled-back"
    assert result.authoritative_snapshot == context.baseline_snapshot
    assert target.snapshot == context.baseline_snapshot


def test_failed_rollback_never_claims_an_authoritative_state(
    enabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        verification="rejected",
        fail_rollback=True,
    )
    result = recurse(
        enabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(DeterministicGovernanceProvider(context), target),
    )

    assert isinstance(result, RSIResult)
    assert result.disposition == "rollback-failed"
    assert result.authoritative_snapshot is None
    assert result.operational_failures[-1].message == "synthetic rollback failed"


def test_application_failure_remains_operational_not_counterevidence(
    enabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        fail_application=True,
    )
    result = recurse(
        enabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(DeterministicGovernanceProvider(context), target),
    )

    assert isinstance(result, RSIResult)
    assert result.disposition == "application-failed"
    assert result.governance.disposition == "accepted"
    assert result.authoritative_snapshot == context.baseline_snapshot
    assert result.operational_failures[-1].message == "synthetic application failed"


@pytest.mark.parametrize(
    ("historical", "forward", "review", "experiment_count", "review_count"),
    [
        ("rejected", "passed", "accepted", 1, 0),
        ("inconclusive", "passed", "accepted", 1, 0),
        ("passed", "rejected", "accepted", 2, 0),
        ("passed", "inconclusive", "accepted", 2, 0),
        ("passed", "passed", "rejected", 2, 1),
    ],
)
def test_each_nonpassing_gate_rejects_without_activation(
    disabled_request: RSIRequest,
    context: ComparisonContext,
    historical: str,
    forward: str,
    review: str,
    experiment_count: int,
    review_count: int,
) -> None:
    provider = DeterministicGovernanceProvider(
        context,
        historical=historical,
        forward_shadow=forward,
        review=review,
    )
    target = DeterministicApplicationTarget(context.baseline_snapshot)

    result = recurse(
        disabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(provider, target),
    )

    assert isinstance(result, RSIResult)
    assert result.disposition == "governance-rejected"
    assert len(provider.experiment_actions) == experiment_count
    assert len(provider.review_actions) == review_count
    assert target.apply_calls == []


def test_irreversible_change_cannot_enter_activation_workflow(
    context: ComparisonContext,
) -> None:
    request = self_change_request(context, activate=True, rollback_supported=False)
    workflow = RSIWorkflow(self_change_registry(DeterministicGovernanceProvider(context)))

    with pytest.raises(ValueError, match="rollback support"):
        workflow.start(request, current_snapshot=context.baseline_snapshot)


def test_unconfigured_self_change_class_fails_closed(
    disabled_request: RSIRequest,
) -> None:
    rule = SelfChangeRule(change_class="reasoner", risk_tier="moderate")
    risk = RiskPolicy(policy_id="narrow-governance", confidence_multiplier=1.0)
    policy = SelfChangeGovernancePolicy(
        policy_id="reasoner-only",
        rules=(rule,),
        risk_policy=risk,
        lineage=(rule.ref, risk.ref),
    )

    with pytest.raises(ValueError, match="not governed"):
        RSIRequest.create(
            rsi_id="ungoverned-selection",
            declaration=disabled_request.declaration,
            improvement=disabled_request.improvement,
            governance=policy,
            requested_by="owner",
        )


def test_stale_meta_target_rejects_start_and_submission(
    disabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    workflow = RSIWorkflow(
        self_change_registry(
            DeterministicGovernanceProvider(context),
            governance_posture="external",
        )
    )
    stale = replace(
        context.baseline_snapshot,
        state={**context.baseline_snapshot.state, "concurrent": True},
    )
    with pytest.raises(ValueError, match="stale"):
        workflow.start(disabled_request, current_snapshot=stale)

    update = workflow.start(disabled_request, current_snapshot=context.baseline_snapshot)
    action = update.progress.state.pending_actions[0]
    result = DeterministicGovernanceProvider(context).experiment(action)
    with pytest.raises(ValueError, match="stale"):
        workflow.submit(
            update.progress,
            result,
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=stale,
            authority="external",
        )


def test_host_boolean_cannot_authorize_a_gate(
    disabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    workflow = RSIWorkflow(
        self_change_registry(
            DeterministicGovernanceProvider(context),
            governance_posture="external",
        )
    )
    update = workflow.start(disabled_request, current_snapshot=context.baseline_snapshot)
    action = update.progress.state.pending_actions[0]
    forged = ActionResult(
        action=action,
        disposition="succeeded",
        payload={"passed": True},
    )

    with pytest.raises(ValueError, match="only its evaluation"):
        workflow.submit(
            update.progress,
            forged,
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="external",
        )


def test_same_actor_review_is_rejected_before_runtime_transition(
    disabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    provider = DeterministicGovernanceProvider(
        context,
        reviewer_id=disabled_request.declaration.candidate_author_id,
    )
    workflow = RSIWorkflow(self_change_registry(provider, governance_posture="external"))
    progress = workflow.start(
        disabled_request,
        current_snapshot=context.baseline_snapshot,
    ).progress
    for _ in range(2):
        action = progress.state.pending_actions[0]
        update = workflow.submit(
            progress,
            provider.experiment(action),
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="external",
        )
        progress = update.progress
    action = progress.state.pending_actions[0]
    command = review_command_from_action(action)
    review = CandidateReview(
        review_id="self-review",
        reviewer_id=command.candidate_author_id,
        candidate=command.candidate,
        experiment=command.experiment,
        evaluation=command.evaluation,
        disposition="accepted",
        findings=("I approve my own candidate",),
        lineage=(command.candidate.ref, command.experiment.ref, command.evaluation.ref),
    )

    with pytest.raises(RSITransitionError, match="cannot independently review"):
        make_review_result(action=action, review=review)


def test_historical_batch_cannot_be_reused_as_forward_shadow(
    disabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    provider = DeterministicGovernanceProvider(context)
    workflow = RSIWorkflow(self_change_registry(provider, governance_posture="external"))
    first = workflow.start(
        disabled_request,
        current_snapshot=context.baseline_snapshot,
    ).progress
    historical_result = provider.experiment(first.state.pending_actions[0])
    second = workflow.submit(
        first,
        historical_result,
        prior_snapshot=context.baseline_snapshot,
        current_snapshot=context.baseline_snapshot,
        authority="external",
    ).progress
    historical_batch = evaluation_from_result(historical_result).batch
    assert isinstance(historical_batch, CandidateTrialBatch)
    action = second.state.pending_actions[0]
    assert evaluation_command_from_action(action).stage == "forward-shadow"
    reused = make_evaluation_result(action=action, batch=historical_batch)

    with pytest.raises(ValueError, match="must be distinct"):
        workflow.submit(
            second,
            reused,
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="external",
        )


def test_governance_infrastructure_failure_is_not_counterevidence(
    disabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    workflow = RSIWorkflow(
        self_change_registry(
            DeterministicGovernanceProvider(context),
            governance_posture="external",
        )
    )
    first = workflow.start(disabled_request, current_snapshot=context.baseline_snapshot)
    failure = RuntimeFailure(
        classification="execution",
        message="historical fixture unavailable",
    )
    result = make_self_change_failure(
        action=first.progress.state.pending_actions[0],
        failure=failure,
    )
    update = workflow.submit(
        first.progress,
        result,
        prior_snapshot=context.baseline_snapshot,
        current_snapshot=context.baseline_snapshot,
        authority="external",
    )

    assert update.progress.result is not None
    assert update.progress.result.disposition == "governance-failed"
    assert update.progress.result.governance.historical is None
    assert update.progress.result.operational_failures == (failure,)


def test_terminal_result_substitution_and_missing_result_fail_closed(
    disabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    result = recurse(
        disabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(DeterministicGovernanceProvider(context)),
    )
    assert isinstance(result, RSIResult)
    workflow = RSIWorkflow(self_change_registry(DeterministicGovernanceProvider(context)))
    terminal = workflow.run_managed(
        workflow.start(
            disabled_request,
            current_snapshot=context.baseline_snapshot,
        ).progress,
        current_snapshot=context.baseline_snapshot,
    ).progress
    assert terminal.result == result

    with pytest.raises(ValueError, match="terminal governance progress requires"):
        RSIProgress(
            request=terminal.request,
            governance_state=terminal.governance_state,
            projection=terminal.projection,
        )
    with pytest.raises(ValueError, match="terminal RSI governance requires RSIResult"):
        replace(terminal, result=None)
    with pytest.raises(ValueError, match="not the exact governance/application projection"):
        replace(terminal, result=replace(result, disposition="governance-rejected"))


def test_accepted_activation_cannot_drop_application_progress(
    enabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    workflow = RSIWorkflow(
        self_change_registry(
            DeterministicGovernanceProvider(context),
            DeterministicApplicationTarget(context.baseline_snapshot),
        )
    )
    update = workflow.start(enabled_request, current_snapshot=context.baseline_snapshot)
    terminal = workflow.run_managed(
        update.progress,
        current_snapshot=context.baseline_snapshot,
    ).progress
    assert terminal.application_progress is not None

    with pytest.raises(ValueError, match="requires application progress"):
        replace(
            terminal,
            approval=None,
            application_progress=None,
            result=None,
        )


def test_external_and_managed_control_planes_produce_the_same_result(
    enabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    automatic = recurse(
        enabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(
            DeterministicGovernanceProvider(context),
            DeterministicApplicationTarget(context.baseline_snapshot),
        ),
    )
    assert isinstance(automatic, RSIResult)

    provider = DeterministicGovernanceProvider(context)
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    workflow = RSIWorkflow(
        self_change_registry(
            provider,
            target,
            governance_posture="external",
            application_posture="external",
        )
    )
    progress = workflow.start(
        enabled_request,
        current_snapshot=context.baseline_snapshot,
    ).progress
    observed = context.baseline_snapshot
    while not progress.terminal:
        action = progress.state.pending_actions[0]
        prior = observed
        if action.kind in {
            "evaluate-self-change-history",
            "evaluate-self-change-shadow",
        }:
            action_result = provider.experiment(action)
        elif action.kind == "review-self-change":
            action_result = provider.review(action)
        elif action.kind in {"apply-selected-candidate", "rollback-applied-target"}:
            action_result = target.apply(action)
            observed = target.snapshot
        else:
            action_result = target.verify(action)
        progress = workflow.submit(
            progress,
            action_result,
            prior_snapshot=prior,
            current_snapshot=observed,
            authority="external",
        ).progress

    assert progress.result == automatic


def test_records_round_trip_and_legacy_selector_guarantees_survive(
    disabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    result = recurse(
        disabled_request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(DeterministicGovernanceProvider(context)),
    )
    assert isinstance(result, RSIResult)
    assert deserialize_record(serialize_record(disabled_request)) == disabled_request
    assert deserialize_record(serialize_record(result)) == result

    SelectorPolicy.require_activation(
        historical_status="passed",
        forward_status="passed",
        review_status="accepted",
    )
    with pytest.raises(RSITransitionError, match="historical"):
        SelectorPolicy.require_activation(
            historical_status="failed",
            forward_status="passed",
            review_status="accepted",
        )
    with pytest.raises(ValueError, match="requires evidence"):
        SelectorPolicy.require_rollback(status="active", evidence_ids=())


def test_classified_application_requires_approval_before_provider_effects(
    enabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    from librsi import apply_improvement

    target = DeterministicApplicationTarget(context.baseline_snapshot)
    with pytest.raises(ValueError, match="matching governance authority"):
        apply_improvement(
            improvement=enabled_request.improvement,
            current_snapshot=enabled_request.declaration.target_snapshot,
            apply=True,
            registry=self_change_registry(None, target),
            application_id="bypass-attempt",
        )
    assert target.apply_calls == []
    assert target.snapshot == context.baseline_snapshot


def test_unregistered_and_equality_spoofed_approvals_fail_before_effects(
    enabled_request: RSIRequest,
    context: ComparisonContext,
) -> None:
    from librsi import ApplicationRequest, ApplicationWorkflow, apply_improvement

    requirement = enabled_request.improvement.request.governance_requirement
    assert requirement is not None
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    lineage = (
        requirement.ref,
        enabled_request.candidate.ref,
        context.baseline_snapshot.ref,
    )
    authorities = (
        ForgedSelfChangeApproval(
            requirement=requirement,
            candidate=enabled_request.candidate,
            current_snapshot=context.baseline_snapshot,
            lineage=lineage,
        ),
        EqualitySpoofSelfChangeApproval(
            requirement=requirement,
            candidate=enabled_request.candidate,
            current_snapshot=context.baseline_snapshot,
            lineage=lineage,
        ),
    )
    for authority in authorities:
        with pytest.raises(ValueError, match="not a canonical record"):
            apply_improvement(
                improvement=enabled_request.improvement,
                current_snapshot=context.baseline_snapshot,
                apply=True,
                governance_authority=authority,
                registry=self_change_registry(None, target),
                application_id="forged-authority",
            )
        with pytest.raises((TypeError, ValueError)):
            deserialize_record(serialize_record(authority))
    assert target.apply_calls == []
    assert target.snapshot == context.baseline_snapshot

    disabled = ApplicationRequest.create(
        application_id="effect-free-inspection",
        improvement=enabled_request.improvement,
        current_snapshot=enabled_request.declaration.target_snapshot,
        apply=False,
    )
    progress = (
        ApplicationWorkflow(self_change_registry(None, target))
        .start(
            disabled,
            current_snapshot=context.baseline_snapshot,
        )
        .progress
    )
    assert progress.result is not None
    assert progress.result.disposition == "application-disabled"
    assert target.apply_calls == []
    assert target.snapshot == context.baseline_snapshot
