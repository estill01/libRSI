"""SQLite persistence for admissions and request-to-runtime bindings."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from ..improvement import ImprovementRequest
from ..investigation import InvestigationRequest
from ..records import SemanticRecord, TargetSnapshot, deserialize_record, serialize_record
from ..rsi import RSIRequest
from ..validation import ValidationRequest
from .records import RunAdmissionBinding, TargetAdmission

WorkflowRequest = ValidationRequest | InvestigationRequest | ImprovementRequest | RSIRequest
_WORKFLOWS: dict[str, type[WorkflowRequest]] = {
    "validation": ValidationRequest,
    "investigation": InvestigationRequest,
    "improvement": ImprovementRequest,
    "rsi": RSIRequest,
}
_RecordT = TypeVar("_RecordT", bound=SemanticRecord)


def _initial_snapshot(request: WorkflowRequest) -> TargetSnapshot | None:
    if type(request) is ValidationRequest or type(request) is InvestigationRequest:
        return request.target_snapshot
    if type(request) is ImprovementRequest:
        return request.baseline
    if type(request) is RSIRequest:
        return request.declaration.target_snapshot
    raise TypeError("unsupported external workflow request")


@dataclass(frozen=True)
class AgentRunBinding:
    workflow: str
    request: WorkflowRequest
    admission: TargetAdmission
    current_snapshot: TargetSnapshot

    def __post_init__(self) -> None:
        expected = _WORKFLOWS.get(self.workflow)
        if expected is None or type(self.request) is not expected:
            raise ValueError("agent run workflow does not match its exact request")
        if type(self.admission) is not TargetAdmission:
            raise TypeError("agent run binding requires a TargetAdmission")
        if type(self.current_snapshot) is not TargetSnapshot:
            raise TypeError("agent run binding requires an exact current snapshot")
        initial_snapshot = _initial_snapshot(self.request)
        if initial_snapshot is None or initial_snapshot != self.admission.target_snapshot:
            raise ValueError("agent run request and admission baseline have diverged")
        if self.current_snapshot.target != self.admission.target_snapshot.target:
            raise ValueError("agent run current snapshot names a different target")
        if self.workflow != "rsi" and self.current_snapshot != initial_snapshot:
            raise ValueError("non-RSI agent runs cannot mutate their admitted current snapshot")

    @property
    def run_id(self) -> str:
        return self.request.canonical_run().run_id

    @property
    def authority(self) -> RunAdmissionBinding:
        return RunAdmissionBinding.create(
            run_id=self.run_id,
            workflow=self.workflow,
            request=self.request,
            admission=self.admission,
            initial_snapshot=self.admission.target_snapshot,
        )


def _decode(serialized: str, expected: type[_RecordT]) -> _RecordT:
    record = deserialize_record(serialized)
    if type(record) is not expected or serialize_record(record) != serialized:
        raise ValueError("agent store record is not exact canonical data")
    return record


class SQLiteAgentStore:
    """Durable non-authoritative registry for requests and target admissions."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        self._connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS agent_admissions (
                admission_id TEXT PRIMARY KEY,
                admission_root TEXT NOT NULL UNIQUE,
                serialized TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                workflow TEXT NOT NULL,
                request_root TEXT NOT NULL UNIQUE,
                request_serialized TEXT NOT NULL,
                admission_root TEXT NOT NULL,
                current_snapshot_root TEXT NOT NULL,
                current_snapshot_serialized TEXT NOT NULL,
                FOREIGN KEY(admission_root) REFERENCES agent_admissions(admission_root)
            );
            CREATE TABLE IF NOT EXISTS agent_run_authorities (
                run_id TEXT PRIMARY KEY,
                binding_root TEXT NOT NULL UNIQUE,
                serialized TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
            );
            """
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQLite agent store is closed")

    def put_admission(self, admission: TargetAdmission) -> TargetAdmission:
        self._ensure_open()
        if type(admission) is not TargetAdmission:
            raise TypeError("agent stores accept exact TargetAdmission records")
        serialized = serialize_record(admission)
        existing = self._connection.execute(
            "SELECT admission_root, serialized FROM agent_admissions WHERE admission_id = ?",
            (admission.admission_id,),
        ).fetchone()
        if existing is not None:
            if existing["admission_root"] != admission.root or existing["serialized"] != serialized:
                raise ValueError("admission id already names divergent canonical data")
            return admission
        same_root = self._connection.execute(
            "SELECT admission_id, serialized FROM agent_admissions WHERE admission_root = ?",
            (admission.root,),
        ).fetchone()
        if same_root is not None:
            raise ValueError("admission root is already bound to a different admission id")
        self._connection.execute(
            "INSERT INTO agent_admissions(admission_id, admission_root, serialized) VALUES (?, ?, ?)",
            (admission.admission_id, admission.root, serialized),
        )
        self._connection.commit()
        return admission

    def get_admission(self, admission_id: str) -> TargetAdmission | None:
        self._ensure_open()
        row = self._connection.execute(
            """
            SELECT admission_id, admission_root, serialized
            FROM agent_admissions WHERE admission_id = ?
            """,
            (admission_id,),
        ).fetchone()
        if row is None:
            return None
        admission = _decode(row["serialized"], TargetAdmission)
        if admission.admission_id != row["admission_id"] or admission.root != row["admission_root"]:
            raise ValueError("stored admission identity diverges from canonical data")
        return admission

    def bind_run(self, binding: AgentRunBinding) -> AgentRunBinding:
        self._ensure_open()
        if type(binding) is not AgentRunBinding:
            raise TypeError("agent stores require an AgentRunBinding")
        request_bytes = serialize_record(binding.request)
        snapshot_bytes = serialize_record(binding.current_snapshot)
        authority = binding.authority
        authority_bytes = serialize_record(authority)
        existing = self._connection.execute(
            "SELECT * FROM agent_runs WHERE run_id = ?", (binding.run_id,)
        ).fetchone()
        if existing is not None:
            loaded = self.load_run(binding.run_id)
            if loaded != binding:
                raise ValueError("run id already names a divergent external binding")
            return binding
        same_request = self._connection.execute(
            "SELECT run_id FROM agent_runs WHERE request_root = ?",
            (binding.request.root,),
        ).fetchone()
        if same_request is not None:
            raise ValueError("request root is already bound to a different run id")
        try:
            self._connection.execute(
                """
                INSERT INTO agent_runs(
                    run_id, workflow, request_root, request_serialized, admission_root,
                    current_snapshot_root, current_snapshot_serialized
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    binding.run_id,
                    binding.workflow,
                    binding.request.root,
                    request_bytes,
                    binding.admission.root,
                    binding.current_snapshot.root,
                    snapshot_bytes,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO agent_run_authorities(run_id, binding_root, serialized)
                VALUES (?, ?, ?)
                """,
                (binding.run_id, authority.root, authority_bytes),
            )
        except Exception:
            self._connection.rollback()
            raise
        self._connection.commit()
        return binding

    def load_run(self, run_id: str) -> AgentRunBinding | None:
        self._ensure_open()
        row = self._connection.execute(
            """
            SELECT r.*, a.admission_id AS stored_admission_id,
                   a.serialized AS admission_serialized,
                   b.binding_root, b.serialized AS binding_serialized
            FROM agent_runs r JOIN agent_admissions a
              ON a.admission_root = r.admission_root
            LEFT JOIN agent_run_authorities b ON b.run_id = r.run_id
            WHERE r.run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        if row["binding_root"] is None or row["binding_serialized"] is None:
            raise ValueError("stored agent run lacks its immutable authority binding")
        expected = _WORKFLOWS.get(row["workflow"])
        if expected is None:
            raise ValueError("stored agent workflow is unsupported")
        request: WorkflowRequest = _decode(row["request_serialized"], expected)
        admission = _decode(row["admission_serialized"], TargetAdmission)
        snapshot = _decode(row["current_snapshot_serialized"], TargetSnapshot)
        authority = _decode(row["binding_serialized"], RunAdmissionBinding)
        if (
            request.root != row["request_root"]
            or admission.root != row["admission_root"]
            or admission.admission_id != row["stored_admission_id"]
            or snapshot.root != row["current_snapshot_root"]
            or authority.root != row["binding_root"]
        ):
            raise ValueError("stored agent binding roots diverge from canonical data")
        binding = AgentRunBinding(
            row["workflow"],
            request,
            admission,
            snapshot,
        )
        if binding.run_id != run_id:
            raise ValueError("stored agent run id diverges from its request")
        if authority != binding.authority:
            raise ValueError("stored run/admission authority association has diverged")
        return binding

    def update_snapshot(
        self,
        run_id: str,
        *,
        prior: TargetSnapshot,
        current: TargetSnapshot,
    ) -> AgentRunBinding:
        self._ensure_open()
        if type(prior) is not TargetSnapshot or type(current) is not TargetSnapshot:
            raise TypeError("agent snapshot updates require exact TargetSnapshot records")
        binding = self.load_run(run_id)
        if binding is None:
            raise ValueError("unknown external run id")
        if prior != binding.current_snapshot:
            raise ValueError("agent current snapshot changed before update")
        if current.target != binding.admission.target_snapshot.target:
            raise ValueError("agent snapshot update names a different target")
        if binding.workflow != "rsi" and current != binding.current_snapshot:
            raise ValueError("non-RSI agent runs cannot mutate their admitted current snapshot")
        changed = self._connection.execute(
            """
            UPDATE agent_runs
            SET current_snapshot_root = ?, current_snapshot_serialized = ?
            WHERE run_id = ? AND current_snapshot_root = ?
            """,
            (current.root, serialize_record(current), run_id, prior.root),
        )
        if changed.rowcount != 1:
            self._connection.rollback()
            raise ValueError("agent current snapshot changed before update")
        self._connection.commit()
        binding = self.load_run(run_id)
        if binding is None:  # pragma: no cover - update invariant
            raise RuntimeError("agent run disappeared after snapshot update")
        return binding

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True
