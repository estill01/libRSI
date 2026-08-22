"""Nonreplaceable validation for measurable improvement intent."""

from __future__ import annotations

from dataclasses import dataclass

from .records import (
    EvaluationContract,
    OperationalizationProposal,
    OperationalizationRequest,
    OperationalizationResult,
)


@dataclass(frozen=True, slots=True)
class OperationalizationPolicy:
    """Validate proposals and issue authority-bearing evaluation contracts."""

    def __post_init__(self) -> None:
        if type(self) is not OperationalizationPolicy:
            raise ValueError("operationalization policy changes require a versioned contract")

    @staticmethod
    def validate_contract(
        request: OperationalizationRequest,
        contract: EvaluationContract,
    ) -> None:
        if type(request) is not OperationalizationRequest:
            raise TypeError("contract validation requires an OperationalizationRequest")
        if type(contract) is not EvaluationContract:
            raise TypeError("contract validation requires an EvaluationContract")
        if contract.goal != request.goal:
            raise ValueError("evaluation contract operationalizes another Goal")
        if contract.baseline.snapshot != request.current_snapshot:
            raise ValueError("evaluation contract baseline is stale or target-mismatched")

    def accept_typed(
        self,
        request: OperationalizationRequest,
        contract: EvaluationContract,
    ) -> OperationalizationResult:
        self.validate_contract(request, contract)
        return OperationalizationResult(
            request=request,
            disposition="operationalized",
            contract=contract,
            lineage=(request.ref, contract.ref),
        )

    def accept_proposal(
        self,
        request: OperationalizationRequest,
        proposal: OperationalizationProposal,
    ) -> OperationalizationResult:
        if type(proposal) is not OperationalizationProposal:
            raise TypeError("operationalization requires an OperationalizationProposal")
        if proposal.request != request:
            raise ValueError("operationalization proposal answers another request")
        if proposal.contract is not None:
            self.validate_contract(request, proposal.contract)
        return OperationalizationResult(
            request=request,
            disposition=proposal.disposition,
            contract=proposal.contract,
            missing_facts=proposal.missing_facts,
            proposal=proposal,
            lineage=(
                request.ref,
                proposal.ref,
                *((proposal.contract.ref,) if proposal.contract is not None else ()),
            ),
        )
