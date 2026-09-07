"""Transactional SQLite reference backend for replayable semantic runtimes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from ..errors import RSITransitionError
from ..records import SemanticRecord, _DecodeCache, _RecordEncoder
from .engine import RuntimeEngine
from .records import Event, Run, RunState, Transition
from .sqlite_schema import (
    RUNTIME_SCHEMA_COMPONENT,
    RUNTIME_SCHEMA_VERSION,
    migrate_runtime_schema,
    validate_runtime_schema,
)

_RecordT = TypeVar("_RecordT", bound=SemanticRecord)


@dataclass(frozen=True)
class _RuntimeHistory:
    run: Run
    events: tuple[Event, ...]
    states: tuple[RunState, ...]
    transitions: tuple[Transition, ...]

    @property
    def state(self) -> RunState:
        return self.states[-1]


def _require_run_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("runtime run id must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError("runtime run id is required")
    return normalized


class _RecordCodec:
    """Reuse immutable record work only within one store operation.

    Decoding is keyed by exact bytes, never a claimed root. Encoding retains its
    object alongside the identity key so garbage collection cannot recycle it.
    Row/chain/schema validation still runs on every read. Within an append,
    replay reuses only prefixes whose complete run/event bytes are unchanged.
    No cache survives the store operation.
    """

    def __init__(self) -> None:
        self._decoded: dict[str, SemanticRecord] = {}
        self._record_cache = _DecodeCache()
        self._record_encoder = _RecordEncoder()
        self._encoded: dict[int, tuple[SemanticRecord, str]] = {}
        self._replay_run: str | None = None
        self._replay_events: tuple[str, ...] = ()
        self._replay_trace: tuple[Transition, ...] = ()

    def decode(
        self,
        serialized: str,
        expected_class: type[_RecordT],
        *,
        expected_root: str,
    ) -> _RecordT:
        record = self._decoded.get(serialized)
        if record is None:
            record = self._record_cache.deserialize(serialized)
            self._decoded[serialized] = record
        if not isinstance(record, expected_class) or record.root != expected_root:
            raise ValueError("stored runtime type/root does not match canonical bytes")
        return record

    def serialize(self, record: SemanticRecord) -> str:
        cached = self._encoded.get(id(record))
        if cached is None:
            cached = (record, self._record_encoder.serialize(record))
            self._encoded[id(record)] = cached
        return cached[1]

    def replay(self, run: Run, events: tuple[Event, ...]) -> tuple[Transition, ...]:
        run_bytes = self.serialize(run)
        event_bytes = tuple(self.serialize(event) for event in events)
        prefix_size = len(self._replay_events)
        if (
            self._replay_run == run_bytes
            and len(event_bytes) >= prefix_size
            and event_bytes[:prefix_size] == self._replay_events
        ):
            trace = list(self._replay_trace)
            state = None if not trace else trace[-1].next_state
            for event in events[prefix_size:]:
                transition = RuntimeEngine._replay_event(run, state, event)
                trace.append(transition)
                state = transition.next_state
            replayed = tuple(trace)
        else:
            replayed = RuntimeEngine.replay_trace(run, events)
        self._replay_run = run_bytes
        self._replay_events = event_bytes
        self._replay_trace = replayed
        return replayed


class SQLiteRuntimeStore:
    """Zero-service append-only runtime storage with replay-checked materialization."""

    SCHEMA_VERSION = RUNTIME_SCHEMA_VERSION

    def __init__(self, path: str | Path = ":memory:") -> None:
        if not isinstance(path, (str, Path)):
            raise TypeError("SQLite runtime path must be text or a Path")
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            migrate_runtime_schema(self._connection)
        except Exception:
            self._connection.close()
            self._closed = True
            raise

    @property
    def schema_version(self) -> int:
        self._ensure_open()
        row = self._connection.execute(
            "SELECT version FROM runtime_schema WHERE component = ?",
            (RUNTIME_SCHEMA_COMPONENT,),
        ).fetchone()
        if row is None:
            raise ValueError("SQLite runtime schema metadata is missing")
        return int(row[0])

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQLite runtime store is closed")

    def _run_locked(self, run_id: str, codec: _RecordCodec) -> Run | None:
        row = self._connection.execute(
            "SELECT run_id, run_root, serialized FROM runtime_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        run = codec.decode(row["serialized"], Run, expected_root=row["run_root"])
        if run.run_id != row["run_id"] or run.run_id != run_id:
            raise ValueError("stored runtime run identity diverges from canonical bytes")
        return run

    def _events_locked(self, run: Run, codec: _RecordCodec) -> tuple[Event, ...]:
        rows = self._connection.execute(
            """
            SELECT run_id, sequence, event_root, serialized
            FROM runtime_events WHERE run_id = ? ORDER BY sequence
            """,
            (run.run_id,),
        ).fetchall()
        events: list[Event] = []
        for expected_sequence, row in enumerate(rows):
            event = codec.decode(row["serialized"], Event, expected_root=row["event_root"])
            if (
                row["run_id"] != run.run_id
                or row["sequence"] != expected_sequence
                or event.sequence != expected_sequence
                or event.run != run.ref
            ):
                raise ValueError("stored runtime event history has a gap or identity drift")
            events.append(event)
        return tuple(events)

    def _states_locked(self, run: Run, codec: _RecordCodec) -> tuple[RunState, ...]:
        rows = self._connection.execute(
            """
            SELECT state_root, run_id, sequence, serialized
            FROM runtime_states WHERE run_id = ? ORDER BY sequence
            """,
            (run.run_id,),
        ).fetchall()
        states: list[RunState] = []
        for expected_sequence, row in enumerate(rows):
            state = codec.decode(row["serialized"], RunState, expected_root=row["state_root"])
            if (
                row["run_id"] != run.run_id
                or row["sequence"] != expected_sequence
                or state.sequence != expected_sequence
                or codec.serialize(state.run) != codec.serialize(run)
            ):
                raise ValueError("stored runtime state history has a gap or identity drift")
            states.append(state)
        return tuple(states)

    def _transitions_locked(self, run: Run, codec: _RecordCodec) -> tuple[Transition, ...]:
        rows = self._connection.execute(
            """
            SELECT transition_root, run_id, sequence, event_root,
                   prior_state_root, next_state_root, serialized
            FROM runtime_transitions WHERE run_id = ? ORDER BY sequence
            """,
            (run.run_id,),
        ).fetchall()
        transitions: list[Transition] = []
        for expected_sequence, row in enumerate(rows):
            transition = codec.decode(
                row["serialized"],
                Transition,
                expected_root=row["transition_root"],
            )
            prior_root = None if transition.prior_state is None else transition.prior_state.root
            if (
                row["run_id"] != run.run_id
                or row["sequence"] != expected_sequence
                or transition.event.sequence != expected_sequence
                or transition.event.run != run.ref
                or row["event_root"] != transition.event.root
                or row["prior_state_root"] != prior_root
                or row["next_state_root"] != transition.next_state.root
            ):
                raise ValueError("stored runtime transition projection diverges from its bytes")
            transitions.append(transition)
        return tuple(transitions)

    def _history_locked(
        self, run_id: str, codec: _RecordCodec | None = None
    ) -> _RuntimeHistory | None:
        codec = _RecordCodec() if codec is None else codec
        run = self._run_locked(run_id, codec)
        if run is None:
            return None
        events = self._events_locked(run, codec)
        states = self._states_locked(run, codec)
        transitions = self._transitions_locked(run, codec)
        if not events or len(events) != len(states) or len(events) != len(transitions):
            raise ValueError("stored runtime history is incomplete")

        for sequence, (event, state, transition) in enumerate(
            zip(events, states, transitions, strict=True)
        ):
            expected_prior = None if sequence == 0 else states[sequence - 1].ref
            expected_previous = None if sequence == 0 else events[sequence - 1].ref
            if (
                transition.prior_state != expected_prior
                or event.previous_event != expected_previous
                or codec.serialize(transition.event) != codec.serialize(event)
                or codec.serialize(transition.next_state) != codec.serialize(state)
            ):
                raise ValueError("stored runtime transition chain is not exact")

        current = self._connection.execute(
            """
            SELECT run_id, state_root, sequence, transition_root
            FROM runtime_current WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if current is None or (
            current["run_id"] != run_id
            or current["state_root"] != states[-1].root
            or current["sequence"] != states[-1].sequence
            or current["transition_root"] != transitions[-1].root
        ):
            raise ValueError("stored runtime current-state projection is incomplete")

        replayed = codec.replay(run, events)
        if len(replayed) != len(transitions) or any(
            codec.serialize(actual) != codec.serialize(stored)
            for actual, stored in zip(replayed, transitions, strict=True)
        ):
            raise ValueError("stored runtime history diverges from deterministic replay")
        return _RuntimeHistory(run, events, states, transitions)

    def append(self, transition: Transition) -> RunState:
        self._ensure_open()
        if not isinstance(transition, Transition):
            raise TypeError("runtime append requires a Transition")
        run = transition.next_state.run
        run_id = run.run_id
        codec = _RecordCodec()
        transition_bytes = codec.serialize(transition)
        event_bytes = codec.serialize(transition.event)
        state_bytes = codec.serialize(transition.next_state)
        run_bytes = codec.serialize(run)

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            validate_runtime_schema(self._connection)
            history = self._history_locked(run_id, codec)
            conflicts = self._connection.execute(
                """
                SELECT transition_root, run_id, sequence, serialized
                FROM runtime_transitions
                WHERE transition_root = ? OR (run_id = ? AND sequence = ?)
                """,
                (transition.root, run_id, transition.event.sequence),
            ).fetchall()
            if conflicts:
                if (
                    len(conflicts) == 1
                    and conflicts[0]["transition_root"] == transition.root
                    and conflicts[0]["run_id"] == run_id
                    and conflicts[0]["sequence"] == transition.event.sequence
                    and conflicts[0]["serialized"] == transition_bytes
                    and history is not None
                ):
                    self._connection.commit()
                    return history.state
                raise ValueError("duplicate runtime transition has divergent bytes or position")

            candidate_events: tuple[Event, ...]
            if history is None:
                if transition.event.sequence != 0 or transition.prior_state is not None:
                    raise RSITransitionError("new runtime history must begin at transition zero")
                self._connection.execute(
                    "INSERT INTO runtime_runs(run_id, run_root, serialized) VALUES (?, ?, ?)",
                    (run_id, run.root, run_bytes),
                )
                candidate_events = (transition.event,)
            else:
                if codec.serialize(history.run) != run_bytes:
                    raise ValueError("runtime transition run diverges from stored run bytes")
                if transition.event.sequence != history.state.sequence + 1:
                    raise RSITransitionError("runtime transition sequence is not append-only")
                if transition.prior_state != history.state.ref:
                    raise RSITransitionError("runtime transition does not cite current state")
                if transition.event.previous_event != history.events[-1].ref:
                    raise RSITransitionError("runtime event does not cite current event")
                candidate_events = (*history.events, transition.event)

            expected = codec.replay(run, candidate_events)[-1]
            if codec.serialize(expected) != transition_bytes:
                raise RSITransitionError(
                    "runtime transition is not the deterministic result of its event history"
                )

            self._connection.execute(
                """
                INSERT INTO runtime_events(run_id, sequence, event_root, serialized)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, transition.event.sequence, transition.event.root, event_bytes),
            )
            self._connection.execute(
                """
                INSERT INTO runtime_states(state_root, run_id, sequence, serialized)
                VALUES (?, ?, ?, ?)
                """,
                (transition.next_state.root, run_id, transition.event.sequence, state_bytes),
            )
            self._connection.execute(
                """
                INSERT INTO runtime_transitions(
                    transition_root, run_id, sequence, event_root,
                    prior_state_root, next_state_root, serialized
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.root,
                    run_id,
                    transition.event.sequence,
                    transition.event.root,
                    None if transition.prior_state is None else transition.prior_state.root,
                    transition.next_state.root,
                    transition_bytes,
                ),
            )
            if history is None:
                self._connection.execute(
                    """
                    INSERT INTO runtime_current(run_id, state_root, sequence, transition_root)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        transition.next_state.root,
                        transition.event.sequence,
                        transition.root,
                    ),
                )
            else:
                updated = self._connection.execute(
                    """
                    UPDATE runtime_current
                    SET state_root = ?, sequence = ?, transition_root = ?
                    WHERE run_id = ? AND state_root = ? AND sequence = ?
                    """,
                    (
                        transition.next_state.root,
                        transition.event.sequence,
                        transition.root,
                        run_id,
                        history.state.root,
                        history.state.sequence,
                    ),
                )
                if updated.rowcount != 1:
                    raise ValueError("runtime current state changed during append")

            stored = self._history_locked(run_id, codec)
            if stored is None:  # pragma: no cover - transaction insertion invariant
                raise RuntimeError("runtime history disappeared during append")
            self._connection.commit()
            return stored.state
        except Exception as error:
            self._connection.rollback()
            if isinstance(error, (TypeError, ValueError, RSITransitionError)):
                raise
            raise ValueError("SQLite runtime transition append failed") from error

    def _read_history(self, run_id: str) -> _RuntimeHistory | None:
        self._ensure_open()
        run_id = _require_run_id(run_id)
        self._connection.execute("BEGIN")
        try:
            validate_runtime_schema(self._connection)
            history = self._history_locked(run_id)
            self._connection.commit()
            return history
        except Exception:
            self._connection.rollback()
            raise

    def load(self, run_id: str) -> RunState | None:
        """Load current state only after validating and replaying its entire history."""

        history = self._read_history(run_id)
        return None if history is None else history.state

    def events(self, run_id: str) -> tuple[Event, ...]:
        history = self._read_history(run_id)
        return () if history is None else history.events

    def transitions(self, run_id: str) -> tuple[Transition, ...]:
        history = self._read_history(run_id)
        return () if history is None else history.transitions

    def resume(self, run_id: str) -> RunState | None:
        """Replay and return the exact durable continuation point for a run."""

        return self.load(run_id)

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> SQLiteRuntimeStore:
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
