"""External event projection over canonical runtime records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..runtime import Event, Transition
from .records import EventProjection


def project_event(
    event: Event,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> EventProjection:
    """Project one exact canonical event for external consumption."""

    if type(event) is not Event:
        raise TypeError("event projection requires an exact canonical Event")
    return EventProjection(event=event, metadata={} if metadata is None else metadata)


def project_transition(
    transition: Transition,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> EventProjection:
    """Project the authoritative event carried by one exact transition."""

    if type(transition) is not Transition:
        raise TypeError("transition projection requires an exact canonical Transition")
    return project_event(transition.event, metadata=metadata)
