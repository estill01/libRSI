"""Canonical records for evidence-bound candidate comparison and selection."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar

from ..identity import FrozenMap
from ..intent import EvaluationContract
from ..interventions import CandidateSnapshot
from ..records import (
    Evaluation,
    ExperimentSpec,
    RecordRef,
    SemanticRecord,
    TrialResult,
    register_record_type,
)

ASSESSMENT_DISPOSITIONS = frozenset({"accepted", "rejected", "inconclusive"})
CRITERION_KINDS = frozenset({"objective", "guardrail"})
CRITERION_DISPOSITIONS = frozenset({"passed", "failed", "inconclusive"})
REVIEW_DISPOSITIONS = frozenset({"accepted", "rejected"})
SELECTION_DISPOSITIONS = frozenset({"selected", "pareto", "none-accepted"})
UNCERTAINTY_METHODS = frozenset({"student-standard-error"})


def _require_text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _finite(value: float | int, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _nonnegative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _refs(value: Sequence[RecordRef], label: str) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    items = tuple(value)
    if any(not isinstance(item, RecordRef) for item in items):
        raise TypeError(f"{label} must contain RecordRef values")
    if len(set(items)) != len(items):
        raise ValueError(f"{label} must be unique")
    return items


def _lineage(value: Sequence[RecordRef], label: str) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    items = tuple(value)
    if any(not isinstance(item, RecordRef) for item in items):
        raise TypeError(f"{label} must contain RecordRef values")
    return items


def _trial_key(result: TrialResult) -> tuple[int, int, str]:
    role_order = {"baseline": 0, "candidate": 1, "subject": 2}
    return (role_order.get(result.trial.role, 3), result.trial.index, result.root)


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RiskPolicy(SemanticRecord):
    """Explicit uncertainty and invalid-trial posture for one selection decision."""

    RECORD_TYPE: ClassVar[str] = "selection_risk_policy"

    policy_id: str
    minimum_valid_trials: int = 2
    maximum_invalid_fraction: float = 0.0
    confidence_multiplier: float = 1.96
    require_independent_review: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _require_text(self.policy_id, "risk policy id"))
        minimum = _nonnegative_int(self.minimum_valid_trials, "minimum valid trials")
        if minimum == 0:
            raise ValueError("minimum valid trials must be positive")
        object.__setattr__(self, "minimum_valid_trials", minimum)
        fraction = _finite(self.maximum_invalid_fraction, "maximum invalid fraction")
        if not 0.0 <= fraction <= 1.0:
            raise ValueError("maximum invalid fraction must be between zero and one")
        object.__setattr__(self, "maximum_invalid_fraction", fraction)
        multiplier = _finite(self.confidence_multiplier, "confidence multiplier")
        if multiplier < 0.0:
            raise ValueError("confidence multiplier must be nonnegative")
        object.__setattr__(self, "confidence_multiplier", multiplier)
        if type(self.require_independent_review) is not bool:
            raise TypeError("require_independent_review must be a boolean")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class UncertaintyInterval(SemanticRecord):
    """Transparent mean interval derived from an exact finite sample."""

    RECORD_TYPE: ClassVar[str] = "uncertainty_interval"

    estimate: float
    lower: float
    upper: float
    sample_count: int
    method: str = "student-standard-error"

    def __post_init__(self) -> None:
        estimate = _finite(self.estimate, "interval estimate")
        lower = _finite(self.lower, "interval lower bound")
        upper = _finite(self.upper, "interval upper bound")
        if lower > estimate or estimate > upper:
            raise ValueError("uncertainty interval must contain its estimate")
        object.__setattr__(self, "estimate", estimate)
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        count = _nonnegative_int(self.sample_count, "interval sample count")
        if count == 0:
            raise ValueError("uncertainty intervals require samples")
        object.__setattr__(self, "sample_count", count)
        method = _require_text(self.method, "uncertainty method")
        if method not in UNCERTAINTY_METHODS:
            raise ValueError(f"unsupported uncertainty method: {method}")
        object.__setattr__(self, "method", method)
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class CandidateReview(SemanticRecord):
    """Independent review of one exact candidate experiment and evaluation."""

    RECORD_TYPE: ClassVar[str] = "candidate_review"

    review_id: str
    reviewer_id: str
    candidate: CandidateSnapshot
    experiment: ExperimentSpec
    evaluation: Evaluation
    disposition: str
    findings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_id", _require_text(self.review_id, "review id"))
        object.__setattr__(self, "reviewer_id", _require_text(self.reviewer_id, "reviewer id"))
        if type(self.candidate) is not CandidateSnapshot:
            raise TypeError("candidate reviews require a CandidateSnapshot")
        if type(self.experiment) is not ExperimentSpec:
            raise TypeError("candidate reviews require an ExperimentSpec")
        if type(self.evaluation) is not Evaluation:
            raise TypeError("candidate reviews require an Evaluation")
        if self.experiment.candidate_snapshot != self.candidate.snapshot:
            raise ValueError("candidate review experiment does not match the exact candidate")
        if self.evaluation.subject_refs != (self.experiment.ref,):
            raise ValueError("candidate review evaluation does not match the exact experiment")
        disposition = _require_text(self.disposition, "candidate review disposition")
        if disposition not in REVIEW_DISPOSITIONS:
            raise ValueError(f"unsupported candidate review disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        findings = tuple(_require_text(item, "candidate review finding") for item in self.findings)
        if not findings:
            raise ValueError("candidate reviews require explicit findings")
        object.__setattr__(self, "findings", findings)
        expected_lineage = (self.candidate.ref, self.experiment.ref, self.evaluation.ref)
        if _refs(self.lineage, "candidate review lineage") != expected_lineage:
            raise ValueError("candidate review lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class CandidateTrialBatch(SemanticRecord):
    """One candidate's exact baseline/candidate experiment under one contract."""

    RECORD_TYPE: ClassVar[str] = "candidate_trial_batch"

    contract: EvaluationContract
    candidate: CandidateSnapshot
    experiment: ExperimentSpec
    results: tuple[TrialResult, ...]
    evaluation: Evaluation
    independent_reviews: tuple[CandidateReview, ...] = ()

    def __post_init__(self) -> None:
        if type(self.contract) is not EvaluationContract:
            raise TypeError("candidate trial batches require an EvaluationContract")
        if type(self.candidate) is not CandidateSnapshot:
            raise TypeError("candidate trial batches require a CandidateSnapshot")
        if type(self.experiment) is not ExperimentSpec:
            raise TypeError("candidate trial batches require an ExperimentSpec")
        results = tuple(self.results)
        if any(type(item) is not TrialResult for item in results):
            raise TypeError("candidate trial batches require TrialResult values")
        if not results:
            raise ValueError("candidate trial batches require trial results")
        if len({item.ref for item in results}) != len(results):
            raise ValueError("candidate trial results must be unique")
        if results != tuple(sorted(results, key=_trial_key)):
            raise ValueError("candidate trial results must use canonical role/index order")
        object.__setattr__(self, "results", results)
        if type(self.evaluation) is not Evaluation:
            raise TypeError("candidate trial batches require an Evaluation")
        reviews = tuple(self.independent_reviews)
        if any(type(item) is not CandidateReview for item in reviews):
            raise TypeError("independent reviews must contain CandidateReview values")
        if len({item.ref for item in reviews}) != len(reviews):
            raise ValueError("independent candidate reviews must be unique")
        if reviews != tuple(sorted(reviews, key=lambda item: item.root)):
            raise ValueError("independent candidate reviews must use canonical root order")
        if any(
            item.candidate != self.candidate
            or item.experiment != self.experiment
            or item.evaluation != self.evaluation
            for item in reviews
        ):
            raise ValueError("independent review does not cover this exact candidate evaluation")
        object.__setattr__(self, "independent_reviews", reviews)
        expected_lineage = (
            self.contract.ref,
            self.candidate.ref,
            self.experiment.ref,
            *(item.ref for item in results),
            self.evaluation.ref,
            *(item.ref for item in reviews),
        )
        if _refs(self.lineage, "candidate trial batch lineage") != expected_lineage:
            raise ValueError("candidate trial batch lineage is incomplete")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        contract: EvaluationContract,
        candidate: CandidateSnapshot,
        experiment: ExperimentSpec,
        results: Sequence[TrialResult],
        independent_reviews: Sequence[CandidateReview] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> CandidateTrialBatch:
        from ..evaluation import ExperimentEvaluator

        raw_results = tuple(results)
        if any(type(item) is not TrialResult for item in raw_results):
            raise TypeError("candidate trial batches require TrialResult values")
        result_items = tuple(sorted(raw_results, key=_trial_key))
        evaluation = ExperimentEvaluator.evaluate(experiment, results=result_items)
        raw_reviews = tuple(independent_reviews)
        if any(type(item) is not CandidateReview for item in raw_reviews):
            raise TypeError("independent reviews must contain CandidateReview values")
        reviews = tuple(sorted(raw_reviews, key=lambda item: item.root))
        return cls(
            contract=contract,
            candidate=candidate,
            experiment=experiment,
            results=result_items,
            evaluation=evaluation,
            independent_reviews=reviews,
            lineage=(
                contract.ref,
                candidate.ref,
                experiment.ref,
                *(item.ref for item in result_items),
                evaluation.ref,
                *(item.ref for item in reviews),
            ),
            metadata=FrozenMap(metadata),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class CriterionAssessment(SemanticRecord):
    """One visible objective or guardrail determination without score aggregation."""

    RECORD_TYPE: ClassVar[str] = "criterion_assessment"

    criterion_kind: str
    criterion_ref: RecordRef
    criterion_id: str
    metric_id: str
    baseline: UncertaintyInterval | None
    candidate: UncertaintyInterval | None
    favorable_effect: UncertaintyInterval | None
    disposition: str
    reason: str

    def __post_init__(self) -> None:
        kind = _require_text(self.criterion_kind, "criterion kind")
        if kind not in CRITERION_KINDS:
            raise ValueError(f"unsupported criterion kind: {kind}")
        object.__setattr__(self, "criterion_kind", kind)
        if not isinstance(self.criterion_ref, RecordRef) or self.criterion_ref.record_type != kind:
            raise TypeError("criterion reference type does not match its kind")
        object.__setattr__(self, "criterion_id", _require_text(self.criterion_id, "criterion id"))
        object.__setattr__(self, "metric_id", _require_text(self.metric_id, "metric id"))
        disposition = _require_text(self.disposition, "criterion disposition")
        if disposition not in CRITERION_DISPOSITIONS:
            raise ValueError(f"unsupported criterion disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        intervals = (self.baseline, self.candidate, self.favorable_effect)
        if disposition == "inconclusive":
            if any(item is not None for item in intervals):
                raise ValueError("inconclusive criteria cannot fabricate metric intervals")
        elif any(type(item) is not UncertaintyInterval for item in intervals):
            raise TypeError("conclusive criteria require exact UncertaintyInterval values")
        object.__setattr__(self, "reason", _require_text(self.reason, "criterion reason"))
        expected_lineage: tuple[RecordRef, ...] = (self.criterion_ref,)
        if self.baseline is not None:
            assert self.candidate is not None and self.favorable_effect is not None
            expected_lineage = (
                self.criterion_ref,
                self.baseline.ref,
                self.candidate.ref,
                self.favorable_effect.ref,
            )
        if _lineage(self.lineage, "criterion assessment lineage") != expected_lineage:
            raise ValueError("criterion assessment lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class CandidateAssessment(SemanticRecord):
    """Eligibility and per-criterion evidence for one exact candidate."""

    RECORD_TYPE: ClassVar[str] = "candidate_assessment"

    batch: CandidateTrialBatch
    risk_policy: RiskPolicy
    criteria: tuple[CriterionAssessment, ...]
    disposition: str
    reasons: tuple[str, ...]
    valid_trials: int
    invalid_trials: int

    def __post_init__(self) -> None:
        if type(self.batch) is not CandidateTrialBatch:
            raise TypeError("candidate assessments require a CandidateTrialBatch")
        if type(self.risk_policy) is not RiskPolicy:
            raise TypeError("candidate assessments require a RiskPolicy")
        criteria = tuple(self.criteria)
        if any(type(item) is not CriterionAssessment for item in criteria):
            raise TypeError("candidate assessments require CriterionAssessment values")
        expected_refs = tuple(item.ref for item in self.batch.contract.objectives) + tuple(
            item.ref for item in self.batch.contract.guardrails
        )
        if tuple(item.criterion_ref for item in criteria) != expected_refs:
            raise ValueError("candidate assessment criteria do not match the exact contract")
        object.__setattr__(self, "criteria", criteria)
        disposition = _require_text(self.disposition, "candidate disposition")
        if disposition not in ASSESSMENT_DISPOSITIONS:
            raise ValueError(f"unsupported candidate disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        reasons = tuple(_require_text(item, "candidate reason") for item in self.reasons)
        if not reasons:
            raise ValueError("candidate assessments require explicit reasons")
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(
            self, "valid_trials", _nonnegative_int(self.valid_trials, "valid trials")
        )
        object.__setattr__(
            self,
            "invalid_trials",
            _nonnegative_int(self.invalid_trials, "invalid trials"),
        )
        from .policy import _assessment_projection

        expected_projection = _assessment_projection(self.batch, self.risk_policy)
        supplied_projection = (
            criteria,
            self.disposition,
            reasons,
            self.valid_trials,
            self.invalid_trials,
        )
        if supplied_projection != expected_projection:
            raise ValueError("candidate assessment is not the exact policy-derived projection")
        expected_lineage = (
            self.batch.ref,
            self.risk_policy.ref,
            *(item.ref for item in criteria),
        )
        if _refs(self.lineage, "candidate assessment lineage") != expected_lineage:
            raise ValueError("candidate assessment lineage is incomplete")
        super().__post_init__()

    @property
    def candidate_ref(self) -> RecordRef:
        return self.batch.candidate.ref


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RankedCandidate(SemanticRecord):
    """Transparent non-dominated rank and pairwise dominance provenance."""

    RECORD_TYPE: ClassVar[str] = "ranked_candidate"

    assessment: CandidateAssessment
    rank: int
    dominated_by: tuple[RecordRef, ...]
    dominates: tuple[RecordRef, ...]

    def __post_init__(self) -> None:
        if type(self.assessment) is not CandidateAssessment:
            raise TypeError("ranked candidates require a CandidateAssessment")
        rank = _nonnegative_int(self.rank, "candidate rank")
        if rank == 0:
            raise ValueError("candidate rank must be positive")
        object.__setattr__(self, "rank", rank)
        dominated_by = _refs(self.dominated_by, "dominating candidate references")
        dominates = _refs(self.dominates, "dominated candidate references")
        if self.assessment.candidate_ref in {*dominated_by, *dominates}:
            raise ValueError("a candidate cannot dominate itself")
        object.__setattr__(self, "dominated_by", dominated_by)
        object.__setattr__(self, "dominates", dominates)
        expected_lineage = (self.assessment.ref, *dominated_by, *dominates)
        if _refs(self.lineage, "candidate ranking lineage") != expected_lineage:
            raise ValueError("candidate ranking lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelectionDecision(SemanticRecord):
    """Exact selected candidate, Pareto set, or valid none-accepted outcome."""

    RECORD_TYPE: ClassVar[str] = "selection_decision"

    selection_id: str
    contract: EvaluationContract
    risk_policy: RiskPolicy
    assessments: tuple[CandidateAssessment, ...]
    rankings: tuple[RankedCandidate, ...]
    disposition: str
    selected: tuple[RecordRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "selection_id", _require_text(self.selection_id, "selection id"))
        if type(self.contract) is not EvaluationContract:
            raise TypeError("selection decisions require an EvaluationContract")
        if type(self.risk_policy) is not RiskPolicy:
            raise TypeError("selection decisions require a RiskPolicy")
        assessments = tuple(self.assessments)
        if any(type(item) is not CandidateAssessment for item in assessments):
            raise TypeError("selection decisions require CandidateAssessment values")
        if not assessments:
            raise ValueError("selection decisions require candidate assessments")
        if len({item.candidate_ref for item in assessments}) != len(assessments):
            raise ValueError("selection candidates must be unique")
        if assessments != tuple(sorted(assessments, key=lambda item: item.candidate_ref.root)):
            raise ValueError("selection assessments must use canonical candidate-root order")
        if any(item.batch.contract != self.contract for item in assessments):
            raise ValueError("parallel candidates must use one exact evaluation contract")
        if any(item.risk_policy != self.risk_policy for item in assessments):
            raise ValueError("parallel candidates must use one exact risk policy")
        object.__setattr__(self, "assessments", assessments)
        rankings = tuple(self.rankings)
        if any(type(item) is not RankedCandidate for item in rankings):
            raise TypeError("selection decisions require RankedCandidate values")
        if {item.assessment.ref for item in rankings} != {
            item.ref for item in assessments if item.disposition == "accepted"
        }:
            raise ValueError("rankings must cover exactly the accepted candidates")
        object.__setattr__(self, "rankings", rankings)
        disposition = _require_text(self.disposition, "selection disposition")
        if disposition not in SELECTION_DISPOSITIONS:
            raise ValueError(f"unsupported selection disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        selected = _refs(self.selected, "selected candidate references")
        accepted_refs = {
            item.candidate_ref for item in assessments if item.disposition == "accepted"
        }
        if not set(selected).issubset(accepted_refs):
            raise ValueError("only accepted candidate assessments may be selected")
        if disposition == "none-accepted" and (selected or rankings):
            raise ValueError("none-accepted decisions cannot select or rank candidates")
        if disposition == "selected" and len(selected) != 1:
            raise ValueError("selected decisions require exactly one candidate")
        if disposition == "pareto" and len(selected) < 2:
            raise ValueError("Pareto decisions require at least two candidates")
        from .policy import _selection_projection

        expected_rankings, expected_selected, expected_disposition = _selection_projection(
            assessments
        )
        if (
            rankings != expected_rankings
            or selected != expected_selected
            or disposition != expected_disposition
        ):
            raise ValueError("selection decision is not the exact policy-derived projection")
        object.__setattr__(self, "selected", selected)
        expected_lineage = (
            self.contract.ref,
            self.risk_policy.ref,
            *(item.ref for item in assessments),
            *(item.ref for item in rankings),
            *selected,
        )
        if _refs(self.lineage, "selection decision lineage") != expected_lineage:
            raise ValueError("selection decision lineage is incomplete")
        super().__post_init__()
