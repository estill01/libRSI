from __future__ import annotations

from librsi import (
    OperationalizationProposal,
    OperationalizationWorkflow,
    make_operationalization_result,
)
from tests.block13_support import intent_context


def test_typed_goal_contract_remains_exact_without_reasoner_round_trip() -> None:
    context = intent_context()
    result = OperationalizationWorkflow().operationalize_typed(
        context.request,
        context.contract,
        current_snapshot=context.snapshot,
    )

    assert result.disposition == "operationalized"
    assert result.contract == context.contract
    assert result.proposal is None


def test_natural_language_goal_accepts_only_validated_structured_proposal() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    started = workflow.start(context.request, current_snapshot=context.snapshot)
    handoff = started.progress.handoff
    assert handoff is not None
    proposal = OperationalizationProposal.propose_contract(
        request=context.request,
        contract=context.contract,
    )

    completed = workflow.submit(
        started.progress,
        make_operationalization_result(action=handoff.action, proposal=proposal),
        current_snapshot=context.snapshot,
    )
    result = completed.progress.result
    assert result is not None

    assert result.disposition == "operationalized"
    assert result.contract == context.contract
    assert result.proposal == proposal
    assert handoff.capability_family == "reasoner"


def test_unmeasurable_intent_stops_with_named_information_gap() -> None:
    context = intent_context()
    workflow = OperationalizationWorkflow()
    started = workflow.start(context.request, current_snapshot=context.snapshot)
    handoff = started.progress.handoff
    assert handoff is not None
    proposal = OperationalizationProposal.pending(
        request=context.request,
        missing_facts=("A calibrated contamination measurement source",),
        unmeasurable=True,
    )

    completed = workflow.submit(
        started.progress,
        make_operationalization_result(action=handoff.action, proposal=proposal),
        current_snapshot=context.snapshot,
    )
    result = completed.progress.result
    assert result is not None

    assert result.disposition == "unmeasurable"
    assert result.contract is None
    assert result.missing_facts == ("A calibrated contamination measurement source",)
