"""Exercise serving against real native adoption, verification, and recovery."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from librsi import (
    ConcurrentAdaptiveLoop,
    ConcurrentLearningStore,
    LearningPolicy,
    LocalConcurrentLearningStore,
    LocalLearningStore,
    Metric,
    record_from_dict,
)
from librsi.identity import thaw

from .test_adaptive_loop import SHADOW, TRAIN, Ideas, Proposer, Reviewer, case


def loop(store, *, adapter=None, task_adapter=None, proposer=None):
    return ConcurrentAdaptiveLoop(
        store,
        adapter=Ideas() if adapter is None else adapter,
        task_adapter=task_adapter,
        proposer=Proposer() if proposer is None else proposer,
        proposer_id="proposer-v1",
        reviewer=Reviewer(),
        reviewer_id="reviewer-v1",
        policy=LearningPolicy(
            objective="Reduce idea error",
            metric=Metric(
                metric_id="loss", unit="distance", direction="decrease", role="objective"
            ),
            minimum_effect=0.5,
        ),
    )


def test_concurrent_facade_is_opt_in_and_preserves_cached_tasks(tmp_path):
    with (
        LocalLearningStore(
            tmp_path / "legacy", profile_id="legacy", initial_configuration={"offsets": [1]}
        ) as legacy,
        pytest.raises(TypeError),
    ):
        loop(legacy)
    with LocalConcurrentLearningStore(
        tmp_path / "concurrent", profile_id="concurrent", initial_configuration={"offsets": [1]}
    ) as store:
        assert isinstance(store, ConcurrentLearningStore)
        learner, serving = Ideas(), Ideas()
        engine = loop(store, adapter=learner, task_adapter=serving)
        measured = engine.run_task(TRAIN[0])
        assert engine.run_task(TRAIN[0]) == measured
        assert len(serving.calls) == 1 and not learner.calls
        with pytest.raises(ValueError):
            engine.run_task(case(TRAIN[0].case_id, 0, 99))
        with store.learning_owner():
            with pytest.raises(RuntimeError):
                engine.learn("overlap", shadow_cases=SHADOW)
            with pytest.raises(RuntimeError):
                engine.history()
        assert engine.learn("not-due", shadow_cases=SHADOW) is None


def test_separate_task_adapter_must_preserve_execution_and_scoring_identity(tmp_path):
    class Different(Ideas):
        adapter_id = "different-semantics-v1"

    with LocalConcurrentLearningStore(
        tmp_path, profile_id="adapters", initial_configuration={"offsets": [1]}
    ) as store:
        with pytest.raises(ValueError):
            loop(store, task_adapter=Different())
        assert not store.feedback()


@pytest.mark.slow
def test_live_tasks_overlap_learning_and_retain_versions_after_promotion(tmp_path):
    proposal_entered, release_proposal = Event(), Event()
    verification_entered, release_verification = Event(), Event()
    task_entered, release_task = Event(), Event()

    class PausedProposer(Proposer):
        stop_next = False

        def respond(self, request):
            if self.stop_next:
                raise KeyboardInterrupt("inspect the next frozen feedback batch")
            proposal_entered.set()
            assert release_proposal.wait(180), "test never released the proposal"
            return super().respond(request)

    class PausedVerification(Ideas):
        def evaluate(self, configuration, item):
            if item.case_id == "verify-a" and tuple(configuration["offsets"]) != (1,):
                verification_entered.set()
                assert release_verification.wait(180), "test never released verification"
            return super().evaluate(configuration, item)

    class SlowTask(Ideas):
        def evaluate(self, configuration, item):
            if item.case_id == "slow-task":
                task_entered.set()
                assert release_task.wait(300), "test never released its ordinary task"
            return super().evaluate(configuration, item)

    verification = (case("verify-a", 50, 53), case("verify-b", 60, 64))
    proposer = PausedProposer()
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="live", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(
            store, adapter=PausedVerification(), task_adapter=SlowTask(), proposer=proposer
        )
        baseline = store.serving_snapshot
        for item in TRAIN:
            engine.run_task(item)
        with ThreadPoolExecutor(max_workers=3) as pool:
            slow = pool.submit(engine.run_task, case("slow-task", 120, 123))
            learning = None
            try:
                assert task_entered.wait(10)
                learning = pool.submit(
                    engine.learn,
                    "first",
                    shadow_cases=SHADOW,
                    verification_cases=verification,
                    activate=True,
                )
                assert proposal_entered.wait(30)
                frozen = store.pass_input("first")
                during_proposal = pool.submit(
                    engine.run_task, case("during-proposal", 100, 103)
                ).result(timeout=10)
                assert during_proposal.target_snapshot == baseline
                assert store.pending_pass == "first"
                with pytest.raises(RuntimeError):
                    engine.learn("overlap", shadow_cases=SHADOW)
                with pytest.raises(RuntimeError):
                    engine.history()
                release_proposal.set()
                assert verification_entered.wait(180)
                assert store.active != baseline
                assert store.serving_snapshot == baseline
                during_verification = pool.submit(
                    engine.run_task, case("during-verification", 110, 113)
                ).result(timeout=10)
                assert during_verification.target_snapshot == baseline
                assert store.pass_input("first") == frozen
                assert {
                    record_from_dict(thaw(row)).value["task_id"] for row in frozen.value["feedback"]
                } == {item.case_id for item in TRAIN}
                release_verification.set()
                result = learning.result(timeout=180)
                assert result is not None and result.adopted
                assert store.serving_snapshot == result.strategy_after != baseline
                after = engine.run_task(case("after-promotion", 130, 133))
                assert after.target_snapshot == result.strategy_after
                release_task.set()
                late = slow.result(timeout=10)
                assert late.target_snapshot == baseline
                assert engine.run_task(case("slow-task", 120, 123)) == late
            finally:
                release_proposal.set()
                release_verification.set()
                release_task.set()
        proposer.stop_next = True
        with pytest.raises(KeyboardInterrupt, match="frozen feedback batch"):
            engine.learn(
                "second",
                shadow_cases=(case("next-shadow-a", 200, 203), case("next-shadow-b", 210, 214)),
                activate=True,
            )
        next_batch = store.pass_input("second")
        assert next_batch.target_snapshot == result.strategy_after
        assert {
            record_from_dict(thaw(row)).value["task_id"] for row in next_batch.value["feedback"]
        } == {
            "during-proposal",
            "during-verification",
            "after-promotion",
            "slow-task",
        }
        assert len(store.feedback()) == 6


@pytest.mark.slow
def test_interrupted_application_reopens_with_baseline_and_can_roll_back(tmp_path, monkeypatch):
    verification = (case("verify-a", 50, 51), case("verify-b", 60, 61))
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="recover", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store)
        baseline = store.serving_snapshot
        for item in TRAIN:
            engine.run_task(item)
        original_apply = store.apply_snapshot

        def interrupted_apply(**kwargs):
            original_apply(**kwargs)
            raise KeyboardInterrupt("after candidate effect, before receipt")

        monkeypatch.setattr(store, "apply_snapshot", interrupted_apply)
        with pytest.raises(KeyboardInterrupt):
            engine.learn(
                "recover", shadow_cases=SHADOW, verification_cases=verification, activate=True
            )
        assert store.active != baseline and store.serving_snapshot == baseline
        assert engine.run_task(case("during-interruption", 70, 71)).target_snapshot == baseline
    with LocalConcurrentLearningStore(tmp_path, profile_id="recover") as store:
        assert store.active != baseline and store.serving_snapshot == baseline
        engine = loop(store)
        assert engine.run_task(case("after-restart", 80, 81)).target_snapshot == baseline
        result = engine.learn(
            "recover", shadow_cases=SHADOW, verification_cases=verification, activate=True
        )
        assert result.disposition == "rolled-back"
        assert store.pending_pass is None
        assert store.serving_snapshot == store.active == baseline
        assert engine.run_task(case("after-rollback", 90, 91)).value["value"] == 0


@pytest.mark.slow
def test_terminal_record_before_publication_recovers_without_repeating_model_calls(
    tmp_path, monkeypatch
):
    learner, serving, proposer = Ideas(), Ideas(), Proposer()
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="terminal", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, adapter=learner, task_adapter=serving, proposer=proposer)
        baseline = store.serving_snapshot
        for item in TRAIN:
            engine.run_task(item)

        def interrupted_finish(pass_id, native):
            store.remember(pass_id, "result", native)
            raise KeyboardInterrupt("terminal recorded before publication")

        monkeypatch.setattr(store, "finish_pass", interrupted_finish)
        with pytest.raises(KeyboardInterrupt):
            engine.learn("terminal", shadow_cases=SHADOW, activate=True)
        assert store.pending_pass == "terminal" and store.active != baseline
        assert store.serving_snapshot == baseline
        calls = len(learner.calls)
    with LocalConcurrentLearningStore(tmp_path, profile_id="terminal") as store:
        engine = loop(store, adapter=learner, task_adapter=serving, proposer=proposer)
        assert engine.run_task(case("before-publication", 70, 73)).target_snapshot == baseline
        result = engine.learn("terminal", shadow_cases=SHADOW, activate=True)
        assert result.adopted and len(learner.calls) == calls and len(proposer.calls) == 1
        assert store.serving_snapshot == result.strategy_after != baseline
        assert (
            engine.run_task(case("after-publication", 80, 83)).target_snapshot
            == result.strategy_after
        )
