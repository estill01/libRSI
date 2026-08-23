from __future__ import annotations

import pytest

from librsi import (
    Claim,
    MemoryProjectionStore,
    Run,
    RuntimeEngine,
    load_projection,
    persist_projection,
    project_event,
    project_result,
    serialize_projection,
)
from tests.block19_support import workflow_results


def test_persistence_strips_transport_metadata_and_reconstructs_exact_result() -> None:
    projection = project_result(
        workflow_results()[1],
        metadata={"transport": "http", "session": "not-semantic"},
    )
    store = MemoryProjectionStore()

    root = persist_projection(store, projection)
    loaded = load_projection(store, root)

    assert loaded is not None
    assert loaded.projection_root == projection.projection_root
    assert loaded.metadata == {}
    assert loaded.result == projection.result  # type: ignore[union-attr]
    assert persist_projection(store, projection) == root


def test_persistence_rejects_divergent_bytes_or_failed_retention() -> None:
    projection = project_result(workflow_results()[0])

    class _DivergentStore:
        def __init__(self) -> None:
            self.value: str | None = "{}"

        def put(self, projection_root: str, serialized: str) -> None:
            self.value = serialized

        def get(self, projection_root: str) -> str | None:
            return self.value

    with pytest.raises(ValueError, match="diverge"):
        persist_projection(_DivergentStore(), projection)

    class _LossyStore:
        def put(self, projection_root: str, serialized: str) -> None:
            self.value = serialized + " "

        def get(self, projection_root: str) -> str | None:
            return getattr(self, "value", None)

    with pytest.raises(ValueError, match="did not retain"):
        persist_projection(_LossyStore(), projection)


def test_load_rejects_wrong_lookup_roots_and_corrupted_documents() -> None:
    projection = project_result(workflow_results()[3])

    class _WrongKeyStore:
        def put(self, projection_root: str, serialized: str) -> None:
            pass

        def get(self, projection_root: str) -> str | None:
            return serialize_projection(projection)

    with pytest.raises(ValueError, match="lookup root"):
        load_projection(_WrongKeyStore(), "0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        load_projection(_WrongKeyStore(), "z" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        load_projection(_WrongKeyStore(), projection.projection_root.upper())


def test_projection_store_contract_is_required_and_missing_values_are_neutral() -> None:
    projection = project_result(workflow_results()[0])
    with pytest.raises(TypeError, match="ProjectionStore"):
        persist_projection(object(), projection)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ProjectionStore"):
        load_projection(object(), projection.projection_root)  # type: ignore[arg-type]
    assert load_projection(MemoryProjectionStore(), projection.projection_root) is None


def test_memory_store_is_immutable_and_event_projections_use_the_same_contract() -> None:
    store = MemoryProjectionStore()
    store.put("a" * 64, "first")
    with pytest.raises(ValueError, match="divergent persisted bytes"):
        store.put("a" * 64, "second")

    claim = Claim(statement="events persist as projections")
    started = RuntimeEngine.start(Run(run_id="persisted-event", intent=claim.ref))
    assert started.transition is not None
    event = project_event(started.transition.event, metadata={"transport": "stream"})
    root = persist_projection(store, event)
    loaded = load_projection(store, root)
    assert loaded is not None
    assert loaded == event
    assert loaded.metadata == {}

    with pytest.raises(TypeError, match="exact projection envelope"):
        persist_projection(store, claim)  # type: ignore[arg-type]
