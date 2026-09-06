from __future__ import annotations

import json

import pytest

from librsi import Observation
from librsi.local.learning import LocalLearningStore


def feedback(store, task_id="task-1", value=1):
    snapshot = store.active
    return Observation(
        kind="learning.feedback",
        value={"task_id": task_id, "score": value},
        target_snapshot=snapshot,
        source_refs=(snapshot.ref,),
    )


def pass_input(store, pass_id="learn-1"):
    return Observation(
        kind="learning.pass",
        value={"pass_id": pass_id},
        target_snapshot=store.active,
        source_refs=(store.active.ref,),
    )


def test_profile_feedback_and_cached_work_survive_restart(tmp_path):
    with LocalLearningStore(
        tmp_path, profile_id="alpha", initial_configuration={"width": 1}
    ) as store:
        initial = store.active
        measured = feedback(store, "z-last-in-sort")
        store.record_feedback(measured)
        store.record_feedback(measured)
        store.record_feedback(feedback(store, "a-second"))
        assert [item.value["task_id"] for item in store.feedback()] == [
            "z-last-in-sort",
            "a-second",
        ]
        with pytest.raises(ValueError, match="different feedback"):
            store.record_feedback(feedback(store, "z-last-in-sort", 2))
        inputs = pass_input(store)
        store.begin_pass(inputs)
        store.remember("learn-1", "completed-call", measured)
    with LocalLearningStore(
        tmp_path, profile_id="alpha", initial_configuration={"width": 1}
    ) as store:
        assert store.active == initial
        assert store.pending_pass == "learn-1"
        assert store.pass_input("learn-1") == inputs
        assert store.cached("learn-1", "completed-call") == measured
        store.remember("learn-1", "completed-call", measured)
        with pytest.raises(ValueError, match="cannot be replaced"):
            store.remember("learn-1", "completed-call", feedback(store, value=2))
        with pytest.raises(RuntimeError, match="pending learning pass"):
            store.record_feedback(feedback(store, "task-3"))
        store.finish_pass("learn-1", measured)
        store.finish_pass("learn-1", measured)
        assert store.pending_pass is None


def test_profile_identity_pass_identity_and_currentness_are_explicit(tmp_path):
    with LocalLearningStore(
        tmp_path, profile_id="alpha", initial_configuration={"width": 1}
    ) as store:
        with pytest.raises(ValueError, match="another profile"):
            LocalLearningStore(tmp_path, profile_id="beta")
        with pytest.raises(ValueError, match="initial configuration has changed"):
            LocalLearningStore(tmp_path, profile_id="alpha", initial_configuration={"width": 2})
        inputs = pass_input(store)
        store.begin_pass(inputs)
        with pytest.raises(ValueError, match="different inputs"):
            store.begin_pass(
                Observation(
                    kind="learning.pass",
                    value={"pass_id": "learn-1", "changed": True},
                    target_snapshot=store.active,
                )
            )
        with pytest.raises(RuntimeError, match="another learning pass"):
            store.begin_pass(pass_input(store, "learn-2"))


def test_strategy_effect_is_recoverable_and_old_revisions_remain(tmp_path):
    with LocalLearningStore(
        tmp_path, profile_id="alpha", initial_configuration={"width": 1}
    ) as store:
        original = store.active
        measured = feedback(store)
        store.record_feedback(measured)
        inputs = pass_input(store)
        store.begin_pass(inputs)
        changed = store.snapshot({"width": 2})
        store.apply_snapshot(expected=original, replacement=changed, effect_root="a" * 64)
    with LocalLearningStore(tmp_path, profile_id="alpha") as store:
        assert (
            store.apply_snapshot(expected=original, replacement=changed, effect_root="a" * 64)
            == changed
        )
        assert store.feedback()[0].target_snapshot == original
        with pytest.raises(ValueError, match="baseline is stale"):
            store.apply_snapshot(expected=original, replacement=changed, effect_root="b" * 64)
        store.apply_snapshot(expected=changed, replacement=original, effect_root="c" * 64)
        assert store.active == original
        with pytest.raises(ValueError, match="effect has drifted"):
            store.apply_snapshot(expected=original, replacement=changed, effect_root="c" * 64)


def test_tampered_artifact_and_cross_profile_active_binding_reject(tmp_path):
    with LocalLearningStore(
        tmp_path / "alpha", profile_id="alpha", initial_configuration={"width": 1}
    ) as store:
        active = store.active
        path = next((store.directory / "artifacts/records/target_snapshot").glob("*.json"))
        original_bytes = path.read_bytes()
        path.write_bytes(original_bytes.replace(b'"width":1', b'"width":2'))
        with pytest.raises(ValueError, match="content no longer matches"):
            _ = store.active
        path.write_bytes(original_bytes)
        assert store.active == active
        binding = json.loads((store.directory / "profile.json").read_text())
        binding["profile_id"] = "beta"
        (store.directory / "profile.json").write_text(json.dumps(binding))
        with pytest.raises(ValueError, match="another profile"):
            _ = store.active
