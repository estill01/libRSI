from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from librsi import (
    Action,
    ActionResult,
    CapabilityDispatcher,
    CapabilityRegistry,
    CapabilityRoute,
    Evidence,
    ExperimentSpec,
    Hypothesis,
    InvestigationEvidenceBatch,
    InvestigationExperimentRequest,
    InvestigationFrontier,
    InvestigationPolicy,
    InvestigationRequest,
    InvestigationWorkflow,
    Question,
    ReasoningResult,
    RSICapabilityError,
    SQLiteKnowledgeStore,
    TargetRef,
    TargetSnapshot,
    investigation_design_reasoning_action,
    investigation_experiment_request_from_action,
    make_investigation_experiment_action,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action_result,
    reasoning_request_from_action,
)


def _bound_context():
    target = TargetRef(target_id="reactor", kind="physical-system")
    stale = TargetSnapshot(target=target, revision="old", state={"temperature": 20})
    current = TargetSnapshot(target=target, revision="current", state={"temperature": 25})
    question = Question(prompt="Which mechanism controls the reaction?", target=target)
    hypotheses = tuple(
        Hypothesis(
            statement=f"Mechanism {index} controls the reaction",
            target=target,
            causal_model={"mechanism": index},
            predictions=({"marker": index},),
            source_refs=(question.ref,),
            status="proposed",
            lineage=(question.ref,),
        )
        for index in (1, 2)
    )
    request = InvestigationRequest.for_question(
        investigation_id="knowledge-investigation",
        question=question,
        target_snapshot=current,
        initial_hypotheses=hypotheses,
        portfolio_mode="sequential",
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    return stale, current, hypotheses, request


def _stored_evidence(hypothesis: Hypothesis, snapshot: TargetSnapshot, kind: str, index: int):
    return Evidence(
        evidence_type=kind,
        data={"sample": index},
        subject_refs=(hypothesis.ref,),
        source_refs=(snapshot.ref,),
        target_snapshot=snapshot,
        weight=1.0,
    )


def test_current_knowledge_can_answer_without_new_reasoning_or_experiments(
    tmp_path: Path,
) -> None:
    stale, current, hypotheses, request = _bound_context()
    with SQLiteKnowledgeStore(tmp_path / "investigation-knowledge.sqlite") as store:
        for hypothesis, relationship in zip(
            hypotheses,
            ("support", "counterexample"),
            strict=True,
        ):
            store.put(_stored_evidence(hypothesis, stale, relationship, 0))
            store.put(_stored_evidence(hypothesis, current, relationship, 1))
            store.put(_stored_evidence(hypothesis, current, relationship, 2))
        update = InvestigationWorkflow().start(request, knowledge_store=store)

        assert update.progress.result is not None
        assert update.progress.result.disposition == "answered"
        assert tuple(branch.status for branch in update.progress.branches) == (
            "supported",
            "rejected",
        )
        assert all(len(branch.evidence) == 2 for branch in update.progress.branches)
        assert all(not branch.gathered_evidence_refs for branch in update.progress.branches)
        assert update.progress.state.actions == ()
        assert tuple(item.event.kind for item in update.transitions) == (
            "run_started",
            "run_completed",
        )
        resumed = InvestigationWorkflow().resume(
            request,
            update.progress.state,
            knowledge_store=store,
        )
        assert resumed.progress == update.progress
        assert resumed.transitions == ()


class _DesignReasoner:
    def __init__(self) -> None:
        self.calls = 0

    def reason(self, action: Action) -> ActionResult:
        self.calls += 1
        request = reasoning_request_from_action(action)
        proposal = ReasoningResult.propose(
            request=request,
            content=make_investigation_observation_content(
                request,
                measurements=("marker",),
            ),
        )
        return make_reasoning_action_result(action=action, result=proposal)


def _waiting_experiment():
    _, _, _, request = _bound_context()
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    reasoner = _DesignReasoner()
    designed = workflow.submit(
        started.progress,
        reasoner.reason(started.progress.state.pending_actions[0]),
    )
    return request, workflow, designed


def _experiment_result(action: Action) -> ActionResult:
    request = investigation_experiment_request_from_action(action)
    evidence = tuple(
        Evidence(
            evidence_type="counterexample",
            data={"sample": sample},
            subject_refs=(request.branch.hypothesis.ref,),
            source_refs=(request.experiment.ref,),
            target_snapshot=request.investigation.target_snapshot,
            weight=1.0,
        )
        for sample in (1, 2)
    )
    return make_investigation_experiment_result(
        action=action,
        batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
    )


def test_investigation_submission_is_owned_exclusively_by_workflow() -> None:
    _, workflow, designed = _waiting_experiment()
    action = designed.progress.state.pending_actions[0]
    result = _experiment_result(action)
    with pytest.raises(RSICapabilityError, match="owned by InvestigationWorkflow"):
        CapabilityDispatcher(
            CapabilityRegistry(
                routes=(
                    CapabilityRoute(
                        action_kind="investigation-experiment",
                        family="experimenter",
                        posture="external",
                    ),
                )
            )
        )

    dispatcher = CapabilityDispatcher(CapabilityRegistry())
    prior_results = designed.progress.state.results
    with pytest.raises(RSICapabilityError, match="submitted through InvestigationWorkflow"):
        dispatcher.submit(designed.progress.state, result)
    assert designed.progress.state.results == prior_results

    submitted = workflow.submit(designed.progress, result)
    assert submitted.progress.state.results[-1] == result

    malformed = replace(result, payload={"narrative": "the hypothesis is false"})
    with pytest.raises(RSICapabilityError, match="submitted through InvestigationWorkflow"):
        dispatcher.submit(designed.progress.state, malformed)


def test_dispatcher_rejects_forbidden_investigation_design_before_transition() -> None:
    _, _, _, request = _bound_context()
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    reasoning = reasoning_request_from_action(action)
    valid = _DesignReasoner().reason(action)
    with pytest.raises(RSICapabilityError, match="owned by InvestigationWorkflow"):
        CapabilityDispatcher(
            CapabilityRegistry(
                routes=(
                    CapabilityRoute(
                        action_kind="investigation-reason",
                        family="reasoner",
                        posture="automatic",
                    ),
                )
            )
        )
    dispatcher = CapabilityDispatcher(CapabilityRegistry())
    with pytest.raises(RSICapabilityError, match="submitted through InvestigationWorkflow"):
        dispatcher.submit(started.progress.state, valid)
    direct = workflow.submit(started.progress, valid)
    assert direct.progress.state.results[-1] == valid

    forbidden = ReasoningResult.propose(
        request=reasoning,
        content={
            "experiments": [
                {
                    "objective": reasoning.context["required_objective"],
                    "design": {"operation": "mutate target", "steps": ["apply patch"]},
                    "criteria": reasoning.context["required_criteria"],
                    "requested_measurements": ["marker"],
                }
            ]
        },
    )
    malformed = make_reasoning_action_result(action=action, result=forbidden)
    with pytest.raises(ValueError, match="closed observation-only schema"):
        workflow.submit(started.progress, malformed)
    assert started.progress.state.results == ()


def test_out_of_order_design_and_experiment_frontiers_fail_before_transition() -> None:
    _, _, _, request = _bound_context()
    workflow = InvestigationWorkflow()
    started = workflow.start(request)
    branches = started.progress.branches
    second = branches[1]
    out_of_order_frontier = InvestigationFrontier.for_branch(
        investigation=request,
        branches=branches,
        selected_branch_id=second.branch_id,
    )
    with pytest.raises(ValueError, match="canonical policy frontier"):
        investigation_design_reasoning_action(out_of_order_frontier)
    assert started.progress.state.results == ()

    experiment = ExperimentSpec(
        experiment_id="out-of-order-second-branch",
        kind="investigation",
        target_snapshot=request.target_snapshot,
        design={"method": "measure", "measurements": ("marker",)},
        criteria={"accepted_relationships": ("support",), "minimum_evidence_items": 1},
        requested_measurements=("marker",),
        lineage=(second.hypothesis.ref,),
    )
    designed_second = InvestigationPolicy().add_experiment(second, experiment)
    designed_roster = (branches[0], designed_second)
    experiment_frontier = InvestigationFrontier.for_branch(
        investigation=request,
        branches=designed_roster,
        selected_branch_id=designed_second.branch_id,
    )
    experiment_request = InvestigationExperimentRequest.for_frontier(
        frontier=experiment_frontier,
        sequence=1,
    )
    with pytest.raises(ValueError, match="canonical policy frontier"):
        make_investigation_experiment_action(
            run=request.canonical_run(),
            request=experiment_request,
        )
    assert started.progress.state.results == ()


def test_reserved_investigation_routes_are_rejected_for_every_family() -> None:
    with pytest.raises(RSICapabilityError, match="owned by InvestigationWorkflow"):
        CapabilityDispatcher(
            CapabilityRegistry(
                routes=(
                    CapabilityRoute(
                        action_kind="investigation-experiment",
                        family="reasoner",
                        posture="external",
                    ),
                )
            )
        )
