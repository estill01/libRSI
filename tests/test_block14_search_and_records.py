from __future__ import annotations

import json
from dataclasses import replace

import pytest

from librsi import (
    SEARCH_AUTHORITY,
    Baseline,
    CandidateProposer,
    CandidateTrialBatch,
    ComparativeSelectionPolicy,
    SearchProposal,
    SearchRequest,
    SelectionDecision,
    TargetSnapshot,
    deserialize_record,
    serialize_record,
)
from tests.block14_support import candidate_for, comparison_context, trial_batch


class FixedSearch:
    def __init__(self, proposal: SearchProposal) -> None:
        self.proposal = proposal

    def propose(self, request: SearchRequest) -> SearchProposal:
        assert request == self.proposal.request
        return self.proposal


def test_search_boundary_is_structurally_proposal_only() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "searched")
    request = SearchRequest.create(
        request_id="bounded-search",
        contract=context.contract,
        maximum_candidates=2,
        search_space={"temperature_c": [31, 32]},
    )
    proposal = SearchProposal.create(
        request=request,
        candidates=(candidate,),
        rationale=("Candidate lies inside the requested bounded search space",),
    )

    assert proposal.authority == SEARCH_AUTHORITY
    assert isinstance(FixedSearch(proposal), CandidateProposer)
    with pytest.raises(ValueError, match="cannot claim selection authority"):
        replace(proposal, authority="accepted")
    assert "selected" not in proposal.to_dict()["data"]


def test_search_budget_and_exact_baseline_are_enforced() -> None:
    context = comparison_context()
    first = candidate_for(context, "first")
    second = candidate_for(context, "second")
    request = SearchRequest.create(
        request_id="one-only",
        contract=context.contract,
        maximum_candidates=1,
        search_space={"mode": ["a", "b"]},
    )

    with pytest.raises(ValueError, match="candidate budget"):
        SearchProposal.create(
            request=request,
            candidates=(first, second),
            rationale=("too many",),
        )

    foreign_snapshot = TargetSnapshot(
        target=context.target,
        revision="foreign-baseline",
        state={"yield_pct": 70.0, "energy_kwh": 20.0, "contamination_ppm": 1.0},
    )
    foreign_baseline = Baseline.create(
        snapshot=foreign_snapshot,
        measurements={"yield_pct": 70.0, "energy_kwh": 20.0, "contamination_ppm": 1.0},
    )
    foreign_contract = type(context.contract).create(
        contract_id="foreign-contract",
        goal=context.contract.goal,
        baseline=foreign_baseline,
        objectives=context.contract.objectives,
        constraints=context.contract.constraints,
        guardrails=context.contract.guardrails,
        stopping_rules=context.contract.stopping_rules,
    )
    foreign_request = SearchRequest.create(
        request_id="foreign-search",
        contract=foreign_contract,
        maximum_candidates=1,
        search_space={"mode": ["a"]},
    )
    with pytest.raises(ValueError, match="exact contract baseline"):
        SearchProposal.create(
            request=foreign_request,
            candidates=(first,),
            rationale=("wrong baseline",),
        )


def test_selection_records_round_trip_losslessly() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "roundtrip")
    batch = trial_batch(context, candidate)
    decision = ComparativeSelectionPolicy.select(
        selection_id="roundtrip",
        contract=context.contract,
        batches=(batch,),
        risk_policy=context.risk_policy,
    )

    restored = deserialize_record(serialize_record(decision))

    assert type(restored) is SelectionDecision
    assert restored == decision
    assert restored.root == decision.root


def test_fabricated_evaluation_and_subclass_smuggling_are_rejected() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "exact")
    batch = trial_batch(context, candidate)

    forged_evaluation = replace(batch.evaluation, disposition="inconclusive")
    forged = CandidateTrialBatch(
        contract=batch.contract,
        candidate=batch.candidate,
        experiment=batch.experiment,
        results=batch.results,
        evaluation=forged_evaluation,
        independent_reviews=batch.independent_reviews,
        lineage=(
            batch.contract.ref,
            batch.candidate.ref,
            batch.experiment.ref,
            *(item.ref for item in batch.results),
            forged_evaluation.ref,
        ),
    )
    with pytest.raises(ValueError, match="exact result"):
        ComparativeSelectionPolicy.assess(forged, risk_policy=context.risk_policy)

    class TrialBatchSubclass(CandidateTrialBatch):
        pass

    subclass = TrialBatchSubclass(
        contract=batch.contract,
        candidate=batch.candidate,
        experiment=batch.experiment,
        results=batch.results,
        evaluation=batch.evaluation,
        independent_reviews=batch.independent_reviews,
        lineage=batch.lineage,
    )
    with pytest.raises(TypeError, match="CandidateTrialBatch"):
        ComparativeSelectionPolicy.assess(subclass, risk_policy=context.risk_policy)


def test_direct_and_serialized_guardrail_promotion_are_rejected() -> None:
    context = comparison_context()
    unsafe = candidate_for(context, "unsafe-forgery")
    batch = trial_batch(
        context,
        unsafe,
        candidate_rows=((80.0, 12.0, 2.5),) * 3,
    )
    decision = ComparativeSelectionPolicy.select(
        selection_id="unsafe-forgery",
        contract=context.contract,
        batches=(batch,),
        risk_policy=context.risk_policy,
    )
    rejected = decision.assessments[0]

    with pytest.raises(ValueError, match="exact policy-derived projection"):
        replace(
            rejected,
            disposition="accepted",
            reasons=("optimizer said this candidate passed",),
        )
    with pytest.raises(ValueError, match="exact policy-derived projection"):
        replace(rejected, valid_trials=999, invalid_trials=0)
    forged_guardrail = replace(
        rejected.criteria[-1],
        disposition="passed",
        reason="hidden guardrail override",
    )
    with pytest.raises(ValueError, match="exact policy-derived projection"):
        replace(rejected, criteria=(*rejected.criteria[:-1], forged_guardrail))

    payload = json.loads(serialize_record(decision))
    payload["data"]["assessments"][0]["data"]["disposition"] = "accepted"
    with pytest.raises(ValueError):
        deserialize_record(json.dumps(payload))


def test_reversed_dominance_and_rank_projection_cannot_select_the_weaker_candidate() -> None:
    context = comparison_context()
    strong = candidate_for(context, "rank-strong")
    weak = candidate_for(context, "rank-weak")
    decision = ComparativeSelectionPolicy.select(
        selection_id="rank-forgery",
        contract=context.contract,
        batches=(
            trial_batch(context, strong, candidate_rows=((80.0, 12.0, 2.0),) * 3),
            trial_batch(context, weak, candidate_rows=((74.0, 17.0, 2.0),) * 3),
        ),
        risk_policy=context.risk_policy,
    )
    by_candidate = {item.assessment.candidate_ref: item for item in decision.rankings}
    strong_rank = by_candidate[strong.ref]
    weak_rank = by_candidate[weak.ref]
    forged_strong = type(strong_rank)(
        assessment=strong_rank.assessment,
        rank=2,
        dominated_by=(weak.ref,),
        dominates=(),
        lineage=(strong_rank.assessment.ref, weak.ref),
    )
    forged_weak = type(weak_rank)(
        assessment=weak_rank.assessment,
        rank=1,
        dominated_by=(),
        dominates=(strong.ref,),
        lineage=(weak_rank.assessment.ref, strong.ref),
    )

    with pytest.raises(ValueError, match="exact policy-derived projection"):
        SelectionDecision(
            selection_id="rank-forgery",
            contract=context.contract,
            risk_policy=context.risk_policy,
            assessments=decision.assessments,
            rankings=(forged_weak, forged_strong),
            disposition="selected",
            selected=(weak.ref,),
            lineage=(
                context.contract.ref,
                context.risk_policy.ref,
                *(item.ref for item in decision.assessments),
                forged_weak.ref,
                forged_strong.ref,
                weak.ref,
            ),
        )


def test_reversed_assessment_or_trial_order_cannot_fork_canonical_identity() -> None:
    context = comparison_context()
    first = candidate_for(context, "order-first")
    second = candidate_for(context, "order-second")
    first_batch = trial_batch(context, first)
    second_batch = trial_batch(context, second, candidate_rows=((75.0, 16.0, 2.0),) * 3)
    decision = ComparativeSelectionPolicy.select(
        selection_id="canonical-order",
        contract=context.contract,
        batches=(first_batch, second_batch),
        risk_policy=context.risk_policy,
    )

    with pytest.raises(ValueError, match="canonical candidate-root order"):
        SelectionDecision(
            selection_id=decision.selection_id,
            contract=decision.contract,
            risk_policy=decision.risk_policy,
            assessments=tuple(reversed(decision.assessments)),
            rankings=decision.rankings,
            disposition=decision.disposition,
            selected=decision.selected,
            lineage=(
                decision.contract.ref,
                decision.risk_policy.ref,
                *(item.ref for item in reversed(decision.assessments)),
                *(item.ref for item in decision.rankings),
                *decision.selected,
            ),
        )
    with pytest.raises(ValueError, match="canonical role/index order"):
        CandidateTrialBatch(
            contract=first_batch.contract,
            candidate=first_batch.candidate,
            experiment=first_batch.experiment,
            results=tuple(reversed(first_batch.results)),
            evaluation=first_batch.evaluation,
            lineage=(
                first_batch.contract.ref,
                first_batch.candidate.ref,
                first_batch.experiment.ref,
                *(item.ref for item in reversed(first_batch.results)),
                first_batch.evaluation.ref,
            ),
        )

    payload = json.loads(serialize_record(decision))
    payload["data"]["assessments"].reverse()
    with pytest.raises(ValueError):
        deserialize_record(json.dumps(payload))
