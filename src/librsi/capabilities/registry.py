"""Deterministic capability resolution without lifecycle authority."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from types import MappingProxyType
from typing import cast

from ..errors import RSICapabilityError
from ..runtime import Action, ActionResult, RunState
from .records import (
    CAPABILITY_FAMILIES,
    CapabilityResolution,
    CapabilityRoute,
    DispatchPlan,
)

CAPABILITY_METHODS = MappingProxyType(
    {
        "inspector": "inspect",
        "retriever": "retrieve",
        "reasoner": "reason",
        "experimenter": "experiment",
        "implementer": "implement",
        "reviewer": "review",
        "applier": "apply",
        "verifier": "verify",
    }
)


class CapabilityRegistry:
    """Exact action routes and at most one implementation per capability family."""

    def __init__(
        self,
        *,
        routes: Sequence[CapabilityRoute] = (),
        implementations: Sequence[object] = (),
    ) -> None:
        if isinstance(routes, (str, bytes, bytearray)) or not isinstance(routes, Sequence):
            raise TypeError("capability routes must be a sequence")
        route_items = tuple(routes)
        if any(not isinstance(item, CapabilityRoute) for item in route_items):
            raise TypeError("capability routes must contain CapabilityRoute values")
        if len({item.action_kind for item in route_items}) != len(route_items):
            raise ValueError("capability action routes must be unique")
        self._routes = {item.action_kind: item for item in route_items}

        if isinstance(implementations, (str, bytes, bytearray)) or not isinstance(
            implementations, Sequence
        ):
            raise TypeError("capability implementations must be a sequence")
        unique: list[object] = []
        for implementation in implementations:
            if not any(implementation is existing for existing in unique):
                unique.append(implementation)
        providers: dict[str, object] = {}
        for family, method_name in CAPABILITY_METHODS.items():
            matches = [
                implementation
                for implementation in unique
                if callable(getattr(implementation, method_name, None))
            ]
            if len(matches) > 1:
                raise ValueError(f"capability family {family!r} has ambiguous implementations")
            if matches:
                providers[family] = matches[0]
        self._providers = providers

    @property
    def routes(self) -> tuple[CapabilityRoute, ...]:
        return tuple(self._routes.values())

    def resolve(self, action: Action) -> CapabilityResolution:
        if not isinstance(action, Action):
            raise TypeError("capability resolution requires an Action")
        route = self._routes.get(action.kind)
        if route is None:
            return CapabilityResolution(
                action=action,
                route=None,
                posture="unavailable",
                reason="no capability route is configured",
            )
        if route.posture == "automatic" and route.family not in self._providers:
            return CapabilityResolution(
                action=action,
                route=route,
                posture="unavailable",
                reason="automatic capability implementation is unavailable",
            )
        return CapabilityResolution(
            action=action,
            route=route,
            posture=route.posture,
            reason=(
                "capability is configured unavailable" if route.posture == "unavailable" else None
            ),
        )

    def plan(self, state: RunState) -> DispatchPlan:
        if not isinstance(state, RunState):
            raise TypeError("capability planning requires a RunState")
        return DispatchPlan(
            state=state,
            resolutions=tuple(self.resolve(action) for action in state.pending_actions),
        )

    def execute(self, resolution: CapabilityResolution) -> ActionResult:
        if not isinstance(resolution, CapabilityResolution):
            raise TypeError("capability execution requires a CapabilityResolution")
        if resolution.posture != "automatic" or resolution.family is None:
            raise RSICapabilityError("only resolved automatic capabilities may execute")
        if resolution.family not in CAPABILITY_FAMILIES:
            raise RSICapabilityError("resolved capability family is unsupported")
        provider = self._providers.get(resolution.family)
        if provider is None:  # pragma: no cover - resolution invariant
            raise RSICapabilityError("automatic capability implementation disappeared")
        method_name = CAPABILITY_METHODS[resolution.family]
        method = cast(Callable[[Action], object], getattr(provider, method_name))
        try:
            result = method(resolution.action)
        except Exception as error:
            raise RSICapabilityError("automatic capability raised an exception") from error
        if not isinstance(result, ActionResult):
            raise RSICapabilityError("capability returned a mismatched result schema")
        if result.action.ref != resolution.action.ref or result.action != resolution.action:
            raise RSICapabilityError("capability result does not cite the exact dispatched action")
        return result
