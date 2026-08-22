from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    ActionResult,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilityRoute,
    Constraint,
    EvaluationContract,
    Goal,
    Guardrail,
    Metric,
    Objective,
    OperationalizationProposal,
    OperationalizationResult,
    OperationalizationResultValidator,
    OperationalizationWorkflow,
    RuntimeEngine,
    RuntimeFailure,
    SemanticRecord,
    TargetSnapshot,
    make_operationalization_failure,
    make_operationalization_result,
    operationalization_request_from_action,
)
from tests.block13_support import intent_context


def test_policy_owned_result_cannot_be_constructed_or_injected_with_other_intent() -> None:
    context = intent_context()
    other_goal = Goal(statement="Reduce energy use", target=context.target)
    other_objective = Objective.create(
        objective_id="other-goal-objective",
        metric=context.objective.metric,
        semantics="maximize",
        goal=other_goal,
    )
    other_contract = EvaluationContract.create(
        contract_id="other-contract",
        goal=other_goal,
        baseline=context.baseline,
        objectives=(other_objective,),
        stopping_rules=(context.stop,),
    )

    with pytest.raises(ValueError, match="another Goal"):
        OperationalizationResult(
            request=context.request,
            disposition="operationalized",
            contract=other_contract,
            lineage=(context.request.ref, other_contract.ref),
        )
    with pytest.raises(TypeError):
        OperationalizationWorkflow(object())  # type: ignore[call-arg]


def test_exact_goal_type_cannot_spoof_operationalization_authority() -> None:
    context = intent_context()

    class SpoofGoal(Goal):
        def __eq__(self, other: object) -> bool:
            return True

    spoof = SpoofGoal(statement=context.goal.statement, target=context.target)
    with pytest.raises(TypeError, match="require a Goal"):
        replace(context.contract, goal=spoof)


def test_target_objective_and_guardrail_ranges_must_intersect() -> None:
    context = intent_context()
    objective_metric = Metric(metric_id="ph", direction="target", role="objective")
    guardrail_metric = Metric(metric_id="ph", direction="target", role="guardrail")
    objective = Objective.create(
        objective_id="target-ph",
        metric=objective_metric,
        semantics="target",
        goal=context.goal,
        target_value=7.0,
    )
    constraint = Constraint(statement="pH must be at least 8", target=context.target)
    guardrail = Guardrail.create(
        guardrail_id="minimum-ph",
        metric=guardrail_metric,
        semantics="must-satisfy",
        constraint=constraint,
        operator=">=",
        threshold=8.0,
    )

    with pytest.raises(ValueError, match="target objective contradicts"):
        EvaluationContract.create(
            contract_id="contradictory-ph",
            goal=context.goal,
            baseline=context.baseline,
            objectives=(objective,),
            constraints=(constraint,),
            guardrails=(guardrail,),
            stopping_rules=(context.stop,),
        )


def test_dispatcher_rejects_malformed_operationalization_before_runtime_mutation() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    waiting = workflow.start(context.request, current_snapshot=context.snapshot).progress
    action = waiting.state.pending_actions[0]
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(routes=(CapabilityRoute("operationalize-goal", "reasoner", "external"),))
    )
    malformed = ActionResult(
        action=action,
        disposition="succeeded",
        payload={"fabricated": "not a proposal"},
    )

    with pytest.raises(ValueError, match="only its exact proposal"):
        dispatcher.submit(
            waiting.state,
            malformed,
            current_snapshot=context.snapshot,
        )
    assert waiting.state.results == ()
    assert waiting.state.pending_actions == (action,)


def test_external_dispatch_and_workflow_resume_share_canonical_runtime() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    waiting = workflow.start(context.request, current_snapshot=context.snapshot).progress
    handoff = waiting.handoff
    assert handoff is not None
    proposal = OperationalizationProposal.propose_contract(
        request=context.request,
        contract=context.contract,
    )
    envelope = make_operationalization_result(action=handoff.action, proposal=proposal)
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(routes=(CapabilityRoute("operationalize-goal", "reasoner", "external"),))
    )

    submitted = dispatcher.submit(
        waiting.state,
        envelope,
        current_snapshot=context.snapshot,
    )
    completed = workflow.resume(
        context.request,
        submitted.state,
        current_snapshot=context.snapshot,
    )

    assert completed.progress.state.status == "completed"
    assert completed.progress.result is not None
    assert completed.progress.result.contract == context.contract
    assert completed.progress.state.outcome is not None
    assert completed.progress.state.outcome.status == "operationalized"


def test_automatic_reasoner_uses_same_validated_runtime_frontier() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    waiting = workflow.start(context.request, current_snapshot=context.snapshot).progress

    class DeterministicReasoner:
        def reason(self, action):
            request = operationalization_request_from_action(action)
            proposal = OperationalizationProposal.propose_contract(
                request=request,
                contract=context.contract,
            )
            return make_operationalization_result(action=action, proposal=proposal)

    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(
            routes=(CapabilityRoute("operationalize-goal", "reasoner", "automatic"),),
            implementations=(DeterministicReasoner(),),
        )
    )
    advanced = dispatcher.advance(waiting.state, current_snapshot=context.snapshot)
    resumed = workflow.resume(
        context.request,
        advanced.state,
        current_snapshot=context.snapshot,
    )

    assert len(advanced.results) == 1
    assert resumed.progress.state.status == "completed"
    assert resumed.progress.result is not None


def test_failure_is_runtime_failure_not_an_unmeasurable_goal() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    waiting = workflow.start(context.request, current_snapshot=context.snapshot).progress
    handoff = waiting.handoff
    assert handoff is not None
    failure = make_operationalization_failure(
        action=handoff.action,
        failure=RuntimeFailure(
            classification="execution",
            message="measurement catalog unavailable",
            retryable=False,
        ),
    )

    failed = workflow.submit(
        waiting,
        failure,
        current_snapshot=context.snapshot,
    )
    resumed = workflow.resume(
        context.request,
        failed.progress.state,
        current_snapshot=context.snapshot,
    )

    assert failed.progress.state.status == "failed"
    assert failed.progress.result is None
    assert failed.progress.failure_result == failure
    assert resumed.progress == failed.progress


def test_dispatch_and_typed_path_require_live_exact_currentness() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    waiting = workflow.start(context.request, current_snapshot=context.snapshot).progress
    stale = TargetSnapshot(
        target=context.target,
        revision="batch-19",
        state=context.snapshot.state,
    )
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(routes=(CapabilityRoute("operationalize-goal", "reasoner", "external"),))
    )
    handoff = waiting.handoff
    assert handoff is not None
    proposal = OperationalizationProposal.propose_contract(
        request=context.request,
        contract=context.contract,
    )
    envelope = make_operationalization_result(action=handoff.action, proposal=proposal)

    with pytest.raises(ValueError, match="explicit current snapshot"):
        dispatcher.submit(waiting.state, envelope)
    with pytest.raises(ValueError, match="stale"):
        dispatcher.submit(waiting.state, envelope, current_snapshot=stale)
    with pytest.raises(ValueError, match="stale"):
        workflow.operationalize_typed(
            context.request,
            context.contract,
            current_snapshot=stale,
        )
    with pytest.raises(ValueError, match="exact pending frontier"):
        OperationalizationResultValidator().require_current_frontier(
            RuntimeEngine.start(context.request.canonical_run()).state,
            handoff.action,
            context.snapshot,
        )


def test_policy_invalid_proposal_is_rejected_before_runtime_mutation() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    waiting = workflow.start(context.request, current_snapshot=context.snapshot).progress
    action = waiting.state.pending_actions[0]
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(routes=(CapabilityRoute("operationalize-goal", "reasoner", "external"),))
    )
    other_goal = Goal(statement="Reduce energy", target=context.target)
    other_objective = Objective.create(
        objective_id="energy",
        metric=context.objective.metric,
        semantics="maximize",
        goal=other_goal,
    )
    other_contract = EvaluationContract.create(
        contract_id="foreign",
        goal=other_goal,
        baseline=context.baseline,
        objectives=(other_objective,),
        stopping_rules=(context.stop,),
    )
    foreign = make_operationalization_result(
        action=action,
        proposal=OperationalizationProposal.propose_contract(
            request=context.request,
            contract=other_contract,
        ),
    )

    with pytest.raises(ValueError, match="another Goal"):
        dispatcher.submit(
            waiting.state,
            foreign,
            current_snapshot=context.snapshot,
        )
    assert waiting.state.results == ()
    assert waiting.state.pending_actions == (action,)

    stale_snapshot = replace(context.snapshot, revision="batch-17")
    stale_baseline = replace(
        context.baseline,
        snapshot=stale_snapshot,
        lineage=(stale_snapshot.ref,),
    )
    stale_contract = replace(
        context.contract,
        baseline=stale_baseline,
        lineage=(
            context.goal.ref,
            stale_baseline.ref,
            context.objective.ref,
            context.constraint.ref,
            context.guardrail.ref,
            context.stop.ref,
        ),
    )
    stale = make_operationalization_result(
        action=action,
        proposal=OperationalizationProposal.propose_contract(
            request=context.request,
            contract=stale_contract,
        ),
    )
    with pytest.raises(ValueError, match="stale"):
        dispatcher.submit(waiting.state, stale, current_snapshot=context.snapshot)
    assert waiting.state.results == ()


def test_exact_duplicate_submission_is_idempotent_but_divergence_is_rejected() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    waiting = workflow.start(context.request, current_snapshot=context.snapshot).progress
    handoff = waiting.handoff
    assert handoff is not None
    proposal = OperationalizationProposal.propose_contract(
        request=context.request,
        contract=context.contract,
    )
    envelope = make_operationalization_result(action=handoff.action, proposal=proposal)
    dispatcher = CapabilityDispatcher(
        CapabilityRegistry(routes=(CapabilityRoute("operationalize-goal", "reasoner", "external"),))
    )

    first = dispatcher.submit(
        waiting.state,
        envelope,
        current_snapshot=context.snapshot,
    )
    duplicate = dispatcher.submit(first.state, envelope)
    assert duplicate.state == first.state
    assert duplicate.transition is None

    completed = workflow.resume(
        context.request,
        first.state,
        current_snapshot=context.snapshot,
    )
    unchanged = workflow.submit(
        completed.progress,
        envelope,
        current_snapshot=replace(context.snapshot, revision="newer"),
    )
    assert unchanged.progress == completed.progress
    assert unchanged.transitions == ()

    divergent = make_operationalization_result(
        action=handoff.action,
        proposal=OperationalizationProposal.pending(
            request=context.request,
            missing_facts=("another metric",),
        ),
    )
    with pytest.raises(ValueError, match="not for a pending action"):
        dispatcher.submit(first.state, divergent)
    with pytest.raises(ValueError, match="no pending proposal"):
        workflow.submit(
            completed.progress,
            divergent,
            current_snapshot=context.snapshot,
        )


def test_contract_rosters_reject_semantic_record_subclasses() -> None:
    context = intent_context()

    class FabricatedObjective(Objective):
        def __post_init__(self) -> None:
            SemanticRecord.__post_init__(self)

    fabricated = FabricatedObjective(
        objective_id="fabricated",
        metric=context.objective.metric,
        semantics="declare-success",
        source_goal=context.goal.ref,
        lineage=(context.goal.ref, context.objective.metric.ref),
    )
    with pytest.raises(TypeError, match="Objective values"):
        EvaluationContract.create(
            contract_id="fabricated-objective",
            goal=context.goal,
            baseline=context.baseline,
            objectives=(fabricated,),
            stopping_rules=(context.stop,),
        )

    class FabricatedConstraint(Constraint):
        pass

    fabricated_constraint = FabricatedConstraint(
        statement=context.constraint.statement,
        target=context.target,
    )
    with pytest.raises(TypeError, match="Constraint values"):
        replace(context.contract, constraints=(fabricated_constraint,))
