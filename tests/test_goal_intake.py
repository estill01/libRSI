from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import CapabilityBinding, Metric, TargetRef, TargetSnapshot, record_from_dict
from librsi.intake import (
    IntakeAdapter,
    IntakeContext,
    IntakeMetric,
    IntakeNeedsInformation,
    IntakeRequest,
)
from librsi.reasoning import ReasoningResult
from librsi.service import LibRSIService


class Proposer:
    """Deterministic transport fixture; tests do not claim live model quality."""

    def __init__(self, *, workflow="improvement", overrides=None):
        self.calls = []
        self.workflow = workflow
        self.overrides = overrides or {}

    def respond(self, request):
        self.calls.append(request)
        content = {
            "intake-routing": {"adapter_id": "prompts-v1", "questions": []},
            "goal-operationalization": {
                "workflow": self.workflow,
                "metric_id": "accuracy",
                "minimum_effect": 0.05,
                "question": "Do missing examples or ambiguous instructions explain the failures?",
                "questions": [],
            },
            "hypothesis-generation": {
                "hypotheses": [
                    {
                        "statement": "Missing examples cause errors",
                        "causal_model": {"change": "examples"},
                        "predictions": [{"test": "examples increase accuracy"}],
                        "confidence": 0.6,
                    },
                    {
                        "statement": "Ambiguous instructions cause errors",
                        "causal_model": {"change": "clarify"},
                        "predictions": [{"test": "clarity increases accuracy"}],
                        "confidence": 0.6,
                    },
                ]
            },
        }[request.kind]
        content = self.overrides.get(request.kind, content)
        if isinstance(content, Exception):
            raise content
        return ReasoningResult.propose(request=request, content=content)


def observed():
    snapshot = TargetSnapshot(
        target=TargetRef(target_id="support-prompt", kind="prompt"),
        revision="1",
        state={"prompt": "Answer the question"},
    )
    return IntakeContext(
        snapshot=snapshot,
        metrics=(
            IntakeMetric(
                Metric(
                    metric_id="accuracy", direction="increase", role="objective", unit="fraction"
                ),
                0.5,
                0.05,
                "Accuracy on the host's labelled task set",
            ),
        ),
        facts={"training_failures": ["ambiguous answer"]},
    )


def adapters(collect=None):
    collect = collect or (lambda request: observed())
    capabilities = (
        CapabilityBinding(action_kind="improvement-cycle", family="reasoner", posture="external"),
        CapabilityBinding(
            action_kind="investigation-reason", family="reasoner", posture="external"
        ),
        CapabilityBinding(
            action_kind="investigation-experiment", family="experimenter", posture="external"
        ),
    )
    return (
        IntakeAdapter("prompts-v1", "Prompt quality and failures", collect, capabilities),
        IntakeAdapter("search-v1", "Search ranking configurations", collect, capabilities),
    )


def service(path, proposer=None, collect=None):
    return LibRSIService.local(
        path, intake_backend=proposer or Proposer(), intake_adapters=adapters(collect)
    )


def test_broad_goal_becomes_measured_native_request_and_survives_restart(tmp_path):
    proposer = Proposer()
    request = IntakeRequest("prompt-1", "Make this prompt more useful", {"audience": "support"})
    with service(tmp_path, proposer) as first:
        result = first.intake(request)["data"]
        assert result["disposition"] == "started"
        assert result["run_id"] == "prompt-1:improvement"
        assert len(result["hypotheses"]) == 2
        binding = first.controller.agent_store.load_run(result["run_id"])
        assert binding.request.contract.goal.statement == request.goal
        assert binding.request.contract.baseline.measurements["accuracy"] == 0.5
        assert binding.request.contract.objectives[0].minimum_effect == 0.05
        assert binding.request.apply is False
        assert len(proposer.calls) == 3
        assert first.intake(request)["data"] == result
        assert len(proposer.calls) == 3
        assert proposer.calls[1].context["observations"]["facts"]["training_failures"] == (
            "ambiguous answer",
        )
    no_calls = Proposer()
    with service(tmp_path, no_calls) as restarted:
        assert restarted.intake(request)["data"] == result
        assert restarted.intake_status(request.request_id)["data"] == result
        assert restarted.get_status(result["run_id"])["data"]["terminal"] is False
        assert no_calls.calls == []
        with pytest.raises(ValueError, match="different input"):
            restarted.intake(replace(request, goal="Different goal"))


@pytest.mark.parametrize("phase", ["intake-routing", "goal-operationalization", "collector"])
def test_missing_information_creates_no_run_and_returns_specific_questions(tmp_path, phase):
    questions = ["Which labelled task set defines success?"]
    override = (
        {"adapter_id": None, "questions": questions}
        if phase == "intake-routing"
        else {
            "workflow": None,
            "metric_id": None,
            "minimum_effect": None,
            "question": None,
            "questions": questions,
        }
    )
    proposer = Proposer(overrides={phase: override})

    def collect(request):
        if phase == "collector":
            raise IntakeNeedsInformation(*questions)
        return observed()

    with service(tmp_path, proposer, collect) as engine:
        request = IntakeRequest("clarify", "Improve this")
        result = engine.intake(request)["data"]
        assert result["disposition"] == "needs-information"
        assert result["questions"] == questions
        assert result["run_id"] is None
        calls = len(proposer.calls)
        assert engine.intake(request)["data"] == result
        assert len(proposer.calls) == calls
        assert engine.controller.agent_store.get_admission("clarify:admission") is None


@pytest.mark.parametrize("field,value", [("metric_id", "imaginary"), ("minimum_effect", 0.001)])
def test_model_cannot_invent_metrics_or_weaken_host_floor(tmp_path, field, value):
    plan = {
        "workflow": "improvement",
        "metric_id": "accuracy",
        "minimum_effect": 0.05,
        "question": "Why the failures?",
        "questions": [],
    }
    plan[field] = value
    with service(tmp_path, Proposer(overrides={"goal-operationalization": plan})) as engine:
        with pytest.raises(ValueError, match="unregistered metric|weakened"):
            engine.intake(IntakeRequest("invalid", "Improve accuracy"))
        assert engine.controller.agent_store.get_admission("invalid:admission") is None


def test_routing_is_allowlisted_and_explicit_adapter_skips_routing_call(tmp_path):
    bad = Proposer(overrides={"intake-routing": {"adapter_id": "shell", "questions": []}})
    with (
        service(tmp_path / "bad", bad) as engine,
        pytest.raises(ValueError, match="unregistered adapter"),
    ):
        engine.intake(IntakeRequest("unknown", "Improve everything"))
    proposer = Proposer()
    with service(tmp_path / "good", proposer) as engine:
        result = engine.intake(IntakeRequest("known", "Improve ranking", adapter_id="search-v1"))
        assert result["data"]["adapter_id"] == "search-v1"
        assert [call.kind for call in proposer.calls] == [
            "goal-operationalization",
            "hypothesis-generation",
        ]


def test_context_collection_is_bounded_before_it_reaches_model(tmp_path):
    proposer = Proposer()
    with service(
        tmp_path, proposer, lambda request: replace(observed(), facts={"bulk": "x" * 300_000})
    ) as engine:
        with pytest.raises(ValueError, match="byte limit"):
            engine.intake(IntakeRequest("large", "Improve accuracy", adapter_id="prompts-v1"))
        assert proposer.calls == []


def test_request_identity_distinguishes_integer_and_float_context(tmp_path):
    with service(tmp_path) as engine:
        request = IntakeRequest("typed", "Improve accuracy", {"setting": 1})
        engine.intake(request)
        with pytest.raises(ValueError, match="different input"):
            engine.intake(replace(request, context={"setting": 1.0}))


def test_adapter_policy_changes_cannot_reinterpret_an_unfinished_intake(tmp_path):
    request = IntakeRequest("policy", "Improve accuracy")
    with (
        service(
            tmp_path, Proposer(overrides={"hypothesis-generation": RuntimeError("interrupted")})
        ) as engine,
        pytest.raises(RuntimeError, match="interrupted"),
    ):
        engine.intake(request)
    changed = tuple(replace(adapter, max_hypotheses=3) for adapter in adapters())
    backend = Proposer()
    with LibRSIService.local(tmp_path, intake_backend=backend, intake_adapters=changed) as engine:
        with pytest.raises(ValueError, match="configuration changed"):
            engine.intake(request)
        assert backend.calls == []


def test_registered_guardrails_and_constraints_survive_goal_translation(tmp_path):
    from librsi import Constraint, Guardrail

    base = observed()
    constraint = Constraint(statement="Do not increase latency", target=base.snapshot.target)
    guardrail = Guardrail.create(
        guardrail_id="latency",
        metric=Metric(metric_id="latency", direction="decrease", role="guardrail", unit="ms"),
        semantics="no-regression",
        constraint=constraint,
    )
    context = replace(
        base,
        constraints=(constraint,),
        guardrails=(guardrail,),
        guardrail_measurements={"latency": 100.0},
    )
    with service(tmp_path, collect=lambda request: context) as engine:
        result = engine.intake(IntakeRequest("guarded", "Improve accuracy"))["data"]
        contract = record_from_dict(result["criteria"])
        assert contract.constraints == (constraint,)
        assert contract.guardrails == (guardrail,)
        assert contract.baseline.measurements["latency"] == 100.0


def test_target_drift_during_planning_is_rejected(tmp_path):
    reads = []

    def collect(request):
        result = observed()
        reads.append(request)
        return (
            result
            if len(reads) == 1
            else replace(result, snapshot=replace(result.snapshot, revision="2"))
        )

    with service(tmp_path, collect=collect) as engine:
        with pytest.raises(ValueError, match="target changed"):
            engine.intake(IntakeRequest("drift", "Improve accuracy"))
        assert engine.controller.agent_store.get_admission("drift:admission") is None


def test_completed_reasoning_is_reused_after_provider_failure(tmp_path):
    first = Proposer(overrides={"hypothesis-generation": RuntimeError("provider unavailable")})
    request = IntakeRequest("resume", "Improve accuracy")
    with service(tmp_path, first) as engine:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            engine.intake(request)
        assert engine.intake_status("resume")["data"]["disposition"] == "pending"
    recovered = Proposer()
    with service(tmp_path, recovered) as engine:
        assert engine.intake(request)["data"]["disposition"] == "started"
        assert [call.kind for call in recovered.calls] == ["hypothesis-generation"]


def test_crash_after_native_start_does_not_start_a_second_run(tmp_path, monkeypatch):
    request = IntakeRequest("receipt", "Improve accuracy")
    with service(tmp_path) as engine:
        save = engine._intake.store.save

        def crash(request_id, receipt):
            if "result" in receipt:
                raise RuntimeError("crash after native start")
            save(request_id, receipt)

        monkeypatch.setattr(engine._intake.store, "save", crash)
        with pytest.raises(RuntimeError, match="crash after"):
            engine.intake(request)
        original = engine.get_run("receipt:improvement")["state_root"]
    proposer = Proposer()
    with service(tmp_path, proposer) as restarted:
        assert restarted.intake(request)["data"]["run_id"] == "receipt:improvement"
        assert restarted.get_run("receipt:improvement")["state_root"] == original
        assert proposer.calls == []


@pytest.mark.slow
def test_intake_investigation_runs_through_existing_experiment_protocol(tmp_path):
    from librsi import Evidence
    from librsi.investigation import (
        InvestigationEvidenceBatch,
        investigation_experiment_request_from_action,
        make_investigation_experiment_result,
    )
    from librsi.investigation.policy import make_investigation_observation_content
    from librsi.reasoning import make_reasoning_action_result, reasoning_request_from_action

    with service(tmp_path, Proposer(workflow="investigation")) as engine:
        result = engine.intake(IntakeRequest("diagnose", "Investigate the failures"))["data"]
        run_id = result["run_id"]
        for _ in range(6):
            if engine.get_status(run_id)["data"]["terminal"]:
                break
            action = record_from_dict(engine.next_actions(run_id)["data"]["action"])
            if action.kind == "investigation-reason":
                request = reasoning_request_from_action(action)
                output = make_reasoning_action_result(
                    action=action,
                    result=ReasoningResult.propose(
                        request=request,
                        content=make_investigation_observation_content(
                            request, measurements=("accuracy",)
                        ),
                    ),
                )
            else:
                request = investigation_experiment_request_from_action(action)
                relationship = (
                    "support" if request.branch.branch_id == "hypothesis-1" else "counterexample"
                )
                evidence = tuple(
                    Evidence(
                        evidence_type=relationship,
                        data={"trial": trial},
                        weight=1.0,
                        subject_refs=(request.branch.hypothesis.ref,),
                        source_refs=(request.experiment.ref,),
                        target_snapshot=request.investigation.target_snapshot,
                    )
                    for trial in range(2)
                )
                output = make_investigation_experiment_result(
                    action=action,
                    batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
                )
            engine.submit_result(run_id, output, authority="external")
        outcome = engine.get_outcome(run_id)
        result = record_from_dict(outcome["data"]["projection"]["result"])
        assert {branch.status for branch in result.branches} == {"supported", "rejected"}
