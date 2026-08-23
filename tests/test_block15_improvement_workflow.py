from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    ActionResult,
    ApplicationHandoff,
    CandidateSnapshot,
    ComparativeSelectionPolicy,
    ImprovementBudget,
    ImprovementCycleProposal,
    ImprovementCycleRequest,
    ImprovementIteration,
    ImprovementPolicy,
    ImprovementRequest,
    ImprovementResult,
    ImprovementWorkflow,
    InterventionImplementationRequest,
    InterventionSpec,
    RuntimeEngine,
    RuntimeFailure,
    SearchDirective,
    SemanticRecord,
    TargetSnapshot,
    cycle_request_from_action,
    deserialize_record,
    improve,
    make_cycle_failure,
    make_cycle_result,
    make_investigation_experiment_result,
    proposal_from_action_result,
    serialize_record,
    validate_cycle_action_result,
)
from tests.block14_support import candidate_for, comparison_context, trial_batch
from tests.block15_support import (
    CycleReasoner,
    DeterministicCycleProvider,
    cycle_proposal,
    hypotheses,
    improvement_request,
)


def test_declarative_improve_runs_hypothesis_to_selection_without_applying() -> None:
    context = comparison_context()
    request = improvement_request(context)
    provider = DeterministicCycleProvider(context, (True,))

    result = improve(request, provider=provider, current_snapshot=context.baseline_snapshot)

    assert result.disposition == "improved"
    assert result.stop_reason == "accepted candidate selected"
    assert result.handoff is not None
    assert result.handoff.apply is False
    assert result.handoff.authority == "proposal-only"
    assert result.handoff.current_snapshot == context.baseline_snapshot
    assert result.iterations[0].proposal.investigation.findings
    assert result.budget_usage["experiments"] == 3


@pytest.mark.parametrize("target_kind", ["physical-process", "software-repository"])
def test_complete_workflow_is_domain_neutral(target_kind: str) -> None:
    context = comparison_context(target_kind=target_kind)
    result = improve(
        improvement_request(context),
        provider=DeterministicCycleProvider(context, (True,)),
        current_snapshot=context.baseline_snapshot,
    )

    assert result.disposition == "improved"
    assert result.request.baseline.target.kind == target_kind


def test_failed_candidate_broadens_and_replaces_falsified_hypothesis() -> None:
    context = comparison_context()
    request = improvement_request(context, patience=3)
    provider = DeterministicCycleProvider(context, (False, True))

    result = improve(request, provider=provider, current_snapshot=context.baseline_snapshot)

    assert result.disposition == "improved"
    assert len(result.iterations) == 2
    assert result.iterations[0].selection.disposition == "none-accepted"
    assert result.iterations[0].next_direction == "broaden"
    assert (
        provider.actions[1].payload["request"]["data"]["directive"]["data"]["direction"]
        == "broaden"
    )
    first = {
        branch.hypothesis.ref for branch in result.iterations[0].proposal.investigation.branches
    }
    second = {
        branch.hypothesis.ref for branch in result.iterations[1].proposal.investigation.branches
    }
    assert first.isdisjoint(second)


def test_no_useful_improvement_is_complete_at_diminishing_return_limit() -> None:
    context = comparison_context()
    result = improve(
        improvement_request(context, patience=1),
        provider=DeterministicCycleProvider(context, (False,)),
        current_snapshot=context.baseline_snapshot,
    )

    assert result.disposition == "no-useful-improvement"
    assert result.handoff is None
    assert result.stop_reason == "diminishing returns"
    assert result.iterations[-1].selection.disposition == "none-accepted"


def test_stepped_api_retries_transient_host_failure_with_exact_action() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    started = workflow.start(
        improvement_request(context), current_snapshot=context.baseline_snapshot
    )
    action = started.progress.state.pending_actions[0]

    retried = workflow.submit(
        started.progress,
        make_cycle_failure(action=action, message="temporary fixture failure"),
        current_snapshot=context.baseline_snapshot,
    )

    retry = retried.progress.state.pending_actions[0]
    assert retry.action_id == action.action_id
    assert retry.attempt == 2
    proposal = cycle_proposal(retry, context=context, accepted=True)
    completed = workflow.submit(
        retried.progress,
        make_cycle_result(action=retry, proposal=proposal),
        current_snapshot=context.baseline_snapshot,
    )
    assert completed.progress.result is not None
    assert completed.progress.result.budget_usage["retries"] == 1


def test_resource_consuming_failure_preserves_a_legitimate_retry() -> None:
    context = comparison_context()
    request = improvement_request(context, max_resource_units=10, max_retries=1)
    workflow = ImprovementWorkflow()
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    assert action.budget_reservation == {"units": 5.0}
    retried = workflow.submit(
        started.progress,
        make_cycle_failure(action=action, message="costly transient", resource_units=1),
        current_snapshot=context.baseline_snapshot,
    )
    assert retried.progress.state.status == "waiting"
    retry = retried.progress.state.pending_actions[0]
    assert retry.attempt == 2
    assert retry.budget_reservation == {"units": 5.0}
    completed = workflow.submit(
        retried.progress,
        make_cycle_result(
            action=retry,
            proposal=cycle_proposal(retry, context=context, accepted=True),
            resource_units=1,
        ),
        current_snapshot=context.baseline_snapshot,
    )
    result = completed.progress.result
    assert result is not None
    assert result.budget_usage["resource_units"] == 2
    assert result.budget_usage["retries"] == 1


def test_failed_cycle_envelopes_cannot_smuggle_semantics_or_resource_dimensions() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    started = workflow.start(
        improvement_request(context), current_snapshot=context.baseline_snapshot
    )
    action = started.progress.state.pending_actions[0]
    failure = RuntimeFailure(
        classification="transient",
        message="host failure",
        retryable=True,
        lineage=(action.ref,),
    )
    smuggled = ActionResult(
        action=action,
        disposition="failed",
        output_refs=(started.progress.request.question.ref,),
        payload={"conclusion": "candidate disproved the hypothesis"},
        resource_usage={"gpu": 100},
        failure=failure,
        lineage=(action.ref, failure.ref),
    )
    with pytest.raises(ValueError, match="per-attempt cap"):
        workflow.submit(
            started.progress,
            smuggled,
            current_snapshot=context.baseline_snapshot,
        )
    with pytest.raises(ValueError, match="cannot smuggle"):
        workflow.submit(
            started.progress,
            replace(smuggled, resource_usage={"units": 1}),
            current_snapshot=context.baseline_snapshot,
        )


def test_resume_rejects_persisted_malformed_failures_before_provider_effects() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    started = workflow.start(
        improvement_request(context), current_snapshot=context.baseline_snapshot
    )
    action = started.progress.state.pending_actions[0]
    failure = RuntimeFailure(
        classification="transient",
        message="persisted host failure",
        retryable=True,
        lineage=(action.ref,),
    )
    smuggled = ActionResult(
        action=action,
        disposition="failed",
        payload={"conclusion": "falsified without evidence"},
        resource_usage={"gpu": 100},
        failure=failure,
        lineage=(action.ref, failure.ref),
    )
    persisted = RuntimeEngine.submit(started.progress.state, smuggled).state

    class CountingProvider:
        calls = 0

        def resource_claim(self, _action):
            self.calls += 1
            return 0

        def improve_cycle(self, _action):
            self.calls += 1
            raise AssertionError("provider must not run")

    provider = CountingProvider()
    with pytest.raises(ValueError, match="authorized per-attempt cap"):
        workflow.run_managed(
            replace(started.progress, state=persisted),
            provider=provider,
            current_snapshot=context.baseline_snapshot,
        )
    assert provider.calls == 0


def test_failed_attempts_cannot_hide_a_nonpolicy_action_behind_runtime_retry() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    request = improvement_request(context)
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    canonical_action = started.progress.state.pending_actions[0]
    canonical_cycle = cycle_request_from_action(canonical_action)
    forged_directive = replace(
        canonical_cycle.directive,
        reason="skip the required canonical hypothesis frontier",
    )
    forged_cycle = ImprovementCycleRequest(
        improvement=request,
        directive=forged_directive,
        remaining_experiments=canonical_cycle.remaining_experiments,
        remaining_resource_units=canonical_cycle.remaining_resource_units,
        resource_units_per_attempt=canonical_cycle.resource_units_per_attempt,
        lineage=(request.ref, forged_directive.ref),
    )
    forged_action = replace(
        canonical_action,
        input_refs=(forged_cycle.ref, request.ref, forged_directive.ref),
        payload={"request": forged_cycle.to_dict()},
        lineage=(request.ref, forged_directive.ref),
    )
    active = RuntimeEngine.start(request.canonical_run()).state
    forged_waiting = RuntimeEngine.request(active, forged_action).state
    persisted = RuntimeEngine.submit(
        forged_waiting,
        make_cycle_failure(action=forged_action, message="retry the forged action"),
    ).state
    assert persisted.pending_actions[0].attempt == 2

    class CountingProvider:
        calls = 0

        def resource_claim(self, _action):
            self.calls += 1
            return 0

        def improve_cycle(self, _action):
            self.calls += 1
            raise AssertionError("provider must not receive a nonpolicy retry")

    provider = CountingProvider()
    with pytest.raises(ValueError, match="exact policy-derived frontier"):
        workflow.run_managed(
            replace(started.progress, state=persisted),
            provider=provider,
            current_snapshot=context.baseline_snapshot,
        )
    assert provider.calls == 0


def test_action_codecs_reject_cross_action_and_policy_rejects_blind_retry() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    request = improvement_request(context, patience=3)
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    first_proposal = cycle_proposal(action, context=context, accepted=False)
    first_result = make_cycle_result(action=action, proposal=first_proposal)
    assert proposal_from_action_result(first_result) == first_proposal
    assert cycle_request_from_action(action) == first_proposal.request
    first = workflow.submit(
        started.progress, first_result, current_snapshot=context.baseline_snapshot
    )
    second_action = first.progress.state.pending_actions[0]
    second_request = cycle_request_from_action(second_action)
    forged = type(first_proposal).create(
        request=second_request,
        investigation=first_proposal.investigation,
        batches=first_proposal.batches,
    )
    with pytest.raises(ValueError, match="blindly retry"):
        ImprovementPolicy.evaluate(forged, previous=first.progress.iterations)
    prior = first.progress.iterations[0]
    forged_selection = ComparativeSelectionPolicy.select(
        selection_id=f"{request.request_id}:selection:2",
        contract=request.contract,
        batches=forged.batches,
        risk_policy=request.risk_policy,
    )
    with pytest.raises(ValueError, match="blindly retry"):
        ImprovementIteration(
            proposal=forged,
            selection=forged_selection,
            next_direction=prior.next_direction,
            previous_iteration=prior,
            rejected_hypotheses=prior.rejected_hypotheses,
            lineage=(
                forged.ref,
                forged_selection.ref,
                prior.ref,
                *prior.rejected_hypotheses,
            ),
        )

    with pytest.raises(ValueError, match="another cycle"):
        make_cycle_result(action=second_action, proposal=first_proposal)


def test_falsified_hypothesis_cannot_return_after_an_intervening_cycle() -> None:
    context = comparison_context()
    request = improvement_request(
        context,
        patience=4,
        max_iterations=4,
        max_experiments=12,
    )
    workflow = ImprovementWorkflow()
    progress = workflow.start(
        request,
        current_snapshot=context.baseline_snapshot,
    ).progress
    for _ in range(2):
        action = progress.state.pending_actions[0]
        proposal = cycle_proposal(action, context=context, accepted=False)
        progress = workflow.submit(
            progress,
            make_cycle_result(action=action, proposal=proposal),
            current_snapshot=context.baseline_snapshot,
        ).progress

    first, second = progress.iterations
    reintroduced = next(
        item for item in request.initial_hypotheses if item.ref in first.rejected_hypotheses
    )
    fresh = hypotheses(request.question, "fresh-third-cycle")[0]
    third_action = progress.state.pending_actions[0]
    laundered = cycle_proposal(
        third_action,
        context=context,
        accepted=False,
        hypothesis_seeds=(reintroduced, fresh),
    )

    with pytest.raises(ValueError, match="falsified hypotheses"):
        ImprovementPolicy.evaluate(laundered, previous=(first, second))

    selection = ComparativeSelectionPolicy.select(
        selection_id=f"{request.request_id}:selection:3",
        contract=request.contract,
        batches=laundered.batches,
        risk_policy=request.risk_policy,
    )
    rejected = tuple(
        branch.hypothesis.ref
        for branch in laundered.investigation.branches
        if branch.status == "rejected"
    )
    with pytest.raises(ValueError, match="falsified hypotheses"):
        ImprovementIteration(
            proposal=laundered,
            selection=selection,
            next_direction="broaden",
            previous_iteration=second,
            rejected_hypotheses=rejected,
            lineage=(laundered.ref, selection.ref, second.ref, *rejected),
        )

    forged = object.__new__(ImprovementIteration)
    object.__setattr__(forged, "proposal", laundered)
    object.__setattr__(forged, "selection", selection)
    object.__setattr__(forged, "next_direction", "broaden")
    object.__setattr__(forged, "previous_iteration", second)
    object.__setattr__(forged, "rejected_hypotheses", rejected)
    object.__setattr__(
        forged,
        "lineage",
        (laundered.ref, selection.ref, second.ref, *rejected),
    )
    object.__setattr__(forged, "metadata", {})
    SemanticRecord.__post_init__(forged)
    with pytest.raises(ValueError, match="falsified hypotheses"):
        deserialize_record(serialize_record(forged))

    persisted = RuntimeEngine.submit(
        progress.state,
        make_cycle_result(action=third_action, proposal=laundered),
    ).state
    with pytest.raises(ValueError, match="falsified hypotheses"):
        workflow.resume(
            request,
            persisted,
            current_snapshot=context.baseline_snapshot,
        )

    class LaunderingProvider:
        calls = 0

        def resource_claim(self, action):
            return action.budget_reservation["units"]

        def improve_cycle(self, action):
            self.calls += 1
            seeds = (reintroduced, fresh) if self.calls == 3 else None
            proposal = cycle_proposal(
                action,
                context=context,
                accepted=False,
                hypothesis_seeds=seeds,
            )
            return make_cycle_result(action=action, proposal=proposal, resource_units=1)

    with pytest.raises(ValueError, match="falsified hypotheses"):
        improve(
            request,
            provider=LaunderingProvider(),
            current_snapshot=context.baseline_snapshot,
        )


def test_resume_reconstructs_exact_iterations_and_rejects_projection_forgery() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    started = workflow.start(
        improvement_request(context, patience=3),
        current_snapshot=context.baseline_snapshot,
    )
    proposal = cycle_proposal(
        started.progress.state.pending_actions[0], context=context, accepted=False
    )
    advanced = workflow.submit(
        started.progress,
        make_cycle_result(action=started.progress.state.pending_actions[0], proposal=proposal),
        current_snapshot=context.baseline_snapshot,
    )

    resumed = workflow.resume(
        advanced.progress.request,
        advanced.progress.state,
        current_snapshot=context.baseline_snapshot,
    )
    assert resumed.transitions == ()
    assert resumed.progress == advanced.progress
    with pytest.raises(ValueError, match="canonical persisted frontier"):
        workflow.submit(
            replace(advanced.progress, iterations=()),
            make_cycle_failure(
                action=advanced.progress.state.pending_actions[0], message="temporary"
            ),
            current_snapshot=context.baseline_snapshot,
        )


def test_resume_reconstructs_completed_result_and_exact_outcome() -> None:
    context = comparison_context()
    request = improvement_request(context)
    workflow = ImprovementWorkflow()
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    completed = workflow.submit(
        started.progress,
        make_cycle_result(
            action=action,
            proposal=cycle_proposal(action, context=context, accepted=True),
        ),
        current_snapshot=context.baseline_snapshot,
    )

    resumed = workflow.resume(
        request,
        completed.progress.state,
        current_snapshot=context.baseline_snapshot,
    )
    assert resumed.transitions == ()
    assert resumed.progress == completed.progress
    assert resumed.progress.result is not None


def test_resume_reconciles_each_active_runtime_frontier_with_exact_transitions() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    request = improvement_request(context, patience=3)

    active_start = RuntimeEngine.start(request.canonical_run()).state
    initial = workflow.resume(
        request,
        active_start,
        current_snapshot=context.baseline_snapshot,
    )
    assert tuple(item.event.kind for item in initial.transitions) == ("action_requested",)
    assert initial.progress.state.status == "waiting"

    first_action = initial.progress.state.pending_actions[0]
    continued_state = RuntimeEngine.submit(
        initial.progress.state,
        make_cycle_result(
            action=first_action,
            proposal=cycle_proposal(first_action, context=context, accepted=False),
        ),
    ).state
    assert continued_state.status == "active"
    continued = workflow.resume(
        request,
        continued_state,
        current_snapshot=context.baseline_snapshot,
    )
    assert tuple(item.event.kind for item in continued.transitions) == ("action_requested",)
    assert len(continued.progress.iterations) == 1
    assert continued.progress.state.pending_actions[0].action_id.endswith(":cycle:2")

    terminal_request = improvement_request(context)
    terminal_start = workflow.start(
        terminal_request,
        current_snapshot=context.baseline_snapshot,
    ).progress
    terminal_action = terminal_start.state.pending_actions[0]
    terminal_state = RuntimeEngine.submit(
        terminal_start.state,
        make_cycle_result(
            action=terminal_action,
            proposal=cycle_proposal(terminal_action, context=context, accepted=True),
        ),
    ).state
    completed = workflow.resume(
        terminal_request,
        terminal_state,
        current_snapshot=context.baseline_snapshot,
    )
    assert tuple(item.event.kind for item in completed.transitions) == ("run_completed",)
    assert completed.progress.result is not None
    assert completed.progress.terminal


def test_replay_rejects_any_new_work_after_the_policy_stop_frontier() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    request = improvement_request(context)
    started = workflow.start(request, current_snapshot=context.baseline_snapshot).progress
    action = started.state.pending_actions[0]
    proposal = cycle_proposal(action, context=context, accepted=True)
    iteration = ImprovementPolicy.evaluate(proposal)
    settled = RuntimeEngine.submit(
        started.state,
        make_cycle_result(action=action, proposal=proposal),
    ).state
    post_stop_directive = SearchDirective(
        iteration=2,
        direction="narrow",
        reason="continue despite an accepted candidate",
        previous_iteration=iteration.ref,
        lineage=(iteration.ref,),
    )
    post_stop_cycle = ImprovementCycleRequest(
        improvement=request,
        directive=post_stop_directive,
        remaining_experiments=request.budget.max_experiments - proposal.experiment_count,
        remaining_resource_units=request.budget.max_resource_units,
        resource_units_per_attempt=(
            request.budget.max_resource_units / (request.budget.max_retries + 1)
        ),
        lineage=(request.ref, post_stop_directive.ref),
    )
    post_stop_action = replace(
        action,
        action_id=f"{request.request_id}:cycle:2",
        input_refs=(post_stop_cycle.ref, request.ref, post_stop_directive.ref),
        payload={"request": post_stop_cycle.to_dict()},
        budget_reservation={"units": post_stop_cycle.resource_units_per_attempt},
        lineage=(request.ref, post_stop_directive.ref),
    )
    persisted = RuntimeEngine.request(settled, post_stop_action).state

    with pytest.raises(ValueError, match="requested work after its policy stop"):
        workflow.resume(
            request,
            persisted,
            current_snapshot=context.baseline_snapshot,
        )


@pytest.mark.parametrize(
    ("request_options", "expected"),
    [
        ({"max_iterations": 1, "patience": 3}, "iteration budget exhausted"),
        ({"max_experiments": 3, "patience": 3}, "experiment budget exhausted"),
    ],
)
def test_each_declared_loop_budget_stops_independently(
    request_options: dict, expected: str
) -> None:
    context = comparison_context()
    request = improvement_request(context, **request_options)
    result = improve(
        request,
        provider=DeterministicCycleProvider(context, (False,)),
        current_snapshot=context.baseline_snapshot,
    )
    assert result.stop_reason == expected


def test_promising_objective_with_failed_guardrail_narrows_but_does_not_promote() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    started = workflow.start(
        improvement_request(context, max_iterations=1, patience=3),
        current_snapshot=context.baseline_snapshot,
    )
    action = started.progress.state.pending_actions[0]
    completed = workflow.submit(
        started.progress,
        make_cycle_result(
            action=action,
            proposal=cycle_proposal(
                action,
                context=context,
                accepted=False,
                guardrail_failure=True,
            ),
        ),
        current_snapshot=context.baseline_snapshot,
    )
    result = completed.progress.result
    assert result is not None
    assert result.disposition == "no-useful-improvement"
    assert result.iterations[0].next_direction == "narrow"


def test_declarative_api_keeps_infrastructure_failure_separate_from_epistemics() -> None:
    context = comparison_context()

    class FailingProvider:
        def resource_claim(self, action):
            return action.budget_reservation["units"]

        def improve_cycle(self, action):
            return make_cycle_failure(action=action, message="host offline", retryable=False)

    with pytest.raises(RuntimeError, match="without an ImprovementResult"):
        improve(
            improvement_request(context),
            provider=FailingProvider(),
            current_snapshot=context.baseline_snapshot,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"max_iterations": 0}, "positive"),
        ({"max_experiments": True}, "integer"),
        ({"max_retries": -1}, "nonnegative"),
        ({"max_resource_units": 0}, "positive"),
        ({"diminishing_return_patience": 0}, "positive"),
    ],
)
def test_improvement_budget_rejects_bypass_values(changes: dict, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        ImprovementBudget(**changes)


def test_records_and_action_codecs_fail_closed_on_authority_or_shape_changes() -> None:
    context = comparison_context()
    request = improvement_request(context)
    with pytest.raises(ValueError, match="cannot authorize"):
        ImprovementRequest(
            request_id=request.request_id,
            operationalization=request.operationalization,
            question=request.question,
            initial_hypotheses=request.initial_hypotheses,
            risk_policy=request.risk_policy,
            budget=request.budget,
            apply=True,
            lineage=request.lineage,
        )
    with pytest.raises(ValueError, match="unsupported search direction"):
        SearchDirective(iteration=1, direction="repeat", reason="blind retry")
    with pytest.raises(TypeError, match="ImprovementIteration"):
        SearchDirective(
            iteration=2,
            direction="broaden",
            reason="use a semantically unrelated predecessor",
            previous_iteration=request.question.ref,
            lineage=(request.question.ref,),
        )

    action = (
        ImprovementWorkflow()
        .start(request, current_snapshot=context.baseline_snapshot)
        .progress.state.pending_actions[0]
    )
    proposal = cycle_proposal(action, context=context, accepted=True)
    with pytest.raises(ValueError, match="experiment allowance"):
        ImprovementCycleProposal(
            request=replace(proposal.request, remaining_experiments=1),
            investigation=proposal.investigation,
            batches=proposal.batches,
            lineage=proposal.lineage,
        )
    with pytest.raises(ValueError, match="reserved action kind"):
        cycle_request_from_action(replace(action, kind="foreign"))
    with pytest.raises(ValueError, match="successful action result"):
        proposal_from_action_result(make_cycle_failure(action=action, message="failed"))


def test_canonical_directive_derivation_rejects_every_invalid_frontier_shape() -> None:
    from librsi.improvement.directives import (
        canonical_search_directive,
        next_search_directive,
    )

    context = comparison_context()
    request = improvement_request(context)
    with pytest.raises(ValueError, match="unsupported search direction"):
        canonical_search_directive(
            iteration=1,
            direction="repeat",
            previous_iteration=None,
        )
    with pytest.raises(ValueError, match="first search directive"):
        canonical_search_directive(
            iteration=1,
            direction="narrow",
            previous_iteration=None,
        )
    with pytest.raises(ValueError, match="later search directives"):
        canonical_search_directive(
            iteration=2,
            direction="initial",
            previous_iteration=None,
        )
    with pytest.raises(TypeError, match="ImprovementIteration predecessor"):
        canonical_search_directive(
            iteration=2,
            direction="broaden",
            previous_iteration=request.question.ref,
        )
    with pytest.raises(TypeError, match="ImprovementIteration predecessor"):
        next_search_directive(request)  # type: ignore[arg-type]


def test_action_envelopes_reject_missing_wrong_and_uncited_semantic_records() -> None:
    context = comparison_context()
    request = improvement_request(context)
    action = (
        ImprovementWorkflow()
        .start(request, current_snapshot=context.baseline_snapshot)
        .progress.state.pending_actions[0]
    )
    proposal = cycle_proposal(action, context=context, accepted=True)
    valid = make_cycle_result(action=action, proposal=proposal)

    with pytest.raises(ValueError, match="lost its request"):
        cycle_request_from_action(replace(action, payload={}))
    with pytest.raises(TypeError, match="another record type"):
        cycle_request_from_action(replace(action, payload={"request": request.question.to_dict()}))
    with pytest.raises(ValueError, match="inputs do not match"):
        cycle_request_from_action(replace(action, input_refs=()))
    with pytest.raises(ValueError, match="lost its proposal"):
        proposal_from_action_result(replace(valid, payload={}))
    with pytest.raises(TypeError, match="another record type"):
        proposal_from_action_result(
            replace(valid, payload={"proposal": request.question.to_dict()})
        )
    with pytest.raises(ValueError, match="does not answer"):
        proposal_from_action_result(replace(valid, output_refs=()))
    with pytest.raises(TypeError, match="requires an ImprovementRequest"):
        ImprovementPolicy.validate_request(request.question)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires an ImprovementCycleProposal"):
        ImprovementPolicy.evaluate(request)  # type: ignore[arg-type]


def test_intervention_cannot_disconnect_candidate_from_hypothesis_evidence() -> None:
    context = comparison_context()
    workflow = ImprovementWorkflow()
    started = workflow.start(
        improvement_request(context), current_snapshot=context.baseline_snapshot
    )
    proposal = cycle_proposal(
        started.progress.state.pending_actions[0], context=context, accepted=True
    )
    foreign_candidate = proposal.batches[0].candidate
    disconnected_ref = foreign_candidate.request.intervention.evidence[0].source_refs[0]
    with pytest.raises(ValueError, match="supporting rationale"):
        replace(
            foreign_candidate.request.intervention,
            supporting_refs=(disconnected_ref,),
            lineage=(
                foreign_candidate.request.intervention.baseline.ref,
                disconnected_ref,
                *(item.ref for item in foreign_candidate.request.intervention.evidence),
                *(item.ref for item in foreign_candidate.request.intervention.constraints),
            ),
        )


def test_direct_iteration_result_and_runtime_state_authority_forgeries_fail_closed() -> None:
    context = comparison_context()
    request = improvement_request(context)
    workflow = ImprovementWorkflow()
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    rejected = ImprovementPolicy.evaluate(cycle_proposal(action, context=context, accepted=False))
    accepted = ImprovementPolicy.evaluate(cycle_proposal(action, context=context, accepted=True))
    with pytest.raises(ValueError, match="exact cycle proposal"):
        replace(rejected, selection=accepted.selection, next_direction="stop")

    completed = workflow.submit(
        started.progress,
        make_cycle_result(action=action, proposal=accepted.proposal, resource_units=3),
        current_snapshot=context.baseline_snapshot,
    )
    result = completed.progress.result
    assert result is not None
    with pytest.raises(ValueError, match="stop reason"):
        replace(result, stop_reason="caller says done")
    with pytest.raises(ValueError, match="runtime derived"):
        replace(
            result,
            budget_usage={
                "iterations": 1,
                "experiments": 3,
                "retries": 0,
                "resource_units": 0,
            },
        )
    forged_state = replace(completed.progress.state, resource_usage={"units": 0})
    with pytest.raises(ValueError, match="replay exactly"):
        workflow.resume(
            request,
            forged_state,
            current_snapshot=context.baseline_snapshot,
        )


def test_policy_and_direct_iteration_share_canonical_directive_authority() -> None:
    context = comparison_context()
    request = improvement_request(context)
    action = (
        ImprovementWorkflow()
        .start(request, current_snapshot=context.baseline_snapshot)
        .progress.state.pending_actions[0]
    )
    canonical_cycle = cycle_request_from_action(action)
    canonical_proposal = cycle_proposal(action, context=context, accepted=True)
    canonical_iteration = ImprovementPolicy.evaluate(canonical_proposal)
    forged_directive = replace(
        canonical_cycle.directive,
        reason="caller-authored reason with the same direction",
    )
    forged_cycle = replace(
        canonical_cycle,
        directive=forged_directive,
        lineage=(request.ref, forged_directive.ref),
    )
    forged_proposal = ImprovementCycleProposal.create(
        request=forged_cycle,
        investigation=canonical_proposal.investigation,
        batches=canonical_proposal.batches,
    )

    with pytest.raises(ValueError, match="exact policy-derived frontier"):
        ImprovementPolicy.evaluate(forged_proposal)
    with pytest.raises(ValueError, match="exact policy-derived frontier"):
        ImprovementIteration(
            proposal=forged_proposal,
            selection=canonical_iteration.selection,
            next_direction=canonical_iteration.next_direction,
            rejected_hypotheses=canonical_iteration.rejected_hypotheses,
            lineage=(
                forged_proposal.ref,
                canonical_iteration.selection.ref,
                *canonical_iteration.rejected_hypotheses,
            ),
        )


def test_result_construction_uses_the_same_exact_replay_authority_as_resume() -> None:
    context = comparison_context()
    request = improvement_request(context)
    action = (
        ImprovementWorkflow()
        .start(request, current_snapshot=context.baseline_snapshot)
        .progress.state.pending_actions[0]
    )
    proposal = cycle_proposal(action, context=context, accepted=True)
    iteration = ImprovementPolicy.evaluate(proposal)
    handoff = ApplicationHandoff(
        request=request,
        selection=iteration.selection,
        current_snapshot=request.baseline,
        lineage=(
            request.ref,
            iteration.selection.ref,
            request.baseline.ref,
            *iteration.selection.selected,
        ),
    )
    canonical_envelope = make_cycle_result(
        action=action,
        proposal=proposal,
        resource_units=3,
    )
    forged_action = replace(action, action_id="caller-authored-cycle")
    forged_envelope = replace(
        canonical_envelope,
        action=forged_action,
        lineage=(forged_action.ref, proposal.ref),
    )
    active = RuntimeEngine.start(request.canonical_run()).state
    waiting = RuntimeEngine.request(active, forged_action).state
    settled = RuntimeEngine.submit(waiting, forged_envelope).state

    with pytest.raises(ValueError, match="exact policy-derived frontier"):
        ImprovementWorkflow().resume(
            request,
            settled,
            current_snapshot=context.baseline_snapshot,
        )
    with pytest.raises(ValueError, match="exact policy-derived frontier"):
        ImprovementResult(
            request=request,
            disposition="improved",
            iterations=(iteration,),
            settled_state=settled,
            handoff=handoff,
            stop_reason="accepted candidate selected",
            budget_usage={
                "iterations": 1,
                "experiments": proposal.experiment_count,
                "retries": 0,
                "resource_units": 3,
            },
            lineage=(request.ref, settled.ref, iteration.ref, handoff.ref),
        )


def test_rejected_hypothesis_and_counterexample_cannot_authorize_candidate() -> None:
    context = comparison_context()
    request = improvement_request(context)
    started = ImprovementWorkflow().start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    proposal = cycle_proposal(action, context=context, accepted=True)
    rejected = next(
        branch for branch in proposal.investigation.branches if branch.status == "rejected"
    )
    intervention = InterventionSpec.create(
        intervention_id="falsified-rationale",
        baseline=context.baseline_snapshot,
        kind="bounded.parameter-change",
        specification={"source": "rejected"},
        rationale=("Use a falsified mechanism",),
        supporting_refs=(rejected.hypothesis.ref,),
        evidence=rejected.evidence,
        expected_effects={"objective": "improve"},
        risks=("Unsupported causal rationale",),
        constraints=(context.constraint,),
        validation_plan={"comparison": "controlled"},
        rollback_expectations={"restore": context.baseline_snapshot.revision},
    )
    candidate = CandidateSnapshot.prepared(
        request=InterventionImplementationRequest.for_intervention(
            intervention, candidate_id="falsified"
        ),
        snapshot=candidate_for(context, "falsified").snapshot,
    )
    forged = ImprovementCycleProposal.create(
        request=proposal.request,
        investigation=proposal.investigation,
        batches=(trial_batch(context, candidate),),
    )
    with pytest.raises(ValueError, match="only supported hypotheses"):
        ImprovementPolicy.evaluate(forged)
    forged_selection = ComparativeSelectionPolicy.select(
        selection_id=f"{request.request_id}:selection:1",
        contract=request.contract,
        batches=forged.batches,
        risk_policy=request.risk_policy,
    )
    with pytest.raises(ValueError, match="only supported hypotheses"):
        ImprovementIteration(
            proposal=forged,
            selection=forged_selection,
            next_direction="stop",
            rejected_hypotheses=(rejected.hypothesis.ref,),
            lineage=(forged.ref, forged_selection.ref, rejected.hypothesis.ref),
        )


def test_experiment_budget_counts_unavailable_investigation_experiments() -> None:
    from librsi import InvestigationEvidenceBatch, investigate
    from librsi.investigation import investigation_experiment_request_from_action

    context = comparison_context()
    request = improvement_request(context)
    action = (
        ImprovementWorkflow()
        .start(request, current_snapshot=context.baseline_snapshot)
        .progress.state.pending_actions[0]
    )
    cycle = cycle_request_from_action(action)

    class UnavailableExperimenter:
        def experiment(self, experiment_action):
            experiment_request = investigation_experiment_request_from_action(experiment_action)
            return make_investigation_experiment_result(
                action=experiment_action,
                batch=InvestigationEvidenceBatch.unavailable(
                    request=experiment_request, reason="fixture unavailable"
                ),
            )

    investigation = investigate(
        question=request.question,
        target_snapshot=request.baseline,
        investigation_id="unavailable-cycle",
        initial_hypotheses=hypotheses(request.question),
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
        reasoner=CycleReasoner(),
        experimenter=UnavailableExperimenter(),
    )
    limited = ImprovementCycleRequest(
        improvement=request,
        directive=cycle.directive,
        remaining_experiments=1,
        remaining_resource_units=request.budget.max_resource_units,
        resource_units_per_attempt=cycle.resource_units_per_attempt,
        lineage=(request.ref, cycle.directive.ref),
    )
    with pytest.raises(ValueError, match="experiment allowance"):
        ImprovementCycleProposal.create(
            request=limited,
            investigation=investigation,
            batches=(cycle_proposal(action, context=context, accepted=True).batches[0],),
        )


def test_managed_provider_is_never_called_before_frontier_and_currentness_validation() -> None:
    context = comparison_context()
    request = improvement_request(context, patience=3)
    workflow = ImprovementWorkflow()
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    advanced = workflow.submit(
        started.progress,
        make_cycle_result(
            action=action,
            proposal=cycle_proposal(action, context=context, accepted=False),
        ),
        current_snapshot=context.baseline_snapshot,
    )

    class CountingProvider:
        calls = 0

        def resource_claim(self, _action):
            return 0

        def improve_cycle(self, _action):
            self.calls += 1
            raise AssertionError("provider must not run")

    provider = CountingProvider()
    with pytest.raises(ValueError, match="managed improvement progress is not canonical"):
        workflow.run_managed(
            replace(advanced.progress, iterations=()),
            provider=provider,
            current_snapshot=context.baseline_snapshot,
        )
    assert provider.calls == 0

    stale = TargetSnapshot(
        target=context.target,
        revision="changed-after-baseline",
        state={"changed": True},
    )
    with pytest.raises(ValueError, match="exact current target snapshot"):
        workflow.run_managed(
            advanced.progress,
            provider=provider,
            current_snapshot=stale,
        )
    assert provider.calls == 0


def test_improvement_result_and_handoff_records_recompute_every_authority_field() -> None:
    context = comparison_context()
    improved = improve(
        improvement_request(context),
        provider=DeterministicCycleProvider(context, (True,)),
        current_snapshot=context.baseline_snapshot,
    )
    assert improved.handoff is not None
    with pytest.raises(TypeError, match="settled RunState"):
        replace(improved, settled_state="state")
    failed_workflow = ImprovementWorkflow()
    failed_start = failed_workflow.start(
        improved.request, current_snapshot=context.baseline_snapshot
    )
    failed_progress = failed_workflow.submit(
        failed_start.progress,
        make_cycle_failure(
            action=failed_start.progress.state.pending_actions[0],
            message="terminal fixture failure",
            retryable=False,
        ),
        current_snapshot=context.baseline_snapshot,
    ).progress
    with pytest.raises(ValueError, match="settled canonical frontier"):
        replace(improved, settled_state=failed_progress.state)
    with pytest.raises(ValueError, match="at least one"):
        replace(improved, iterations=())
    with pytest.raises(ValueError, match="application handoff"):
        replace(improved, handoff=None)
    with pytest.raises(ValueError, match="cannot grant"):
        replace(improved.handoff, apply=True)
    with pytest.raises(ValueError, match="currentness"):
        replace(
            improved.handoff,
            current_snapshot=TargetSnapshot(
                target=context.target, revision="stale", state={"stale": True}
            ),
        )
    other_request = replace(improved.request, request_id="other-improvement")
    other_handoff = ApplicationHandoff(
        request=other_request,
        selection=improved.handoff.selection,
        current_snapshot=other_request.baseline,
        lineage=(
            other_request.ref,
            improved.handoff.selection.ref,
            other_request.baseline.ref,
            *improved.handoff.selection.selected,
        ),
    )
    with pytest.raises(ValueError, match="exact result projection"):
        replace(
            improved,
            handoff=other_handoff,
            lineage=(
                improved.request.ref,
                improved.settled_state.ref,
                *(item.ref for item in improved.iterations),
                other_handoff.ref,
            ),
        )
    with pytest.raises(ValueError, match="complete budget usage"):
        replace(improved, budget_usage={})
    with pytest.raises(ValueError, match="nonnegative"):
        replace(
            improved,
            budget_usage={
                "iterations": 1,
                "experiments": 3,
                "retries": 0,
                "resource_units": -1,
            },
        )
    with pytest.raises(ValueError, match="iteration or experiment usage"):
        replace(
            improved,
            budget_usage={
                "iterations": 1,
                "experiments": 2,
                "retries": 0,
                "resource_units": 1,
            },
        )

    no_improvement = improve(
        improvement_request(context, patience=1),
        provider=DeterministicCycleProvider(context, (False,)),
        current_snapshot=context.baseline_snapshot,
    )
    with pytest.raises(ValueError, match="exact policy projection"):
        replace(no_improvement, stop_reason="iteration budget exhausted")
    with pytest.raises(ValueError, match="exact policy projection"):
        replace(no_improvement, stop_reason="experiment budget exhausted")

    iteration_limited = improve(
        improvement_request(context, max_iterations=1, patience=3),
        provider=DeterministicCycleProvider(context, (False,)),
        current_snapshot=context.baseline_snapshot,
    )
    with pytest.raises(ValueError, match="exact policy projection"):
        replace(iteration_limited, stop_reason="diminishing returns")


def test_iteration_learning_and_search_directive_are_not_caller_replaceable() -> None:
    context = comparison_context()
    request = improvement_request(context)
    action = (
        ImprovementWorkflow()
        .start(request, current_snapshot=context.baseline_snapshot)
        .progress.state.pending_actions[0]
    )
    iteration = ImprovementPolicy.evaluate(cycle_proposal(action, context=context, accepted=False))
    with pytest.raises(ValueError, match="evidence-derived projection"):
        replace(iteration, next_direction="narrow")
    with pytest.raises(ValueError, match="evidence-derived projection"):
        replace(iteration, rejected_hypotheses=())
    override = replace(
        iteration.proposal.request.directive,
        reason="caller override",
    )
    overridden_request = ImprovementCycleRequest(
        improvement=request,
        directive=override,
        remaining_experiments=iteration.proposal.request.remaining_experiments,
        remaining_resource_units=iteration.proposal.request.remaining_resource_units,
        resource_units_per_attempt=iteration.proposal.request.resource_units_per_attempt,
        lineage=(request.ref, override.ref),
    )
    with pytest.raises(ValueError, match="policy-derived frontier"):
        ImprovementPolicy.evaluate(
            ImprovementCycleProposal.create(
                request=overridden_request,
                investigation=iteration.proposal.investigation,
                batches=iteration.proposal.batches,
            )
        )


def test_policy_history_must_begin_at_the_root_and_remain_continuous() -> None:
    context = comparison_context()
    request = improvement_request(context, max_iterations=3, patience=3)
    workflow = ImprovementWorkflow()
    started = workflow.start(request, current_snapshot=context.baseline_snapshot).progress
    first_action = started.state.pending_actions[0]
    first_proposal = cycle_proposal(first_action, context=context, accepted=False)
    first = ImprovementPolicy.evaluate(first_proposal)
    advanced = workflow.submit(
        started,
        make_cycle_result(action=first_action, proposal=first_proposal),
        current_snapshot=context.baseline_snapshot,
    ).progress
    second_proposal = cycle_proposal(
        advanced.state.pending_actions[0],
        context=context,
        accepted=False,
    )
    second = ImprovementPolicy.evaluate(second_proposal, previous=(first,))

    with pytest.raises(ValueError, match="continuous iteration chain"):
        ImprovementPolicy.evaluate(second_proposal, previous=(second,))


def test_aggregate_experiment_allowance_is_recomputed_across_cycles() -> None:
    context = comparison_context()
    request = improvement_request(context, max_experiments=3, max_iterations=3, patience=3)
    first_action = (
        ImprovementWorkflow()
        .start(request, current_snapshot=context.baseline_snapshot)
        .progress.state.pending_actions[0]
    )
    first = ImprovementPolicy.evaluate(
        cycle_proposal(first_action, context=context, accepted=False)
    )
    directive = SearchDirective(
        iteration=2,
        direction=first.next_direction,
        reason="forge a fresh allowance",
        previous_iteration=first.ref,
        lineage=(first.ref,),
    )
    forged_request = ImprovementCycleRequest(
        improvement=request,
        directive=directive,
        remaining_experiments=3,
        remaining_resource_units=9,
        resource_units_per_attempt=4.5,
        lineage=(request.ref, directive.ref),
    )
    forged_action = replace(
        first_action,
        action_id="bounded-improvement:cycle:2",
        input_refs=(forged_request.ref, request.ref, directive.ref),
        payload={"request": forged_request.to_dict()},
        budget_reservation={"units": 4.5},
        lineage=(request.ref, directive.ref),
    )
    second = cycle_proposal(forged_action, context=context, accepted=False)
    with pytest.raises(ValueError, match="exact remaining budget"):
        ImprovementPolicy.evaluate(second, previous=(first,))
    forged_selection = ComparativeSelectionPolicy.select(
        selection_id=f"{request.request_id}:selection:2",
        contract=request.contract,
        batches=second.batches,
        risk_policy=request.risk_policy,
    )
    with pytest.raises(ValueError, match="exact remaining budget"):
        ImprovementIteration(
            proposal=second,
            selection=forged_selection,
            next_direction=first.next_direction,
            previous_iteration=first,
            rejected_hypotheses=first.rejected_hypotheses,
            lineage=(
                second.ref,
                forged_selection.ref,
                first.ref,
                *first.rejected_hypotheses,
            ),
        )


def test_resource_claim_is_authorized_before_managed_provider_effects() -> None:
    context = comparison_context()
    request = improvement_request(context, max_resource_units=1)
    workflow = ImprovementWorkflow()
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    assert started.progress.state.pending_actions[0].budget_reservation == {"units": 0.5}

    class OverBudgetProvider:
        calls = 0

        def resource_claim(self, _action):
            return 2

        def improve_cycle(self, _action):
            self.calls += 1
            raise AssertionError("effectful method must not run")

    provider = OverBudgetProvider()
    with pytest.raises(ValueError, match="persisted per-attempt cap"):
        workflow.run_managed(
            started.progress,
            provider=provider,
            current_snapshot=context.baseline_snapshot,
        )
    assert provider.calls == 0


def test_resource_and_action_envelopes_fail_closed_at_every_edge() -> None:
    from librsi.improvement.policy import validate_cycle_admissibility

    context = comparison_context()
    request = improvement_request(context)
    workflow = ImprovementWorkflow()
    started = workflow.start(request, current_snapshot=context.baseline_snapshot)
    action = started.progress.state.pending_actions[0]
    proposal = cycle_proposal(action, context=context, accepted=True)
    valid = make_cycle_result(action=action, proposal=proposal)

    with pytest.raises(ValueError, match="canonical resource frontier"):
        cycle_request_from_action(replace(action, budget_reservation={}))
    with pytest.raises(ValueError, match="noncanonical lineage"):
        cycle_request_from_action(replace(action, lineage=()))
    retried = workflow.submit(
        started.progress,
        make_cycle_failure(action=action, message="retry"),
        current_snapshot=context.baseline_snapshot,
    ).progress.state.pending_actions[0]
    with pytest.raises(ValueError, match="lost runtime lineage"):
        cycle_request_from_action(replace(retried, lineage=()))
    with pytest.raises(ValueError, match="authorized cycle resources"):
        proposal_from_action_result(replace(valid, resource_usage={"gpu": 1}))
    with pytest.raises(ValueError, match="pre-authorized allowance"):
        make_cycle_result(action=action, proposal=proposal, resource_units=True)
    with pytest.raises(ValueError, match="pre-authorized allowance"):
        make_cycle_failure(action=action, message="invalid usage", resource_units=True)
    with pytest.raises(TypeError, match="requires an ActionResult"):
        validate_cycle_action_result(request)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be numeric"):
        replace(proposal.request, remaining_resource_units="all")
    with pytest.raises(ValueError, match="finite and positive"):
        replace(proposal.request, remaining_resource_units=0)
    with pytest.raises(ValueError, match="resource allowance exceeds"):
        replace(
            proposal.request,
            remaining_resource_units=request.budget.max_resource_units + 1,
        )
    with pytest.raises(TypeError, match="per-attempt resource units must be numeric"):
        replace(proposal.request, resource_units_per_attempt="all")
    with pytest.raises(ValueError, match="finite, positive, and within remaining"):
        replace(proposal.request, resource_units_per_attempt=0)
    with pytest.raises(TypeError, match="cycle admissibility"):
        validate_cycle_admissibility(request)  # type: ignore[arg-type]


def test_resource_exhaustion_has_one_policy_owned_terminal_reason() -> None:
    context = comparison_context()
    result = improve(
        improvement_request(context, max_resource_units=1, max_retries=0, patience=3),
        provider=DeterministicCycleProvider(context, (False,)),
        current_snapshot=context.baseline_snapshot,
    )
    assert result.stop_reason == "resource budget exhausted"
    assert result.disposition == "no-useful-improvement"
