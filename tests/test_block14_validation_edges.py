from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    SEARCH_AUTHORITY,
    CandidateAssessment,
    CandidateTrialBatch,
    ComparativeSelectionPolicy,
    CriterionAssessment,
    RankedCandidate,
    RiskPolicy,
    SearchProposal,
    SearchRequest,
    SelectionDecision,
    UncertaintyInterval,
    favorable_effect,
    mean_interval,
)
from librsi.comparison.policy import _compare_interval
from tests.block14_support import candidate_for, comparison_context, trial_batch


def _selection_fixture() -> tuple[
    CandidateTrialBatch,
    RiskPolicy,
    CandidateAssessment,
    RankedCandidate,
    SelectionDecision,
]:
    context = comparison_context()
    candidate = candidate_for(context, "edge")
    batch = trial_batch(context, candidate)
    decision = ComparativeSelectionPolicy.select(
        selection_id="edge-selection",
        contract=context.contract,
        batches=(batch,),
        risk_policy=context.risk_policy,
    )
    return batch, context.risk_policy, decision.assessments[0], decision.rankings[0], decision


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"policy_id": " "}, "required"),
        ({"minimum_valid_trials": True}, "integer"),
        ({"minimum_valid_trials": 0}, "positive"),
        ({"maximum_invalid_fraction": False}, "number"),
        ({"maximum_invalid_fraction": 1.1}, "between zero and one"),
        ({"confidence_multiplier": float("inf")}, "finite"),
        ({"confidence_multiplier": -1.0}, "nonnegative"),
        ({"require_independent_review": 1}, "boolean"),
    ],
)
def test_risk_policy_rejects_ambiguous_or_nonfinite_configuration(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        RiskPolicy(**({"policy_id": "risk"} | changes))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"estimate": True}, "number"),
        ({"lower": float("nan")}, "finite"),
        ({"lower": 2.0}, "contain"),
        ({"sample_count": -1}, "nonnegative"),
        ({"sample_count": 0}, "require samples"),
        ({"method": "opaque"}, "unsupported uncertainty"),
    ],
)
def test_uncertainty_interval_is_finite_ordered_and_explicit(
    changes: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "estimate": 1.0,
        "lower": 0.0,
        "upper": 2.0,
        "sample_count": 2,
    }
    values.update(changes)
    with pytest.raises((TypeError, ValueError), match=message):
        UncertaintyInterval(**values)  # type: ignore[arg-type]


def test_statistical_primitives_cover_singletons_directions_and_invalid_inputs() -> None:
    singleton = mean_interval((3.0,), confidence_multiplier=1.0)
    assert (singleton.lower, singleton.upper) == (3.0, 3.0)
    baseline = UncertaintyInterval(estimate=10.0, lower=9.0, upper=11.0, sample_count=3)
    candidate = UncertaintyInterval(estimate=8.0, lower=7.0, upper=9.0, sample_count=3)
    assert favorable_effect(baseline, candidate, direction="decrease").estimate == 2.0
    overlapping = UncertaintyInterval(estimate=10.0, lower=9.0, upper=11.0, sample_count=3)
    assert favorable_effect(baseline, overlapping, direction="target").upper == 0.0
    outside = UncertaintyInterval(estimate=15.0, lower=14.0, upper=16.0, sample_count=3)
    assert favorable_effect(baseline, outside, direction="target").upper < 0.0
    with pytest.raises(ValueError, match="finite samples"):
        mean_interval((), confidence_multiplier=1.0)
    with pytest.raises(ValueError, match="finite samples"):
        mean_interval((float("nan"),), confidence_multiplier=1.0)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        mean_interval((1.0,), confidence_multiplier=-1.0)
    with pytest.raises(ValueError, match="unsupported metric direction"):
        favorable_effect(baseline, candidate, direction="sideways")


def test_candidate_trial_batch_rejects_inexact_fields_and_lineage() -> None:
    batch, _, _, _, _ = _selection_fixture()
    fields = {
        "contract": batch.contract,
        "candidate": batch.candidate,
        "experiment": batch.experiment,
        "results": batch.results,
        "evaluation": batch.evaluation,
        "independent_reviews": batch.independent_reviews,
        "lineage": batch.lineage,
    }
    cases = (
        ({"contract": object()}, "EvaluationContract"),
        ({"candidate": object()}, "CandidateSnapshot"),
        ({"experiment": object()}, "ExperimentSpec"),
        ({"results": (object(),)}, "TrialResult"),
        ({"results": ()}, "require trial results"),
        ({"results": (batch.results[0], batch.results[0])}, "must be unique"),
        ({"evaluation": object()}, "Evaluation"),
        ({"independent_reviews": (object(),)}, "CandidateReview"),
        ({"lineage": ()}, "lineage is incomplete"),
    )
    for changes, message in cases:
        invalid = fields | changes
        with pytest.raises((TypeError, ValueError), match=message):
            CandidateTrialBatch(**invalid)  # type: ignore[arg-type]


def test_criterion_assessment_rejects_fabricated_semantics() -> None:
    _, _, assessment, _, _ = _selection_fixture()
    criterion = assessment.criteria[0]
    with pytest.raises(ValueError, match="unsupported criterion kind"):
        replace(criterion, criterion_kind="score")
    with pytest.raises(TypeError, match="reference type"):
        replace(criterion, criterion_kind="guardrail")
    with pytest.raises(ValueError, match="unsupported criterion disposition"):
        replace(criterion, disposition="accepted")
    with pytest.raises(ValueError, match="cannot fabricate"):
        replace(criterion, disposition="inconclusive")
    with pytest.raises(TypeError, match="exact UncertaintyInterval"):
        replace(criterion, baseline=None)
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(criterion, lineage=(criterion.criterion_ref,))
    inconclusive = CriterionAssessment(
        criterion_kind="objective",
        criterion_ref=criterion.criterion_ref,
        criterion_id=criterion.criterion_id,
        metric_id=criterion.metric_id,
        baseline=None,
        candidate=None,
        favorable_effect=None,
        disposition="inconclusive",
        reason="missing samples",
        lineage=(criterion.criterion_ref,),
    )
    assert inconclusive.favorable_effect is None


def test_assessment_and_ranking_records_fail_closed() -> None:
    batch, policy, assessment, ranking, _ = _selection_fixture()
    with pytest.raises(TypeError, match="CandidateTrialBatch"):
        replace(assessment, batch=object())
    with pytest.raises(TypeError, match="RiskPolicy"):
        replace(assessment, risk_policy=object())
    with pytest.raises(TypeError, match="CriterionAssessment"):
        replace(assessment, criteria=(object(),))
    with pytest.raises(ValueError, match="exact contract"):
        replace(assessment, criteria=tuple(reversed(assessment.criteria)))
    with pytest.raises(ValueError, match="unsupported candidate disposition"):
        replace(assessment, disposition="selected")
    with pytest.raises(ValueError, match="explicit reasons"):
        replace(assessment, reasons=())
    with pytest.raises(ValueError, match="nonnegative"):
        replace(assessment, valid_trials=-1)
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(assessment, lineage=(batch.ref, policy.ref))

    with pytest.raises(TypeError, match="CandidateAssessment"):
        replace(ranking, assessment=object())
    with pytest.raises(ValueError, match="positive"):
        replace(ranking, rank=0)
    with pytest.raises(ValueError, match="cannot dominate itself"):
        replace(
            ranking,
            dominates=(assessment.candidate_ref,),
            lineage=(assessment.ref, assessment.candidate_ref),
        )
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(ranking, lineage=())


def test_selection_decision_rejects_impossible_outcomes() -> None:
    _, _, assessment, ranking, decision = _selection_fixture()
    with pytest.raises(TypeError, match="EvaluationContract"):
        replace(decision, contract=object())
    with pytest.raises(TypeError, match="RiskPolicy"):
        replace(decision, risk_policy=object())
    with pytest.raises(TypeError, match="CandidateAssessment"):
        replace(decision, assessments=(object(),))
    with pytest.raises(ValueError, match="require candidate assessments"):
        replace(decision, assessments=())
    with pytest.raises(TypeError, match="RankedCandidate"):
        replace(decision, rankings=(object(),))
    with pytest.raises(ValueError, match="unsupported selection disposition"):
        replace(decision, disposition="optimizer-picked")
    with pytest.raises(ValueError, match="exactly the accepted"):
        replace(decision, rankings=())
    with pytest.raises(ValueError, match="only accepted"):
        replace(decision, selected=(decision.contract.ref,))
    with pytest.raises(ValueError, match="cannot select or rank"):
        replace(decision, disposition="none-accepted")
    with pytest.raises(ValueError, match="exactly one"):
        replace(decision, selected=(), disposition="selected", rankings=(ranking,))
    with pytest.raises(ValueError, match="at least two"):
        replace(decision, disposition="pareto")
    with pytest.raises(ValueError, match="exact policy-derived projection"):
        rank_two = replace(ranking, rank=2)
        replace(
            decision,
            rankings=(rank_two,),
            lineage=(
                decision.contract.ref,
                decision.risk_policy.ref,
                assessment.ref,
                rank_two.ref,
                *decision.selected,
            ),
        )


def test_search_records_reject_malformed_requests_and_proposals() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "search-edge")
    request = SearchRequest.create(
        request_id="search-edge",
        contract=context.contract,
        maximum_candidates=1,
        search_space={"temperature": [31]},
    )
    proposal = SearchProposal.create(
        request=request,
        candidates=(candidate,),
        rationale=("bounded",),
    )
    with pytest.raises(ValueError, match="required"):
        replace(request, request_id=" ")
    with pytest.raises(TypeError, match="EvaluationContract"):
        replace(request, contract=object())
    for value in (True, 0):
        with pytest.raises(ValueError, match="positive integer"):
            replace(request, maximum_candidates=value)
    with pytest.raises(ValueError, match="explicit search space"):
        replace(request, search_space={})
    with pytest.raises(ValueError, match="lineage"):
        replace(request, lineage=())
    with pytest.raises(TypeError, match="SearchRequest"):
        replace(proposal, request=object())
    with pytest.raises(TypeError, match="CandidateSnapshot"):
        replace(proposal, candidates=(object(),))
    with pytest.raises(ValueError, match="require candidates"):
        replace(proposal, candidates=())
    with pytest.raises(ValueError, match="must be unique"):
        replace(proposal, candidates=(candidate, candidate))
    with pytest.raises(ValueError, match="require rationale"):
        replace(proposal, rationale=())
    with pytest.raises(ValueError, match="selection authority"):
        replace(proposal, authority="selected")
    with pytest.raises(ValueError, match="lineage is incomplete"):
        replace(proposal, lineage=())
    assert proposal.authority == SEARCH_AUTHORITY


def test_public_policy_validates_inputs_and_risk_boundaries() -> None:
    batch, policy, _, _, _ = _selection_fixture()
    with pytest.raises(TypeError, match="CandidateTrialBatch"):
        ComparativeSelectionPolicy.assess(object(), risk_policy=policy)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RiskPolicy"):
        ComparativeSelectionPolicy.assess(batch, risk_policy=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="EvaluationContract"):
        ComparativeSelectionPolicy.select(
            selection_id="bad",
            contract=object(),
            batches=(batch,),
            risk_policy=policy,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="RiskPolicy"):
        ComparativeSelectionPolicy.select(
            selection_id="bad",
            contract=batch.contract,
            batches=(batch,),
            risk_policy=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="must be a sequence"):
        ComparativeSelectionPolicy.select(
            selection_id="bad",
            contract=batch.contract,
            batches="bad",  # type: ignore[arg-type]
            risk_policy=policy,
        )
    with pytest.raises(ValueError, match="requires candidate batches"):
        ComparativeSelectionPolicy.select(
            selection_id="bad", contract=batch.contract, batches=(), risk_policy=policy
        )
    with pytest.raises(TypeError, match="CandidateTrialBatch"):
        ComparativeSelectionPolicy.select(
            selection_id="bad",
            contract=batch.contract,
            batches=(object(),),  # type: ignore[arg-type]
            risk_policy=policy,
        )
    with pytest.raises(ValueError, match="must be unique"):
        ComparativeSelectionPolicy.select(
            selection_id="bad",
            contract=batch.contract,
            batches=(batch, batch),
            risk_policy=policy,
        )


@pytest.mark.parametrize(
    ("operator", "threshold", "expected"),
    [
        (">", 0.0, True),
        (">=", 1.0, True),
        ("<", 3.0, True),
        ("<=", 2.0, True),
        ("==", 1.0, False),
    ],
)
def test_thresholds_use_the_conservative_interval_edge(
    operator: str, threshold: float, expected: bool
) -> None:
    interval = UncertaintyInterval(estimate=1.5, lower=1.0, upper=2.0, sample_count=3)
    assert _compare_interval(interval, operator, threshold) is expected
    with pytest.raises(ValueError, match="unsupported comparison operator"):
        _compare_interval(interval, "~=", threshold)


def test_all_invalid_candidate_trials_return_inconclusive_criteria_not_an_exception() -> None:
    context = comparison_context()
    candidate = candidate_for(context, "all-invalid")
    batch = trial_batch(
        context,
        candidate,
        invalid=(("candidate", 0), ("candidate", 1), ("candidate", 2)),
    )

    decision = ComparativeSelectionPolicy.select(
        selection_id="all-invalid",
        contract=context.contract,
        batches=(batch,),
        risk_policy=context.risk_policy,
    )

    assert decision.disposition == "none-accepted"
    assessment = decision.assessments[0]
    assert assessment.disposition == "inconclusive"
    assert all(item.disposition == "inconclusive" for item in assessment.criteria)
    assert all(item.favorable_effect is None for item in assessment.criteria)


def test_minimum_valid_trial_policy_can_reject_an_otherwise_valid_batch() -> None:
    batch, _, _, _, _ = _selection_fixture()
    strict = RiskPolicy(policy_id="more-repetitions", minimum_valid_trials=4)

    assessment = ComparativeSelectionPolicy.assess(batch, risk_policy=strict)

    assert assessment.disposition == "inconclusive"
    assert "insufficient valid" in assessment.reasons[0]
