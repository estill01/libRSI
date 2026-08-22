"""Control-plane-neutral capability dispatch over the Block 7 state machine."""

from __future__ import annotations

from ..errors import RSICapabilityError
from ..runtime import (
    TERMINAL_RUN_STATUSES,
    ActionResult,
    RunState,
    RuntimeEngine,
    RuntimeUpdate,
    Transition,
)
from .records import DispatchBatch, DispatchPlan
from .registry import CapabilityRegistry


class CapabilityDispatcher:
    """Execute one automatic frontier; all state changes still pass through RuntimeEngine."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("capability dispatcher requires a CapabilityRegistry")
        for route in registry.routes:
            if route.action_kind in {
                "investigation-reason",
                "investigation-experiment",
            }:
                raise RSICapabilityError(
                    "investigation actions are owned by InvestigationWorkflow and cannot "
                    "be configured on CapabilityDispatcher"
                )
            if route.action_kind not in {
                "reason",
                "validation-evidence",
            }:
                continue
            expected_family = "reasoner" if route.action_kind == "reason" else "experimenter"
            if route.family != expected_family:
                raise RSICapabilityError(
                    f"{route.action_kind} actions require an exact {expected_family} route"
                )
        self._registry = registry

    def next(self, state: RunState) -> DispatchPlan:
        """Return the exact pending-action partition without mutating runtime state."""

        return self._registry.plan(state)

    def _submit_authorized(
        self,
        state: RunState,
        result: ActionResult,
        *,
        authority: str,
    ) -> RuntimeUpdate:
        if not isinstance(result, ActionResult):
            raise TypeError("capability submission requires an ActionResult")
        if result.action.kind in {
            "investigation-reason",
            "investigation-experiment",
        }:
            raise RSICapabilityError(
                "investigation results must be submitted through InvestigationWorkflow"
            )
        if result.action.kind == "reason":
            # The reserved structured-reasoning path is validated by libRSI itself.
            # Host validators configured on the registry run in addition below and
            # cannot weaken or replace this authority boundary.
            from ..reasoning.validation import ReasoningResultValidator

            ReasoningResultValidator().validate(state, result)
        elif result.action.kind == "validation-evidence":
            from ..validation.actions import ValidationEvidenceResultValidator

            ValidationEvidenceResultValidator().validate(state, result)
        self._registry.validate(state, result)
        resolution = self._registry.resolve(result.action)
        expected_family = {
            "reason": "reasoner",
            "validation-evidence": "experimenter",
        }.get(result.action.kind)
        if expected_family is not None and resolution.family != expected_family:
            raise RSICapabilityError(
                f"{result.action.kind} actions require an exact {expected_family} route"
            )
        if resolution.posture == "unavailable":
            raise RSICapabilityError("unavailable capability results cannot be submitted")
        if resolution.posture != authority:
            raise RSICapabilityError(
                "capability result authority does not match the resolved posture"
            )
        return RuntimeEngine.submit(state, result)

    def submit(
        self,
        state: RunState,
        result: ActionResult,
        *,
        authority: str = "external",
    ) -> RuntimeUpdate:
        """Apply an explicitly external or human-reserved result through RuntimeEngine."""

        if authority not in {"external", "human-reserved"}:
            raise RSICapabilityError("external submission authority is unsupported")
        return self._submit_authorized(state, result, authority=authority)

    def advance(self, state: RunState) -> DispatchBatch:
        """Execute currently automatic actions once in canonical pending order."""

        initial_plan = self.next(state)
        current = state
        transitions: list[Transition] = []
        results: list[ActionResult] = []
        for resolution in initial_plan.resolutions:
            if resolution.posture != "automatic":
                continue
            if current.status in TERMINAL_RUN_STATUSES:
                break
            if resolution.action.ref not in {item.ref for item in current.pending_actions}:
                raise RSICapabilityError("automatic action is no longer pending")
            result = self._registry.execute(resolution)
            update = self._submit_authorized(current, result, authority="automatic")
            if update.transition is None:
                raise RSICapabilityError("automatic dispatch unexpectedly produced no transition")
            results.append(result)
            transitions.append(update.transition)
            current = update.state
        return DispatchBatch(
            prior_state=state,
            state=current,
            transitions=tuple(transitions),
            results=tuple(results),
            plan=self.next(current),
        )
