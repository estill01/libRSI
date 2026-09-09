from __future__ import annotations

import pytest

from librsi import AdaptiveLoop, LearningCase, LearningPolicy, LocalLearningStore, TaskMeasurement
from librsi.comparison import CandidateReview
from librsi.reasoning import ReasoningResult
from librsi.records import Metric
from librsi.rsi import make_review_result, review_command_from_action

from .learning_store_support import ConsumerLearningStore


class Ideas:
    adapter_id = "integer-ideas-v1"

    def __init__(self):
        self.calls = []

    def validate_configuration(self, configuration):
        if set(configuration) != {"offsets"} or not configuration["offsets"]:
            raise ValueError("expected nonempty offsets")
        if any(type(value) is not int for value in configuration["offsets"]):
            raise ValueError("offsets must be integers")

    def evaluate(self, configuration, case):
        self.calls.append((dict(configuration), case.case_id))
        ideas = [case.payload["base"] + offset for offset in configuration["offsets"]]
        loss = min(abs(case.payload["target"] - idea) for idea in ideas)
        return TaskMeasurement({"ideas": ideas}, loss)


class Proposer:
    def __init__(self):
        self.calls = []

    def respond(self, request):
        self.calls.append(request)
        offsets = sorted(
            {item["case"]["target"] - item["case"]["base"] for item in request.context["feedback"]}
        )
        return ReasoningResult.propose(
            request=request,
            content={
                "hypotheses": [
                    {
                        "statement": f"Generate ideas with offsets {values}",
                        "causal_model": {"configuration": {"offsets": values}},
                        "predictions": [{"loss": "decrease"}],
                        "confidence": 0.6,
                    }
                    for values in (offsets, [max(offsets)])
                ]
            },
        )


class Reviewer:
    def __init__(self, reject=False):
        self.calls = []
        self.reject = reject

    def review(self, action):
        self.calls.append(action)
        command = review_command_from_action(action)
        passes = command.evaluation.disposition == "passed" and not self.reject
        return make_review_result(
            action=action,
            review=CandidateReview(
                review_id=f"{action.action_id}:independent",
                reviewer_id="reviewer-v1",
                candidate=command.candidate,
                experiment=command.experiment,
                evaluation=command.evaluation,
                disposition="accepted" if passes else "rejected",
                findings=(
                    "Measured held-out evaluation passes" if passes else "Review rejects revision",
                ),
                lineage=(command.candidate.ref, command.experiment.ref, command.evaluation.ref),
            ),
        )


def case(name, base, target):
    return LearningCase(name, {"base": base, "target": target})


SHADOW = (case("shadow-a", 20, 25), case("shadow-b", 30, 36))
TRAIN = (case("task-a", 0, 3), case("task-b", 10, 14))


def loop(store, *, adapter=None, proposer=None, reviewer=None, **policy):
    return AdaptiveLoop(
        store,
        adapter=Ideas() if adapter is None else adapter,
        proposer=Proposer() if proposer is None else proposer,
        proposer_id="proposer-v1",
        reviewer=Reviewer() if reviewer is None else reviewer,
        reviewer_id="reviewer-v1",
        policy=LearningPolicy(
            objective="Reduce idea error",
            metric=Metric(
                metric_id="loss",
                unit="distance",
                direction="decrease",
                role="objective",
            ),
            minimum_effect=policy.pop("minimum_effect", 0.5),
            **policy,
        ),
    )


@pytest.mark.parametrize("store_factory", [LocalLearningStore, ConsumerLearningStore])
def test_adoption_survives_restart_and_changes_next_task(tmp_path, monkeypatch, store_factory):
    adapter, proposer, reviewer = Ideas(), Proposer(), Reviewer()
    with store_factory(
        tmp_path, profile_id="ideas", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, adapter=adapter, proposer=proposer, reviewer=reviewer)
        baseline = store.active
        assert engine.learn("not-due", shadow_cases=SHADOW, activate=True) is None
        feedback = [engine.run_task(item) for item in TRAIN]
        original_apply = store.apply_snapshot

        def interrupted_apply(**kwargs):
            original_apply(**kwargs)
            raise KeyboardInterrupt("crash after the local effect, before its receipt")

        monkeypatch.setattr(store, "apply_snapshot", interrupted_apply)
        with pytest.raises(KeyboardInterrupt):
            engine.learn("pass-1", shadow_cases=SHADOW, activate=True)
        assert store.pending_pass == "pass-1" and store.active != baseline
        with pytest.raises(RuntimeError, match="pending"):
            engine.run_task(case("blocked", 99, 100))
        with pytest.raises(RuntimeError, match="pending"):
            engine.learn("different", shadow_cases=SHADOW)
        recorded_count = len(adapter.calls)
    with store_factory(tmp_path, profile_id="ideas") as store:
        engine = loop(store, adapter=adapter, proposer=proposer, reviewer=reviewer)
        original_finish = store.finish_pass

        def interrupted_finish(pass_id, native):
            store.remember(pass_id, "result", native)
            raise KeyboardInterrupt("crash after recording terminal result")

        monkeypatch.setattr(store, "finish_pass", interrupted_finish)
        with pytest.raises(KeyboardInterrupt):
            engine.learn("pass-1", shadow_cases=SHADOW, activate=True)
        assert store.pending_pass == "pass-1"
        monkeypatch.setattr(store, "finish_pass", original_finish)
        result = engine.learn("pass-1", shadow_cases=SHADOW, activate=True)
        assert result is not None
        # Only the four still-unrecorded verification measurements ran after recovery.
        assert len(adapter.calls) == recorded_count + 4
        assert result.adopted, result.disposition
        assert store.active == result.strategy_after != baseline
        assert store.pending_pass is None
        assert len(proposer.calls) == len(reviewer.calls) == 1
        assert "shadow-a" not in str(proposer.calls[0].context)
        count = len(adapter.calls)
        assert engine.run_task(TRAIN[0]) == feedback[0]
        assert len(adapter.calls) == count
    with store_factory(tmp_path, profile_id="ideas") as store:
        engine = loop(store, adapter=adapter, proposer=proposer, reviewer=reviewer)
        assert engine.learn("pass-1", shadow_cases=SHADOW, activate=True) == result
        assert len(adapter.calls) == count
        next_task = engine.run_task(case("next", 40, 44))
        assert next_task.target_snapshot == result.strategy_after
        assert next_task.value["value"] == 0
        assert next_task.value["output"]["ideas"] != (41,)
        assert engine.learn("not-due", shadow_cases=SHADOW, activate=True) is None


@pytest.mark.parametrize("variant", ["empty", "duplicate", "unchanged", "invalid", "error"])
def test_invalid_proposals_fail_without_strategy_change(tmp_path, variant):
    class Invalid(Proposer):
        def respond(self, request):
            if variant == "error":
                raise OSError("provider offline")
            proposal = super().respond(request)
            items = [dict(item) for item in proposal.content["hypotheses"]]
            if variant == "empty":
                items = []
            elif variant == "duplicate":
                items[1] = items[0]
            elif variant == "unchanged":
                items[0]["causal_model"] = {"configuration": {"offsets": [1]}}
            else:
                items[0]["causal_model"] = {"configuration": {"wrong": True}}
            return ReasoningResult.propose(request=request, content={"hypotheses": items})

    with LocalLearningStore(
        tmp_path, profile_id="invalid", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, proposer=Invalid())
        baseline = store.active
        for item in TRAIN:
            engine.run_task(item)
        result = engine.learn("invalid", shadow_cases=SHADOW, activate=True)
        assert result.disposition == "failed"
        failure = store.runtime.resume("invalid:ideas").failures[-1]
        assert failure.classification == ("execution" if variant == "error" else "invalid-result")
        assert not result.adopted and store.active == baseline and store.pending_pass is None
        assert engine.learn("no-repeat", shadow_cases=SHADOW) is None


def test_input_bounds_and_identity_conflicts_precede_effects(tmp_path):
    adapter, proposer = Ideas(), Proposer()
    with LocalLearningStore(
        tmp_path, profile_id="bounds", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, adapter=adapter, proposer=proposer)
        for item in TRAIN:
            engine.run_task(item)
        with pytest.raises(ValueError, match="task id"):
            engine.run_task(case("task-a", 1, 99))
        for shadow in (
            (SHADOW[0],),
            SHADOW * 2,
            (case("renamed", 0, 3), SHADOW[0]),
            TRAIN,
            (case("x", 5, 7), case("y", 5, 7)),
        ):
            with pytest.raises(ValueError):
                engine.learn("bad", shadow_cases=shadow, activate=True)
        assert len(adapter.calls) == 2 and not proposer.calls and store.pending_pass is None
        with pytest.raises(ValueError, match="allowances"):
            loop(store, min_new_feedback=3, max_cases=2)
        with pytest.raises(TypeError, match="adapter"):
            loop(store, adapter=object())
        with pytest.raises(TypeError, match="reviewer"):
            loop(store, reviewer=object())


@pytest.mark.parametrize(
    "activate,reject,disposition",
    [
        (False, False, "activation-disabled"),
        (True, True, "governance-rejected"),
    ],
)
def test_governance_and_activation_choice_preserve_baseline(
    tmp_path, activate, reject, disposition
):
    with LocalLearningStore(
        tmp_path, profile_id="governed", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, reviewer=Reviewer(reject=reject))
        baseline = store.active
        for item in TRAIN:
            engine.run_task(item)
        result = engine.learn("guarded", shadow_cases=SHADOW, activate=activate)
        assert result.disposition == disposition
        assert not result.adopted and store.active == baseline
        with pytest.raises(ValueError, match="different configuration"):
            engine.learn("guarded", shadow_cases=SHADOW, activate=not activate)


@pytest.mark.parametrize("store_factory", [LocalLearningStore, ConsumerLearningStore])
def test_failed_verification_rolls_back_actual_strategy(tmp_path, store_factory):
    verification = (case("verify-a", 50, 51), case("verify-b", 60, 61))
    with store_factory(
        tmp_path, profile_id="rollback", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store)
        baseline = store.active
        for item in TRAIN:
            engine.run_task(item)
        result = engine.learn(
            "rollback", shadow_cases=SHADOW, verification_cases=verification, activate=True
        )
        assert result.disposition == "rolled-back"
        assert result.native.application.application.produced_snapshot != baseline
        assert result.native.application.verification.disposition != "passed"
        assert store.active == baseline and store.pending_pass is None
        assert engine.run_task(case("next", 80, 81)).value["value"] == 0


def test_no_supported_revisions_preserve_baseline(tmp_path):
    class Worse(Proposer):
        def respond(self, request):
            proposal = super().respond(request)
            items = [dict(item) for item in proposal.content["hypotheses"]]
            for item, offset in zip(items, (-10, -20), strict=True):
                item["causal_model"] = {"configuration": {"offsets": [offset]}}
            return ReasoningResult.propose(request=request, content={"hypotheses": items})

    with LocalLearningStore(
        tmp_path, profile_id="worse", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, proposer=Worse())
        baseline = store.active
        for item in TRAIN:
            engine.run_task(item)
        result = engine.learn("worse", shadow_cases=SHADOW, activate=True)
        assert result.disposition == "no-supported-revision"
        assert store.active == baseline and not result.adopted


def test_supported_but_insufficient_effect_is_not_adopted(tmp_path):
    with LocalLearningStore(
        tmp_path, profile_id="small", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, minimum_effect=10)
        baseline = store.active
        for item in TRAIN:
            engine.run_task(item)
        result = engine.learn("small", shadow_cases=SHADOW, activate=True)
        assert result.native.handoff is None
        assert result.native.iterations
        assert not result.adopted and store.active == baseline and store.pending_pass is None


def test_public_consumer_profiles_keep_feedback_and_strategy_separate(tmp_path):
    import librsi

    public = {
        "AdaptiveLoop",
        "LearningAdapter",
        "LearningCase",
        "LearningPolicy",
        "LearningResult",
        "LocalLearningStore",
        "TaskMeasurement",
    }
    assert public <= set(librsi.__all__)
    with (
        LocalLearningStore(
            tmp_path / "a", profile_id="consumer-a", initial_configuration={"offsets": [1]}
        ) as a,
        LocalLearningStore(
            tmp_path / "b", profile_id="consumer-b", initial_configuration={"offsets": [1]}
        ) as b,
    ):
        first = loop(a).run_task(TRAIN[0])
        second = loop(b).run_task(TRAIN[1])
        assert first.target_snapshot != second.target_snapshot
        assert a.feedback() == (first,) and b.feedback() == (second,)
        assert loop(a).learn("a", shadow_cases=SHADOW) is None
        assert loop(b).learn("b", shadow_cases=SHADOW) is None
