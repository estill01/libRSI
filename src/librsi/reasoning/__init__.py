"""Structured, provider-neutral cognitive work that remains proposal-only."""

from .actions import (
    REASONING_ACTION_KIND,
    make_reasoning_action,
    make_reasoning_action_result,
    make_reasoning_failure,
    reasoning_request_from_action,
    reasoning_result_from_action_result,
)
from .adapters import ReasoningBackend, StructuredReasoner
from .records import ReasoningRequest, ReasoningResult
from .schemas import REASONING_KINDS, REASONING_SCHEMA_VALIDATORS, validate_reasoning_content
from .validation import (
    ReasoningResultValidator,
    require_reasoning_derivation,
    validate_reasoning_result_shape,
)

__all__ = [
    "REASONING_ACTION_KIND",
    "REASONING_KINDS",
    "REASONING_SCHEMA_VALIDATORS",
    "ReasoningBackend",
    "ReasoningRequest",
    "ReasoningResult",
    "ReasoningResultValidator",
    "StructuredReasoner",
    "make_reasoning_action",
    "make_reasoning_action_result",
    "make_reasoning_failure",
    "reasoning_request_from_action",
    "reasoning_result_from_action_result",
    "require_reasoning_derivation",
    "validate_reasoning_content",
    "validate_reasoning_result_shape",
]
