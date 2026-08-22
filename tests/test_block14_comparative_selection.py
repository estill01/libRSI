from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Baseline,
    CandidateReview,
    CandidateTrialBatch,
    ComparativeSelectionPolicy,
    EvaluationContract,
    Guardrail,
    Metric,
    Objective,
    RiskPolicy,
    TargetSnapshot,
)
from tests.block14_support import candidate_for, comparison_context, trial_batch


def test_dominating_candidate_is_selected_with_visible_pairwise_provenance() -> None:
    context = comparison_context()
    strong = candidate_for(context, "strong")
    weak = candidate_for(context, "weak")
    strong_batch = trial_batch(
        context,
        strong,
        candidate_rows=((78.0, 14.0, 1.8),) * 3,
    )
    weak_batch = trial_batch(
        context,
        weak,
        candidate_rows=((74.0, 17.0, 2.0),) * 3,
    )

    decision = ComparativeSelectionPolicy.select(
        selection_id="dominance",
        contract=context.contract,
        batches=(weak_batch, strong_batch),
        risk_policy=context.risk_policy,
    )

    assert decision.disposition == "selected"
    assert decision.selected == (strong.ref,)
    assert [item.rank for item in decision.rankings] == [1, 2]
    strong_rank = next(
        item for item in decision.rankings if item.assessment.candidate_ref == strong.ref
    )
    assert strong_rank.dominates == (weak.ref,)
    assert strong_rank.dominated_by == ()
    assert all("score" not in item.to_dict()["data"] for item in decision.assessments)


def test_conflicting_objectives_return_a_pareto_set_without_hidden_tiebreak() -> None:
    context = comparison_context()
    yield_first = candidate_for(context, "yield-first")
    energy_first = candidate_for(context, "energy-first")
    yield_batch = trial_batch(
        context,
        yield_first,
        candidate_rows=((80.0, 17.0, 2.0),) * 3,
    )
    energy_batch = trial_batch(
        context,
        energy_first,
        candidate_rows=((74.0, 12.0, 2.0),) * 3,
    )

    decision = ComparativeSelectionPolicy.select(
        selection_id="pareto",
        contract=context.contract,
        batches=(yield_batch, energy_batch),
        risk_policy=context.risk_policy,
    )

    assert decision.disposition == "pareto"
    assert set(decision.selected) == {yield_first.ref, energy_first.ref}
    assert all(item.rank == 1 for item in decision.rankings)
    assert all(not item.dominated_by and not item.dominates for item in decision.rankings)


def test_guardrail_failure_produces_a_valid_none_accepted_decision() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "unsafe")
    batch = trial_batch(
        context,
        candidate,
        candidate_rows=((80.0, 12.0, 2.2),) * 3,
    )

    decision = ComparativeSelectionPolicy.select(
        selection_id="none",
        contract=context.contract,
        batches=(batch,),
        risk_policy=context.risk_policy,
    )

    assert decision.disposition == "none-accepted"
    assert decision.selected == ()
    assert decision.rankings == ()
    assessment = decision.assessments[0]
    assert assessment.disposition == "rejected"
    guardrail = next(item for item in assessment.criteria if item.criterion_kind == "guardrail")
    assert guardrail.disposition == "failed"
    assert "violates" in guardrail.reason


def test_invalid_trial_cannot_be_promoted_even_when_remaining_means_pass() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "partially-invalid")
    batch = trial_batch(context, candidate, invalid=(("candidate", 2),))

    assessment = ComparativeSelectionPolicy.assess(batch, risk_policy=context.risk_policy)

    assert assessment.disposition == "inconclusive"
    assert assessment.invalid_trials == 1
    assert "invalid-trial fraction" in assessment.reasons[0]


def test_uncertainty_is_applied_to_minimum_effect_conservatively() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "uncertain")
    batch = trial_batch(
        context,
        candidate,
        candidate_rows=((84.0, 17.0, 2.0), (68.0, 17.0, 2.0), (76.0, 17.0, 2.0)),
    )

    assessment = ComparativeSelectionPolicy.assess(batch, risk_policy=context.risk_policy)
    yield_assessment = next(item for item in assessment.criteria if item.metric_id == "yield_pct")

    assert yield_assessment.favorable_effect.estimate == pytest.approx(4.0)
    assert yield_assessment.favorable_effect.lower < 1.0
    assert yield_assessment.disposition == "failed"
    assert assessment.disposition == "rejected"


def test_parallel_lanes_must_share_one_exact_contract() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "contract-a")
    batch = trial_batch(context, candidate)
    other = comparison_context()
    other_contract = replace(other.contract, contract_id="other-contract")

    with pytest.raises(ValueError, match="one exact evaluation contract"):
        ComparativeSelectionPolicy.select(
            selection_id="mixed",
            contract=other_contract,
            batches=(batch,),
            risk_policy=context.risk_policy,
        )


def test_configurable_review_policy_is_enforced_without_becoming_universal() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "reviewed")
    batch = trial_batch(context, candidate)
    strict = RiskPolicy(policy_id="review-required", require_independent_review=True)

    assert (
        ComparativeSelectionPolicy.assess(batch, risk_policy=context.risk_policy).disposition
        == "accepted"
    )
    strict_assessment = ComparativeSelectionPolicy.assess(batch, risk_policy=strict)
    assert strict_assessment.disposition == "inconclusive"
    assert strict_assessment.reasons == ("independent accepting review is required but absent",)

    accepted_review = CandidateReview(
        review_id="independent-review",
        reviewer_id="reviewer-2",
        candidate=batch.candidate,
        experiment=batch.experiment,
        evaluation=batch.evaluation,
        disposition="accepted",
        findings=("Exact evidence and guardrail interpretation accepted",),
        lineage=(batch.candidate.ref, batch.experiment.ref, batch.evaluation.ref),
    )
    reviewed_batch = CandidateTrialBatch.create(
        contract=batch.contract,
        candidate=batch.candidate,
        experiment=batch.experiment,
        results=batch.results,
        independent_reviews=(accepted_review,),
    )
    assert (
        ComparativeSelectionPolicy.assess(reviewed_batch, risk_policy=strict).disposition
        == "accepted"
    )
    rejected_review = replace(accepted_review, disposition="rejected")
    rejected_review_batch = CandidateTrialBatch.create(
        contract=batch.contract,
        candidate=batch.candidate,
        experiment=batch.experiment,
        results=batch.results,
        independent_reviews=(rejected_review,),
    )
    assert (
        ComparativeSelectionPolicy.assess(rejected_review_batch, risk_policy=strict).disposition
        == "inconclusive"
    )


def test_target_objective_uses_the_complete_uncertainty_interval() -> None:
    context = comparison_context()
    metric = Metric(metric_id="yield_pct", direction="target", role="objective", unit="percent")
    objective = Objective.create(
        objective_id="target-yield",
        metric=metric,
        semantics="target",
        goal=context.contract.goal,
        target_value=76.0,
        tolerance=1.0,
    )
    contract = EvaluationContract.create(
        contract_id="target-yield-contract",
        goal=context.contract.goal,
        baseline=context.contract.baseline,
        objectives=(objective, context.contract.objectives[1]),
        constraints=context.contract.constraints,
        guardrails=context.contract.guardrails,
        stopping_rules=context.contract.stopping_rules,
    )
    target_context = replace(context, contract=contract, yield_metric=metric)
    passing = candidate_for(target_context, "target-pass")
    failing = candidate_for(target_context, "target-fail")

    passing_assessment = ComparativeSelectionPolicy.assess(
        trial_batch(target_context, passing, candidate_rows=((76.0, 16.0, 2.0),) * 3),
        risk_policy=context.risk_policy,
    )
    failing_assessment = ComparativeSelectionPolicy.assess(
        trial_batch(target_context, failing, candidate_rows=((80.0, 16.0, 2.0),) * 3),
        risk_policy=context.risk_policy,
    )

    assert passing_assessment.disposition == "accepted"
    assert failing_assessment.disposition == "rejected"
    target_result = passing_assessment.criteria[0]
    assert target_result.disposition == "passed"
    assert target_result.favorable_effect is not None
    assert target_result.favorable_effect.estimate == pytest.approx(4.0)


def test_must_satisfy_guardrail_is_a_conservative_gate() -> None:
    context = comparison_context()
    guardrail = Guardrail.create(
        guardrail_id="contamination-threshold",
        metric=context.contamination_metric,
        semantics="must-satisfy",
        constraint=context.constraint,
        operator="<=",
        threshold=2.0,
    )
    contract = EvaluationContract.create(
        contract_id="threshold-guardrail",
        goal=context.contract.goal,
        baseline=context.contract.baseline,
        objectives=context.contract.objectives,
        constraints=context.contract.constraints,
        guardrails=(guardrail,),
        stopping_rules=context.contract.stopping_rules,
    )
    threshold_context = replace(context, contract=contract)
    safe = candidate_for(threshold_context, "threshold-safe")
    unsafe = candidate_for(threshold_context, "threshold-unsafe")

    safe_assessment = ComparativeSelectionPolicy.assess(
        trial_batch(threshold_context, safe, candidate_rows=((76.0, 16.0, 1.9),) * 3),
        risk_policy=context.risk_policy,
    )
    unsafe_assessment = ComparativeSelectionPolicy.assess(
        trial_batch(threshold_context, unsafe, candidate_rows=((76.0, 16.0, 2.1),) * 3),
        risk_policy=context.risk_policy,
    )

    assert safe_assessment.disposition == "accepted"
    assert unsafe_assessment.disposition == "rejected"


def test_candidate_prepared_from_another_baseline_is_incomparable() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "stale-baseline")
    batch = trial_batch(context, candidate)
    foreign_snapshot = TargetSnapshot(
        target=context.target,
        revision="batch-20",
        state={"yield_pct": 73.0, "energy_kwh": 17.0, "contamination_ppm": 2.0},
    )
    foreign_baseline = Baseline.create(
        snapshot=foreign_snapshot,
        measurements={"yield_pct": 73.0, "energy_kwh": 17.0, "contamination_ppm": 2.0},
    )
    foreign_contract = EvaluationContract.create(
        contract_id="foreign-baseline",
        goal=context.contract.goal,
        baseline=foreign_baseline,
        objectives=context.contract.objectives,
        constraints=context.contract.constraints,
        guardrails=context.contract.guardrails,
        stopping_rules=context.contract.stopping_rules,
    )
    mismatched = CandidateTrialBatch(
        contract=foreign_contract,
        candidate=batch.candidate,
        experiment=batch.experiment,
        results=batch.results,
        evaluation=batch.evaluation,
        lineage=(
            foreign_contract.ref,
            batch.candidate.ref,
            batch.experiment.ref,
            *(item.ref for item in batch.results),
            batch.evaluation.ref,
        ),
    )

    with pytest.raises(ValueError, match="incomparable baseline"):
        ComparativeSelectionPolicy.assess(mismatched, risk_policy=context.risk_policy)


def test_sparse_valid_trials_are_insufficient_per_metric_and_cannot_rank() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "sparse-metrics")
    batch = trial_batch(context, candidate, sparse_metrics=True)

    decision = ComparativeSelectionPolicy.select(
        selection_id="sparse-metrics",
        contract=context.contract,
        batches=(batch,),
        risk_policy=context.risk_policy,
    )

    assert batch.evaluation.disposition == "inconclusive"
    assert decision.disposition == "none-accepted"
    assessment = decision.assessments[0]
    assert assessment.disposition == "inconclusive"
    assert all(item.disposition == "inconclusive" for item in assessment.criteria)
    assert any("insufficient comparative metric samples" in reason for reason in assessment.reasons)
    assert any("not conclusive passing evidence" in reason for reason in assessment.reasons)
