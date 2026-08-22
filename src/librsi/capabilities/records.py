"""Explicit capability routing and control-plane-neutral dispatch views."""

from __future__ import annotations

from dataclasses import dataclass

from ..records import serialize_record
from ..runtime import Action, ActionResult, RunState, Transition

CAPABILITY_FAMILIES = frozenset(
    {
        "inspector",
        "retriever",
        "reasoner",
        "experimenter",
        "implementer",
        "reviewer",
        "applier",
        "verifier",
    }
)
CAPABILITY_POSTURES = frozenset({"automatic", "external", "human-reserved", "unavailable"})


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


@dataclass(frozen=True)
class CapabilityRoute:
    """Configured authority posture for one exact Action kind."""

    action_kind: str
    family: str
    posture: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_kind", _require_text(self.action_kind, "action kind"))
        family = _require_text(self.family, "capability family")
        if family not in CAPABILITY_FAMILIES:
            raise ValueError(f"unsupported capability family: {family}")
        object.__setattr__(self, "family", family)
        posture = _require_text(self.posture, "capability posture")
        if posture not in CAPABILITY_POSTURES:
            raise ValueError(f"unsupported capability posture: {posture}")
        object.__setattr__(self, "posture", posture)


@dataclass(frozen=True)
class CapabilityResolution:
    """Effective disposition of one pending action under current configuration."""

    action: Action
    route: CapabilityRoute | None
    posture: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, Action):
            raise TypeError("capability resolution requires an Action")
        if self.route is not None:
            if not isinstance(self.route, CapabilityRoute):
                raise TypeError("capability resolution route must be a CapabilityRoute")
            if self.route.action_kind != self.action.kind:
                raise ValueError("capability route does not match the exact action kind")
        posture = _require_text(self.posture, "resolved capability posture")
        if posture not in CAPABILITY_POSTURES:
            raise ValueError(f"unsupported resolved capability posture: {posture}")
        if posture != "unavailable" and (self.route is None or posture != self.route.posture):
            raise ValueError("resolved capability posture diverges from its route")
        object.__setattr__(self, "posture", posture)
        if self.reason is not None:
            object.__setattr__(self, "reason", _require_text(self.reason, "resolution reason"))
        if posture == "unavailable" and self.reason is None:
            raise ValueError("unavailable capability resolutions require a reason")

    @property
    def family(self) -> str | None:
        return None if self.route is None else self.route.family


@dataclass(frozen=True)
class DispatchPlan:
    """A pure partition of one state's pending actions by authority posture."""

    state: RunState
    resolutions: tuple[CapabilityResolution, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, RunState):
            raise TypeError("dispatch plans require a RunState")
        resolutions = tuple(self.resolutions)
        if any(not isinstance(item, CapabilityResolution) for item in resolutions):
            raise TypeError("dispatch plans require CapabilityResolution values")
        if tuple(item.action for item in resolutions) != self.state.pending_actions:
            raise ValueError("dispatch plan must resolve every pending action exactly once")
        object.__setattr__(self, "resolutions", resolutions)

    def actions_for(self, posture: str) -> tuple[Action, ...]:
        posture = _require_text(posture, "capability posture")
        if posture not in CAPABILITY_POSTURES:
            raise ValueError(f"unsupported capability posture: {posture}")
        return tuple(
            resolution.action for resolution in self.resolutions if resolution.posture == posture
        )

    @property
    def automatic_actions(self) -> tuple[Action, ...]:
        return self.actions_for("automatic")

    @property
    def external_actions(self) -> tuple[Action, ...]:
        return self.actions_for("external")

    @property
    def human_reserved_actions(self) -> tuple[Action, ...]:
        return self.actions_for("human-reserved")

    @property
    def unavailable_actions(self) -> tuple[Action, ...]:
        return self.actions_for("unavailable")


@dataclass(frozen=True)
class DispatchBatch:
    """Transitions produced by one automatic frontier, plus its remaining plan."""

    prior_state: RunState
    state: RunState
    transitions: tuple[Transition, ...]
    results: tuple[ActionResult, ...]
    plan: DispatchPlan

    def __post_init__(self) -> None:
        if not isinstance(self.prior_state, RunState) or not isinstance(self.state, RunState):
            raise TypeError("dispatch batches require RunState values")
        transitions = tuple(self.transitions)
        results = tuple(self.results)
        if any(not isinstance(item, Transition) for item in transitions):
            raise TypeError("dispatch batches require Transition values")
        if any(not isinstance(item, ActionResult) for item in results):
            raise TypeError("dispatch batches require ActionResult values")
        if len(transitions) != len(results):
            raise ValueError("dispatch transitions and results must correlate exactly")
        if not isinstance(self.plan, DispatchPlan) or self.plan.state != self.state:
            raise ValueError("dispatch batch plan must describe its resulting state")
        current = self.prior_state
        for transition, result in zip(transitions, results, strict=True):
            if (
                transition.prior_state != current.ref
                or transition.event.result is None
                or serialize_record(transition.event.result) != serialize_record(result)
            ):
                raise ValueError("dispatch batch must contain one exact runtime result chain")
            current = transition.next_state
        if serialize_record(current) != serialize_record(self.state):
            raise ValueError("dispatch batch final state diverges from its transitions")
        object.__setattr__(self, "transitions", transitions)
        object.__setattr__(self, "results", results)
