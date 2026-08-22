from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Baseline,
    Constraint,
    EvaluationContract,
    Goal,
    Guardrail,
    Metric,
    Objective,
    OperationalizationPolicy,
    OperationalizationProposal,
    OperationalizationRequest,
    OperationalizationResult,
    OperationalizationWorkflow,
    RecordRef,
    RuntimeFailure,
    TargetRef,
    TargetSnapshot,
    make_operationalization_action,
    make_operationalization_failure,
    make_operationalization_result,
    operationalization_proposal_from_result,
    operationalization_request_from_action,
)
from tests.block13_support import intent_context


def test_baseline_rejects_wrong_shapes_and_identity_drift() -> None:
    context = intent_context()
    with pytest.raises(TypeError, match="TargetSnapshot"):
        Baseline(snapshot="snapshot", measurements={}, lineage=())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a mapping"):
        Baseline(snapshot=context.snapshot, measurements=(), lineage=(context.snapshot.ref,))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="metric id"):
        Baseline.create(snapshot=context.snapshot, measurements={" ": 1.0})
    with pytest.raises(TypeError, match="must be a number"):
        Baseline.create(snapshot=context.snapshot, measurements={"yield": True})
    with pytest.raises(ValueError, match="lineage"):
        replace(context.baseline, lineage=())


def test_objective_rejects_untyped_or_internally_conflicting_semantics() -> None:
    context = intent_context()
    metric = context.objective.metric
    with pytest.raises(TypeError, match="require a Metric"):
        replace(context.objective, metric="yield")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported objective"):
        replace(context.objective, semantics="improve")
    with pytest.raises(TypeError, match="source_goal"):
        replace(context.objective, source_goal=context.snapshot.ref)
    with pytest.raises(ValueError, match="nonnegative"):
        replace(context.objective, minimum_effect=-1.0)
    with pytest.raises(ValueError, match="Metric direction"):
        replace(context.objective, semantics="minimize")
    with pytest.raises(ValueError, match="target value"):
        Objective.create(
            objective_id="target",
            metric=Metric(metric_id="ph", direction="target"),
            semantics="target",
            goal=context.goal,
        )
    with pytest.raises(ValueError, match="minimum effect"):
        Objective.create(
            objective_id="target",
            metric=Metric(metric_id="ph", direction="target"),
            semantics="target",
            goal=context.goal,
            target_value=7.0,
            minimum_effect=0.1,
        )
    with pytest.raises(ValueError, match="do not accept target"):
        Objective.create(
            objective_id="max",
            metric=metric,
            semantics="maximize",
            goal=context.goal,
            target_value=80.0,
        )
    with pytest.raises(ValueError, match="lineage"):
        replace(context.objective, lineage=(context.goal.ref,))
    with pytest.raises(TypeError, match="requires a Goal"):
        Objective.create(
            objective_id="bad",
            metric=metric,
            semantics="maximize",
            goal=context.snapshot,  # type: ignore[arg-type]
        )


def test_guardrail_rejects_untyped_and_ambiguous_rules() -> None:
    context = intent_context()
    guardrail = context.guardrail
    with pytest.raises(TypeError, match="require a Metric"):
        replace(guardrail, metric="contamination")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="guardrail role"):
        replace(guardrail, metric=context.objective.metric)
    with pytest.raises(ValueError, match="unsupported guardrail"):
        replace(guardrail, semantics="prefer")
    with pytest.raises(TypeError, match="source_constraint"):
        replace(guardrail, source_constraint=context.goal.ref)
    with pytest.raises(ValueError, match="nonnegative"):
        replace(guardrail, allowed_regression=-0.1)
    with pytest.raises(ValueError, match="operator and threshold"):
        replace(guardrail, semantics="must-satisfy")
    with pytest.raises(ValueError, match="do not accept allowed"):
        replace(
            guardrail,
            semantics="must-satisfy",
            operator="<=",
            threshold=3.0,
            allowed_regression=0.5,
        )
    with pytest.raises(ValueError, match="increase/decrease"):
        replace(
            guardrail,
            metric=Metric(metric_id="contamination_ppm", direction="target", role="guardrail"),
        )
    with pytest.raises(ValueError, match="derive their bound"):
        replace(guardrail, operator="<=", threshold=3.0)
    with pytest.raises(ValueError, match="lineage"):
        replace(guardrail, lineage=(context.constraint.ref,))
    with pytest.raises(TypeError, match="requires a Constraint"):
        Guardrail.create(
            guardrail_id="bad",
            metric=guardrail.metric,
            semantics="no-regression",
            constraint=context.goal,  # type: ignore[arg-type]
        )


def test_contract_rejects_incomplete_rosters_and_cross_target_inputs() -> None:
    context = intent_context()
    other_target = TargetRef(target_id="other", kind="physical-process")
    other_snapshot = TargetSnapshot(target=other_target, revision="1", state={})
    other_baseline = Baseline.create(
        snapshot=other_snapshot,
        measurements={"yield_pct": 72.0, "contamination_ppm": 2.0},
    )
    with pytest.raises(ValueError, match="another goal target"):
        replace(
            context.contract,
            baseline=other_baseline,
            lineage=(
                context.goal.ref,
                other_baseline.ref,
                context.objective.ref,
                context.constraint.ref,
                context.guardrail.ref,
                context.stop.ref,
            ),
        )
    with pytest.raises(ValueError, match="at least one objective"):
        replace(context.contract, objectives=())
    with pytest.raises(ValueError, match="explicit stopping"):
        replace(context.contract, stopping_rules=())
    with pytest.raises(ValueError, match="objective ids"):
        replace(
            context.contract,
            objectives=(context.objective, replace(context.objective, minimum_effect=2.0)),
        )
    with pytest.raises(ValueError, match="guardrail ids"):
        replace(
            context.contract,
            guardrails=(context.guardrail, replace(context.guardrail, allowed_regression=0.5)),
        )
    with pytest.raises(ValueError, match="stopping rule ids"):
        replace(
            context.contract,
            stopping_rules=(
                context.stop,
                replace(context.stop, condition="Stop once measurements are fully named"),
            ),
        )

    other_goal = Goal(statement="Increase yield", target=context.target)
    other_objective = Objective.create(
        objective_id="other",
        metric=context.objective.metric,
        semantics="maximize",
        goal=other_goal,
    )
    with pytest.raises(ValueError, match="exact contract Goal"):
        replace(
            context.contract,
            objectives=(other_objective,),
            lineage=(
                context.goal.ref,
                context.baseline.ref,
                other_objective.ref,
                context.constraint.ref,
                context.guardrail.ref,
                context.stop.ref,
            ),
        )
    with pytest.raises(ValueError, match="typed Guardrail"):
        replace(context.contract, constraints=())

    other_constraint = Constraint(statement="Keep safe", target=other_target)
    other_guardrail = Guardrail.create(
        guardrail_id="other",
        metric=context.guardrail.metric,
        semantics="no-regression",
        constraint=other_constraint,
    )
    with pytest.raises(ValueError, match="another target"):
        EvaluationContract.create(
            contract_id="other",
            goal=context.goal,
            baseline=context.baseline,
            objectives=(context.objective,),
            constraints=(other_constraint,),
            guardrails=(other_guardrail,),
            stopping_rules=(context.stop,),
        )
    with pytest.raises(ValueError, match="lineage"):
        replace(context.contract, lineage=(context.goal.ref,))


def test_contract_rejects_conflicting_metric_definitions_and_objectives() -> None:
    context = intent_context()
    conflicting_metric = Metric(
        metric_id=context.objective.metric.metric_id,
        direction="increase",
        role="objective",
        unit="fraction",
    )
    conflicting_objective = Objective.create(
        objective_id="conflicting-definition",
        metric=conflicting_metric,
        semantics="maximize",
        goal=context.goal,
    )
    with pytest.raises(ValueError, match="conflicting definitions"):
        EvaluationContract.create(
            contract_id="metric-conflict",
            goal=context.goal,
            baseline=context.baseline,
            objectives=(context.objective, conflicting_objective),
            constraints=(context.constraint,),
            guardrails=(context.guardrail,),
            stopping_rules=(context.stop,),
        )

    second = Objective.create(
        objective_id="same-metric-second-objective",
        metric=context.objective.metric,
        semantics="maximize",
        goal=context.goal,
    )
    with pytest.raises(ValueError, match="contradictory objectives"):
        EvaluationContract.create(
            contract_id="objective-conflict",
            goal=context.goal,
            baseline=context.baseline,
            objectives=(context.objective, second),
            constraints=(context.constraint,),
            guardrails=(context.guardrail,),
            stopping_rules=(context.stop,),
        )


@pytest.mark.parametrize("operator", [">", ">=", "<", "<=", "=="])
def test_all_guardrail_operators_form_valid_bounds(operator: str) -> None:
    context = intent_context()
    rule = Guardrail.create(
        guardrail_id=f"operator-{operator}",
        metric=context.guardrail.metric,
        semantics="must-satisfy",
        constraint=context.constraint,
        operator=operator,
        threshold=2.0,
    )
    contract = EvaluationContract.create(
        contract_id=f"operator-contract-{operator}",
        goal=context.goal,
        baseline=context.baseline,
        objectives=(context.objective,),
        constraints=(context.constraint,),
        guardrails=(rule,),
        stopping_rules=(context.stop,),
    )
    assert contract.guardrails == (rule,)


def test_request_proposal_result_and_handoff_validate_every_authority_edge() -> None:
    context = intent_context()
    request = context.request
    other_target = TargetRef(target_id="other", kind="physical-process")
    other_snapshot = TargetSnapshot(target=other_target, revision="1", state={})
    with pytest.raises(ValueError, match="does not match"):
        OperationalizationRequest.create(
            request_id="wrong-target", goal=context.goal, current_snapshot=other_snapshot
        )
    with pytest.raises(TypeError, match="known facts"):
        replace(request, known_facts=())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="known fact"):
        replace(request, known_facts={"fact": " "})
    with pytest.raises(ValueError, match="lineage"):
        replace(request, lineage=(context.goal.ref,))

    with pytest.raises(ValueError, match="unsupported operationalization"):
        OperationalizationProposal(
            request=request,
            disposition="accepted",
            missing_facts=("metric",),
            lineage=(request.ref, request.goal.ref, request.current_snapshot.ref),
        )
    with pytest.raises(ValueError, match="require only a contract"):
        OperationalizationProposal(
            request=request,
            disposition="operationalized",
            missing_facts=("metric",),
            lineage=(request.ref, request.goal.ref, request.current_snapshot.ref),
        )
    with pytest.raises(ValueError, match="named missing facts"):
        OperationalizationProposal(
            request=request,
            disposition="pending-information",
            lineage=(request.ref, request.goal.ref, request.current_snapshot.ref),
        )
    pending = OperationalizationProposal.pending(request=request, missing_facts=("metric",))
    with pytest.raises(ValueError, match="lineage"):
        replace(pending, lineage=(request.ref,))

    with pytest.raises(ValueError, match="require only a contract"):
        OperationalizationResult(
            request=request,
            disposition="operationalized",
            missing_facts=("metric",),
            lineage=(request.ref,),
        )
    with pytest.raises(ValueError, match="named missing facts"):
        OperationalizationResult(
            request=request,
            disposition="pending-information",
            lineage=(request.ref,),
        )
    other_request = replace(request, request_id="other")
    with pytest.raises(ValueError, match="another request"):
        OperationalizationResult(
            request=other_request,
            disposition=pending.disposition,
            missing_facts=pending.missing_facts,
            proposal=pending,
            lineage=(other_request.ref, pending.ref),
        )
    with pytest.raises(ValueError, match="rewrite"):
        OperationalizationResult(
            request=request,
            disposition="unmeasurable",
            missing_facts=pending.missing_facts,
            proposal=pending,
            lineage=(request.ref, pending.ref),
        )

    started = OperationalizationWorkflow().start(request, current_snapshot=context.snapshot)
    handoff = started.progress.handoff
    assert handoff is not None
    with pytest.raises(ValueError, match="not canonical"):
        replace(handoff, action=replace(handoff.action, action_id="other"))
    with pytest.raises(ValueError, match="Reasoner"):
        replace(handoff, capability_family="applier")
    with pytest.raises(ValueError, match="output schema"):
        replace(handoff, expected_output_record_type="evidence")
    with pytest.raises(ValueError, match="lineage"):
        replace(handoff, lineage=(request.ref,))


def test_action_failure_and_workflow_submission_errors_are_structured() -> None:
    context = intent_context()
    action = make_operationalization_action(context.request)
    proposal = OperationalizationProposal.propose_contract(
        request=context.request,
        contract=context.contract,
    )
    success = make_operationalization_result(
        action=action,
        proposal=proposal,
        resource_usage={"tokens": 2},
    )
    failure = make_operationalization_failure(
        action=action,
        failure=RuntimeFailure(
            classification="execution", message="reasoner unavailable", retryable=False
        ),
        resource_usage={"attempts": 1},
    )
    assert failure.disposition == "failed"
    with pytest.raises(ValueError, match="do not contain proposals"):
        operationalization_proposal_from_result(failure)
    with pytest.raises(TypeError, match="decoding requires"):
        operationalization_request_from_action("action")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require an OperationalizationRequest"):
        make_operationalization_action(context.goal)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require an OperationalizationProposal"):
        make_operationalization_result(action=action, proposal=context.contract)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require a RuntimeFailure"):
        make_operationalization_failure(action=action, failure=context.goal)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="decoding requires an ActionResult"):
        operationalization_proposal_from_result(action)  # type: ignore[arg-type]

    workflow = OperationalizationWorkflow()
    started = workflow.start(context.request, current_snapshot=context.snapshot)
    handoff = started.progress.handoff
    assert handoff is not None
    with pytest.raises(TypeError, match="OperationalizationProgress"):
        workflow.submit(
            context.request,  # type: ignore[arg-type]
            success,
            current_snapshot=context.snapshot,
        )
    with pytest.raises(ValueError, match="not canonically"):
        workflow.submit(
            started.progress,
            replace(success, action=replace(action, action_id="other")),
            current_snapshot=context.snapshot,
        )
    with pytest.raises(TypeError, match="requires an exact request"):
        workflow.start(context.goal, current_snapshot=context.snapshot)  # type: ignore[arg-type]


def test_policy_rejects_wrong_types_goals_baselines_and_proposals() -> None:
    context = intent_context()
    policy = OperationalizationPolicy()
    with pytest.raises(TypeError, match="OperationalizationRequest"):
        policy.validate_contract(context.goal, context.contract)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="EvaluationContract"):
        policy.validate_contract(context.request, context.goal)  # type: ignore[arg-type]

    other_goal = Goal(statement="Reduce energy", target=context.target)
    other_objective = Objective.create(
        objective_id="energy",
        metric=context.objective.metric,
        semantics="maximize",
        goal=other_goal,
    )
    other_contract = EvaluationContract.create(
        contract_id="other-goal",
        goal=other_goal,
        baseline=context.baseline,
        objectives=(other_objective,),
        stopping_rules=(context.stop,),
    )
    with pytest.raises(ValueError, match="another Goal"):
        policy.validate_contract(context.request, other_contract)

    stale_request = replace(
        context.request,
        current_snapshot=replace(context.snapshot, revision="new"),
        lineage=(context.goal.ref, replace(context.snapshot, revision="new").ref),
    )
    with pytest.raises(ValueError, match="stale"):
        policy.validate_contract(stale_request, context.contract)
    with pytest.raises(TypeError, match="OperationalizationProposal"):
        policy.accept_proposal(context.request, context.contract)  # type: ignore[arg-type]


def test_contract_runtime_records_remain_goal_intent_not_claim_or_evidence() -> None:
    context = intent_context()
    run = context.request.canonical_run()
    action = context.request.canonical_action()

    assert run.intent == context.goal.ref
    assert run.target_snapshot == context.snapshot
    assert action.input_refs == (context.request.ref, context.goal.ref, context.snapshot.ref)
    assert not isinstance(context.contract, Goal)
    assert context.contract.record_type == "evaluation_contract"
    assert context.goal.record_type == "goal"
    assert context.goal.ref != RecordRef("claim", context.goal.root)
