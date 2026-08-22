"""Proposal-only boundary for replaceable candidate-generation systems."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol, runtime_checkable

from ..identity import FrozenMap
from ..intent import EvaluationContract
from ..interventions import CandidateSnapshot
from ..records import SemanticRecord, register_record_type

SEARCH_AUTHORITY = "proposal-only"


def _require_text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SearchRequest(SemanticRecord):
    """Bounded request to propose candidates, never to accept them."""

    RECORD_TYPE: ClassVar[str] = "candidate_search_request"

    request_id: str
    contract: EvaluationContract
    maximum_candidates: int
    search_space: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_text(self.request_id, "search request id"))
        if type(self.contract) is not EvaluationContract:
            raise TypeError("search requests require an EvaluationContract")
        if (
            isinstance(self.maximum_candidates, bool)
            or not isinstance(self.maximum_candidates, int)
            or self.maximum_candidates <= 0
        ):
            raise ValueError("maximum candidates must be a positive integer")
        if not isinstance(self.search_space, Mapping) or not self.search_space:
            raise ValueError("search requests require an explicit search space")
        object.__setattr__(self, "search_space", FrozenMap(self.search_space))
        if tuple(self.lineage) != (self.contract.ref,):
            raise ValueError("search request lineage must cite its exact contract")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        contract: EvaluationContract,
        maximum_candidates: int,
        search_space: Mapping[str, object],
    ) -> SearchRequest:
        return cls(
            request_id=request_id,
            contract=contract,
            maximum_candidates=maximum_candidates,
            search_space=search_space,
            lineage=(contract.ref,),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SearchProposal(SemanticRecord):
    """Replaceable search output with structurally limited proposal authority."""

    RECORD_TYPE: ClassVar[str] = "candidate_search_proposal"

    request: SearchRequest
    candidates: tuple[CandidateSnapshot, ...]
    rationale: tuple[str, ...]
    authority: str = SEARCH_AUTHORITY

    def __post_init__(self) -> None:
        if type(self.request) is not SearchRequest:
            raise TypeError("search proposals require a SearchRequest")
        candidates = tuple(self.candidates)
        if any(type(item) is not CandidateSnapshot for item in candidates):
            raise TypeError("search proposals require CandidateSnapshot values")
        if not candidates:
            raise ValueError("search proposals require candidates")
        if len({item.ref for item in candidates}) != len(candidates):
            raise ValueError("search proposal candidates must be unique")
        if len(candidates) > self.request.maximum_candidates:
            raise ValueError("search proposal exceeds its candidate budget")
        baseline = self.request.contract.baseline.snapshot
        if any(
            item.request.intervention.baseline != baseline
            or item.snapshot.target != baseline.target
            for item in candidates
        ):
            raise ValueError("search proposal candidate is outside the exact contract baseline")
        object.__setattr__(self, "candidates", candidates)
        rationale = tuple(_require_text(item, "search rationale") for item in self.rationale)
        if not rationale:
            raise ValueError("search proposals require rationale")
        object.__setattr__(self, "rationale", rationale)
        if self.authority != SEARCH_AUTHORITY:
            raise ValueError("search proposals cannot claim selection authority")
        expected_lineage = (self.request.ref, *(item.ref for item in candidates))
        if tuple(self.lineage) != expected_lineage:
            raise ValueError("search proposal lineage is incomplete")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        request: SearchRequest,
        candidates: Sequence[CandidateSnapshot],
        rationale: Sequence[str],
    ) -> SearchProposal:
        candidate_items = tuple(candidates)
        return cls(
            request=request,
            candidates=candidate_items,
            rationale=tuple(rationale),
            lineage=(request.ref, *(item.ref for item in candidate_items)),
        )


@runtime_checkable
class CandidateProposer(Protocol):
    """External search port. It cannot return a SelectionDecision."""

    def propose(self, request: SearchRequest) -> SearchProposal: ...
