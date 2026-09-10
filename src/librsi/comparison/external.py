"""Stateless wire boundary for hosts that own storage and experiment execution.

This module decodes canonical records and delegates to ComparativeSelectionPolicy.
It has no runtime store, host callbacks, application authority, or activation path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from ..identity import digest
from ..intent import EvaluationContract
from ..records import SemanticRecord, TargetSnapshot, record_from_dict
from .policy import ComparativeSelectionPolicy
from .records import CandidateTrialBatch, RiskPolicy

REQUEST_SCHEMA = "librsi.comparison.request.v1"
RESPONSE_SCHEMA = "librsi.comparison.response.v1"
MAX_BATCHES = 32
_FIELDS = {"schema", "selection_id", "current_snapshot", "contract", "risk_policy", "batches"}
_Record = TypeVar("_Record", bound=SemanticRecord)


def _record(value: Any, expected: type[_Record]) -> _Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"expected a canonical {expected.__name__} record")
    result = record_from_dict(value)
    if type(result) is not expected:
        raise ValueError(f"expected a canonical {expected.__name__} record")
    return result


def evaluate_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a comparison from exact records, returning advisory evidence.

    The current snapshot is the host's assertion, not an independently fetched
    fact. Hosts must hydrate authorized, current evidence before calling and
    recheck it before any later effect. A selected candidate is not approval.
    """
    if not isinstance(payload, Mapping) or set(payload) != _FIELDS:
        raise ValueError("comparison request fields are missing or unsupported")
    if payload["schema"] != REQUEST_SCHEMA:
        raise ValueError("unsupported comparison request schema")
    selection_id = payload["selection_id"]
    if not isinstance(selection_id, str) or not selection_id.strip():
        raise ValueError("selection_id must be nonempty text")
    batches = payload["batches"]
    if not isinstance(batches, list) or not 1 <= len(batches) <= MAX_BATCHES:
        raise ValueError(f"comparison requires 1 to {MAX_BATCHES} candidate batches")
    contract = _record(payload["contract"], EvaluationContract)
    snapshot = _record(payload["current_snapshot"], TargetSnapshot)
    if snapshot != contract.baseline.snapshot:
        raise ValueError("current snapshot differs from the exact contract baseline")
    decision = ComparativeSelectionPolicy.select(
        selection_id=selection_id,
        contract=contract,
        batches=tuple(_record(item, CandidateTrialBatch) for item in batches),
        risk_policy=_record(payload["risk_policy"], RiskPolicy),
    )
    return {
        "schema": RESPONSE_SCHEMA,
        "status": "succeeded",
        "request_root": digest(payload),
        "activation_authorized": False,
        "decision": decision.to_dict(),
    }
