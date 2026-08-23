"""Minimal replaceable persistence contract for canonical projection documents."""

from __future__ import annotations

import string
from dataclasses import replace
from typing import Protocol, runtime_checkable

from .codec import deserialize_projection, serialize_projection
from .records import EventProjection, OutcomeProjection, Projection

_HEX = frozenset(string.hexdigits.lower())


@runtime_checkable
class ProjectionStore(Protocol):
    """Host-supplied exact-byte storage keyed by projection root."""

    def put(self, projection_root: str, serialized: str) -> None: ...

    def get(self, projection_root: str) -> str | None: ...


class MemoryProjectionStore:
    """Small deterministic in-memory reference implementation."""

    def __init__(self) -> None:
        self._documents: dict[str, str] = {}

    def put(self, projection_root: str, serialized: str) -> None:
        existing = self._documents.get(projection_root)
        if existing is not None and existing != serialized:
            raise ValueError("projection root already has divergent persisted bytes")
        self._documents[projection_root] = serialized

    def get(self, projection_root: str) -> str | None:
        return self._documents.get(projection_root)


def _without_transport_metadata(projection: Projection) -> Projection:
    if type(projection) is OutcomeProjection:
        return replace(projection, metadata={})
    if type(projection) is EventProjection:
        return replace(projection, metadata={})
    raise TypeError("projection persistence requires an exact projection envelope")


def persist_projection(store: ProjectionStore, projection: Projection) -> str:
    """Persist stable metadata-free bytes and verify the host retained them exactly."""

    if not isinstance(store, ProjectionStore):
        raise TypeError("projection persistence requires a ProjectionStore")
    canonical = _without_transport_metadata(projection)
    serialized = serialize_projection(canonical)
    existing = store.get(canonical.projection_root)
    if existing is not None and existing != serialized:
        raise ValueError("persisted projection bytes diverge from the canonical document")
    store.put(canonical.projection_root, serialized)
    if store.get(canonical.projection_root) != serialized:
        raise ValueError("projection store did not retain the exact canonical document")
    return canonical.projection_root


def load_projection(store: ProjectionStore, projection_root: str) -> Projection | None:
    """Load, reconstruct, and key-check one persisted projection."""

    if not isinstance(store, ProjectionStore):
        raise TypeError("projection loading requires a ProjectionStore")
    if (
        not isinstance(projection_root, str)
        or len(projection_root) != 64
        or projection_root != projection_root.lower()
        or any(character not in _HEX for character in projection_root.lower())
    ):
        raise ValueError("projection root must be a SHA-256 hex digest")
    serialized = store.get(projection_root)
    if serialized is None:
        return None
    projection = deserialize_projection(serialized)
    if projection.projection_root != projection_root:
        raise ValueError("persisted projection does not match its lookup root")
    canonical = _without_transport_metadata(projection)
    if serialized != serialize_projection(canonical):
        raise ValueError("persisted projection is not the exact metadata-free canonical document")
    return projection
