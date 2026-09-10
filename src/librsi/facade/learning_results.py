"""Native learning-result views shared by execution and historical inspection."""

from __future__ import annotations

from dataclasses import dataclass

from ..improvement import ImprovementResult
from ..investigation import InvestigationResult
from ..records import Observation, Outcome, TargetSnapshot
from ..rsi import RSIResult
from .learning_store import LearningStore

LearningTerminal = Outcome | InvestigationResult | ImprovementResult | RSIResult


@dataclass(frozen=True)
class LearningResult:
    """A native terminal result, never an independent acceptance decision."""

    pass_id: str
    native: LearningTerminal
    strategy_after: TargetSnapshot

    @property
    def disposition(self) -> str:
        if isinstance(self.native, Outcome):
            return self.native.status
        if isinstance(self.native, InvestigationResult):
            return (
                "no-supported-revision"
                if self.native.terminal_status == "completed"
                else self.native.terminal_status
            )
        return self.native.disposition

    @property
    def adopted(self) -> bool:
        return isinstance(self.native, RSIResult) and self.native.disposition == "verified"


def learning_result(
    store: LearningStore, inputs: Observation, native: LearningTerminal
) -> LearningResult:
    """Bind a native result to its historical inputs, without asserting currentness."""
    if not isinstance(native, (Outcome, InvestigationResult, ImprovementResult, RSIResult)):
        raise ValueError("pass result is not a native terminal result")
    pass_id = inputs.value["pass_id"]
    baseline = inputs.target_snapshot
    if baseline is None or baseline.target != store.target:
        raise ValueError("learning result belongs to another profile")
    if isinstance(native, RSIResult):
        matches = (
            native.request.rsi_id == pass_id
            and native.request.declaration.target_snapshot == baseline
        )
    elif isinstance(native, ImprovementResult):
        matches = native.request.request_id == pass_id and native.request.baseline == baseline
    elif isinstance(native, InvestigationResult):
        matches = (
            native.investigation.investigation_id == f"{pass_id}:investigate"
            and native.investigation.target_snapshot == baseline
        )
    else:
        state = store.runtime.resume(f"{pass_id}:ideas")
        matches = state is not None and state.status == "failed" and state.outcome == native
    if not matches:
        raise ValueError("terminal result belongs to another learning pass")
    after = native.authoritative_snapshot if isinstance(native, RSIResult) else baseline
    if after is None:
        raise RuntimeError("native result leaves strategy authority unresolved")
    return LearningResult(pass_id, native, after)
