"""Granular host capability protocols with no lifecycle or epistemic authority."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..runtime import Action, ActionResult, RunState


@runtime_checkable
class Inspector(Protocol):
    def inspect(self, action: Action) -> ActionResult: ...


@runtime_checkable
class Retriever(Protocol):
    def retrieve(self, action: Action) -> ActionResult: ...


@runtime_checkable
class Reasoner(Protocol):
    def reason(self, action: Action) -> ActionResult: ...


@runtime_checkable
class Experimenter(Protocol):
    def experiment(self, action: Action) -> ActionResult: ...


@runtime_checkable
class Implementer(Protocol):
    def implement(self, action: Action) -> ActionResult: ...


@runtime_checkable
class Reviewer(Protocol):
    def review(self, action: Action) -> ActionResult: ...


@runtime_checkable
class Applier(Protocol):
    def apply(self, action: Action) -> ActionResult: ...


@runtime_checkable
class Verifier(Protocol):
    def verify(self, action: Action) -> ActionResult: ...


@runtime_checkable
class CapabilityResultValidator(Protocol):
    """Action-kind-specific validation applied before any runtime mutation."""

    action_kind: str

    def validate(self, state: RunState, result: ActionResult) -> None: ...
