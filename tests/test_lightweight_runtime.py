from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from librsi import Run, RuntimeEngine, SQLiteRuntimeStore
from tests.test_block7_runtime_sqlite_integrity import _trace


def test_store_read_reuses_embedded_run_across_history_rows(tmp_path, monkeypatch):
    trace = _trace()
    with SQLiteRuntimeStore(tmp_path / "shared.sqlite") as store:
        for transition in trace:
            store.append(transition)
        calls = []
        original = Run.__post_init__

        def counted(self):
            calls.append(self.run_id)
            original(self)

        monkeypatch.setattr(Run, "__post_init__", counted)
        run_id = trace[0].next_state.run.run_id
        assert store.resume(run_id) == trace[-1].next_state
        assert calls == [run_id]
        assert store.resume(run_id) == trace[-1].next_state
        assert calls == [run_id, run_id]


def test_append_replays_each_event_once_but_next_read_revalidates(tmp_path, monkeypatch):
    trace = _trace()
    with SQLiteRuntimeStore(tmp_path / "replay.sqlite") as store:
        store.append(trace[0])
        calls = []
        original = RuntimeEngine._replay_event

        def counted(cls, run, state, event):
            calls.append(event.sequence)
            return original(run, state, event)

        monkeypatch.setattr(RuntimeEngine, "_replay_event", classmethod(counted))
        assert store.append(trace[1]) == trace[1].next_state
        assert calls == [0, 1]
        calls.clear()
        assert store.resume(trace[0].next_state.run.run_id) == trace[1].next_state
        assert calls == [0, 1]


def test_append_detects_trigger_corruption_of_already_decoded_prefix(tmp_path) -> None:
    database = tmp_path / "trigger.sqlite"
    trace = _trace()
    with SQLiteRuntimeStore(database) as store:
        store.append(trace[0])
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                """
                CREATE TRIGGER corrupt_prefix AFTER INSERT ON runtime_transitions
                WHEN NEW.sequence = 1 BEGIN
                    UPDATE runtime_events SET serialized = '{}' WHERE sequence = 0;
                END
                """
            )
        with pytest.raises((ValueError, TypeError)):
            store.append(trace[1])
        assert store.resume(trace[0].next_state.run.run_id) == trace[0].next_state


def test_later_operations_do_not_reuse_an_earlier_verified_prefix(tmp_path) -> None:
    database = tmp_path / "between.sqlite"
    trace = _trace()
    with SQLiteRuntimeStore(database) as store:
        store.append(trace[0])
        store.append(trace[1])
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("UPDATE runtime_states SET sequence = 99 WHERE sequence = 0")
        with pytest.raises(ValueError):
            store.append(trace[2])
        with pytest.raises(ValueError):
            store.resume(trace[0].next_state.run.run_id)
