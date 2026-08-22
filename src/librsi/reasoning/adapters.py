"""Provider-neutral managed reasoner adapter for the generic capability protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..runtime import Action, ActionResult
from .actions import make_reasoning_action_result, reasoning_request_from_action
from .records import ReasoningRequest, ReasoningResult


@runtime_checkable
class ReasoningBackend(Protocol):
    """A provider-neutral source of validated structured proposals."""

    def respond(self, request: ReasoningRequest) -> ReasoningResult: ...


@dataclass(frozen=True)
class StructuredReasoner:
    """Adapt a backend to the granular Block 8 Reasoner capability."""

    backend: ReasoningBackend

    def __post_init__(self) -> None:
        if not isinstance(self.backend, ReasoningBackend):
            raise TypeError("structured reasoner backend must implement ReasoningBackend")

    def reason(self, action: Action) -> ActionResult:
        request = reasoning_request_from_action(action)
        result = self.backend.respond(request)
        if not isinstance(result, ReasoningResult):
            raise TypeError("reasoning backend must return a ReasoningResult")
        return make_reasoning_action_result(action=action, result=result)
