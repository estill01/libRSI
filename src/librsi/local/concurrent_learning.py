"""One-process durable bindings for concurrent serving and serialized learning.

The native application pointer may temporarily name an unverified candidate.
Serving instead pins the pending pass's baseline until its native terminal result
is committed. A separate SQLite ownership fence prevents a second local owner;
short in-process locks protect profile mutations without enclosing model calls.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from ..facade.learning_records import LearningCase, TaskMeasurement
from ..facade.learning_results import LearningTerminal, learning_result
from ..identity import digest, thaw
from ..records import (
    Metric,
    Observation,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    record_from_dict,
)
from .artifacts import _artifact_path
from .learning import LocalLearningStore, _text


class LocalConcurrentLearningStore(LocalLearningStore):
    """One local owner, many serving threads, and one learning operation at a time.

    Use a dedicated profile directory on an unsynchronized local filesystem. This
    backend uses schema 2 and intentionally does not migrate serialized schema-1
    profiles. All request/learning calls must share this instance; it is not a
    distributed queue. Drain request executions before closing the store.

    Task execution can be repeated after an interruption or concurrent duplicate
    submission. Admission pins its original inputs and snapshot, and exact repeated
    completions are idempotent. Hosts own idempotency for external effects.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        profile_id: str,
        initial_configuration: Mapping[str, Any] | None = None,
    ) -> None:
        self._state_lock = threading.RLock()
        self._learning_lock = threading.Lock()
        self._durable_directories: set[Path] = set()
        self._profile_sync_pending = True
        self._closed = False
        self._initializing = True
        root = Path(directory).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self._ownership = sqlite3.connect(root / "owner.sqlite", timeout=0, check_same_thread=False)
        try:
            self._ownership.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as error:
            self._ownership.close()
            self._closed = True
            raise RuntimeError("learning profile already has an owner") from error
        try:
            super().__init__(
                root,
                profile_id=profile_id,
                initial_configuration=initial_configuration,
            )
        except BaseException:
            self._ownership.close()
            self._closed = True
            raise
        finally:
            self._initializing = False

    def __enter__(self) -> LocalConcurrentLearningStore:
        self._require_open()
        return self

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("learning store is closed")

    @contextmanager
    def learning_owner(self) -> Iterator[None]:
        """Fence learning and runtime-history access without blocking serving."""
        with self._state_lock:
            self._require_open()
            if not self._learning_lock.acquire(blocking=False):
                raise RuntimeError("another learning operation owns this profile")
        try:
            yield
        finally:
            self._learning_lock.release()

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            if not self._learning_lock.acquire(blocking=False):
                raise RuntimeError("cannot close a profile with active learning")
            try:
                super().close()
                self._ownership.close()
                self._closed = True
            finally:
                self._learning_lock.release()

    def _read(self) -> dict[str, Any]:
        self._require_open()
        if self._profile_sync_pending:
            with self._path.open("rb") as stream:
                os.fsync(stream.fileno())
            self._sync_directories(self._path.parent)
            self._profile_sync_pending = False
        value = json.loads(self._path.read_text(encoding="utf-8"))
        fields = {
            "schema",
            "profile_id",
            "initial",
            "active",
            "last_effect",
            "feedback",
            "passes",
            "pending_pass",
            "task_admissions",
        }
        if not isinstance(value, dict) or set(value) != fields or value["schema"] != 2:
            raise ValueError("concurrent learning requires schema-2 profile bindings")
        if value["profile_id"] != self.profile_id:
            raise ValueError("learning directory belongs to another profile")
        if (
            not isinstance(value["task_admissions"], dict)
            or not isinstance(value["passes"], dict)
            or not isinstance(value["feedback"], list)
        ):
            raise ValueError("invalid concurrent learning profile bindings")
        active = self._load(value["active"])
        if not isinstance(active, TargetSnapshot) or active.target != self.target:
            raise ValueError("active strategy belongs to another profile")
        pending = value["pending_pass"]
        if pending is not None and (not isinstance(pending, str) or pending not in value["passes"]):
            raise ValueError("pending learning pass lost its input binding")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        self._require_open()
        if self._initializing and value.get("schema") == 1:
            value = {**value, "schema": 2, "task_admissions": {}}
        if value.get("schema") != 2:
            raise ValueError("concurrent learning requires schema-2 profile bindings")
        self._profile_sync_pending = True
        super()._write(value)
        self._sync_directories(self._path.parent)
        self._profile_sync_pending = False

    def _sync_directories(self, directory: Path) -> None:
        """Persist entries through the first already-durable ancestor.

        The immediate parent is always synced after a rename. Newly created
        directory chains also require their parent entries to reach storage.
        Directory fsync must be supported by the selected local filesystem.
        """
        synced = []
        while True:
            already_durable = directory in self._durable_directories
            descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            synced.append(directory)
            if already_durable or directory.parent == directory:
                break
            directory = directory.parent
        self._durable_directories.update(synced)

    def _save(self, record: SemanticRecord) -> dict[str, Any]:
        path = _artifact_path(
            self.artifacts.directory, f"records/{record.record_type}/{record.root}.json"
        )
        temporary = path.with_name(f".{path.name}.tmp")
        if temporary.exists() or temporary.is_symlink():
            # This profile's exclusive owner and state lock exclude another
            # writer. An interrupted artifact rename may leave arbitrary or
            # partial bytes here; discard only this exact canonical record's
            # uncommitted temporary file, then recompute it through the normal
            # content-checking artifact writer. Never trust/reuse its bytes.
            temporary.unlink()
        reference = super()._save(record)
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
        self._sync_directories(path.parent)
        return reference

    def _pass_input(self, state: Mapping[str, Any], pass_id: str) -> Observation:
        record = self._load(state["passes"][pass_id]["input"])
        if (
            not isinstance(record, Observation)
            or record.kind != "learning.pass"
            or record.value["pass_id"] != pass_id
            or record.target_snapshot is None
            or record.target_snapshot.target != self.target
        ):
            raise ValueError("learning pass input identity has changed")
        return record

    def _serving_snapshot(self, state: Mapping[str, Any]) -> TargetSnapshot:
        pending = state["pending_pass"]
        snapshot: SemanticRecord | None
        if pending is not None:
            snapshot = self._pass_input(state, pending).target_snapshot
        else:
            snapshot = self._load(state["active"])
        if not isinstance(snapshot, TargetSnapshot) or snapshot.target != self.target:
            raise ValueError("serving strategy belongs to another profile")
        return snapshot

    @property
    def serving_snapshot(self) -> TargetSnapshot:
        with self._state_lock:
            return self._serving_snapshot(self._read())

    @property
    def active(self) -> TargetSnapshot:
        with self._state_lock:
            return super().active

    @property
    def pending_pass(self) -> str | None:
        with self._state_lock:
            return super().pending_pass

    @property
    def pass_ids(self) -> tuple[str, ...]:
        with self._state_lock:
            return super().pass_ids

    def pass_input(self, pass_id: str) -> Observation | None:
        with self._state_lock:
            return super().pass_input(pass_id)

    def begin_pass(self, inputs: Observation) -> None:
        with self._state_lock:
            super().begin_pass(inputs)

    def cached(self, pass_id: str, key: str) -> SemanticRecord | None:
        with self._state_lock:
            return super().cached(pass_id, key)

    def remember(self, pass_id: str, key: str, record: SemanticRecord) -> None:
        with self._state_lock:
            super().remember(pass_id, key, record)

    def apply_snapshot(
        self,
        *,
        expected: TargetSnapshot,
        replacement: TargetSnapshot,
        effect_root: str,
    ) -> TargetSnapshot:
        with self._state_lock:
            return super().apply_snapshot(
                expected=expected, replacement=replacement, effect_root=effect_root
            )

    def finish_pass(self, pass_id: str, result: SemanticRecord) -> None:
        """Atomically retain a native terminal result and publish its verified state."""
        with self._state_lock:
            state = self._read()
            inputs = self._pass_input(state, pass_id)
            records = state["passes"][pass_id]["records"]
            existing = records.get("result")
            if existing is not None:
                if self._load(existing) != result:
                    raise ValueError("completed learning work cannot be replaced")
                if state["pending_pass"] != pass_id:
                    # Historical retries cannot republish an older snapshot or
                    # clear the identity of a newer in-flight learning pass.
                    return
            if state["pending_pass"] != pass_id:
                raise RuntimeError("learning pass is not pending")
            terminal = learning_result(self, inputs, cast(LearningTerminal, result))
            if not terminal.adopted and terminal.strategy_after != inputs.target_snapshot:
                raise ValueError("unverified strategy cannot be published for serving")
            if self._load(state["active"]) != terminal.strategy_after:
                raise RuntimeError("active strategy does not match the native terminal result")
            records["result"] = self._save(result)
            state["pending_pass"] = None
            self._write(state)

    def _admission(self, value: Mapping[str, Any], task_id: str) -> Observation:
        record = self._load(value)
        fields = {"task_id", "case", "adapter_id", "metric_id", "metric_root"}
        if (
            not isinstance(record, Observation)
            or record.kind != "learning.task-admission"
            or record.target_snapshot is None
            or record.target_snapshot.target != self.target
            or not isinstance(record.value, Mapping)
            or set(record.value) != fields
            or record.value["task_id"] != task_id
        ):
            raise ValueError("task admission is not bound to its task and profile")
        case_record = record_from_dict(thaw(record.value["case"]))
        if not isinstance(case_record, Observation) or case_record.kind != "learning.case":
            raise ValueError("task admission must retain its exact learning case")
        case = LearningCase(case_record.value["case_id"], case_record.value["payload"])
        if case.case_id != task_id or case.record != case_record:
            raise ValueError("task admission must retain its exact learning case")
        _text(record.value["adapter_id"], "adapter id")
        _text(record.value["metric_id"], "metric id")
        RecordRef(record_type="metric", root=record.value["metric_root"])
        if record.source_refs != (case_record.ref, record.target_snapshot.ref):
            raise ValueError("task admission must retain its producing strategy")
        return record

    def admit_task(self, case: LearningCase, *, adapter_id: str, metric: Metric) -> Observation:
        """Durably pin a task before execution; retries retain the original snapshot."""
        if not isinstance(case, LearningCase):
            raise TypeError("ordinary tasks require LearningCase")
        _text(case.case_id, "task id")
        adapter_id = _text(adapter_id, "adapter id")
        if not isinstance(metric, Metric):
            raise TypeError("task admission requires a Metric")
        _text(metric.metric_id, "metric id")
        with self._state_lock:
            state = self._read()
            existing = state["task_admissions"].get(case.case_id)
            if existing is not None:
                admission = self._admission(existing, case.case_id)
                if (
                    digest(admission.value["case"]) != digest(case.record.to_dict())
                    or admission.value["adapter_id"] != adapter_id
                    or admission.value["metric_id"] != metric.metric_id
                    or admission.value["metric_root"] != metric.root
                ):
                    raise ValueError("task id already names different inputs or scoring")
                return admission
            if super().feedback(case.case_id):
                raise ValueError("task id already has feedback without a concurrent admission")
            snapshot = self._serving_snapshot(state)
            admission = Observation(
                kind="learning.task-admission",
                target_snapshot=snapshot,
                value={
                    "task_id": case.case_id,
                    "case": case.record.to_dict(),
                    "adapter_id": adapter_id,
                    "metric_id": metric.metric_id,
                    "metric_root": metric.root,
                },
                source_refs=(case.record.ref, snapshot.ref),
            )
            state["task_admissions"][case.case_id] = self._save(admission)
            self._write(state)
            return admission

    @staticmethod
    def _task_feedback(admission: Observation, measured: TaskMeasurement) -> Observation:
        return Observation(
            kind="learning.feedback",
            target_snapshot=admission.target_snapshot,
            value={
                **dict(admission.value),
                "output": measured.output,
                "value": measured.value,
            },
            source_refs=(*admission.source_refs, admission.ref),
        )

    def complete_task(self, admission: Observation, measurement: TaskMeasurement) -> Observation:
        """Retain actual producing lineage even after a newer strategy is published."""
        if not isinstance(admission, Observation) or admission.kind != "learning.task-admission":
            raise ValueError("completion requires an exact task admission")
        if not isinstance(measurement, TaskMeasurement):
            raise TypeError("learning adapter must return TaskMeasurement")
        task_id = _text(admission.value["task_id"], "task id")
        with self._state_lock:
            state = self._read()
            saved = state["task_admissions"].get(task_id)
            if saved is None or self._admission(saved, task_id) != admission:
                raise ValueError("completion does not match a recorded task admission")
            observation = self._task_feedback(admission, measurement)
            existing = self.feedback(task_id)
            if existing:
                if existing != (observation,):
                    raise ValueError("task id already names different feedback")
                return existing[0]
            state["feedback"].append({"task_id": task_id, "record": self._save(observation)})
            self._write(state)
            return observation

    def feedback(self, task_id: str | None = None) -> tuple[Observation, ...]:
        with self._state_lock:
            state = self._read()
            observations = super().feedback(task_id)
            for observation in observations:
                saved = state["task_admissions"].get(observation.value["task_id"])
                if saved is None:
                    continue
                admission = self._admission(saved, observation.value["task_id"])
                expected = self._task_feedback(
                    admission,
                    TaskMeasurement(observation.value["output"], observation.value["value"]),
                )
                if observation != expected:
                    raise ValueError("task feedback does not match its exact admission")
            return observations

    def record_feedback(self, observation: Observation) -> Observation:
        """Keep the serialized feedback contract; admitted tasks use complete_task."""
        with self._state_lock:
            state = self._read()
            if isinstance(observation, Observation) and isinstance(observation.value, Mapping):
                task_id = observation.value.get("task_id")
                if isinstance(task_id, str) and task_id in state["task_admissions"]:
                    existing = self.feedback(task_id)
                    if existing == (observation,):
                        return observation
                    raise ValueError("admitted task feedback requires complete_task")
            return super().record_feedback(observation)
