from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from librsi import SQLiteRuntimeStore
from tests.test_block7_runtime_sqlite_integrity import _trace


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
