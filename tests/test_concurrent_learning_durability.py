"""Fault injection at record flush and profile publication boundaries."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from librsi import LearningCase, LocalConcurrentLearningStore, Metric, Observation, TaskMeasurement

METRIC = Metric(metric_id="loss", direction="decrease", role="objective", unit="distance")


def admit(store, task_id="task-1"):
    return store.admit_task(
        LearningCase(task_id, {"input": task_id}), adapter_id="adapter-v1", metric=METRIC
    )


def fail_sync_for(monkeypatch, path: Path):
    """Keep failing the selected real file/directory descriptor until restored."""
    original = os.fsync
    calls = []

    def interrupted(descriptor):
        stat = os.fstat(descriptor)
        if path.exists():
            expected = path.stat()
            if (stat.st_dev, stat.st_ino) == (expected.st_dev, expected.st_ino):
                calls.append(path)
                raise OSError("injected durability failure")
        return original(descriptor)

    monkeypatch.setattr(os, "fsync", interrupted)
    return original, calls


def test_feedback_artifact_is_flushed_before_profile_can_reference_it(tmp_path, monkeypatch):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="artifact", initial_configuration={"width": 1}
    ) as store:
        pinned = admit(store)
        measured = TaskMeasurement({"answer": 1}, 0)
        record = store._task_feedback(pinned, measured)
        artifact = tmp_path / "artifacts" / "records" / "observation" / f"{record.root}.json"
        profile_before = (tmp_path / "profile.json").read_bytes()
        original_sync, failures = fail_sync_for(monkeypatch, artifact)
        with pytest.raises(OSError, match="durability failure"):
            store.complete_task(pinned, measured)
        assert failures
        assert (tmp_path / "profile.json").read_bytes() == profile_before
        assert not store.feedback()
        monkeypatch.setattr(os, "fsync", original_sync)
        observed = store.complete_task(pinned, measured)
        assert observed == record
        assert store.feedback() == (record,)


def test_failed_profile_sync_must_be_repaired_before_feedback_is_returned(tmp_path, monkeypatch):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="feedback", initial_configuration={"width": 1}
    ) as store:
        pinned = admit(store)
        measured = TaskMeasurement({"answer": 1}, 0)
        original_sync, failures = fail_sync_for(monkeypatch, tmp_path)
        with pytest.raises(OSError, match="durability failure"):
            store.complete_task(pinned, measured)
        # The rename may have happened, but neither reads nor exact retries may
        # acknowledge that write while directory durability is unresolved.
        with pytest.raises(OSError, match="durability failure"):
            store.feedback()
        with pytest.raises(OSError, match="durability failure"):
            store.complete_task(pinned, measured)
        assert len(failures) == 3
        monkeypatch.setattr(os, "fsync", original_sync)
        recovered = store.complete_task(pinned, measured)
        assert store.feedback() == (recovered,)
        assert store.complete_task(pinned, measured) == recovered
    with LocalConcurrentLearningStore(tmp_path, profile_id="feedback") as store:
        assert store.feedback() == (recovered,)


def test_reopening_repairs_admission_sync_before_allowing_execution(tmp_path, monkeypatch):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="reopen", initial_configuration={"width": 1}
    ) as store:
        baseline = store.serving_snapshot
        original_sync, failures = fail_sync_for(monkeypatch, tmp_path)
        with pytest.raises(OSError, match="durability failure"):
            admit(store)
        assert failures
    # Opening with the same unresolved sync fault must fail and release ownership.
    with pytest.raises(OSError, match="durability failure"):
        LocalConcurrentLearningStore(tmp_path, profile_id="reopen")
    monkeypatch.setattr(os, "fsync", original_sync)
    with LocalConcurrentLearningStore(tmp_path, profile_id="reopen") as store:
        pinned = admit(store)
        assert pinned.target_snapshot == baseline
        assert (
            store.complete_task(pinned, TaskMeasurement({"answer": 1}, 0)).target_snapshot
            == baseline
        )
        assert len(store.feedback()) == 1


def test_application_sync_failure_cannot_publish_an_unverified_candidate(tmp_path, monkeypatch):
    with LocalConcurrentLearningStore(
        tmp_path, profile_id="application", initial_configuration={"width": 1}
    ) as store:
        baseline = store.serving_snapshot
        store.begin_pass(
            Observation(
                kind="learning.pass",
                value={"pass_id": "learning"},
                target_snapshot=baseline,
                source_refs=(baseline.ref,),
            )
        )
        candidate = store.snapshot({"width": 2})
        original_sync, failures = fail_sync_for(monkeypatch, tmp_path)
        with pytest.raises(OSError, match="durability failure"):
            store.apply_snapshot(expected=baseline, replacement=candidate, effect_root="a" * 64)
        with pytest.raises(OSError, match="durability failure"):
            _ = store.serving_snapshot
        assert failures
        monkeypatch.setattr(os, "fsync", original_sync)
        # Repairing the uncertain application write preserves pending-pass
        # isolation; it is not evidence of successful candidate verification.
        assert store.active == candidate
        assert store.serving_snapshot == baseline
        assert admit(store).target_snapshot == baseline
    with LocalConcurrentLearningStore(tmp_path, profile_id="application") as store:
        assert store.active == candidate
        assert store.serving_snapshot == baseline


@pytest.mark.parametrize("partial", [False, True])
def test_interrupted_artifact_rename_is_recoverable_after_reopening(tmp_path, monkeypatch, partial):
    original_replace = Path.replace
    orphaned = []

    def interrupted_replace(source, target):
        if source.parent.name == "observation" and source.name.endswith(".json.tmp"):
            if partial:
                source.write_bytes(source.read_bytes()[:17])
            orphaned.append(source)
            raise KeyboardInterrupt("after artifact write, before rename")
        return original_replace(source, target)

    with LocalConcurrentLearningStore(
        tmp_path, profile_id="rename", initial_configuration={"width": 1}
    ) as store:
        baseline = store.serving_snapshot
        profile_before = (tmp_path / "profile.json").read_bytes()
        with monkeypatch.context() as interrupted:
            interrupted.setattr(Path, "replace", interrupted_replace)
            with pytest.raises(KeyboardInterrupt, match="before rename"):
                admit(store)
        assert len(orphaned) == 1 and orphaned[0].is_file()
        assert (tmp_path / "profile.json").read_bytes() == profile_before
        assert not store.feedback()
    with LocalConcurrentLearningStore(tmp_path, profile_id="rename") as store:
        pinned = admit(store)
        assert pinned.target_snapshot == baseline
        assert not orphaned[0].exists()
        completed = store.complete_task(pinned, TaskMeasurement({"answer": 1}, 0))
        assert completed.target_snapshot == baseline
        assert store.feedback() == (completed,)
    with LocalConcurrentLearningStore(tmp_path, profile_id="rename") as store:
        assert admit(store) == pinned
        assert store.feedback() == (completed,)
