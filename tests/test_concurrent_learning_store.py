"""Durable serving admissions are independent of native application progress."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from librsi import (
    LearningCase,
    LocalConcurrentLearningStore,
    LocalLearningStore,
    Metric,
    Observation,
    TaskMeasurement,
)

METRIC = Metric(metric_id="loss", direction="decrease", role="objective", unit="distance")


def admission(store, task_id="task-1", *, payload=None, adapter_id="adapter-v1", metric=METRIC):
    return store.admit_task(
        LearningCase(task_id, {"input": task_id} if payload is None else payload),
        adapter_id=adapter_id,
        metric=metric,
    )


def pass_input(store, pass_id="learn-1"):
    baseline = store.active
    return Observation(
        kind="learning.pass",
        value={"pass_id": pass_id},
        target_snapshot=baseline,
        source_refs=(baseline.ref,),
    )


def subprocess_environment():
    environment = os.environ.copy()
    source = str(Path(__file__).resolve().parents[1] / "src")
    prior = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = source if not prior else os.pathsep.join((source, prior))
    return environment


def test_admission_and_exact_completion_survive_reopening(tmp_path):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="served", initial_configuration={"width": 1}
    ) as store:
        original = store.serving_snapshot
        pinned = admission(store)
        assert pinned.target_snapshot == original
    with LocalConcurrentLearningStore(tmp_path, profile_id="served") as store:
        assert admission(store) == pinned
        measured = TaskMeasurement({"answer": "one"}, 1)
        feedback = store.complete_task(pinned, measured)
        assert store.complete_task(pinned, measured) == feedback
        assert feedback.target_snapshot == original
        assert pinned.ref in feedback.source_refs
        assert original.ref in feedback.source_refs
        assert feedback.value["adapter_id"] == "adapter-v1"
        assert feedback.value["metric_root"] == METRIC.root
    with LocalConcurrentLearningStore(tmp_path, profile_id="served") as store:
        assert store.feedback("task-1") == (feedback,)
        assert admission(store) == pinned
        with pytest.raises(ValueError):
            store.complete_task(pinned, TaskMeasurement({"answer": "different"}, 2))
        assert store.feedback() == (feedback,)


@pytest.mark.parametrize(
    "changed",
    [
        {"payload": {"input": "changed"}},
        {"adapter_id": "adapter-v2"},
        {"metric": Metric(metric_id="cost", direction="decrease", role="objective")},
        {"metric": Metric(metric_id="loss", direction="increase", role="objective")},
    ],
)
def test_task_identity_binds_case_adapter_and_metric(tmp_path, changed):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="identity", initial_configuration={"width": 1}
    ) as store:
        pinned = admission(store)
        with pytest.raises(ValueError):
            admission(store, **changed)
        assert admission(store) == pinned
        assert not store.feedback()


def test_completion_rejects_unadmitted_changed_and_foreign_snapshots(tmp_path):
    with (
        LocalConcurrentLearningStore(
            tmp_path / "a", profile_id="a", initial_configuration={"width": 1}
        ) as a,
        LocalConcurrentLearningStore(
            tmp_path / "b", profile_id="b", initial_configuration={"width": 1}
        ) as b,
    ):
        pinned = admission(a)
        measured = TaskMeasurement({"answer": 1}, 0)
        with pytest.raises(ValueError):
            b.complete_task(pinned, measured)
        forged = Observation(
            kind=pinned.kind,
            value=pinned.value,
            target_snapshot=a.snapshot({"width": 99}),
            source_refs=pinned.source_refs,
        )
        with pytest.raises(ValueError):
            a.complete_task(forged, measured)
        with pytest.raises((TypeError, ValueError)):
            a.complete_task(pinned, object())
        assert not a.feedback() and not b.feedback()


def test_unusable_identifiers_reject_before_a_task_is_admitted(tmp_path):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="identifiers", initial_configuration={"width": 1}
    ) as store:
        before = (tmp_path / "profile.json").read_bytes()
        with pytest.raises(ValueError):
            admission(store, " task-1 ")
        with pytest.raises(ValueError):
            admission(store, adapter_id=" adapter-v1 ")
        assert (tmp_path / "profile.json").read_bytes() == before


def test_unverified_effect_never_changes_serving_even_after_restart(tmp_path):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="pending", initial_configuration={"width": 1}
    ) as store:
        baseline = store.serving_snapshot
        store.begin_pass(pass_input(store))
        candidate = store.snapshot({"width": 2})
        store.apply_snapshot(expected=baseline, replacement=candidate, effect_root="a" * 64)
        assert store.active == candidate
        assert store.serving_snapshot == baseline
        pinned = admission(store)
        assert pinned.target_snapshot == baseline
    with LocalConcurrentLearningStore(tmp_path, profile_id="pending") as store:
        assert store.active == candidate
        assert store.serving_snapshot == baseline
        assert admission(store) == pinned
        feedback = store.complete_task(pinned, TaskMeasurement({"answer": 1}, 0))
        assert feedback.target_snapshot == baseline
        with pytest.raises((TypeError, ValueError)):
            store.finish_pass("learn-1", feedback)
        assert store.pending_pass == "learn-1"
        assert store.serving_snapshot == baseline


def test_parallel_task_completions_and_learning_writes_lose_no_feedback(tmp_path):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="parallel", initial_configuration={"width": 1}
    ) as store:
        inputs = pass_input(store)
        store.begin_pass(inputs)
        barrier = Barrier(8, timeout=10)

        def work(index):
            pinned = admission(store, f"task-{index}")
            barrier.wait()
            observation = store.complete_task(pinned, TaskMeasurement({"index": index}, index))
            store.remember("learn-1", f"work-{index}", observation)
            return observation

        with ThreadPoolExecutor(max_workers=8) as pool:
            observations = tuple(pool.map(work, range(32)))
        assert len(store.feedback()) == 32
        assert {item.root for item in store.feedback()} == {item.root for item in observations}
        assert store.pass_input("learn-1") == inputs
        for index, observed in enumerate(observations):
            assert store.cached("learn-1", f"work-{index}") == observed
    with LocalConcurrentLearningStore(tmp_path, profile_id="parallel") as store:
        assert len(store.feedback()) == 32
        assert store.pending_pass == "learn-1"


def test_learning_owner_excludes_other_threads_without_blocking_serving(tmp_path):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="owner", initial_configuration={"width": 1}
    ) as store:
        with store.learning_owner(), ThreadPoolExecutor(max_workers=1) as pool:
            pinned = pool.submit(admission, store).result(timeout=10)
            assert pinned.target_snapshot == store.serving_snapshot

            def competing_learner():
                with store.learning_owner():
                    pytest.fail("a second learner entered the owned profile")

            future = pool.submit(competing_learner)
            with pytest.raises(RuntimeError):
                future.result(timeout=10)
        with store.learning_owner():
            assert store.serving_snapshot == store.active


def test_directory_ownership_is_fenced_across_processes_and_released_on_close(tmp_path):
    code = """
import sys
from librsi import LocalConcurrentLearningStore
try:
    store = LocalConcurrentLearningStore(sys.argv[1], profile_id="owner")
except RuntimeError:
    print("ownership rejected")
else:
    store.close()
    raise SystemExit("second process acquired an owned profile")
"""
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="owner", initial_configuration={"width": 1}
    ) as store:
        with pytest.raises(RuntimeError):
            LocalConcurrentLearningStore(tmp_path, profile_id="owner")
        result = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path)],
            env=subprocess_environment(),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert result.stdout.strip() == "ownership rejected"
        assert store.serving_snapshot.state["width"] == 1
    with LocalConcurrentLearningStore(tmp_path, profile_id="owner") as reopened:
        assert reopened.serving_snapshot.state["width"] == 1


def test_process_exit_releases_ownership_and_keeps_durable_admission(tmp_path):
    code = """
import os
import sys
from librsi import LearningCase, LocalConcurrentLearningStore, Metric
store = LocalConcurrentLearningStore(
    sys.argv[1], profile_id="crashed", initial_configuration={"width": 1}
)
store.admit_task(
    LearningCase("task-1", {"input": "task-1"}),
    adapter_id="adapter-v1",
    metric=Metric(metric_id="loss", direction="decrease", role="objective", unit="distance"),
)
os._exit(0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env=subprocess_environment(),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    with LocalConcurrentLearningStore(tmp_path, profile_id="crashed") as store:
        pinned = admission(store)
        feedback = store.complete_task(pinned, TaskMeasurement({"answer": 1}, 0))
        assert feedback.target_snapshot == store.serving_snapshot


def test_failed_initialization_releases_directory_ownership(tmp_path):
    with pytest.raises(ValueError):
        LocalConcurrentLearningStore(tmp_path, profile_id="owner")
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="owner", initial_configuration={"width": 1}
    ):
        pass
    with pytest.raises(ValueError):
        LocalConcurrentLearningStore(tmp_path, profile_id="different")
    with LocalConcurrentLearningStore(tmp_path, profile_id="owner") as store:
        assert store.serving_snapshot.state["width"] == 1


def test_legacy_and_concurrent_profiles_cannot_be_opened_as_each_other(tmp_path):
    with LocalLearningStore(
        tmp_path / "legacy", profile_id="legacy", initial_configuration={"width": 1}
    ):
        pass
    with pytest.raises(ValueError):
        LocalConcurrentLearningStore(tmp_path / "legacy", profile_id="legacy")
    with LocalLearningStore(tmp_path / "legacy", profile_id="legacy") as legacy:
        assert legacy.active.state["width"] == 1
    with LocalConcurrentLearningStore(
        tmp_path / "concurrent", profile_id="concurrent", initial_configuration={"width": 1}
    ):
        pass
    with pytest.raises(ValueError):
        LocalLearningStore(tmp_path / "concurrent", profile_id="concurrent")
    with LocalConcurrentLearningStore(tmp_path / "concurrent", profile_id="concurrent"):
        pass
