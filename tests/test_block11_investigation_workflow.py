from __future__ import annotations

from librsi import (
    Action,
    ActionResult,
    Evidence,
    InvestigationEvidenceBatch,
    InvestigationRequest,
    InvestigationWorkflow,
    Question,
    ReasoningResult,
    investigate,
    investigation_experiment_request_from_action,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action_result,
    reasoning_request_from_action,
)


class _CompetingReasoner:
    def __init__(self) -> None:
        self.requests = []

    def reason(self, action: Action) -> ActionResult:
        request = reasoning_request_from_action(action)
        self.requests.append(request)
        if request.kind == "hypothesis-generation":
            content = {
                "hypotheses": [
                    {
                        "statement": "The inlet is limiting the observed rate",
                        "causal_model": {"cause": "inlet"},
                        "predictions": [{"signal": "inlet-pressure"}],
                        "confidence": 0.9,
                    },
                    {
                        "statement": "The outlet is limiting the observed rate",
                        "causal_model": {"cause": "outlet"},
                        "predictions": [{"signal": "outlet-pressure"}],
                        "confidence": 0.1,
                    },
                ]
            }
        else:
            content = make_investigation_observation_content(
                request,
                measurements=("pressure-response",),
            )
        proposal = ReasoningResult.propose(request=request, content=content)
        return make_reasoning_action_result(action=action, result=proposal)


class _FalsifyFirstExperimenter:
    def __init__(self) -> None:
        self.requests = []

    def experiment(self, action: Action) -> ActionResult:
        request = investigation_experiment_request_from_action(action)
        self.requests.append(request)
        relationship = "counterexample" if request.branch.branch_id == "hypothesis-1" else "support"
        evidence = tuple(
            Evidence(
                evidence_type=relationship,
                data={"sample": sample, "branch": request.branch.branch_id},
                subject_refs=(request.branch.hypothesis.ref,),
                source_refs=(request.experiment.ref,),
                target_snapshot=request.investigation.target_snapshot,
                weight=1.0,
            )
            for sample in (1, 2)
        )
        batch = InvestigationEvidenceBatch.collected(request=request, evidence=evidence)
        return make_investigation_experiment_result(action=action, batch=batch)


def test_investigate_falsifies_one_branch_and_retains_supported_alternative() -> None:
    reasoner = _CompetingReasoner()
    experimenter = _FalsifyFirstExperimenter()
    result = investigate(
        question=Question(prompt="What limits the observed process rate?"),
        investigation_id="competing-causes",
        reasoner=reasoner,
        experimenter=experimenter,
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )

    assert result.disposition == "answered"
    assert result.stop_reason == "sufficient"
    assert tuple(branch.status for branch in result.branches) == ("rejected", "supported")
    assert tuple(item.statement for item in result.findings) == (
        "The outlet is limiting the observed rate",
    )
    assert result.findings[0].evidence_refs == result.branches[1].belief.evidence_refs
    assert result.unresolved == ()
    assert result.run == result.investigation.canonical_run().ref
    assert all(
        branch.belief.confidence != branch.hypothesis.confidence for branch in result.branches
    )
    assert result.branches[0].hypothesis.status == "proposed"
    assert result.branches[1].hypothesis.status == "proposed"


def test_parallel_portfolio_round_robins_design_before_execution() -> None:
    request = InvestigationRequest.for_question(
        investigation_id="parallel-round-robin",
        question=Question(prompt="Which mechanism dominates?"),
        portfolio_mode="parallel",
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    workflow = InvestigationWorkflow()
    completed = workflow.run_managed(
        workflow.start(request).progress,
        reasoner=_CompetingReasoner(),
        experimenter=_FalsifyFirstExperimenter(),
    )

    assert completed.progress.result is not None
    assert tuple(action.action_id for action in completed.progress.state.actions) == (
        "investigation-hypotheses",
        "investigation-design-hypothesis-1-1",
        "investigation-design-hypothesis-2-1",
        "investigation-experiment-hypothesis-1-2",
        "investigation-experiment-hypothesis-2-2",
    )


def test_sequential_portfolio_completes_one_lane_before_the_next() -> None:
    request = InvestigationRequest.for_question(
        investigation_id="sequential-lanes",
        question=Question(prompt="Which mechanism dominates?"),
        portfolio_mode="sequential",
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    workflow = InvestigationWorkflow()
    completed = workflow.run_managed(
        workflow.start(request).progress,
        reasoner=_CompetingReasoner(),
        experimenter=_FalsifyFirstExperimenter(),
    )

    assert completed.progress.result is not None
    assert tuple(action.action_id for action in completed.progress.state.actions) == (
        "investigation-hypotheses",
        "investigation-design-hypothesis-1-1",
        "investigation-experiment-hypothesis-1-1",
        "investigation-design-hypothesis-2-1",
        "investigation-experiment-hypothesis-2-2",
    )
    assert completed.progress.state.action_count == 5


class _RedesignExperimenter:
    def __init__(self) -> None:
        self.iterations: list[int] = []

    def experiment(self, action: Action) -> ActionResult:
        request = investigation_experiment_request_from_action(action)
        iteration = len(request.branch.experiments)
        self.iterations.append(iteration)
        relationship = "null" if iteration == 1 else "support"
        weight = 0.0 if relationship == "null" else 1.0
        count = 1 if relationship == "null" else 2
        evidence = tuple(
            Evidence(
                evidence_type=relationship,
                data={"iteration": iteration, "sample": sample},
                subject_refs=(request.branch.hypothesis.ref,),
                source_refs=(request.experiment.ref,),
                weight=weight,
            )
            for sample in range(count)
        )
        return make_investigation_experiment_result(
            action=action,
            batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
        )


def test_inconclusive_evidence_redesigns_before_stopping() -> None:
    reasoner = _CompetingReasoner()
    experimenter = _RedesignExperimenter()
    result = investigate(
        question=Question(prompt="Which explanation survives a redesigned measurement?"),
        investigation_id="redesign-inconclusive",
        portfolio_mode="sequential",
        reasoner=reasoner,
        experimenter=experimenter,
        max_hypotheses=2,
        max_experiments=4,
        max_redesigns_per_hypothesis=1,
    )

    assert experimenter.iterations == [1, 2, 1, 2]
    assert any(
        request.kind == "experiment-design" and request.context["design_iteration"] == 2
        for request in reasoner.requests
    )
    redesign = next(
        request
        for request in reasoner.requests
        if request.kind == "experiment-design" and request.context["design_iteration"] == 2
    )
    assert redesign.context["prior_experiment_root"] is not None
    assert len(redesign.context["evidence_roots"]) == 1
    assert all(request.kind != "intervention-generation" for request in reasoner.requests)
    assert result.disposition == "answered"
    assert all(branch.status == "supported" for branch in result.branches)
