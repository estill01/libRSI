"""Canonical workflow-result to public Outcome derivation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..improvement import ImprovementResult, improvement_outcome
from ..investigation import InvestigationResult, investigation_outcome
from ..records import Outcome
from ..rsi import RSIResult, rsi_outcome
from ..validation import ValidationResult, validation_outcome
from .records import OutcomeProjection, ResultRecord

_WORKFLOW_TYPES = {
    ValidationResult: "validation",
    InvestigationResult: "investigation",
    ImprovementResult: "improvement",
    RSIResult: "rsi",
}


def workflow_for_result(result: ResultRecord) -> str:
    """Return the closed workflow kind for one exact public result class."""

    workflow = _WORKFLOW_TYPES.get(type(result))
    if workflow is None:
        raise TypeError("outcome projections require a supported exact workflow result")
    return workflow


def outcome_for_result(result: ResultRecord) -> Outcome:
    """Derive the one complete public Outcome for a canonical workflow result."""

    if type(result) is ValidationResult:
        return validation_outcome(result)
    if type(result) is InvestigationResult:
        return investigation_outcome(result)
    if type(result) is ImprovementResult:
        return improvement_outcome(result)
    if type(result) is RSIResult:
        return rsi_outcome(result)
    raise TypeError("outcome projections require a supported exact workflow result")


def project_result(
    result: ResultRecord,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> OutcomeProjection:
    """Project one canonical result without adding semantic authority."""

    return OutcomeProjection(
        workflow=workflow_for_result(result),
        result=result,
        outcome=outcome_for_result(result),
        metadata={} if metadata is None else metadata,
    )
