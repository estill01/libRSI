"""Single-owner application bindings for adaptive strategies and task feedback.

Workflow status stays in the ordinary RuntimeStore. This file owns only the
consumer's current configuration and immutable input/output references.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..identity import canonical_json, digest
from ..records import (
    ArtifactRef,
    Observation,
    RecordRef,
    SemanticRecord,
    TargetRef,
    TargetSnapshot,
    deserialize_record,
    record_from_dict,
    serialize_record,
)
from ..runtime import SQLiteRuntimeStore
from .artifacts import LocalArtifactStore


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be nonempty normalized text")
    return value


class LocalLearningStore:
    """Persist one consumer profile; callers serialize all use of its directory.

    Reopening with a different profile or initial configuration rejects. Completed
    records are immutable. An external host effect interrupted before its result
    is recorded may execute again; this adapter does not promise exactly-once I/O.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        profile_id: str,
        initial_configuration: Mapping[str, Any] | None = None,
    ) -> None:
        self.profile_id = _text(profile_id, "profile id")
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.target = TargetRef(target_id=profile_id, kind="adaptive-strategy")
        self.artifacts = LocalArtifactStore(self.directory / "artifacts")
        self._path = self.directory / "profile.json"
        if self._path.exists():
            state = self._read()
            if initial_configuration is not None:
                seed = self._load(state["initial"])
                if seed != self.snapshot(initial_configuration):
                    raise ValueError("profile initial configuration has changed")
        else:
            if initial_configuration is None:
                raise ValueError("a new profile requires an initial configuration")
            initial = self._save(self.snapshot(initial_configuration))
            self._write(
                {
                    "schema": 1,
                    "profile_id": profile_id,
                    "initial": initial,
                    "active": initial,
                    "last_effect": None,
                    "feedback": [],
                    "passes": {},
                    "pending_pass": None,
                }
            )
        self.runtime = SQLiteRuntimeStore(self.directory / "runtime.sqlite")

    def __enter__(self) -> LocalLearningStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self.runtime.close()

    def snapshot(self, configuration: Mapping[str, Any]) -> TargetSnapshot:
        if not isinstance(configuration, Mapping) or not configuration:
            raise ValueError("strategy configuration must be a nonempty JSON object")
        return TargetSnapshot(
            target=self.target,
            revision=digest(configuration),
            state=configuration,
        )

    def _save(self, record: SemanticRecord) -> dict[str, Any]:
        ref = self.artifacts.put(
            f"records/{record.record_type}/{record.root}.json",
            serialize_record(record).encode("utf-8"),
            media_type="application/json",
        )
        return ref.to_dict()

    def _load(self, value: Mapping[str, Any]) -> SemanticRecord:
        ref = record_from_dict(dict(value))
        if not isinstance(ref, ArtifactRef):
            raise ValueError("profile binding must reference an immutable artifact")
        record = deserialize_record(self.artifacts.get(ref).decode("utf-8"))
        if ref.artifact_id != f"records/{record.record_type}/{record.root}.json":
            raise ValueError("profile artifact does not name its canonical record")
        return record

    def _read(self) -> dict[str, Any]:
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
        }
        if not isinstance(value, dict) or set(value) != fields or value["schema"] != 1:
            raise ValueError("unsupported learning profile bindings")
        if value["profile_id"] != self.profile_id:
            raise ValueError("learning directory belongs to another profile")
        active = self._load(value["active"])
        if not isinstance(active, TargetSnapshot) or active.target != self.target:
            raise ValueError("active strategy belongs to another profile")
        if value["pending_pass"] is not None and value["pending_pass"] not in value["passes"]:
            raise ValueError("pending learning pass lost its input binding")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        temporary = self._path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self._path)

    @property
    def active(self) -> TargetSnapshot:
        active = self._load(self._read()["active"])
        assert isinstance(active, TargetSnapshot)
        return active

    @property
    def pending_pass(self) -> str | None:
        return self._read()["pending_pass"]

    def feedback(self, task_id: str | None = None) -> tuple[Observation, ...]:
        entries = self._read()["feedback"]
        result = []
        for entry in entries:
            key = entry["task_id"]
            if task_id is not None and key != task_id:
                continue
            record = self._load(entry["record"])
            if (
                not isinstance(record, Observation)
                or record.kind != "learning.feedback"
                or record.target_snapshot is None
                or record.target_snapshot.target != self.target
                or record.value["task_id"] != key
            ):
                raise ValueError("feedback is not bound to its task and profile")
            result.append(record)
        return tuple(result)

    def record_feedback(self, observation: Observation) -> Observation:
        if not isinstance(observation, Observation) or observation.kind != "learning.feedback":
            raise ValueError("expected measured learning feedback")
        task_id = _text(observation.value["task_id"], "task id")
        state = self._read()
        existing = self.feedback(task_id)
        if existing:
            if existing != (observation,):
                raise ValueError("task id already names different feedback")
            return existing[0]
        if state["pending_pass"] is not None:
            raise RuntimeError("resume the pending learning pass before ordinary tasks")
        if observation.target_snapshot != self.active:
            raise ValueError("task feedback was measured under a stale strategy")
        if self.active.ref not in observation.source_refs:
            raise ValueError("feedback must retain its producing strategy")
        state["feedback"].append({"task_id": task_id, "record": self._save(observation)})
        self._write(state)
        return observation

    def pass_input(self, pass_id: str) -> Observation | None:
        entry = self._read()["passes"].get(pass_id)
        if entry is None:
            return None
        record = self._load(entry["input"])
        if (
            not isinstance(record, Observation)
            or record.kind != "learning.pass"
            or record.value["pass_id"] != pass_id
            or record.target_snapshot is None
            or record.target_snapshot.target != self.target
        ):
            raise ValueError("learning pass input identity has changed")
        return record

    def begin_pass(self, inputs: Observation) -> None:
        if not isinstance(inputs, Observation) or inputs.kind != "learning.pass":
            raise ValueError("expected learning pass input binding")
        pass_id = _text(inputs.value["pass_id"], "pass id")
        state = self._read()
        existing = self.pass_input(pass_id)
        if existing is not None:
            if existing != inputs:
                raise ValueError("pass id already names different inputs")
            return
        if state["pending_pass"] is not None:
            raise RuntimeError("another learning pass is pending")
        if inputs.target_snapshot != self.active:
            raise ValueError("learning pass baseline is stale")
        state["passes"][pass_id] = {"input": self._save(inputs), "records": {}}
        state["pending_pass"] = pass_id
        self._write(state)

    def cached(self, pass_id: str, key: str) -> SemanticRecord | None:
        entry = self._read()["passes"][pass_id]["records"].get(key)
        return None if entry is None else self._load(entry)

    def remember(self, pass_id: str, key: str, record: SemanticRecord) -> None:
        state = self._read()
        records = state["passes"][pass_id]["records"]
        if key in records:
            if self._load(records[key]) != record:
                raise ValueError("completed learning work cannot be replaced")
            return
        if state["pending_pass"] != pass_id:
            raise RuntimeError("learning pass is not pending")
        records[key] = self._save(record)
        self._write(state)

    def finish_pass(self, pass_id: str, result: SemanticRecord) -> None:
        # The caller supplies the terminal result derived by the native workflows.
        self.remember(pass_id, "result", result)
        state = self._read()
        if state["pending_pass"] not in {None, pass_id}:
            raise RuntimeError("another learning pass is pending")
        state["pending_pass"] = None
        self._write(state)

    def apply_snapshot(
        self,
        *,
        expected: TargetSnapshot,
        replacement: TargetSnapshot,
        effect_root: str,
    ) -> TargetSnapshot:
        """Host-side compare-and-swap; the runner owns native application authority.

        The current data and exact effect identity are written together, allowing
        a repeated native action to recover after an interrupted runtime append.
        """
        state = self._read()
        effect_root = RecordRef(record_type="action", root=effect_root).root
        if state["pending_pass"] is None:
            raise RuntimeError("strategy application requires a pending learning pass")
        if expected.target != self.target or replacement.target != self.target:
            raise ValueError("strategy effect belongs to another profile")
        active = self.active
        if state["last_effect"] == effect_root:
            if active != replacement:
                raise ValueError("recorded strategy effect has drifted")
            return active
        if active != expected:
            raise ValueError("strategy effect baseline is stale")
        state["active"] = self._save(replacement)
        state["last_effect"] = _text(effect_root, "effect root")
        self._write(state)
        return replacement
