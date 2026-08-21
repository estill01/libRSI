from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, TypeAlias

FrozenScalar: TypeAlias = None | bool | int | float | str
FrozenValue: TypeAlias = FrozenScalar | tuple["FrozenValue", ...] | "FrozenMap"


class FrozenMap(Mapping[str, FrozenValue]):
    """Small deeply immutable mapping for canonical semantic data.

    Keys are normalized into lexical order and every nested value is frozen. The
    representation is intentionally JSON-shaped so identity generation and durable
    serialization do not depend on process-local object behavior.
    """

    __slots__ = ("_items",)

    def __init__(self, value: Mapping[str, Any] | None = None) -> None:
        source = value or {}
        if any(not isinstance(key, str) for key in source):
            raise TypeError("canonical mappings require string keys")
        self._items = tuple((key, freeze(source[key])) for key in sorted(source))

    def __getitem__(self, key: str) -> FrozenValue:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return hash(self._items)

    def __repr__(self) -> str:
        return f"FrozenMap({thaw(self)!r})"

    def to_dict(self) -> dict[str, Any]:
        return {key: thaw(value) for key, value in self._items}


def freeze(value: Any) -> FrozenValue:
    """Recursively convert supported JSON-shaped values into immutable values."""

    if isinstance(value, FrozenMap):
        return value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical values require finite floats")
        return value
    if isinstance(value, Mapping):
        return FrozenMap(value)
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def thaw(value: FrozenValue) -> Any:
    """Convert an immutable canonical value into ordinary JSON-compatible data."""

    if isinstance(value, FrozenMap):
        return value.to_dict()
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    normalized = thaw(freeze(value))
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_ids(values: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in (values or ()) if str(value)}))
