from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    OperationalizationProposal,
    make_operationalization_action,
    make_operationalization_result,
    operationalization_proposal_from_result,
    operationalization_request_from_action,
)
from tests.block13_support import intent_context


def test_operationalization_action_and_proposal_are_exactly_correlated() -> None:
    context = intent_context()
    action = make_operationalization_action(context.request)
    proposal = OperationalizationProposal.propose_contract(
        request=context.request,
        contract=context.contract,
    )
    result = make_operationalization_result(action=action, proposal=proposal)

    assert operationalization_request_from_action(action) == context.request
    assert operationalization_proposal_from_result(result) == proposal
    assert result.output_refs == (proposal.ref,)


def test_operationalization_codecs_reject_payload_or_authority_substitution() -> None:
    context = intent_context()
    action = make_operationalization_action(context.request)
    proposal = OperationalizationProposal.propose_contract(
        request=context.request,
        contract=context.contract,
    )
    result = make_operationalization_result(action=action, proposal=proposal)

    with pytest.raises(ValueError, match="only its exact request"):
        operationalization_request_from_action(
            replace(action, payload={"request": context.request.to_dict(), "claim": "improved"})
        )
    with pytest.raises(ValueError, match="only its exact proposal"):
        operationalization_proposal_from_result(
            replace(result, payload={"proposal": proposal.to_dict(), "accepted": True})
        )
    with pytest.raises(ValueError, match="cite only its exact proposal"):
        operationalization_proposal_from_result(
            replace(result, output_refs=(context.contract.ref,))
        )
