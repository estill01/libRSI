"""Pre-transition validation and downstream proposal-lineage guards."""

from __future__ import annotations

from dataclasses import dataclass

from ..records import Evidence, Intervention, SemanticRecord
from ..runtime import ActionResult, RunState
from .actions import REASONING_ACTION_KIND, reasoning_request_from_action
from .actions import reasoning_result_from_action_result as decode_result
from .records import ReasoningResult


@dataclass(frozen=True)
class ReasoningResultValidator:
    """Fail closed on malformed external or managed reasoning responses."""

    action_kind: str = REASONING_ACTION_KIND

    def validate(self, state: RunState, result: ActionResult) -> None:
        if not isinstance(state, RunState):
            raise TypeError("reasoning validation requires a RunState")
        if not isinstance(result, ActionResult):
            raise TypeError("reasoning validation requires an ActionResult")
        request = reasoning_request_from_action(result.action)
        if request.target_snapshot != state.run.target_snapshot:
            raise ValueError("reasoning request target snapshot is stale or mismatched")
        if result.disposition == "succeeded":
            decode_result(result)
            return
        if result.output_refs or result.payload:
            raise ValueError("failed reasoning results cannot contain proposal outputs")


def require_reasoning_derivation(
    result: ReasoningResult,
    decision: SemanticRecord,
) -> SemanticRecord:
    """Require evidence/interventions to retain proposal and original input lineage."""

    if not isinstance(result, ReasoningResult):
        raise TypeError("reasoning derivation requires a ReasoningResult")
    if not isinstance(decision, (Evidence, Intervention)):
        raise TypeError("reasoning derivation supports Evidence or Intervention decisions")
    required = frozenset((result.ref, result.request.ref, *result.request.input_refs))
    if not required.issubset(decision.lineage):
        raise ValueError("derived decision is missing reasoning proposal or input lineage")
    snapshot = result.request.target_snapshot
    if snapshot is not None:
        if isinstance(decision, Evidence) and decision.target_snapshot != snapshot:
            raise ValueError("derived evidence does not retain the exact target snapshot")
        if isinstance(decision, Intervention) and decision.target != snapshot.target:
            raise ValueError("derived intervention does not retain the exact target")
    return decision
