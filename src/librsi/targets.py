"""Domain-neutral target composition, snapshots, and currentness semantics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias

from .records import (
    Evidence,
    TargetCapabilities,
    TargetComparison,
    TargetComponent,
    TargetRef,
    TargetSnapshot,
)

Target: TypeAlias = TargetRef


def _items(value: Sequence[Any], *, label: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    return tuple(value)


def _component_currentness(
    baseline: TargetSnapshot,
    current: TargetSnapshot,
) -> dict[str, bool]:
    return {
        component.component_id: (baseline.components[index].root == current.components[index].root)
        for index, component in enumerate(baseline.target.components)
    }


@dataclass(frozen=True)
class TargetPolicy:
    """Reference owner for generic target topology and exact currentness checks."""

    @staticmethod
    def capabilities(
        target: TargetRef,
        *,
        supported: Sequence[str] = (),
        locally_available: Sequence[str] = (),
    ) -> TargetCapabilities:
        if not isinstance(target, TargetRef):
            raise TypeError("target capabilities require a TargetRef")
        return TargetCapabilities(
            target=target,
            supported=_items(supported, label="supported target capabilities"),
            locally_available=_items(
                locally_available,
                label="locally available target capabilities",
            ),
        )

    @staticmethod
    def component(
        *,
        component_id: str,
        target: TargetRef,
        capabilities: TargetCapabilities | None = None,
    ) -> TargetComponent:
        return TargetComponent(
            component_id=component_id,
            target=target,
            capabilities=capabilities,
        )

    @staticmethod
    def compose(
        *,
        target_id: str,
        components: Sequence[TargetComponent],
        kind: str = "composite",
        locator: Mapping[str, Any] | None = None,
    ) -> TargetRef:
        component_items = _items(components, label="target components")
        if not component_items:
            raise ValueError("composite targets require at least one component")
        return TargetRef(
            target_id=target_id,
            kind=kind,
            locator={} if locator is None else locator,
            components=component_items,
        )

    @staticmethod
    def snapshot(
        target: TargetRef,
        *,
        state: Mapping[str, Any],
        revision: str | None = None,
        components: Sequence[TargetSnapshot] = (),
    ) -> TargetSnapshot:
        if not isinstance(target, TargetRef):
            raise TypeError("target snapshot requires a TargetRef")
        if not isinstance(state, Mapping):
            raise TypeError("target snapshot state must be a mapping")
        return TargetSnapshot(
            target=target,
            state=state,
            revision=revision,
            components=_items(components, label="target snapshot components"),
        )

    @staticmethod
    def compare(
        baseline: TargetSnapshot,
        current: TargetSnapshot,
    ) -> TargetComparison:
        if not isinstance(baseline, TargetSnapshot) or not isinstance(
            current,
            TargetSnapshot,
        ):
            raise TypeError("target comparison requires TargetSnapshot records")
        if baseline.target != current.target:
            raise ValueError("target comparison snapshots must reference the exact same target")
        return TargetComparison(
            baseline=baseline,
            current=current,
            disposition="current" if baseline.root == current.root else "stale",
            component_currentness=_component_currentness(baseline, current),
        )

    def is_current(
        self,
        baseline: TargetSnapshot,
        current: TargetSnapshot,
    ) -> bool:
        return self.compare(baseline, current).disposition == "current"

    def require_current(
        self,
        baseline: TargetSnapshot,
        current: TargetSnapshot,
    ) -> TargetComparison:
        comparison = self.compare(baseline, current)
        if comparison.disposition != "current":
            raise ValueError("target snapshot is stale")
        return comparison

    def evidence_currentness(
        self,
        evidence: Evidence,
        current: TargetSnapshot,
    ) -> TargetComparison:
        if not isinstance(evidence, Evidence):
            raise TypeError("evidence currentness requires an Evidence record")
        if evidence.target_snapshot is None:
            raise ValueError("evidence currentness requires an exact target snapshot")
        return self.compare(evidence.target_snapshot, current)

    def require_evidence_current(
        self,
        evidence: Evidence,
        current: TargetSnapshot,
    ) -> TargetComparison:
        comparison = self.evidence_currentness(evidence, current)
        if comparison.disposition != "current":
            raise ValueError("evidence target snapshot is stale")
        return comparison
