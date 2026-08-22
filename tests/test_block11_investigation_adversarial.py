from __future__ import annotations

from pathlib import Path

import pytest

from librsi import (
    Action,
    ActionResult,
    BeliefState,
    EpistemicPolicy,
    Evidence,
    ExperimentSpec,
    Hypothesis,
    InvestigationEvidenceBatch,
    InvestigationExperimentRequest,
    InvestigationPolicy,
    InvestigationProgress,
    InvestigationRequest,
    InvestigationWorkflow,
    LinearEvidenceAggregator,
    PortfolioPolicy,
    Question,
    ReasoningRequest,
    ReasoningResult,
    Run,
    RunBudget,
    RuntimeEngine,
    SQLiteKnowledgeStore,
    investigation_experiment_request_from_action,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action,
    make_reasoning_action_result,
    reasoning_request_from_action,
)


def _seeded():
    question = Question(prompt="Which competing cause explains the signal?")
    hypotheses = tuple(
        Hypothesis(
            statement=f"Cause {index} explains the signal",
            causal_model={"cause": index},
            predictions=({"signal": index},),
            source_refs=(question.ref,),
            confidence=0.5,
            status="proposed",
            lineage=(question.ref,),
        )
        for index in (1, 2)
    )
    request = InvestigationRequest.for_question(
        investigation_id="adversarial-investigation",
        question=question,
        initial_hypotheses=hypotheses,
        portfolio_mode="sequential",
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    return question, hypotheses, request, workflow, started


def _design_result(action: Action, *, design=None) -> ActionResult:
    request = reasoning_request_from_action(action)
    content = make_investigation_observation_content(
        request,
        measurements=("signal",),
    )
    if design is not None:
        content["experiments"][0]["design"] = design  # type: ignore[index]
    proposal = ReasoningResult.propose(
        request=request,
        content=content,
    )
    return make_reasoning_action_result(action=action, result=proposal)


class _CountingReasoner:
    def __init__(self) -> None:
        self.calls = 0

    def reason(self, action: Action) -> ActionResult:
        self.calls += 1
        return _design_result(action)


def test_owned_policy_rejects_subclasses_mutation_and_spoofed_components() -> None:
    class _BranchPromoter(InvestigationPolicy):
        def belief(self, *args, **kwargs):  # pragma: no cover - construction must fail
            return BeliefState(subject_ref=args[1].ref, status="supported", confidence=1.0)

    with pytest.raises(ValueError, match="versioned semantic policy contract"):
        _BranchPromoter()
    with pytest.raises(ValueError, match="versioned semantic policy contract"):
        InvestigationPolicy(
            EpistemicPolicy(LinearEvidenceAggregator(support_scale=0.3)),
            PortfolioPolicy(),
        )

    class _EqualitySpoofPortfolio:
        def __eq__(self, other):
            return True

    with pytest.raises(ValueError, match="versioned semantic policy contract"):
        InvestigationPolicy(
            EpistemicPolicy(),
            _EqualitySpoofPortfolio(),  # type: ignore[arg-type]
        )

    external = InvestigationPolicy()
    workflow = InvestigationWorkflow(external)
    object.__setattr__(
        external,
        "epistemics",
        EpistemicPolicy(LinearEvidenceAggregator(support_scale=0.3)),
    )
    _, _, request, _, _ = _seeded()
    assert workflow.start(request).progress.branches[0].belief.confidence == 0.5


def test_direct_and_managed_paths_reject_injected_branch_state_before_effect() -> None:
    _, _, request, workflow, started = _seeded()
    original = started.progress.branches[0]
    experiment = ExperimentSpec(
        experiment_id="injected-experiment",
        kind="investigation",
        design={"measure": "signal"},
        criteria={"decisive": True},
        requested_measurements=("signal",),
        lineage=(original.hypothesis.ref,),
    )
    designed = InvestigationPolicy().add_experiment(original, experiment)
    gap = InvestigationExperimentRequest.for_branch(
        branches=(designed, started.progress.branches[1]),
        branch=designed,
        sequence=1,
    )
    evidence = tuple(
        Evidence(
            evidence_type="support",
            data={"injected": sample},
            subject_refs=(original.hypothesis.ref,),
            source_refs=(experiment.ref,),
            weight=1.0,
        )
        for sample in (1, 2)
    )
    injected = InvestigationPolicy().apply_batch(
        designed,
        InvestigationEvidenceBatch.collected(request=gap, evidence=evidence),
    )
    forged = InvestigationProgress(
        investigation=request,
        state=started.progress.state,
        branches=(injected, started.progress.branches[1]),
    )
    result = _design_result(started.progress.state.pending_actions[0])
    with pytest.raises(ValueError, match="canonical persisted frontier"):
        workflow.submit(forged, result)
    reasoner = _CountingReasoner()
    with pytest.raises(ValueError, match="canonical persisted frontier"):
        workflow.run_managed(forged, reasoner=reasoner)
    assert reasoner.calls == 0


def test_managed_path_rejects_substituted_intervention_action_before_effect() -> None:
    _, _, request, workflow, started = _seeded()
    expected = started.progress.state.pending_actions[0]
    expected_request = reasoning_request_from_action(expected)
    substituted_request = ReasoningRequest(
        request_id=expected_request.request_id,
        kind="intervention-generation",
        instruction="propose a target change",
        input_refs=expected_request.input_refs,
        target_snapshot=expected_request.target_snapshot,
        context={},
        lineage=expected_request.input_refs,
    )
    substituted_action = make_reasoning_action(
        run=request.canonical_run(),
        action_id=expected.action_id,
        request=substituted_request,
    )
    active = RuntimeEngine.start(request.canonical_run()).state
    waiting = RuntimeEngine.request(active, substituted_action).state
    forged = InvestigationProgress(
        investigation=request,
        state=waiting,
        branches=started.progress.branches,
    )
    reasoner = _CountingReasoner()
    with pytest.raises(ValueError, match="not policy-derived"):
        workflow.run_managed(forged, reasoner=reasoner)
    assert reasoner.calls == 0


def test_managed_path_rejects_drifted_run_budget_before_effect() -> None:
    _, _, request, workflow, started = _seeded()
    canonical_action = started.progress.state.pending_actions[0]
    reasoning = reasoning_request_from_action(canonical_action)
    drifted_run = Run(
        run_id=request.investigation_id,
        intent=request.question.ref,
        budget=RunBudget(max_actions=99, max_failures=99, max_retries=0),
        lineage=(request.ref,),
    )
    drifted_action = make_reasoning_action(
        run=drifted_run,
        action_id=canonical_action.action_id,
        request=reasoning,
    )
    waiting = RuntimeEngine.request(RuntimeEngine.start(drifted_run).state, drifted_action).state
    forged = InvestigationProgress(
        investigation=request,
        state=waiting,
        branches=started.progress.branches,
    )
    reasoner = _CountingReasoner()
    with pytest.raises(ValueError, match="run envelope has drifted"):
        workflow.run_managed(forged, reasoner=reasoner)
    assert reasoner.calls == 0


def test_missing_reused_knowledge_store_fails_before_reasoner_effect(tmp_path: Path) -> None:
    question, hypotheses, request, workflow, _ = _seeded()
    with SQLiteKnowledgeStore(tmp_path / "reused.sqlite") as store:
        for hypothesis in hypotheses:
            store.put(
                Evidence(
                    evidence_type="support",
                    data={"sample": 1},
                    subject_refs=(hypothesis.ref,),
                    source_refs=(question.ref,),
                    weight=1.0,
                )
            )
        started = workflow.start(request, knowledge_store=store)
        result = _design_result(started.progress.state.pending_actions[0])
        with pytest.raises(ValueError, match="not policy-derived"):
            workflow.submit(started.progress, result)
        reasoner = _CountingReasoner()
        with pytest.raises(ValueError, match="not policy-derived"):
            workflow.run_managed(started.progress, reasoner=reasoner)
        assert reasoner.calls == 0
        accepted = workflow.submit(
            started.progress,
            result,
            knowledge_store=store,
        )
        assert accepted.progress.state.action_count == 2


def test_reasoning_cannot_expand_branches_or_smuggle_change_authority() -> None:
    request = InvestigationRequest.for_question(
        investigation_id="bounded-generation",
        question=Question(prompt="Which cause?"),
        max_hypotheses=2,
        max_experiments=2,
    )
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    generation = reasoning_request_from_action(action)
    overflow = ReasoningResult.propose(
        request=generation,
        content={
            "hypotheses": [
                {
                    "statement": f"Cause {index}",
                    "causal_model": {"cause": index},
                    "predictions": [{"signal": index}],
                    "confidence": 0.5,
                }
                for index in (1, 2, 3)
            ]
        },
    )
    with pytest.raises(ValueError, match="bounded competing set"):
        workflow.submit(
            started.progress,
            make_reasoning_action_result(action=action, result=overflow),
        )
    assert started.progress.state.results == ()

    _, _, _, seeded_workflow, seeded = _seeded()
    design_action = seeded.progress.state.pending_actions[0]
    with pytest.raises(ValueError, match="closed observation-only schema"):
        seeded_workflow.submit(
            seeded.progress,
            _design_result(
                design_action,
                design={"intervention": {"kind": "target-change"}},
            ),
        )
    assert seeded.progress.state.results == ()


def test_unavailable_experiments_stop_without_endless_branch_expansion() -> None:
    _, _, _, workflow, started = _seeded()

    class _UnavailableExperimenter:
        def experiment(self, action: Action) -> ActionResult:
            request = investigation_experiment_request_from_action(action)
            return make_investigation_experiment_result(
                action=action,
                batch=InvestigationEvidenceBatch.unavailable(
                    request=request,
                    reason="instrument unavailable",
                ),
            )

    completed = workflow.run_managed(
        started.progress,
        reasoner=_CountingReasoner(),
        experimenter=_UnavailableExperimenter(),
    )
    assert completed.progress.result is not None
    assert completed.progress.result.disposition == "inconclusive"
    assert completed.progress.result.stop_reason == "evidence-unavailable"
    assert all(branch.status == "retired" for branch in completed.progress.branches)
    assert completed.progress.state.action_count == 4
