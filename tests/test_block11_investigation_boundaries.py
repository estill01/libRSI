from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from librsi import (
    EVIDENCE_RELATIONSHIPS,
    Action,
    ActionResult,
    Evidence,
    ExperimentSpec,
    FrozenMap,
    Hypothesis,
    InvestigationEvidenceBatch,
    InvestigationExperimentRequest,
    InvestigationExperimentResultValidator,
    InvestigationFinding,
    InvestigationFrontier,
    InvestigationPolicy,
    InvestigationProgress,
    InvestigationReasoningResultValidator,
    InvestigationRequest,
    InvestigationUpdate,
    InvestigationWorkflow,
    Question,
    ReasoningResult,
    RunBudget,
    RuntimeEngine,
    RuntimeFailure,
    TargetRef,
    TargetSnapshot,
    investigation_batch_from_action_result,
    investigation_design_reasoning_action,
    investigation_experiment_request_from_action,
    investigation_hypothesis_reasoning_action,
    investigation_unresolved,
    make_investigation_experiment_action,
    make_investigation_experiment_failure,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action_result,
    make_reasoning_failure,
    reasoning_request_from_action,
    record_from_dict,
)


def _context(*, bound: bool = False):
    target = TargetRef(target_id="boundary-target", kind="system") if bound else None
    snapshot = (
        TargetSnapshot(target=target, revision="r1", state={"mode": "test"})
        if target is not None
        else None
    )
    question = Question(prompt="Which bounded explanation survives?", target=target)
    hypotheses = tuple(
        Hypothesis(
            statement=f"Explanation {index} survives",
            target=target,
            causal_model={"cause": index},
            predictions=({"signal": index},),
            source_refs=(question.ref,),
            status="proposed",
            lineage=(question.ref,),
        )
        for index in (1, 2)
    )
    investigation = InvestigationRequest.for_question(
        investigation_id="boundary-investigation",
        question=question,
        target_snapshot=snapshot,
        initial_hypotheses=hypotheses,
        portfolio_mode="sequential",
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    policy = InvestigationPolicy()
    branches = tuple(
        policy.initial_branch(
            investigation=investigation,
            branch_id=f"hypothesis-{index}",
            hypothesis=hypothesis,
        )
        for index, hypothesis in enumerate(hypotheses, start=1)
    )
    experiment = ExperimentSpec(
        experiment_id="boundary-experiment",
        kind="investigation",
        target_snapshot=snapshot,
        design={"measure": "signal"},
        criteria={"decisive": True},
        requested_measurements=("signal",),
        lineage=(branches[0].hypothesis.ref,),
    )
    designed = policy.add_experiment(branches[0], experiment)
    request = InvestigationExperimentRequest.for_branch(
        branches=(designed, branches[1]),
        branch=designed,
        sequence=1,
    )
    evidence = tuple(
        Evidence(
            evidence_type="support",
            data={"sample": sample},
            subject_refs=(designed.hypothesis.ref,),
            source_refs=(experiment.ref,),
            target_snapshot=snapshot,
            weight=1.0,
        )
        for sample in (1, 2)
    )
    batch = InvestigationEvidenceBatch.collected(request=request, evidence=evidence)
    action = make_investigation_experiment_action(
        run=investigation.canonical_run(),
        request=request,
    )
    result = make_investigation_experiment_result(action=action, batch=batch)
    supported = policy.apply_batch(designed, batch)
    return (
        target,
        snapshot,
        question,
        hypotheses,
        investigation,
        policy,
        branches,
        experiment,
        designed,
        request,
        evidence,
        batch,
        action,
        result,
        supported,
    )


def _design_result(action: Action, *, experiments: object | None = None) -> ActionResult:
    request = reasoning_request_from_action(action)
    content = make_investigation_observation_content(
        request,
        measurements=("signal",),
    )
    if experiments is not None:
        content["experiments"] = experiments
    proposal = ReasoningResult.propose(
        request=request,
        content=content,
    )
    return make_reasoning_action_result(action=action, result=proposal)


def test_experiment_action_codecs_reject_every_shape_and_correlation_drift() -> None:
    (
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        request,
        evidence,
        batch,
        action,
        result,
        _,
    ) = _context()
    run = request.investigation.canonical_run()

    with pytest.raises(TypeError, match="require a Run"):
        make_investigation_experiment_action(run="run", request=request)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="InvestigationExperimentRequest"):
        make_investigation_experiment_action(run=run, request="request")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="canonical run"):
        make_investigation_experiment_action(
            run=replace(run, budget=RunBudget(max_actions=99)),
            request=request,
        )
    with pytest.raises(TypeError, match="requires an Action"):
        investigation_experiment_request_from_action("action")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not an investigation experiment"):
        investigation_experiment_request_from_action(replace(action, kind="other"))
    with pytest.raises(TypeError, match="payload must be a mapping"):
        investigation_experiment_request_from_action(
            replace(action, payload={"request": "not-a-mapping"})
        )
    with pytest.raises(TypeError, match="must decode"):
        investigation_experiment_request_from_action(
            replace(action, payload={"request": request.investigation.to_dict()})
        )
    with pytest.raises(ValueError, match="id has drifted"):
        investigation_experiment_request_from_action(replace(action, action_id="drifted"))

    with pytest.raises(TypeError, match="evidence batch"):
        make_investigation_experiment_result(action=action, batch="batch")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RuntimeFailure"):
        make_investigation_experiment_failure(action=action, failure="failure")  # type: ignore[arg-type]
    failure = RuntimeFailure(classification="execution", message="instrument failed")
    failed = make_investigation_experiment_failure(action=action, failure=failure)
    assert failed.failure == failure

    with pytest.raises(TypeError, match="requires an ActionResult"):
        investigation_batch_from_action_result("result")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="do not contain evidence"):
        investigation_batch_from_action_result(failed)
    with pytest.raises(TypeError, match="payload must be a mapping"):
        malformed = object.__new__(ActionResult)
        for name in ActionResult.__dataclass_fields__:
            object.__setattr__(malformed, name, getattr(result, name))
        object.__setattr__(malformed, "payload", {"batch": "not-a-mapping"})
        investigation_batch_from_action_result(malformed)
    with pytest.raises(TypeError, match="decode to an InvestigationEvidenceBatch"):
        investigation_batch_from_action_result(
            replace(result, payload={"batch": request.to_dict()})
        )
    with pytest.raises(ValueError, match="exact dispatched request"):
        other_request = replace(request, sequence=2)
        other_batch = InvestigationEvidenceBatch.collected(
            request=other_request,
            evidence=evidence,
        )
        investigation_batch_from_action_result(
            replace(
                result,
                output_refs=(other_batch.ref,),
                payload={"batch": other_batch.to_dict()},
            )
        )
    with pytest.raises(ValueError, match="cite only the exact evidence batch"):
        investigation_batch_from_action_result(replace(result, output_refs=()))


def test_experiment_result_validator_covers_success_and_failure_envelopes() -> None:
    *_, request, _, _, action, result, _ = _context()
    state = RuntimeEngine.request(
        RuntimeEngine.start(request.investigation.canonical_run()).state, action
    ).state
    validator = InvestigationExperimentResultValidator()
    validator.validate(state, result)

    with pytest.raises(TypeError, match="requires a RunState"):
        validator.validate("state", result)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires an ActionResult"):
        validator.validate(state, "result")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stale or mismatched"):
        other_state = RuntimeEngine.start(
            replace(request.investigation.canonical_run(), run_id="other-run")
        ).state
        validator.validate(other_state, result)
    failure = RuntimeFailure(classification="execution", message="failed")
    failed = make_investigation_experiment_failure(action=action, failure=failure)
    validator.validate(state, failed)
    with pytest.raises(ValueError, match="cannot contain batch outputs"):
        validator.validate(state, replace(failed, payload={"error": "extra"}))
    with pytest.raises(ValueError, match="require a RuntimeFailure"):
        malformed = object.__new__(ActionResult)
        for name in ActionResult.__dataclass_fields__:
            object.__setattr__(malformed, name, getattr(failed, name))
        object.__setattr__(malformed, "failure", None)
        validator.validate(state, malformed)


def test_investigation_reasoning_builders_and_validator_fail_closed() -> None:
    (
        _,
        _,
        _,
        _,
        investigation,
        _,
        branches,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
    ) = _context()
    workflow = InvestigationWorkflow()
    started = workflow.start(investigation)
    action = started.progress.state.pending_actions[0]
    result = _design_result(action)
    validator = InvestigationReasoningResultValidator()
    validator.validate(started.progress.state, result)

    generation_investigation = InvestigationRequest.for_question(
        investigation_id="boundary-generation",
        question=Question(prompt="Which explanation should be tested?"),
        max_hypotheses=2,
        max_experiments=2,
    )
    assert (
        investigation_hypothesis_reasoning_action(generation_investigation).kind
        == "investigation-reason"
    )
    with pytest.raises(ValueError, match="seeded investigations"):
        investigation_hypothesis_reasoning_action(investigation)
    frontier = InvestigationFrontier.for_branch(
        investigation=investigation,
        branches=branches,
        selected_branch_id=branches[0].branch_id,
    )
    assert investigation_design_reasoning_action(frontier) == action
    with pytest.raises(TypeError, match="InvestigationRequest"):
        investigation_hypothesis_reasoning_action("request")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="InvestigationFrontier"):
        investigation_design_reasoning_action("request")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="selected branch"):
        investigation_design_reasoning_action(
            InvestigationFrontier.for_hypothesis_generation(generation_investigation)
        )
    with pytest.raises(TypeError, match="requires a RunState"):
        validator.validate("state", result)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires an ActionResult"):
        validator.validate(started.progress.state, "result")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stale or mismatched"):
        validator.validate(
            RuntimeEngine.start(replace(investigation.canonical_run(), run_id="other")).state,
            result,
        )
    with pytest.raises(ValueError, match="pending action"):
        validator.validate(RuntimeEngine.start(investigation.canonical_run()).state, result)

    failure = make_reasoning_failure(
        action=action,
        failure=RuntimeFailure(classification="execution", message="reasoner failed"),
    )
    validator.validate(started.progress.state, failure)


def test_observation_content_helper_and_closed_schema_reject_open_shapes() -> None:
    (
        _,
        _,
        _,
        _,
        investigation,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
    ) = _context()
    action = InvestigationWorkflow().start(investigation).progress.state.pending_actions[0]
    request = reasoning_request_from_action(action)

    assert make_investigation_observation_content(
        request,
        measurements=("signal.p95",),
        method="observe",
    )["experiments"]
    with pytest.raises(TypeError, match="experiment-design request"):
        make_investigation_observation_content("request", measurements=("signal",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="investigation request"):
        make_investigation_observation_content(
            replace(request, context={"required_objective": "exact"}),
            measurements=("signal",),
        )
    with pytest.raises(ValueError, match="observation-only"):
        make_investigation_observation_content(
            request,
            measurements=("signal",),
            method="mutate",
        )
    with pytest.raises(TypeError, match="must be a sequence"):
        make_investigation_observation_content(request, measurements="signal")
    with pytest.raises(ValueError, match="bounded identifier"):
        make_investigation_observation_content(
            request,
            measurements=("apply patch to target",),
        )
    with pytest.raises(ValueError, match="must be unique"):
        make_investigation_observation_content(
            request,
            measurements=("signal", "signal"),
        )
    context = dict(request.context)
    context.pop("required_objective")
    with pytest.raises(ValueError, match="lost its required objective"):
        make_investigation_observation_content(
            replace(request, context=context),
            measurements=("signal",),
        )


def test_request_and_branch_records_reject_noncanonical_shape() -> None:
    (
        target,
        snapshot,
        question,
        hypotheses,
        investigation,
        _,
        branches,
        experiment,
        designed,
        _,
        evidence,
        _,
        _,
        _,
        _,
    ) = _context(bound=True)
    branch = branches[0]

    with pytest.raises(TypeError, match="require a Question"):
        replace(investigation, question="question")
    with pytest.raises(ValueError, match="TargetSnapshot"):
        replace(investigation, target_snapshot=None)
    with pytest.raises(ValueError, match="unsupported investigation portfolio"):
        replace(investigation, portfolio_mode="random")
    with pytest.raises(TypeError, match="maximum hypotheses must be an integer"):
        replace(investigation, max_hypotheses=True)
    with pytest.raises(ValueError, match="competing hypotheses"):
        replace(investigation, max_hypotheses=1)
    with pytest.raises(ValueError, match="maximum experiments must be positive"):
        replace(investigation, max_experiments=0)
    with pytest.raises(ValueError, match="must be nonnegative"):
        replace(investigation, max_redesigns_per_hypothesis=-1)
    with pytest.raises(TypeError, match="must be Hypothesis"):
        replace(investigation, initial_hypotheses=("hypothesis",))
    with pytest.raises(ValueError, match="declared hypothesis budget"):
        replace(
            investigation,
            initial_hypotheses=(*hypotheses, replace(hypotheses[1], statement="third")),
        )
    with pytest.raises(ValueError, match="must be unique"):
        replace(investigation, initial_hypotheses=(hypotheses[0], hypotheses[0]))
    with pytest.raises(ValueError, match="target does not match"):
        other_target = TargetRef(target_id="other", kind="system")
        replace(
            investigation,
            initial_hypotheses=(replace(hypotheses[0], target=other_target), hypotheses[1]),
        )
    with pytest.raises(ValueError, match="falsifiable predictions"):
        replace(
            investigation,
            initial_hypotheses=(replace(hypotheses[0], predictions=()), hypotheses[1]),
        )
    with pytest.raises(ValueError, match="lineage must retain"):
        replace(investigation, lineage=(question.ref,))
    with pytest.raises(TypeError, match="require a Question"):
        InvestigationRequest.for_question(investigation_id="bad", question="question")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="exact request"):
        replace(branch, investigation="request")
    with pytest.raises(ValueError, match="branch id is required"):
        replace(branch, branch_id=" ")
    with pytest.raises(TypeError, match="require a Hypothesis"):
        replace(branch, hypothesis="hypothesis")
    with pytest.raises(ValueError, match="target has drifted"):
        replace(branch, hypothesis=replace(branch.hypothesis, target=other_target))
    with pytest.raises(ValueError, match="does not cite the question"):
        replace(branch, hypothesis=replace(branch.hypothesis, source_refs=()))
    with pytest.raises(ValueError, match="not falsifiable"):
        replace(branch, hypothesis=replace(branch.hypothesis, predictions=()))
    with pytest.raises(TypeError, match="require a BeliefState"):
        replace(branch, belief="belief")
    with pytest.raises(TypeError, match="ExperimentSpec"):
        replace(branch, experiments=("experiment",))
    with pytest.raises(ValueError, match="must be unique"):
        replace(designed, experiments=(experiment, experiment))
    with pytest.raises(ValueError, match="investigation experiments"):
        replace(designed, experiments=(replace(experiment, kind="other"),))
    with pytest.raises(ValueError, match="currentness has drifted"):
        replace(designed, experiments=(replace(experiment, target_snapshot=None),))
    with pytest.raises(ValueError, match="does not cite its hypothesis"):
        replace(designed, experiments=(replace(experiment, lineage=(question.ref,)),))
    with pytest.raises(TypeError, match="contain Evidence"):
        replace(designed, evidence=("evidence",))
    with pytest.raises(ValueError, match="origins must exactly partition"):
        replace(designed, evidence=(evidence[0],), gathered_evidence_refs=())
    with pytest.raises(ValueError, match="belief is not canonically"):
        replace(branch, belief=replace(branch.belief, confidence=0.6))
    with pytest.raises(ValueError, match="unsupported investigation branch status"):
        replace(branch, status="unknown")
    with pytest.raises(ValueError, match="unsupported by its evidence"):
        replace(branch, status="supported")
    with pytest.raises(ValueError, match="unsupported branch retirement"):
        replace(branch, status="retired", retired_reason="arbitrary")
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(branch, lineage=())
    assert target is not None and snapshot is not None


def test_experiment_batch_finding_and_result_records_reject_drift() -> None:
    (
        _,
        snapshot,
        question,
        _,
        investigation,
        policy,
        branches,
        experiment,
        designed,
        request,
        evidence,
        batch,
        _,
        successful_action_result,
        supported,
    ) = _context(bound=True)

    with pytest.raises(TypeError, match="exact frontier"):
        replace(request, frontier="frontier")
    with pytest.raises(ValueError, match="selected branch"):
        generation_investigation = InvestigationRequest.for_question(
            investigation_id="request-generation-frontier",
            question=Question(prompt="Which explanation should be tested?"),
            max_hypotheses=2,
            max_experiments=2,
        )
        replace(
            request,
            frontier=InvestigationFrontier.for_hypothesis_generation(generation_investigation),
        )
    with pytest.raises(ValueError, match="another request"):
        other_request = replace(
            investigation, investigation_id="other", lineage=investigation.lineage
        )
        replace(request.frontier, investigation=other_request)
    with pytest.raises(TypeError, match="require an ExperimentSpec"):
        replace(request, experiment="experiment")
    with pytest.raises(ValueError, match="branch frontier"):
        replace(request, experiment=replace(experiment, experiment_id="other"))
    with pytest.raises(TypeError, match="sequence must be an integer"):
        replace(request, sequence=True)
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(request, lineage=())
    with pytest.raises(TypeError, match="designed branch"):
        InvestigationExperimentRequest.for_branch(
            branches=branches,
            branch=branches[0],
            sequence=1,
        )
    with pytest.raises(ValueError, match="competing hypothesis branches"):
        InvestigationFrontier.for_branch(
            investigation=investigation,
            branches=(designed,),
            selected_branch_id=designed.branch_id,
        )
    with pytest.raises(ValueError, match="complete seed roster"):
        InvestigationFrontier.for_branch(
            investigation=investigation,
            branches=(branches[1], designed),
            selected_branch_id=designed.branch_id,
        )

    with pytest.raises(TypeError, match="exact request"):
        replace(batch, request="request")
    with pytest.raises(ValueError, match="unsupported investigation evidence disposition"):
        replace(batch, disposition="unknown")
    with pytest.raises(TypeError, match="contain Evidence"):
        replace(batch, evidence=("evidence",))
    with pytest.raises(ValueError, match="unique evidence"):
        replace(batch, evidence=(evidence[0], evidence[0]))
    with pytest.raises(ValueError, match="leaked between hypotheses"):
        replace(batch, evidence=(replace(evidence[0], subject_refs=(branches[1].hypothesis.ref,)),))
    with pytest.raises(ValueError, match="exact experiment"):
        replace(batch, evidence=(replace(evidence[0], source_refs=(question.ref,)),))
    with pytest.raises(ValueError, match="stale or target-mismatched"):
        other_snapshot = replace(snapshot, revision="r2")
        replace(batch, evidence=(replace(evidence[0], target_snapshot=other_snapshot),))
    with pytest.raises(ValueError, match="relationship is unsupported"):
        replace(batch, evidence=(replace(evidence[0], evidence_type="narrative"),))
    with pytest.raises(ValueError, match="explicit weight"):
        replace(batch, evidence=(replace(evidence[0], weight=None),))
    with pytest.raises(ValueError, match="cannot be empty"):
        InvestigationEvidenceBatch.collected(request=request, evidence=())
    with pytest.raises(ValueError, match="cannot contain a reason"):
        replace(batch, reason="extra")
    with pytest.raises(ValueError, match="cannot contain evidence"):
        replace(batch, disposition="unavailable", reason="none")
    with pytest.raises(ValueError, match="reason is required"):
        InvestigationEvidenceBatch.unavailable(request=request, reason=" ")
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(batch, lineage=())

    finding = InvestigationFinding.from_branch(supported)
    with pytest.raises(TypeError, match="InvestigationBranch"):
        replace(finding, branch="branch")
    with pytest.raises(ValueError, match="supported branch"):
        replace(finding, branch=branches[0])
    with pytest.raises(ValueError, match="statement is required"):
        replace(finding, statement=" ")
    with pytest.raises(ValueError, match="cannot synthesize"):
        replace(finding, statement="new conclusion")
    with pytest.raises(ValueError, match="exact branch evidence"):
        replace(finding, evidence_refs=())
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(finding, lineage=())
    with pytest.raises(TypeError, match="InvestigationBranch"):
        InvestigationFinding.from_branch("branch")  # type: ignore[arg-type]

    rejected = policy.retire(branches[1], "no-action")
    result = policy.build_result(
        investigation=investigation,
        branches=(supported, rejected),
    )
    with pytest.raises(TypeError, match="InvestigationRequest"):
        replace(result, investigation="request")
    with pytest.raises(ValueError, match="canonical Run"):
        replace(result, run=question.ref)
    with pytest.raises(TypeError, match="must be an ActionResult"):
        replace(result, failure_result="failure")
    with pytest.raises(ValueError, match="exact failed workflow result"):
        replace(result, failure_result=successful_action_result)
    with pytest.raises(ValueError, match="unsupported investigation stop reason"):
        replace(result, stop_reason="unknown")
    for forged_reason in (
        "runtime-failure",
        "evidence-unavailable",
        "experiment-budget",
        "no-viable-hypotheses",
    ):
        with pytest.raises(ValueError, match="unsupported by its exact state"):
            replace(result, stop_reason=forged_reason)
        serialized = deepcopy(result.to_dict())
        serialized["data"]["stop_reason"] = forged_reason
        with pytest.raises(ValueError, match="unsupported by its exact state"):
            record_from_dict(serialized)
    with pytest.raises(ValueError, match="competing hypothesis"):
        replace(result, branches=(supported,), findings=(finding,), evidence=supported.evidence)
    with pytest.raises(TypeError, match="InvestigationBranch"):
        replace(result, branches=("branch", "branch-2"))
    with pytest.raises(ValueError, match="branch ids must be unique"):
        replace(result, branches=(supported, replace(rejected, branch_id=supported.branch_id)))
    with pytest.raises(ValueError, match="cannot retain active"):
        replace(result, branches=(supported, branches[1]))
    with pytest.raises(ValueError, match="exact supported branches"):
        replace(result, findings=())
    with pytest.raises(ValueError, match="evidence does not match"):
        replace(result, evidence=())
    with pytest.raises(ValueError, match="unsupported investigation disposition"):
        replace(result, disposition="unknown")
    with pytest.raises(ValueError, match="unsupported by its branches"):
        replace(result, disposition="inconclusive")
    with pytest.raises(ValueError, match="unresolved items have drifted"):
        replace(result, unresolved=("invented gap",))
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(result, lineage=())
    assert investigation_unresolved(()) == ("hypothesis generation did not complete",)


def test_policy_boundaries_and_exact_result_projection() -> None:
    (
        _,
        _,
        _,
        _,
        investigation,
        policy,
        branches,
        experiment,
        designed,
        _,
        _,
        batch,
        _,
        _,
        supported,
    ) = _context()

    with pytest.raises(TypeError, match="InvestigationPolicy"):
        InvestigationPolicy.owned_canonical("policy")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="InvestigationRequest"):
        policy.belief("request", branches[0].hypothesis, ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Hypothesis"):
        policy.belief(investigation, "hypothesis", ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="InvestigationBranch"):
        policy.add_experiment("branch", experiment)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="terminal"):
        policy.add_experiment(supported, experiment)
    with pytest.raises(TypeError, match="ExperimentSpec"):
        policy.add_experiment(branches[0], "experiment")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="InvestigationBranch"):
        policy.apply_batch("branch", batch)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="InvestigationEvidenceBatch"):
        policy.apply_batch(designed, "batch")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact branch frontier"):
        policy.apply_batch(branches[1], batch)
    with pytest.raises(ValueError, match="active branch"):
        InvestigationExperimentRequest.for_branch(
            branches=(supported, branches[1]),
            branch=supported,
            sequence=2,
        )
    with pytest.raises(TypeError, match="InvestigationBranch"):
        policy.retire("branch", "no-action")  # type: ignore[arg-type]
    assert policy.retire(supported, "no-action") == supported
    assert policy.prioritized_branch(investigation, (supported,)) is None
    assert not policy.can_design(investigation, supported, total_experiments=0)
    assert not policy.can_design(investigation, designed, total_experiments=1)
    assert policy.can_design(investigation, branches[0], total_experiments=0)

    settled = policy.settle(investigation, branches, reason="runtime-failure")
    assert all(item.retired_reason == "runtime-failure" for item in settled)
    budgeted_request = replace(investigation, max_experiments=1)
    budgeted_branches = tuple(
        policy.initial_branch(
            investigation=budgeted_request,
            branch_id=branch.branch_id,
            hypothesis=branch.hypothesis,
        )
        for branch in branches
    )
    budgeted_design = policy.add_experiment(
        budgeted_branches[0], replace(experiment, lineage=(budgeted_branches[0].hypothesis.ref,))
    )
    budgeted = policy.settle(budgeted_request, (budgeted_design, budgeted_branches[1]))
    assert all(item.retired_reason == "experiment-budget" for item in budgeted)

    result = policy.build_result(
        investigation=investigation,
        branches=(supported, policy.retire(branches[1], "no-action")),
    )
    assert result.disposition == "partially-answered"


def test_policy_experiment_design_rejects_reasoning_and_change_authority_drift() -> None:
    *_, investigation, policy, branches, _, _, _, _, _, _, _, _ = _context()
    workflow = InvestigationWorkflow()
    started = workflow.start(investigation)
    action = started.progress.state.pending_actions[0]
    reasoning = reasoning_request_from_action(action)
    advertised_criteria = reasoning.context["required_criteria"]
    assert advertised_criteria["accepted_relationships"] == tuple(sorted(EVIDENCE_RELATIONSHIPS))
    provider_content = make_investigation_observation_content(
        reasoning,
        measurements=("signal",),
    )
    assert provider_content["experiments"][0]["criteria"] == {
        "accepted_relationships": list(advertised_criteria["accepted_relationships"]),
        "minimum_evidence_items": advertised_criteria["minimum_evidence_items"],
    }
    valid = ReasoningResult.propose(
        request=reasoning,
        content=provider_content,
    )
    experiment = policy.build_experiment(
        investigation=investigation,
        branch=branches[0],
        result=valid,
    )
    assert experiment.kind == "investigation"

    generation_request = replace(reasoning, kind="hypothesis-generation")
    generation = ReasoningResult.propose(
        request=generation_request,
        content={
            "hypotheses": [
                {
                    "statement": "one",
                    "causal_model": {},
                    "predictions": [{}],
                    "confidence": 0.5,
                },
                {
                    "statement": "two",
                    "causal_model": {},
                    "predictions": [{}],
                    "confidence": 0.5,
                },
            ]
        },
    )
    with pytest.raises(ValueError, match="exact reasoning kind"):
        policy.build_experiment(investigation=investigation, branch=branches[0], result=generation)

    for authority in (
        {"steps": [{"target-change": {"enabled": True}}]},
        {"steps": ({"implementation": "hidden"},)},
        {"targetChange": {"kind": "mutation"}},
        {"Target Change": {"kind": "mutation"}},
        {"TARGETChange": {"kind": "mutation"}},
        {"proposed.change": {"kind": "mutation"}},
        {"target_changes": {"kind": "mutation"}},
        {"targetchange": {"kind": "mutation"}},
        {"changeTarget": {"kind": "mutation"}},
        {"targetMutation": {"kind": "mutation"}},
        {"ｔａｒｇｅｔChange": {"kind": "mutation"}},
        {"implementationPlan": {"steps": ("apply-patch-to-target",)}},
        {"operation": "mutate-target", "steps": ("apply-patch-to-target",)},
    ):
        exact = valid.content["experiments"][0]
        drifted = replace(
            valid,
            content=FrozenMap(
                {
                    "experiments": (
                        FrozenMap(
                            {
                                "objective": exact["objective"],
                                "design": FrozenMap(authority),
                                "criteria": exact["criteria"],
                                "requested_measurements": ("signal",),
                            }
                        ),
                    )
                }
            ),
        )
        with pytest.raises(ValueError, match="closed observation-only schema"):
            policy.build_experiment(
                investigation=investigation,
                branch=branches[0],
                result=drifted,
            )

    proposal = valid.content["experiments"][0]
    wrong_objective = replace(
        valid,
        content={"experiments": (FrozenMap({**proposal, "objective": "apply-patch-to-target"}),)},
    )
    with pytest.raises(ValueError, match="exact observation-only request"):
        policy.build_experiment(
            investigation=investigation,
            branch=branches[0],
            result=wrong_objective,
        )
    wrong_method = replace(
        valid,
        content={
            "experiments": (
                FrozenMap(
                    {
                        **proposal,
                        "design": FrozenMap({"method": "mutate", "measurements": ("signal",)}),
                    }
                ),
            )
        },
    )
    with pytest.raises(ValueError, match="observation-only"):
        policy.build_experiment(
            investigation=investigation,
            branch=branches[0],
            result=wrong_method,
        )

    class _MethodEqualitySpoof(str):
        def __hash__(self) -> int:
            return hash("measure")

        def __eq__(self, other: object) -> bool:
            return str(other) == "measure"

    spoofed_method = _MethodEqualitySpoof("mutate")
    with pytest.raises(ValueError, match="observation-only"):
        make_investigation_observation_content(
            reasoning,
            measurements=("signal",),
            method=spoofed_method,
        )
    direct_method_spoof = replace(
        valid,
        content={
            "experiments": (
                FrozenMap(
                    {
                        **proposal,
                        "design": FrozenMap(
                            {
                                "method": spoofed_method,
                                "measurements": ("signal",),
                            }
                        ),
                    }
                ),
            )
        },
    )
    with pytest.raises(ValueError, match="observation-only"):
        policy.build_experiment(
            investigation=investigation,
            branch=branches[0],
            result=direct_method_spoof,
        )

    class _MeasurementEqualitySpoof(str):
        def __hash__(self) -> int:
            return hash("signal")

        def __eq__(self, other: object) -> bool:
            return str(other) == "signal"

    spoofed_measurement = _MeasurementEqualitySpoof("mutate")
    with pytest.raises(ValueError, match="bounded identifier values"):
        make_investigation_observation_content(
            reasoning,
            measurements=(spoofed_measurement,),
        )
    direct_measurement_spoof = replace(
        valid,
        content={
            "experiments": (
                FrozenMap(
                    {
                        **proposal,
                        "design": FrozenMap(
                            {
                                "method": "measure",
                                "measurements": (spoofed_measurement,),
                            }
                        ),
                        "requested_measurements": (spoofed_measurement,),
                    }
                ),
            )
        },
    )
    with pytest.raises(ValueError, match="bounded identifier values"):
        policy.build_experiment(
            investigation=investigation,
            branch=branches[0],
            result=direct_measurement_spoof,
        )

    for criteria, message in (
        (
            FrozenMap({**proposal["criteria"], "decision": "apply-patch"}),
            "closed evidence schema",
        ),
        (
            FrozenMap(
                {
                    **proposal["criteria"],
                    "minimum_evidence_items": True,
                }
            ),
            "one or more canonical evidence items",
        ),
        (
            FrozenMap(
                {
                    **proposal["criteria"],
                    "accepted_relationships": ("support",),
                }
            ),
            "canonical evidence relationships",
        ),
    ):
        malformed = replace(
            valid,
            content={"experiments": (FrozenMap({**proposal, "criteria": criteria}),)},
        )
        with pytest.raises(ValueError, match=message):
            policy.build_experiment(
                investigation=investigation,
                branch=branches[0],
                result=malformed,
            )

    drifted_measurement = replace(
        valid,
        content={"experiments": (FrozenMap({**proposal, "requested_measurements": ("other",)}),)},
    )
    with pytest.raises(ValueError, match="drifted across proposal fields"):
        policy.build_experiment(
            investigation=investigation,
            branch=branches[0],
            result=drifted_measurement,
        )


def test_progress_updates_and_public_entrypoints_reject_mismatched_types() -> None:
    (
        _,
        _,
        _,
        _,
        investigation,
        _,
        branches,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
    ) = _context()
    workflow = InvestigationWorkflow()
    started = workflow.start(investigation)
    progress = started.progress

    with pytest.raises(TypeError, match="InvestigationRequest"):
        InvestigationProgress(investigation="request", state=progress.state, branches=())
    with pytest.raises(TypeError, match="RunState"):
        InvestigationProgress(investigation=investigation, state="state", branches=())
    with pytest.raises(ValueError, match="runtime does not match"):
        other_run = replace(investigation.canonical_run(), run_id="other")
        InvestigationProgress(
            investigation=investigation,
            state=RuntimeEngine.start(other_run).state,
            branches=(),
        )
    with pytest.raises(TypeError, match="InvestigationBranch"):
        replace(progress, branches=("branch",))
    with pytest.raises(ValueError, match="branch ids must be unique"):
        replace(
            progress, branches=(branches[0], replace(branches[1], branch_id=branches[0].branch_id))
        )
    with pytest.raises(TypeError, match="InvestigationProgress"):
        InvestigationUpdate(progress="progress", transitions=())
    with pytest.raises(TypeError, match="Transition"):
        InvestigationUpdate(progress=progress, transitions=("transition",))
    with pytest.raises(TypeError, match="start requires"):
        workflow.start("request")
    with pytest.raises(TypeError, match="resume requires an InvestigationRequest"):
        workflow.resume("request", progress.state)
    with pytest.raises(TypeError, match="resume requires a RunState"):
        workflow.resume(investigation, "state")
    with pytest.raises(TypeError, match="step requires"):
        workflow.step("progress")
    with pytest.raises(TypeError, match="submission requires"):
        workflow.submit("progress", "result")
    with pytest.raises(ValueError, match="exact pending action"):
        workflow.submit(progress, "result")


def test_managed_capability_requirements_are_checked_at_the_exact_frontier() -> None:
    (
        _,
        _,
        _,
        _,
        investigation,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
    ) = _context()
    workflow = InvestigationWorkflow()
    started = workflow.start(investigation)
    with pytest.raises(TypeError, match="requires a Reasoner"):
        workflow.run_managed(started.progress)

    designed = workflow.submit(
        started.progress,
        _design_result(started.progress.state.pending_actions[0]),
    )
    with pytest.raises(TypeError, match="require an Experimenter"):
        workflow.run_managed(designed.progress)
