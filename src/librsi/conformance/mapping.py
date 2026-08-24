"""Generic consumer state projection into canonical composite target records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..identity import FrozenMap
from ..records import TargetRef, TargetSnapshot
from ..targets import TargetPolicy


@dataclass(frozen=True, slots=True)
class ComponentState:
    """Transient caller input projected into canonical target records, not a new ledger."""

    component_id: str
    kind: str
    revision: str
    state: Mapping[str, Any]
    locator: Mapping[str, Any] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        for name in ("component_id", "kind", "revision"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"component {name} is required")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.state, Mapping) or not self.state:
            raise ValueError("component state is required")
        if not isinstance(self.locator, Mapping):
            raise TypeError("component locator must be a mapping")
        object.__setattr__(self, "state", FrozenMap(self.state))
        object.__setattr__(self, "locator", FrozenMap(self.locator))


@dataclass(frozen=True, slots=True)
class CompositeSnapshot:
    target: TargetRef
    snapshot: TargetSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.target, TargetRef) or not isinstance(self.snapshot, TargetSnapshot):
            raise TypeError("composite mapping requires canonical target and snapshot records")
        if self.snapshot.target != self.target:
            raise ValueError("composite mapping target and snapshot must match")


def map_composite_snapshot(
    *, target_id: str, components: Sequence[ComponentState], kind: str = "composite"
) -> CompositeSnapshot:
    """Atomically map caller-supplied components without inferring currentness."""

    if isinstance(components, (str, bytes, bytearray)) or not isinstance(components, Sequence):
        raise TypeError("components must be a sequence of ComponentState values")
    supplied = tuple(components)
    if not supplied or any(type(item) is not ComponentState for item in supplied):
        raise ValueError("components must contain exact ComponentState values")
    if len({item.component_id for item in supplied}) != len(supplied):
        raise ValueError("component ids must be unique")
    items = tuple(sorted(supplied, key=lambda item: item.component_id))
    atomic_targets = tuple(
        TargetRef(target_id=item.component_id, kind=item.kind, locator=item.locator)
        for item in items
    )
    target_components = tuple(
        TargetPolicy.component(component_id=item.component_id, target=atomic_targets[index])
        for index, item in enumerate(items)
    )
    target = TargetPolicy.compose(target_id=target_id, kind=kind, components=target_components)
    snapshots = tuple(
        TargetPolicy.snapshot(atomic_targets[index], revision=item.revision, state=item.state)
        for index, item in enumerate(items)
    )
    snapshot = TargetPolicy.snapshot(
        target,
        revision="+".join(item.revision for item in items),
        state={"component_roots": [item.root for item in snapshots]},
        components=snapshots,
    )
    return CompositeSnapshot(target=target, snapshot=snapshot)
