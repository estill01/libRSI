"""Regression coverage for sparse gains and order-independent facade evidence."""

from dataclasses import replace
from itertools import permutations

import pytest

from librsi import LearningCase, LocalLearningStore, Observation, TaskMeasurement
from librsi.epistemics import LinearEvidenceAggregator
from librsi.facade import learning_host, learning_inputs

from .test_adaptive_loop import Ideas, loop


class Sparse(Ideas):
    def evaluate(self, configuration, case):
        revised = configuration["offsets"] != (1,)
        value = case.payload["effect"] if revised else 0
        return TaskMeasurement({}, -value)


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.slow
def test_sparse_gain_and_frozen_v2_resume(tmp_path, monkeypatch, version):
    original_begin = LocalLearningStore.begin_pass

    def begin(store, inputs):
        if version == 2:
            inputs = replace(inputs, value={**inputs.value, "learning_version": 2})
        return original_begin(store, inputs)

    monkeypatch.setattr(LocalLearningStore, "begin_pass", begin)
    with LocalLearningStore(
        tmp_path, profile_id="sparse", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, adapter=Sparse(), max_cases=8, max_feedback=8, minimum_effect=0.01)

        def cases(stage):
            return tuple(
                LearningCase(
                    f"{stage}-{i}",
                    {
                        "base": i,
                        "target": i + 3 + i % 2,
                        "effect": 1 if i < 2 else 0,
                        "stage": stage,
                    },
                )
                for i in range(8)
            )

        for case in cases("train"):
            engine.run_task(case)
        # Freeze a pending pass before constructing any experiment evidence.
        learning_inputs.prepare(
            store,
            policy=engine.policy,
            adapter_id=engine.adapter.adapter_id,
            proposer_id=engine.proposer_id,
            reviewer_id=engine.reviewer_id,
            pass_id="sparse",
            shadow=cases("shadow"),
            verification=cases("verify"),
            activate=True,
            follow_up_to=None,
        )
    captured = []
    original_evidence = learning_host.Evidence

    def evidence(**kwargs):
        result = original_evidence(**kwargs)
        captured.append(result)
        return result

    monkeypatch.setattr(learning_host, "Evidence", evidence)
    with LocalLearningStore(tmp_path, profile_id="sparse") as store:
        engine = loop(store, adapter=Sparse(), max_cases=8, max_feedback=8, minimum_effect=0.01)
        result = engine.learn(
            "sparse",
            shadow_cases=cases("shadow"),
            verification_cases=cases("verify"),
            activate=True,
        )
        assert store.pass_input("sparse").value["learning_version"] == version
        assert captured
        ties = [e for e in captured if e.data["baseline"] == e.data["candidate"]]
        assert all(e.evidence_type == ("null" if version == 3 else "counterexample") for e in ties)
        if version == 3:
            assert result.adopted
            assert all(e.weight == 0 for e in ties)
        root = store.active.root
        assert (
            engine.learn(
                "sparse",
                shadow_cases=cases("shadow"),
                verification_cases=cases("verify"),
                activate=True,
            )
            == result
        )
    with LocalLearningStore(tmp_path, profile_id="sparse") as store:
        assert store.active.root == root


def test_mixed_effects_do_not_clip_or_depend_on_evidence_order(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from librsi import Hypothesis
    from librsi.facade.learning_host import LearningHost
    from librsi.investigation import INVESTIGATION_EXPERIMENT_ACTION_KIND

    with LocalLearningStore(
        tmp_path, profile_id="weights", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store)
        inputs = Observation(
            kind="learning.pass",
            target_snapshot=store.active,
            value={
                "pass_id": "weights",
                "learning_version": 3,
                "training": [],
                "shadow": [],
                "verification": [],
            },
        )
        host = LearningHost(store, inputs, engine.policy, engine.adapter)
        effects = [1, 1, 1, -0.1, -0.1, 0]
        host.training = tuple(LearningCase(str(i), {"index": i}) for i in range(len(effects)))
        hypothesis = Hypothesis(
            statement="mixed gains", causal_model={"configuration": {"offsets": [3]}}
        )
        experiment = Observation(kind="test", value={})
        request = SimpleNamespace(
            branch=SimpleNamespace(hypothesis=hypothesis), experiment=experiment
        )
        monkeypatch.setattr(
            learning_host, "investigation_experiment_request_from_action", lambda _: request
        )
        monkeypatch.setattr(
            learning_host.InvestigationEvidenceBatch, "collected", lambda **kw: kw["evidence"]
        )
        monkeypatch.setattr(
            learning_host, "make_investigation_experiment_result", lambda **kw: kw["batch"]
        )

        def measure(snapshot, case, stage):
            value = 0 if snapshot == host.baseline else -effects[case.payload["index"]]
            return Observation(kind="measurement", value={"value": value})

        monkeypatch.setattr(host, "measure", measure)
        items = host.experiment(SimpleNamespace(kind=INVESTIGATION_EXPERIMENT_ACTION_KIND))
        assert sum(e.weight for e in items) == pytest.approx(2.5)
        assert items[-1].evidence_type == "null" and items[-1].weight == 0
        aggregator = LinearEvidenceAggregator()
        confidences = []
        for order in permutations(items):
            confidence = 0.5
            for item in order:
                _, confidence = aggregator.transition(
                    current_confidence=confidence,
                    relationship=item.evidence_type,
                    weight=item.weight,
                )
            confidences.append(confidence)
        assert max(confidences) - min(confidences) < 1e-14
        assert min(confidences) > 0.75
