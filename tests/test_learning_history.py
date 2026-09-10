from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import LearningAttempt, LocalLearningStore, Observation
from librsi.facade.learning_history import ordered_inputs
from librsi.reasoning import ReasoningResult

from .learning_store_support import ConsumerLearningStore
from .test_adaptive_loop import SHADOW, TRAIN, Ideas, Proposer, loop


class Unproductive(Proposer):
    def respond(self, request):
        self.calls.append(request)
        return ReasoningResult.propose(
            request=request,
            content={
                "hypotheses": [
                    {
                        "statement": f"Try offset {offset}",
                        "causal_model": {"configuration": {"offsets": [offset]}},
                        "predictions": [{"loss": "decrease"}],
                        "confidence": 0.5,
                    }
                    for offset in (-10, -20)
                ]
            },
        )


@pytest.fixture(scope="module", params=[LocalLearningStore, ConsumerLearningStore])
def rejected(tmp_path_factory, request):
    path = tmp_path_factory.mktemp("history")
    factory = request.param
    with factory(path, profile_id="history", initial_configuration={"offsets": [1]}) as store:
        engine = loop(store, proposer=Unproductive())
        for item in TRAIN:
            engine.run_task(item)
        result = engine.learn("z-first", shadow_cases=SHADOW)
        assert result.disposition == "no-supported-revision"
    return factory, path, result


def test_actual_rejected_history_reopens_through_public_store_port(rejected):
    factory, path, result = rejected
    with factory(path, profile_id="history") as store:
        attempt = loop(store).history()[0]
        assert isinstance(attempt, LearningAttempt)
        assert attempt.result == result and attempt.sequence == 1
        assert attempt.disposition == "no-supported-revision"
        assert len(attempt.measurements) == 6  # baseline and two candidates, two cases
        assert attempt.proposal.request.request_id == "z-first:ideas"
        assert attempt.inputs.ref in attempt.feedback.source_refs
        assert result.native.ref in attempt.feedback.source_refs
        assert attempt.feedback.value["historical_only"] is True
        assert {row["value"] for row in attempt.feedback.value["trials"]} == {2, 3, 13, 14, 23, 24}


def test_safe_context_excludes_shadow_and_nested_native_trees(rejected):
    factory, path, _ = rejected
    with factory(path, profile_id="history") as store:
        attempt = loop(store).history()[0]
        safe = attempt.feedback.to_dict()
        assert "shadow-a" not in str(safe) and "shadow-b" not in str(safe)
        assert "verification" not in str(safe)
        assert "native" not in safe["value"] and "operations" not in safe["value"]
        assert len(safe["value"]["hypotheses"]) == 2
        assert set(safe["value"]["trials"][0]) == {
            "case_id",
            "case",
            "configuration",
            "strategy_root",
            "measurement_root",
            "status",
            "output",
            "value",
        }


def test_scope_qualified_costs_are_retained_not_assumed_total(rejected):
    factory, path, _ = rejected
    with factory(path, profile_id="history") as store:
        attempt = loop(store).history()[0]
        for operation in attempt.operations:
            cost = operation.metadata["learning_operation"]
            assert cost["scope"] == "host-action-inclusive"
            assert cost["wall_seconds"] >= 0 and cost["process_cpu_seconds"] >= 0
            assert cost["provider_usage"] is None and cost["child_cpu_seconds"] is None
            assert cost["additive"] is False
        assert all(
            row.value["operation"]["scope"] == "adapter-call" for row in attempt.measurements
        )
        assert loop(store).history(limit=0) == ()
        for invalid in (True, -1, 1.5):
            with pytest.raises(ValueError, match="limit"):
                loop(store).history(limit=invalid)


def test_provider_failure_message_is_operator_visible_but_not_proposer_feedback(tmp_path):
    class Broken(Proposer):
        def respond(self, request):
            raise RuntimeError("private-heldout-canary")

    with LocalLearningStore(
        tmp_path, profile_id="failure", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, proposer=Broken())
        for item in TRAIN:
            engine.run_task(item)
        engine.learn("failure", shadow_cases=SHADOW)
        attempt = engine.history()[0]
        assert attempt.disposition == "failed" and attempt.proposal is None
        assert "private-heldout-canary" in str(attempt.operations)
        assert "private-heldout-canary" not in str(attempt.feedback.to_dict())
        assert attempt.feedback.value["failure_classes"] == ("execution",)


def test_failed_adapter_call_is_retained_without_inventing_a_score(tmp_path):
    class Broken(Ideas):
        def evaluate(self, configuration, case):
            if configuration["offsets"][0] < 0:
                raise RuntimeError("adapter-failure-canary")
            return super().evaluate(configuration, case)

    with LocalLearningStore(
        tmp_path, profile_id="adapter", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, adapter=Broken(), proposer=Unproductive())
        for item in TRAIN:
            engine.run_task(item)
        engine.learn("adapter", shadow_cases=SHADOW)
        attempt = engine.history()[0]
        failures = [
            row for row in attempt.measurements if row.kind == "learning.measurement-failure"
        ]
        assert failures and failures[0].value["operation"]["scope"] == "adapter-call"
        safe_failures = [
            row for row in attempt.feedback.value["trials"] if row["status"] == "failed"
        ]
        assert safe_failures and all(
            "value" not in row and "output" not in row for row in safe_failures
        )
        assert "adapter-failure-canary" not in str(attempt.feedback.to_dict())


def test_ordering_is_explicit_and_never_inferred_from_pass_id_mapping(rejected):
    factory, path, _ = rejected
    with factory(path, profile_id="history") as store:
        first = store.pass_input("z-first")
        second = replace(first, value={**first.value, "pass_id": "a-second", "sequence": 2})

        class Reordered:
            target = store.target
            pass_ids = ("a-second", "z-first")

            def pass_input(self, pass_id):
                return second if pass_id == "a-second" else first

        assert [row.value["pass_id"] for row in ordered_inputs(Reordered())] == [
            "z-first",
            "a-second",
        ]
        second = replace(second, value={**second.value, "sequence": 1})
        with pytest.raises(ValueError, match="ambiguous"):
            ordered_inputs(Reordered())
        legacy = dict(first.value)
        legacy.pop("sequence")
        first = replace(first, value=legacy)
        second = replace(second, value={**legacy, "pass_id": "a-second"})
        rows = ordered_inputs(Reordered())
        assert [row.value["pass_id"] for row in rows] == ["a-second", "z-first"]
        assert all("sequence" not in row.value for row in rows)


def test_substituted_measurement_or_terminal_result_rejects(rejected):
    factory, path, _ = rejected
    with factory(path, profile_id="history") as store:
        engine = loop(store)
        original = store.cached

        def wrong(pass_id, key):
            row = original(pass_id, key)
            if key.startswith("measure:training:") and row is not None:
                return replace(row, source_refs=())
            return row

        store.cached = wrong
        with pytest.raises(ValueError, match="historical measurement"):
            engine.history()
        store.cached = lambda pass_id, key: (
            Observation(kind="fake", value={}) if key == "result" else original(pass_id, key)
        )
        with pytest.raises(ValueError, match="native terminal"):
            engine.history()
