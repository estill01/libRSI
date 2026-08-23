from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    HISTORICAL_EVALUATION_ACTION_KIND,
    ActionResult,
    CapabilityRegistry,
    CapabilityRoute,
    DispatchPlan,
    MetaTargetDeclaration,
    RecordRef,
    RSIProgress,
    RSIResult,
    RSIUpdate,
    RSIWorkflow,
    Run,
    RuntimeEngine,
    RuntimeFailure,
    SelfChangeActionResultValidator,
    SelfChangeGovernancePolicy,
    SelfChangePolicy,
    SelfChangeProjection,
    evaluation_command_from_action,
    evaluation_from_result,
    governance_disposition,
    governance_projection_fields,
    make_evaluation_action,
    make_evaluation_result,
    make_review_action,
    make_review_result,
    make_self_change_failure,
    recurse,
    replay_governance_state,
    review_command_from_action,
    review_from_result,
)
from tests.block14_support import ComparisonContext, comparison_context
from tests.block16_support import DeterministicApplicationTarget
from tests.block17_support import (
    DeterministicGovernanceProvider,
    self_change_registry,
    self_change_request,
)


@pytest.fixture(scope="module")
def context() -> ComparisonContext:
    return comparison_context(target_kind="governance-validation-target")


@pytest.fixture(scope="module")
def bundle(context: ComparisonContext):
    request = self_change_request(context)
    result = recurse(
        request,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(DeterministicGovernanceProvider(context)),
    )
    assert isinstance(result, RSIResult)
    governance = result.governance
    assert governance.historical and governance.forward_shadow and governance.independent_review
    return request, result, governance


def test_rule_and_policy_validation_edges(bundle) -> None:
    request, _, _ = bundle
    rule = request.governance.rules[0]
    for rule_changes, message in (
        ({"change_class": 1}, "must be text"),
        ({"change_class": "unknown"}, "unsupported self-change class"),
        ({"risk_tier": 1}, "must be text"),
        ({"risk_tier": "extreme"}, "unsupported self-change risk tier"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            replace(rule, **rule_changes)

    risk = request.governance.risk_policy
    first, second = request.governance.rules[:2]
    cases = (
        ({"rules": ()}, "typed class rules"),
        ({"rules": (object(),)}, "typed class rules"),
        ({"rules": (first, first)}, "unique classes"),
        ({"rules": (second, first)}, "canonical class order"),
        ({"risk_policy": object()}, "exact RiskPolicy"),
        ({"lineage": ()}, "lineage is incomplete"),
    )
    for policy_changes, message in cases:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(request.governance, **policy_changes)
    assert SelfChangeGovernancePolicy.strict(risk_policy=risk).risk_policy == risk


def test_meta_target_validation_edges(bundle, context: ComparisonContext) -> None:
    request, _, _ = bundle
    declaration = request.declaration
    other = replace(context.baseline_snapshot, revision="other")
    cases = (
        ({"declaration_id": 1}, "must be text"),
        ({"target_snapshot": object()}, "exact TargetSnapshot"),
        ({"change_classes": ()}, "supported self-change classes"),
        ({"change_classes": ("selection-policy", "selection-policy")}, "unique"),
        ({"change_classes": ("selection-policy", "reasoner")}, "canonical order"),
        ({"candidate_author_id": ""}, "required"),
        ({"rollback_snapshot": other}, "exact declared baseline"),
        ({"lineage": ()}, "lineage is incomplete"),
    )
    for changes, message in cases:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(declaration, **changes)
    with pytest.raises(TypeError, match="rollback support"):
        MetaTargetDeclaration.create(
            declaration_id="bad",
            target_snapshot=context.baseline_snapshot,
            change_classes=("reasoner",),
            candidate_author_id="author",
            rollback_supported=1,  # type: ignore[arg-type]
        )


def test_rsi_request_validation_edges(bundle) -> None:
    request, _, _ = bundle
    other_snapshot = replace(request.declaration.target_snapshot, revision="other")
    other_declaration = MetaTargetDeclaration.create(
        declaration_id="other",
        target_snapshot=other_snapshot,
        change_classes=request.declaration.change_classes,
        candidate_author_id=request.declaration.candidate_author_id,
    )
    cases = (
        ({"rsi_id": 1}, "must be text"),
        ({"declaration": object()}, "MetaTargetDeclaration"),
        ({"governance": object()}, "SelfChangeGovernancePolicy"),
        ({"requested_by": ""}, "required"),
        ({"activate": 1}, "must be a boolean"),
        ({"lineage": ()}, "lineage is incomplete"),
        ({"declaration": other_declaration}, "does not match the improvement baseline"),
    )
    for changes, message in cases:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(request, **changes)


def test_evaluation_command_and_record_validation_edges(bundle) -> None:
    request, _, governance = bundle
    historical = governance.historical
    assert historical is not None
    command = evaluation_command_from_action(historical.action)
    wrong_ref = RecordRef("candidate_review", "0" * 64)
    wrong_snapshot = replace(command.baseline, revision="wrong")
    cases = (
        ({"request": wrong_ref}, "RSIRequest reference"),
        ({"stage": "unknown"}, "unsupported self-change evaluation stage"),
        ({"contract": object()}, "EvaluationContract"),
        ({"risk_policy": object()}, "RiskPolicy"),
        ({"candidate": object()}, "CandidateSnapshot"),
        ({"baseline": object()}, "exact baseline"),
        ({"predecessor": historical.ref}, "cannot have a predecessor"),
        ({"baseline": wrong_snapshot}, "exact baseline"),
        ({"lineage": ()}, "lineage is incomplete"),
    )
    for command_changes, message in cases:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(command, **command_changes)

    for evaluation_changes, message in (
        ({"request": wrong_ref}, "exact command"),
        ({"stage": "forward-shadow"}, "exact command"),
        ({"batch": object()}, "CandidateTrialBatch"),
        ({"assessment": object()}, "not contract-derived"),
        (
            {"disposition": "passed" if historical.disposition != "passed" else "rejected"},
            "assessment-derived",
        ),
        ({"reason": "host says yes"}, "assessment-derived"),
        ({"lineage": ()}, "lineage is incomplete"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            replace(historical, **evaluation_changes)


def test_review_command_and_record_validation_edges(bundle) -> None:
    request, _, governance = bundle
    forward = governance.forward_shadow
    report = governance.independent_review
    assert forward is not None and report is not None
    command = review_command_from_action(report.action)
    wrong_ref = RecordRef("candidate_review", "0" * 64)
    cases = (
        ({"request": wrong_ref}, "RSIRequest reference"),
        ({"forward_evaluation": wrong_ref}, "forward evaluation reference"),
        ({"candidate": object()}, "CandidateSnapshot"),
        ({"experiment": object()}, "experiment and evaluation"),
        ({"evaluation": object()}, "experiment and evaluation"),
        ({"candidate_author_id": ""}, "required"),
        ({"lineage": ()}, "lineage is incomplete"),
    )
    for changes, message in cases:
        with pytest.raises((TypeError, ValueError), match=message):
            replace(command, **changes)

    for review_changes, message in (
        ({"request": wrong_ref}, "exact command"),
        ({"forward_evaluation": wrong_ref}, "exact command"),
        ({"review": object()}, "exact command"),
        ({"disposition": "rejected"}, "reviewer-derived"),
        ({"reason": "narration"}, "reviewer-derived"),
        ({"lineage": ()}, "lineage is incomplete"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            replace(report, **review_changes)

    assert make_review_action(request, forward) == report.action


def test_action_codec_validation_edges(bundle) -> None:
    request, _, governance = bundle
    historical = governance.historical
    forward = governance.forward_shadow
    report = governance.independent_review
    assert historical and forward and report
    action = historical.action
    for value, message in (
        (object(), "requires an Action"),
        (replace(action, kind="wrong"), "not a self-change evaluation"),
        (replace(action, payload={}), "only its command"),
        (replace(action, payload={"command": "bad"}), "must be a mapping"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            evaluation_command_from_action(value)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="CandidateTrialBatch"):
        make_evaluation_result(action=action, batch=object())  # type: ignore[arg-type]

    succeeded = ActionResult(action=action, disposition="succeeded", payload={})
    with pytest.raises(ValueError, match="only its evaluation"):
        evaluation_from_result(succeeded)
    with pytest.raises(ValueError, match="no epistemic gate"):
        evaluation_from_result(
            make_self_change_failure(
                action=action,
                failure=RuntimeFailure(classification="execution", message="failed"),
            )
        )
    with pytest.raises(ValueError, match="not a self-change governance action"):
        make_self_change_failure(
            action=replace(action, kind="other"),
            failure=RuntimeFailure(classification="execution", message="failed"),
        )

    review_action = report.action
    for value, message in (
        (object(), "requires an Action"),
        (replace(review_action, kind="wrong"), "not a self-change independent review"),
        (replace(review_action, payload={}), "only its command"),
        (replace(review_action, payload={"command": "bad"}), "must be a mapping"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            review_command_from_action(value)  # type: ignore[arg-type]
    wrong_review = replace(report.review, candidate=request.candidate)
    assert wrong_review.candidate == request.candidate
    failed_review = ActionResult(action=review_action, disposition="succeeded", payload={})
    with pytest.raises(ValueError, match="only its exact review"):
        review_from_result(failed_review)


def test_validator_policy_and_replay_edges(bundle, context: ComparisonContext) -> None:
    request, _, governance = bundle
    historical = governance.historical
    assert historical is not None
    validator = SelfChangeActionResultValidator()
    waiting = RuntimeEngine.request(
        RuntimeEngine.start(request.canonical_run()).state,
        historical.action,
    ).state
    result = make_evaluation_result(action=historical.action, batch=historical.batch)
    with pytest.raises(TypeError, match="exact runtime records"):
        validator.validate(object(), result)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="pending action"):
        validator.validate(RuntimeEngine.start(request.canonical_run()).state, result)
    failed_with_output = replace(
        make_self_change_failure(
            action=historical.action,
            failure=RuntimeFailure(classification="execution", message="failed"),
        ),
        output_refs=(historical.ref,),
    )
    with pytest.raises(ValueError, match="cannot contain"):
        validator.validate(waiting, failed_with_output)

    with pytest.raises(TypeError, match="requires an RSIRequest"):
        SelfChangePolicy.validate_request(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="explicit current snapshot"):
        SelfChangePolicy.require_current(request, object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stale"):
        SelfChangePolicy.require_current(
            request,
            replace(context.baseline_snapshot, revision="stale"),
        )
    with pytest.raises(ValueError, match="activation-disabled"):
        SelfChangePolicy.approval(request, governance)


def test_governance_approval_and_result_validation_edges(
    bundle, context: ComparisonContext
) -> None:
    request, result, governance = bundle
    for governance_changes, message in (
        ({"request": object()}, "exact request and state"),
        ({"disposition": "rejected"}, "not runtime-derived"),
        ({"historical": None}, "not runtime-derived"),
        ({"operational_failures": (object(),)}, "RuntimeFailure"),
        ({"lineage": ()}, "lineage is incomplete"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            replace(governance, **governance_changes)

    enabled = self_change_request(context, activate=True)
    enabled_result = recurse(
        enabled,
        current_snapshot=context.baseline_snapshot,
        registry=self_change_registry(
            DeterministicGovernanceProvider(context),
            DeterministicApplicationTarget(context.baseline_snapshot),
        ),
    )
    assert isinstance(enabled_result, RSIResult) and enabled_result.approval
    approval = enabled_result.approval
    for approval_changes, message in (
        ({"request": request}, "activation-enabled"),
        ({"governance": governance}, "exact accepted governance"),
        (
            {
                "requirement": replace(
                    approval.requirement,
                    requirement_id="another-requirement",
                )
            },
            "another governance requirement",
        ),
        ({"candidate": object()}, "another candidate"),
        (
            {"current_snapshot": replace(context.baseline_snapshot, revision="stale")},
            "stale",
        ),
        (
            {"rollback_snapshot": replace(context.baseline_snapshot, revision="wrong")},
            "exact rollback",
        ),
        ({"risk_tier": "moderate"}, "policy-derived"),
        ({"lineage": ()}, "lineage is incomplete"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            replace(approval, **approval_changes)

    for result_changes, message in (
        ({"request": object()}, "require an RSIRequest"),
        ({"governance": object()}, "exact governance"),
        ({"disposition": "verified"}, "not the exact governance/application projection"),
        ({"operational_failures": (object(),)}, "RuntimeFailure"),
        ({"lineage": ()}, "lineage is incomplete"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            replace(result, **result_changes)


def test_workflow_and_progress_validation_edges(bundle, context: ComparisonContext) -> None:
    request, result, governance = bundle
    with pytest.raises(TypeError, match="CapabilityRegistry"):
        RSIWorkflow(object())  # type: ignore[arg-type]
    with pytest.raises(Exception, match="exact experimenter route"):
        RSIWorkflow(
            CapabilityRegistry(
                routes=(
                    CapabilityRoute(
                        HISTORICAL_EVALUATION_ACTION_KIND,
                        "reviewer",
                        "external",
                    ),
                )
            )
        )
    workflow = RSIWorkflow(CapabilityRegistry())
    update = workflow.start(request, current_snapshot=context.baseline_snapshot)
    assert update.plan.unavailable_actions == update.progress.state.pending_actions
    assert isinstance(recurse(request, current_snapshot=context.baseline_snapshot), object)

    with pytest.raises(TypeError, match="exact request and governance state"):
        RSIProgress(request=object(), governance_state=update.progress.governance_state)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not runtime-derived"):
        replace(update.progress, projection=SelfChangeProjection(historical=governance.historical))
    with pytest.raises(TypeError, match="exact progress and ActionResult"):
        workflow.submit(
            update.progress,
            object(),  # type: ignore[arg-type]
            prior_snapshot=context.baseline_snapshot,
            current_snapshot=context.baseline_snapshot,
            authority="external",
        )


def test_forward_and_review_construction_require_exact_predecessors(bundle) -> None:
    request, _, governance = bundle
    historical = governance.historical
    forward = governance.forward_shadow
    assert historical and forward
    with pytest.raises(ValueError, match="passed historical"):
        make_evaluation_action(request, stage="forward-shadow")
    with pytest.raises(ValueError, match="cannot cite a predecessor"):
        make_evaluation_action(request, stage="historical", historical=historical)
    with pytest.raises(ValueError, match="passed forward-shadow"):
        make_review_action(request, historical)

    forward_command = evaluation_command_from_action(forward.action)
    with pytest.raises(ValueError, match="historical evidence"):
        replace(forward_command, predecessor=None)


def test_remaining_codec_and_replay_fail_closed_edges(bundle) -> None:
    request, _, governance = bundle
    historical = governance.historical
    forward = governance.forward_shadow
    report = governance.independent_review
    assert historical and forward and report

    with pytest.raises(TypeError, match="require an RSIRequest"):
        make_evaluation_action(object(), stage="historical")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="wrong record type"):
        evaluation_command_from_action(
            replace(historical.action, payload={"command": request.to_dict()})
        )
    with pytest.raises(ValueError, match="not command-derived"):
        evaluation_command_from_action(replace(historical.action, action_id="altered-historical"))

    evaluation_result = make_evaluation_result(
        action=historical.action,
        batch=historical.batch,
    )
    with pytest.raises(TypeError, match="requires an ActionResult"):
        evaluation_from_result(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a mapping"):
        evaluation_from_result(replace(evaluation_result, payload={"evaluation": "bad"}))
    with pytest.raises(ValueError, match="does not answer"):
        evaluation_from_result(
            replace(evaluation_result, payload={"evaluation": request.to_dict()})
        )
    with pytest.raises(ValueError, match="outputs are not exact"):
        evaluation_from_result(replace(evaluation_result, output_refs=(historical.ref,)))

    with pytest.raises(TypeError, match="require an RSIRequest"):
        make_review_action(object(), forward)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="wrong record type"):
        review_command_from_action(replace(report.action, payload={"command": request.to_dict()}))
    with pytest.raises(ValueError, match="not command-derived"):
        review_command_from_action(replace(report.action, action_id="altered-review"))
    with pytest.raises(ValueError, match="exact command"):
        make_review_result(action=report.action, review=object())  # type: ignore[arg-type]

    review_result = make_review_result(action=report.action, review=report.review)
    with pytest.raises(TypeError, match="requires an ActionResult"):
        review_from_result(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no governance decision"):
        review_from_result(
            make_self_change_failure(
                action=report.action,
                failure=RuntimeFailure(classification="execution", message="failed"),
            )
        )
    with pytest.raises(TypeError, match="must be a mapping"):
        review_from_result(replace(review_result, payload={"review": "bad"}))
    with pytest.raises(ValueError, match="does not answer"):
        review_from_result(replace(review_result, payload={"review": request.to_dict()}))
    with pytest.raises(ValueError, match="outputs are not exact"):
        review_from_result(replace(review_result, output_refs=(report.ref,)))
    with pytest.raises(TypeError, match="RuntimeFailure"):
        make_self_change_failure(action=report.action, failure=object())  # type: ignore[arg-type]

    other_action = replace(historical.action, kind="unregistered-self-change-kind")
    other_state = RuntimeEngine.request(
        RuntimeEngine.start(request.canonical_run()).state,
        other_action,
    ).state
    other_result = ActionResult(
        action=other_action,
        disposition="failed",
        failure=RuntimeFailure(classification="execution", message="failed"),
    )
    with pytest.raises(ValueError, match="not a self-change governance action"):
        SelfChangeActionResultValidator().validate(other_state, other_result)

    with pytest.raises(ValueError, match="lacks historical"):
        governance_disposition(SelfChangeProjection())
    with pytest.raises(ValueError, match="lacks forward-shadow"):
        governance_disposition(SelfChangeProjection(historical=historical))
    with pytest.raises(ValueError, match="lacks independent review"):
        governance_disposition(SelfChangeProjection(historical=historical, forward_shadow=forward))
    with pytest.raises(TypeError, match="requires an RSIRequest"):
        replay_governance_state(object(), governance.settled_state)  # type: ignore[arg-type]
    foreign = RuntimeEngine.start(
        Run(
            run_id="foreign",
            intent=request.ref,
            target_snapshot=request.declaration.target_snapshot,
        )
    ).state
    with pytest.raises(ValueError, match="run envelope has drifted"):
        replay_governance_state(request, foreign)
    initial = RuntimeEngine.start(request.canonical_run()).state
    with pytest.raises(ValueError, match="terminal settled frontier"):
        governance_projection_fields(request, initial, SelfChangeProjection())


def test_update_and_application_policy_type_edges(bundle) -> None:
    request, _, governance = bundle
    workflow = RSIWorkflow(CapabilityRegistry())
    update = workflow.start(request, current_snapshot=request.declaration.target_snapshot)
    with pytest.raises(TypeError, match="require RSIProgress"):
        RSIUpdate(object(), (), update.plan)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Transition records"):
        RSIUpdate(update.progress, (object(),), update.plan)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact live state"):
        RSIUpdate(
            update.progress,
            (),
            DispatchPlan(
                state=RuntimeEngine.start(request.canonical_run()).state,
                resolutions=(),
            ),
        )
    with pytest.raises(TypeError, match="SelfChangeApproval"):
        SelfChangePolicy.application_request(
            object(),  # type: ignore[arg-type]
            current_snapshot=request.declaration.target_snapshot,
        )
    other = replace(request, requested_by="other", lineage=request.lineage)
    with pytest.raises(ValueError, match="belongs to another request"):
        SelfChangePolicy.result_fields(
            other,
            governance,
            approval=None,
            application=None,
        )
