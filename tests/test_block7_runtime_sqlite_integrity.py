from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from librsi import (
    Action,
    ActionResult,
    Goal,
    KnowledgeWrite,
    Outcome,
    Run,
    RuntimeEngine,
    SQLiteKnowledgeStore,
    SQLiteRuntimeStore,
    Transition,
    persist_transitions,
    serialize_record,
)


def _trace(run_id: str = "integrity") -> tuple[Transition, ...]:
    run = Run(run_id=run_id, intent=Goal(statement="Protect runtime integrity").ref)
    started = RuntimeEngine.start(run)
    requested = RuntimeEngine.request(
        started.state,
        Action(run=run.ref, action_id="inspect", kind="inspect"),
    )
    submitted = RuntimeEngine.submit(
        requested.state,
        ActionResult(action=requested.state.pending_actions[0], disposition="succeeded"),
    )
    completed = RuntimeEngine.complete(
        submitted.state,
        Outcome(intent=run.intent, status="validated"),
    )
    result = tuple(update.transition for update in (started, requested, submitted, completed))
    assert all(isinstance(item, Transition) for item in result)
    return result  # type: ignore[return-value]


def _persist(database: Path, trace: tuple[Transition, ...] | None = None) -> tuple[Transition, ...]:
    trace = _trace() if trace is None else trace
    with SQLiteRuntimeStore(database) as store:
        persist_transitions(store, trace)
    return trace


def test_runtime_and_knowledge_schemas_coexist_without_authority_overlap(
    tmp_path: Path,
) -> None:
    database = tmp_path / "coexist.sqlite"
    knowledge_record = Goal(statement="Reusable semantic knowledge")
    trace = _trace()

    with (
        SQLiteKnowledgeStore(database) as knowledge,
        SQLiteRuntimeStore(database) as runtime,
    ):
        knowledge.put(knowledge_record, source_run_id=trace[0].next_state.run.run_id)
        persist_transitions(runtime, trace)
        assert knowledge.schema_version == 1
        assert runtime.schema_version == 1
        assert runtime.resume(trace[0].next_state.run.run_id) == trace[-1].next_state
        with pytest.raises(ValueError, match="not knowledge state"):
            KnowledgeWrite(trace[0].event)

    with (
        SQLiteKnowledgeStore(database) as knowledge,
        SQLiteRuntimeStore(database) as runtime,
    ):
        assert knowledge.get(knowledge_record.root) == knowledge_record
        assert runtime.resume(trace[0].next_state.run.run_id) == trace[-1].next_state


def test_runtime_schema_migration_is_transactional_exact_and_independent(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "malformed.sqlite"
    with closing(sqlite3.connect(malformed)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE runtime_schema (
                component TEXT PRIMARY KEY
                    CHECK (component IN ('runtime', 'runtime ')),
                version INTEGER NOT NULL CHECK (version > 0)
            );
            INSERT INTO runtime_schema(component, version) VALUES ('runtime', 1);
            """
        )
    with pytest.raises(ValueError, match="schema is incomplete"):
        SQLiteRuntimeStore(malformed)
    with closing(sqlite3.connect(malformed)) as connection, connection:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert names == {"runtime_schema"}

    future = tmp_path / "future.sqlite"
    with SQLiteRuntimeStore(future):
        pass
    with closing(sqlite3.connect(future)) as connection, connection:
        connection.execute("UPDATE runtime_schema SET version = 999")
    with pytest.raises(ValueError, match="newer"):
        SQLiteRuntimeStore(future)

    claimed_but_incomplete = tmp_path / "claimed-incomplete.sqlite"
    with SQLiteRuntimeStore(claimed_but_incomplete):
        pass
    with closing(sqlite3.connect(claimed_but_incomplete)) as connection, connection:
        connection.execute("DROP TABLE runtime_current")
    with pytest.raises(ValueError, match="schema is incomplete"):
        SQLiteRuntimeStore(claimed_but_incomplete)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE runtime_events SET sequence = 99 WHERE sequence = 1",
        "UPDATE runtime_transitions SET prior_state_root = NULL WHERE sequence = 1",
        "UPDATE runtime_current SET sequence = 0",
        "UPDATE runtime_runs SET run_root = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'",
    ],
)
def test_resume_rejects_gaps_and_corrupted_materialized_projections(
    tmp_path: Path,
    statement: str,
) -> None:
    database = tmp_path / f"tamper-{abs(hash(statement))}.sqlite"
    trace = _persist(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(statement)
    with SQLiteRuntimeStore(database) as store, pytest.raises(ValueError):
        store.resume(trace[0].next_state.run.run_id)


def test_resume_rejects_wrong_serialized_type_and_broken_foreign_keys(
    tmp_path: Path,
) -> None:
    wrong_type = tmp_path / "wrong-type.sqlite"
    trace = _persist(wrong_type)
    with closing(sqlite3.connect(wrong_type)) as connection, connection:
        connection.execute(
            "UPDATE runtime_events SET serialized = ? WHERE sequence = 1",
            (serialize_record(trace[0].next_state.run),),
        )
    with SQLiteRuntimeStore(wrong_type) as store, pytest.raises(ValueError, match="type/root"):
        store.resume(trace[0].next_state.run.run_id)

    broken_fk = tmp_path / "broken-fk.sqlite"
    _persist(broken_fk)
    with closing(sqlite3.connect(broken_fk)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM runtime_states WHERE sequence = 2")
    with pytest.raises(ValueError, match="referential integrity"):
        SQLiteRuntimeStore(broken_fk)


def test_append_rolls_back_all_partial_rows_on_storage_failure(tmp_path: Path) -> None:
    database = tmp_path / "rollback.sqlite"
    trace = _trace()
    with SQLiteRuntimeStore(database) as store:
        store.append(trace[0])
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            """
            CREATE TRIGGER reject_runtime_transition
            BEFORE INSERT ON runtime_transitions
            WHEN NEW.sequence = 1
            BEGIN
                SELECT RAISE(ABORT, 'injected failure');
            END
            """
        )

    with SQLiteRuntimeStore(database) as store:
        with pytest.raises(ValueError, match="append failed"):
            store.append(trace[1])
        assert store.resume(trace[0].next_state.run.run_id) == trace[0].next_state
        assert len(store.events(trace[0].next_state.run.run_id)) == 1
        assert len(store.transitions(trace[0].next_state.run.run_id)) == 1


def test_schema_and_append_interfaces_fail_closed_on_invalid_inputs(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="path"):
        SQLiteRuntimeStore(7)  # type: ignore[arg-type]
    with SQLiteRuntimeStore(tmp_path / "inputs.sqlite") as store:
        with pytest.raises(TypeError, match="Transition"):
            store.append("run completed")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="text"):
            store.resume(7)  # type: ignore[arg-type]


def test_divergent_bytes_for_the_same_semantic_root_are_rejected(tmp_path: Path) -> None:
    database = tmp_path / "bytes.sqlite"
    trace = _persist(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE runtime_transitions SET serialized = ? WHERE sequence = 1",
            (serialize_record(trace[1].event),),
        )
    with SQLiteRuntimeStore(database) as store, pytest.raises(ValueError, match="type/root"):
        store.append(trace[1])
