"""Immutable behavioral roots for privately executed qualified modules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import Enum
from types import (
    CellType,
    ClassMethodDescriptorType,
    CodeType,
    FunctionType,
    GetSetDescriptorType,
    MemberDescriptorType,
    MethodDescriptorType,
    ModuleType,
    WrapperDescriptorType,
)
from typing import Any

_IGNORED_MODULE_NAMES = frozenset(
    {"__builtins__", "__cached__", "__loader__", "__spec__", "__warningregistry__"}
)


def _type_ref(value: object) -> list[str]:
    kind = type(value)
    return [kind.__module__, kind.__qualname__]


def _freeze(value: object, seen: set[int]) -> Any:
    if value is None or type(value) in (bool, int, float, str):
        return value
    if type(value) is bytes:
        return ["bytes", value.hex()]
    identity = id(value)
    if identity in seen:
        return ["cycle", *_type_ref(value)]
    seen.add(identity)
    try:
        if type(value) is CodeType:
            return _code(value, seen)
        if type(value) is FunctionType:
            return _function(value, seen)
        if isinstance(value, type):
            return ["type", value.__module__, value.__qualname__]
        if isinstance(value, Enum):
            return [
                "enum",
                type(value).__module__,
                type(value).__qualname__,
                value.name,
                _freeze(value.value, seen),
            ]
        if isinstance(value, (tuple, list)):
            return [type(value).__name__, *(_freeze(item, seen) for item in value)]
        if isinstance(value, (set, frozenset)):
            rows = [_freeze(item, seen) for item in value]
            return [type(value).__name__, *sorted(rows, key=_canonical)]
        if isinstance(value, Mapping):
            rows = [(_freeze(key, seen), _freeze(item, seen)) for key, item in value.items()]
            return ["mapping", *sorted(rows, key=lambda row: _canonical(row[0]))]
        if type(value) is ModuleType:
            return ["module", value.__name__]
        if type(value) in (
            ClassMethodDescriptorType,
            GetSetDescriptorType,
            MemberDescriptorType,
            MethodDescriptorType,
            WrapperDescriptorType,
        ):
            return ["descriptor", *_type_ref(value), repr(value)]
        return ["value", *_type_ref(value), repr(value)]
    finally:
        seen.remove(identity)


def _function(function: FunctionType, seen: set[int]) -> list[object]:
    closure: tuple[object, ...] = ()
    if function.__closure__ is not None:
        closure = tuple(
            "<empty>" if _empty(cell) else _freeze(cell.cell_contents, seen)
            for cell in function.__closure__
        )
    return [
        "function",
        function.__module__,
        function.__qualname__,
        hashlib.sha256(_canonical(_code(function.__code__, seen)).encode()).hexdigest(),
        _freeze(function.__defaults__, seen),
        _freeze(function.__kwdefaults__, seen),
        _freeze(function.__annotations__, seen),
        _freeze(function.__dict__, seen),
        closure,
    ]


def _code(code: CodeType, seen: set[int]) -> list[object]:
    return [
        "code",
        code.co_name,
        code.co_qualname,
        code.co_filename,
        code.co_firstlineno,
        code.co_argcount,
        code.co_posonlyargcount,
        code.co_kwonlyargcount,
        code.co_nlocals,
        code.co_stacksize,
        code.co_flags,
        code.co_code.hex(),
        code.co_linetable.hex(),
        code.co_exceptiontable.hex(),
        _freeze(code.co_consts, seen),
        _freeze(code.co_names, seen),
        _freeze(code.co_varnames, seen),
        _freeze(code.co_freevars, seen),
        _freeze(code.co_cellvars, seen),
    ]


def _empty(cell: CellType) -> bool:
    try:
        _ = cell.cell_contents
    except ValueError:
        return True
    return False


def _class(value: type[object], seen: set[int]) -> list[object]:
    attributes: list[tuple[str, object]] = []
    for name, item in vars(value).items():
        if isinstance(item, (classmethod, staticmethod)):
            frozen = _callable(item.__func__, seen)
        elif isinstance(item, property):
            frozen = [
                "property",
                None if item.fget is None else _callable(item.fget, seen),
                None if item.fset is None else _callable(item.fset, seen),
                None if item.fdel is None else _callable(item.fdel, seen),
            ]
        elif type(item) is FunctionType:
            frozen = _function(item, seen)
        else:
            frozen = _freeze(item, seen)
        attributes.append((name, frozen))
    return [
        "class",
        value.__module__,
        value.__qualname__,
        [(base.__module__, base.__qualname__) for base in value.__bases__],
        sorted(attributes),
    ]


def _callable(value: object, seen: set[int]) -> Any:
    if type(value) is FunctionType:
        return _function(value, seen)
    return _freeze(value, seen)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def module_behavior_root(module: ModuleType) -> str:
    """Hash executable and field behavior without retaining mutable object references."""

    if type(module) is not ModuleType:
        raise TypeError("behavioral roots require an exact module")
    rows: list[tuple[str, object]] = []
    for name, value in vars(module).items():
        if name in _IGNORED_MODULE_NAMES:
            continue
        if type(value) is FunctionType and value.__module__ == module.__name__:
            frozen = _function(value, set())
        elif isinstance(value, type) and value.__module__ == module.__name__:
            frozen = _class(value, set())
        else:
            frozen = _freeze(value, set())
        rows.append((name, frozen))
    return hashlib.sha256((_canonical(sorted(rows)) + "\n").encode()).hexdigest()
