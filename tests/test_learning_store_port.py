from __future__ import annotations

import pytest

from librsi import LearningStore, LocalLearningStore
from librsi.facade import LearningStore as FacadeLearningStore

from .learning_store_support import ConsumerLearningStore, as_learning_store
from .test_adaptive_loop import SHADOW, TRAIN, Ideas, Proposer, Reviewer, loop


def test_consumer_store_records_and_reuses_tasks_after_reopen(tmp_path):
    adapter, proposer, reviewer = Ideas(), Proposer(), Reviewer()
    with ConsumerLearningStore(
        tmp_path, profile_id="consumer", initial_configuration={"offsets": [1]}
    ) as store:
        assert isinstance(store, LearningStore)
        assert FacadeLearningStore is LearningStore
        assert not isinstance(store, LocalLearningStore)
        assert not hasattr(store, "directory") and not hasattr(store, "artifacts")
        engine = loop(
            as_learning_store(store), adapter=adapter, proposer=proposer, reviewer=reviewer
        )
        observed = engine.run_task(TRAIN[0])
        assert observed.target_snapshot == store.active
        assert engine.learn("not-due", shadow_cases=SHADOW) is None
    with ConsumerLearningStore(tmp_path, profile_id="consumer") as store:
        engine = loop(store, adapter=adapter, proposer=proposer, reviewer=reviewer)
        assert engine.run_task(TRAIN[0]) == observed
        assert len(adapter.calls) == 1
        assert not proposer.calls and not reviewer.calls


@pytest.mark.parametrize("store", [None, object()])
def test_incomplete_store_rejected_before_consumer_calls(store):
    adapter, proposer, reviewer = Ideas(), Proposer(), Reviewer()
    with pytest.raises(TypeError, match="requires a LearningStore"):
        loop(store, adapter=adapter, proposer=proposer, reviewer=reviewer)
    assert not adapter.calls and not proposer.calls and not reviewer.calls


def test_invalid_runtime_store_rejected_before_consumer_calls(tmp_path):
    adapter, proposer, reviewer = Ideas(), Proposer(), Reviewer()
    with ConsumerLearningStore(
        tmp_path, profile_id="consumer", initial_configuration={"offsets": [1]}
    ) as store:
        store.runtime = object()
        with pytest.raises(TypeError, match="requires a RuntimeStore"):
            loop(store, adapter=adapter, proposer=proposer, reviewer=reviewer)
    assert not adapter.calls and not proposer.calls and not reviewer.calls


def test_consumer_write_failure_stops_before_proposals_or_trials(tmp_path):
    class UnavailableStore(ConsumerLearningStore):
        def begin_pass(self, inputs):
            raise OSError("consumer persistence unavailable")

    adapter, proposer, reviewer = Ideas(), Proposer(), Reviewer()
    with UnavailableStore(
        tmp_path, profile_id="consumer", initial_configuration={"offsets": [1]}
    ) as store:
        engine = loop(store, adapter=adapter, proposer=proposer, reviewer=reviewer)
        for case in TRAIN:
            engine.run_task(case)
        baseline = store.active
        with pytest.raises(OSError, match="consumer persistence unavailable"):
            engine.learn("cannot-start", shadow_cases=SHADOW, activate=True)
        assert store.active == baseline and store.pending_pass is None
    assert len(adapter.calls) == len(TRAIN)
    assert not proposer.calls and not reviewer.calls
