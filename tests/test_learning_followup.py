from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import LearningCase, LocalLearningStore
from librsi.reasoning import ReasoningResult

from .learning_store_support import ConsumerLearningStore
from .test_adaptive_loop import SHADOW, TRAIN, Ideas, Proposer, case, loop

FRESH = (case("fresh-a", 100, 105), case("fresh-b", 200, 206))
LATER = (case("later-a", 300, 305), case("later-b", 400, 406))


class FailedProvider(Proposer):
    def respond(self, request):
        self.calls.append(request)
        raise OSError("private-provider-diagnostic")


def failed(store, **policy):
    engine = loop(store, proposer=FailedProvider(), **policy)
    for item in TRAIN:
        engine.run_task(item)
    assert engine.learn("first", shadow_cases=SHADOW).disposition == "failed"
    return engine


@pytest.mark.parametrize("factory", [LocalLearningStore, ConsumerLearningStore])
def test_reflection_and_proposal_are_bounded_frozen_and_reused_after_crash(tmp_path, factory):
    class Reflecting(FailedProvider):
        def respond(self, request):
            if request.kind != "reflection":
                return super().respond(request)
            self.calls.append(request)
            history = request.context["history"]
            assert history[0]["failure_classes"] == ("execution",)
            assert "private-provider-diagnostic" not in str(request.context)
            assert "shadow-a" not in str(request.context)
            return ReasoningResult.propose(
                request=request,
                content={
                    "summary": "The provider did not produce a measurable revision.",
                    "observations": ["Recorded operation failed with execution classification."],
                    "open_questions": [
                        "Can a subsequent bounded request produce valid candidates?"
                    ],
                },
            )

    backend, adapter = Reflecting(), Ideas()
    with factory(tmp_path, profile_id="follow", initial_configuration={"offsets": [1]}) as store:
        failed(store, reflect_on_failure=True)
        engine = loop(store, proposer=backend, adapter=adapter, reflect_on_failure=True)
        remember = store.remember

        def interrupted(pass_id, key, record):
            remember(pass_id, key, record)
            if key.startswith("action:") and record.action.action_id == "second:ideas":
                raise KeyboardInterrupt("after recording host result, before submission")

        store.remember = interrupted
        with pytest.raises(KeyboardInterrupt):
            engine.learn("second", follow_up_to="first", shadow_cases=FRESH)
        frozen = store.pass_input("second")
        assert len(backend.calls) == 2 and not adapter.calls
        assert backend.calls[1].context["reflection"]["observations"]
        assert frozen.value["follow_up_depth"] == 1
    with factory(tmp_path, profile_id="follow") as store:
        engine = loop(store, proposer=backend, adapter=adapter, reflect_on_failure=True)
        result = engine.learn("second", follow_up_to="first", shadow_cases=FRESH)
        assert result.disposition == "failed" and len(backend.calls) == 2
        assert store.pass_input("second") == frozen
        assert engine.learn("second", follow_up_to="first", shadow_cases=FRESH) == result
        attempt = engine.history(limit=1)[0]
        assert attempt.reflection.request == backend.calls[0]
        assert (
            attempt.operations[0].metadata["learning_operation"]["scope"] == "host-action-inclusive"
        )
        with pytest.raises(ValueError, match="different configuration"):
            loop(store).learn("second", follow_up_to="first", shadow_cases=FRESH)
        with pytest.raises(ValueError, match="already has"):
            engine.learn("branch", follow_up_to="first", shadow_cases=LATER)
        with pytest.raises(ValueError, match="allowance"):
            engine.learn("third", follow_up_to="second", shadow_cases=LATER)
        assert engine.learn("not-due", shadow_cases=LATER) is None


def test_reflection_failure_ends_pass_without_proposal_or_effect(tmp_path):
    with LocalLearningStore(
        tmp_path, profile_id="failure", initial_configuration={"offsets": [1]}
    ) as store:
        failed(store)
        backend, adapter = FailedProvider(), Ideas()
        engine = loop(store, proposer=backend, adapter=adapter, reflect_on_failure=True)
        result = engine.learn("follow", follow_up_to="first", shadow_cases=FRESH)
        assert result.disposition == "failed" and not result.adopted
        assert [row.kind for row in backend.calls] == ["reflection"] and not adapter.calls
        assert store.runtime.resume("follow:ideas") is None
        assert engine.history(limit=1)[0].proposal is None
        assert engine.learn("follow", follow_up_to="first", shadow_cases=FRESH) == result
        assert len(backend.calls) == 1


def test_followup_checks_freshness_scoring_and_allowances_before_reasoning(tmp_path):
    with LocalLearningStore(
        tmp_path, profile_id="bounds", initial_configuration={"offsets": [1]}
    ) as store:
        engine = failed(store)
        for shadow, verification in (
            (SHADOW, None),
            (tuple(LearningCase("renamed-" + row.case_id, row.payload) for row in SHADOW), None),
            (FRESH, SHADOW),
            (FRESH, TRAIN),
        ):
            with pytest.raises(ValueError, match="held-out"):
                engine.learn(
                    "bad",
                    follow_up_to="first",
                    shadow_cases=shadow,
                    verification_cases=verification,
                )
        for policy, message in (
            ({"max_followups": 0}, "allowance"),
            ({"history_limit": 0}, "history"),
        ):
            with pytest.raises(ValueError, match=message):
                loop(store, **policy).learn("bad", follow_up_to="first", shadow_cases=FRESH)
        with pytest.raises(ValueError, match="baseline or scoring"):
            engine.learn("bad", follow_up_to="missing", shadow_cases=FRESH)
        engine.policy = replace(engine.policy, objective="Different objective")
        with pytest.raises(ValueError, match="baseline or scoring"):
            engine.learn("bad", follow_up_to="first", shadow_cases=FRESH)
        with pytest.raises(ValueError, match="baseline or scoring"):
            loop(store, minimum_effect=0.1).learn("bad", follow_up_to="first", shadow_cases=FRESH)
        assert store.pending_pass is None and len(store.pass_ids) == 1


def test_fresh_feedback_scheduling_includes_only_compatible_bounded_history(tmp_path):
    with LocalLearningStore(
        tmp_path, profile_id="default", initial_configuration={"offsets": [1]}
    ) as store:
        failed(store)
        backend = FailedProvider()
        engine = loop(store, proposer=backend, history_limit=1)
        for row in (case("new-a", 10, 13), case("new-b", 20, 24)):
            engine.run_task(row)
        engine.learn("second", shadow_cases=FRESH)
        assert len(backend.calls) == 1
        assert backend.calls[0].kind == "hypothesis-generation"
        assert backend.calls[0].context["history"][0]["pass_id"] == "first"
        assert backend.calls[0].context["follow_up_to"] is None


@pytest.mark.parametrize(
    "policy",
    [
        {"history_limit": True},
        {"history_limit": -1},
        {"max_followups": -1},
        {"max_followups": True},
        {"reflect_on_failure": 1},
    ],
)
def test_policy_rejects_unbounded_or_ambiguous_options(tmp_path, policy):
    with (
        LocalLearningStore(
            tmp_path, profile_id="policy", initial_configuration={"offsets": [1]}
        ) as store,
        pytest.raises(ValueError),
    ):
        loop(store, **policy)
