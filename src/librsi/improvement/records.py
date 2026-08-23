"""Canonical records for bounded, evidence-driven improvement loops."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, TypeVar

from ..comparison import CandidateTrialBatch, RiskPolicy, SelectionDecision
from ..identity import FrozenMap
from ..intent import EvaluationContract, OperationalizationResult
from ..investigation import InvestigationResult
from ..records import (
    Hypothesis,
    Question,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    register_record_type,
)
from ..runtime import Run, RunBudget, RunState

IMPROVEMENT_ACTION_KIND = "improvement-cycle"
IMPROVEMENT_AUTHORITY = "proposal-only"
IMPROVEMENT_DISPOSITIONS = frozenset({"improved", "no-useful-improvement"})
SEARCH_DIRECTIONS = frozenset({"initial", "broaden", "narrow"})


def _text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    value = value.strip()
    if not value:
        raise ValueError(f"{label} is required")
    return value


def _positive(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


_RecordT = TypeVar("_RecordT", bound=SemanticRecord)


def _records(value: Sequence[_RecordT], kind: type[_RecordT], label: str) -> tuple[_RecordT, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    items = tuple(value)
    if any(type(item) is not kind for item in items):
        raise TypeError(f"{label} contains the wrong record type")
    if len({item.ref for item in items}) != len(items):
        raise ValueError(f"{label} must be unique")
    return items


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ImprovementBudget(SemanticRecord):
    """Visible iteration, experiment, retry, resource, and sufficiency limits."""

    RECORD_TYPE: ClassVar[str] = "improvement_budget"

    max_iterations: int = 3
    max_experiments: int = 12
    max_retries: int = 2
    max_resource_units: float = 100.0
    diminishing_return_patience: int = 2

    def __post_init__(self) -> None:
        for name in (
            "max_iterations",
            "max_experiments",
            "diminishing_return_patience",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise TypeError("max_retries must be an integer")
        if self.max_retries < 0:
            raise ValueError("max_retries must be nonnegative")
        if isinstance(self.max_resource_units, bool) or not isinstance(
            self.max_resource_units, (int, float)
        ):
            raise TypeError("max_resource_units must be numeric")
        units = float(self.max_resource_units)
        if units <= 0.0:
            raise ValueError("max_resource_units must be positive")
        object.__setattr__(self, "max_resource_units", units)
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ImprovementRequest(SemanticRecord):
    """One already-operationalized goal and its hypothesis-search envelope."""

    RECORD_TYPE: ClassVar[str] = "improvement_request"

    request_id: str
    operationalization: OperationalizationResult
    question: Question
    initial_hypotheses: tuple[Hypothesis, ...]
    risk_policy: RiskPolicy
    budget: ImprovementBudget = field(default_factory=ImprovementBudget)
    apply: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request id"))
        if type(self.operationalization) is not OperationalizationResult:
            raise TypeError("improvement requires an OperationalizationResult")
        if self.operationalization.disposition != "operationalized":
            raise ValueError("improvement requires a completed operationalization")
        contract = self.operationalization.contract
        if type(contract) is not EvaluationContract:
            raise ValueError("improvement requires an exact evaluation contract")
        if type(self.question) is not Question:
            raise TypeError("improvement requires a Question")
        if self.question.target != contract.baseline.snapshot.target:
            raise ValueError("improvement question does not match the contract target")
        hypotheses = _records(self.initial_hypotheses, Hypothesis, "initial hypotheses")
        if len(hypotheses) < 2:
            raise ValueError("improvement requires competing falsifiable hypotheses")
        if any(
            item.target != self.question.target
            or self.question.ref not in item.source_refs
            or not item.predictions
            for item in hypotheses
        ):
            raise ValueError("initial hypotheses must be falsifiable answers to the exact question")
        object.__setattr__(self, "initial_hypotheses", hypotheses)
        if type(self.risk_policy) is not RiskPolicy:
            raise TypeError("improvement requires a RiskPolicy")
        if type(self.budget) is not ImprovementBudget:
            raise TypeError("improvement requires an ImprovementBudget")
        if type(self.apply) is not bool:
            raise TypeError("apply must be a boolean")
        if self.apply:
            raise ValueError("improvement selection cannot authorize target application")
        expected = (
            self.operationalization.ref,
            contract.ref,
            self.question.ref,
            *(item.ref for item in hypotheses),
            self.risk_policy.ref,
            self.budget.ref,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("improvement request lineage is incomplete")
        super().__post_init__()

    @property
    def contract(self) -> EvaluationContract:
        contract = self.operationalization.contract
        assert isinstance(contract, EvaluationContract)
        return contract

    @property
    def baseline(self) -> TargetSnapshot:
        return self.contract.baseline.snapshot

    def canonical_run(self) -> Run:
        return Run(
            run_id=f"{self.request_id}:improvement",
            intent=self.ref,
            target_snapshot=self.baseline,
            budget=RunBudget(
                max_actions=self.budget.max_iterations + self.budget.max_retries,
                max_failures=self.budget.max_retries + 1,
                max_retries=self.budget.max_retries,
                resource_limits={"units": self.budget.max_resource_units},
            ),
            lineage=(self.ref, self.operationalization.ref),
        )

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        operationalization: OperationalizationResult,
        question: Question,
        initial_hypotheses: Sequence[Hypothesis],
        risk_policy: RiskPolicy,
        budget: ImprovementBudget | None = None,
    ) -> ImprovementRequest:
        budget = ImprovementBudget() if budget is None else budget
        hypotheses = tuple(initial_hypotheses)
        contract = operationalization.contract
        if not isinstance(contract, EvaluationContract):
            raise ValueError("improvement requires an exact evaluation contract")
        return cls(
            request_id=request_id,
            operationalization=operationalization,
            question=question,
            initial_hypotheses=hypotheses,
            risk_policy=risk_policy,
            budget=budget,
            lineage=(
                operationalization.ref,
                contract.ref,
                question.ref,
                *(item.ref for item in hypotheses),
                risk_policy.ref,
                budget.ref,
            ),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SearchDirective(SemanticRecord):
    """Policy-owned direction for the next hypothesis/intervention cycle."""

    RECORD_TYPE: ClassVar[str] = "improvement_search_directive"

    iteration: int
    direction: str
    reason: str
    previous_iteration: RecordRef | None = None

    def __post_init__(self) -> None:
        iteration = _positive(self.iteration, "iteration")
        object.__setattr__(self, "iteration", iteration)
        direction = _text(self.direction, "search direction")
        if direction not in SEARCH_DIRECTIONS:
            raise ValueError(f"unsupported search direction: {direction}")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "reason", _text(self.reason, "search reason"))
        if self.previous_iteration is not None and (
            not isinstance(self.previous_iteration, RecordRef)
            or self.previous_iteration.record_type != "improvement_iteration"
        ):
            raise TypeError("search directive predecessors must reference ImprovementIteration")
        if iteration == 1:
            if direction != "initial" or self.previous_iteration is not None:
                raise ValueError("the first search directive must be the initial frontier")
        elif direction == "initial" or self.previous_iteration is None:
            raise ValueError(
                "later search directives require a prior iteration and learned direction"
            )
        expected = () if self.previous_iteration is None else (self.previous_iteration,)
        if tuple(self.lineage) != expected:
            raise ValueError("search directive lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ImprovementCycleRequest(SemanticRecord):
    """Exact input frontier for one independently executable improvement cycle."""

    RECORD_TYPE: ClassVar[str] = "improvement_cycle_request"

    improvement: ImprovementRequest
    directive: SearchDirective
    remaining_experiments: int
    remaining_resource_units: float
    resource_units_per_attempt: float

    def __post_init__(self) -> None:
        if type(self.improvement) is not ImprovementRequest:
            raise TypeError("cycle requests require an ImprovementRequest")
        if type(self.directive) is not SearchDirective:
            raise TypeError("cycle requests require a SearchDirective")
        remaining = _positive(self.remaining_experiments, "remaining experiments")
        if remaining > self.improvement.budget.max_experiments:
            raise ValueError("cycle experiment allowance exceeds the improvement budget")
        object.__setattr__(self, "remaining_experiments", remaining)
        if isinstance(self.remaining_resource_units, bool) or not isinstance(
            self.remaining_resource_units, (int, float)
        ):
            raise TypeError("remaining resource units must be numeric")
        units = float(self.remaining_resource_units)
        if not math.isfinite(units) or units <= 0.0:
            raise ValueError("remaining resource units must be finite and positive")
        if units > self.improvement.budget.max_resource_units:
            raise ValueError("cycle resource allowance exceeds the improvement budget")
        object.__setattr__(self, "remaining_resource_units", units)
        if isinstance(self.resource_units_per_attempt, bool) or not isinstance(
            self.resource_units_per_attempt, (int, float)
        ):
            raise TypeError("per-attempt resource units must be numeric")
        per_attempt = float(self.resource_units_per_attempt)
        if not math.isfinite(per_attempt) or per_attempt <= 0.0 or per_attempt > units:
            raise ValueError(
                "per-attempt resource units must be finite, positive, and within remaining"
            )
        object.__setattr__(self, "resource_units_per_attempt", per_attempt)
        if tuple(self.lineage) != (self.improvement.ref, self.directive.ref):
            raise ValueError("cycle request lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ImprovementCycleProposal(SemanticRecord):
    """Untrusted but fully typed investigation-to-comparison cycle output."""

    RECORD_TYPE: ClassVar[str] = "improvement_cycle_proposal"

    request: ImprovementCycleRequest
    investigation: InvestigationResult
    batches: tuple[CandidateTrialBatch, ...]

    def __post_init__(self) -> None:
        if type(self.request) is not ImprovementCycleRequest:
            raise TypeError("cycle proposals require their exact request")
        if type(self.investigation) is not InvestigationResult:
            raise TypeError("cycle proposals require an InvestigationResult")
        batches = _records(self.batches, CandidateTrialBatch, "candidate trial batches")
        if not batches:
            raise ValueError("cycle proposals require at least one tested candidate")
        if self.experiment_count > self.request.remaining_experiments:
            raise ValueError("cycle proposal exceeds its experiment allowance")
        object.__setattr__(self, "batches", batches)
        expected = (self.request.ref, self.investigation.ref, *(item.ref for item in batches))
        if tuple(self.lineage) != expected:
            raise ValueError("cycle proposal lineage is incomplete")
        super().__post_init__()

    @property
    def experiment_count(self) -> int:
        investigation_experiments = {
            experiment.ref
            for branch in self.investigation.branches
            for experiment in branch.experiments
        }
        return len(investigation_experiments) + len(self.batches)

    @classmethod
    def create(
        cls,
        *,
        request: ImprovementCycleRequest,
        investigation: InvestigationResult,
        batches: Sequence[CandidateTrialBatch],
    ) -> ImprovementCycleProposal:
        items = tuple(batches)
        return cls(
            request=request,
            investigation=investigation,
            batches=items,
            lineage=(request.ref, investigation.ref, *(item.ref for item in items)),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ImprovementIteration(SemanticRecord):
    """Policy-owned interpretation of one cycle and its hypothesis-learning effect."""

    RECORD_TYPE: ClassVar[str] = "improvement_iteration"

    proposal: ImprovementCycleProposal
    selection: SelectionDecision
    next_direction: str
    previous_iteration: ImprovementIteration | None = None
    rejected_hypotheses: tuple[RecordRef, ...] = ()

    def __post_init__(self) -> None:
        if type(self.proposal) is not ImprovementCycleProposal:
            raise TypeError("improvement iterations require a cycle proposal")
        if type(self.selection) is not SelectionDecision:
            raise TypeError("improvement iterations require a SelectionDecision")
        from ..comparison import ComparativeSelectionPolicy
        from .policy import validate_cycle_sequence

        request = self.proposal.request.improvement
        previous = self.previous_iteration
        if previous is not None and type(previous) is not ImprovementIteration:
            raise TypeError("improvement iteration predecessors must be ImprovementIteration")
        if previous is not None and previous.proposal.request.improvement != request:
            raise ValueError("improvement iteration predecessor belongs to another request")
        expected_rejected = validate_cycle_sequence(self.proposal, previous)
        expected_selection = ComparativeSelectionPolicy.select(
            selection_id=(
                f"{request.request_id}:selection:{self.proposal.request.directive.iteration}"
            ),
            contract=request.contract,
            batches=self.proposal.batches,
            risk_policy=request.risk_policy,
        )
        if self.selection != expected_selection:
            raise ValueError("improvement selection is not derived from the exact cycle proposal")
        direction = _text(self.next_direction, "next direction")
        rejected = tuple(self.rejected_hypotheses)
        if any(
            not isinstance(item, RecordRef) or item.record_type != "hypothesis" for item in rejected
        ):
            raise TypeError("rejected hypotheses must reference Hypothesis records")
        expected_direction = (
            "stop"
            if self.selection.disposition != "none-accepted"
            else "narrow"
            if any(
                any(
                    criterion.criterion_kind == "objective" and criterion.disposition == "passed"
                    for criterion in assessment.criteria
                )
                for assessment in self.selection.assessments
            )
            else "broaden"
        )
        if rejected != expected_rejected or direction != expected_direction:
            raise ValueError("improvement learning is not the exact evidence-derived projection")
        object.__setattr__(self, "next_direction", direction)
        object.__setattr__(self, "rejected_hypotheses", rejected)
        expected = (
            self.proposal.ref,
            self.selection.ref,
            *((previous.ref,) if previous is not None else ()),
            *rejected,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("improvement iteration lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ApplicationHandoff(SemanticRecord):
    """Complete selection handoff with no application authority."""

    RECORD_TYPE: ClassVar[str] = "application_handoff"

    request: ImprovementRequest
    selection: SelectionDecision
    current_snapshot: TargetSnapshot
    apply: bool = False
    authority: str = IMPROVEMENT_AUTHORITY

    def __post_init__(self) -> None:
        if type(self.request) is not ImprovementRequest:
            raise TypeError("application handoff requires an ImprovementRequest")
        if type(self.selection) is not SelectionDecision or not self.selection.selected:
            raise ValueError("application handoff requires an accepted selection")
        if self.selection.contract != self.request.contract:
            raise ValueError("application handoff selection uses another contract")
        if self.current_snapshot != self.request.baseline:
            raise ValueError("application handoff currentness differs from the exact baseline")
        if self.apply is not False or self.authority != IMPROVEMENT_AUTHORITY:
            raise ValueError("improvement handoff cannot grant application authority")
        if tuple(self.lineage) != (
            self.request.ref,
            self.selection.ref,
            self.current_snapshot.ref,
            *self.selection.selected,
        ):
            raise ValueError("application handoff lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ImprovementResult(SemanticRecord):
    """Complete evidence-backed improvement or valid no-useful-improvement outcome."""

    RECORD_TYPE: ClassVar[str] = "improvement_result"

    request: ImprovementRequest
    disposition: str
    iterations: tuple[ImprovementIteration, ...]
    settled_state: RunState
    handoff: ApplicationHandoff | None = None
    stop_reason: str
    budget_usage: Mapping[str, float] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        if type(self.request) is not ImprovementRequest:
            raise TypeError("improvement results require an ImprovementRequest")
        disposition = _text(self.disposition, "improvement disposition")
        if disposition not in IMPROVEMENT_DISPOSITIONS:
            raise ValueError(f"unsupported improvement disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        iterations = _records(self.iterations, ImprovementIteration, "improvement iterations")
        if not iterations:
            raise ValueError("improvement results require at least one completed iteration")
        object.__setattr__(self, "iterations", iterations)
        if type(self.settled_state) is not RunState:
            raise TypeError("improvement results require their exact settled RunState")
        if (
            self.settled_state.run != self.request.canonical_run()
            or self.settled_state.status != "active"
            or self.settled_state.pending_actions
        ):
            raise ValueError("improvement result state is not a settled canonical frontier")
        from .replay import replay_improvement_state

        replay, derived = replay_improvement_state(self.request, self.settled_state)
        if replay != self.settled_state:  # pragma: no cover - canonical replay invariant
            raise RuntimeError("settled improvement replay returned another frontier")
        if iterations != derived:
            raise ValueError("improvement result iterations are not runtime and policy derived")
        if disposition == "improved":
            if type(self.handoff) is not ApplicationHandoff:
                raise ValueError("improved results require an application handoff")
            if iterations[-1].selection != self.handoff.selection:
                raise ValueError("application handoff must expose the terminal selection")
            canonical_handoff = ApplicationHandoff(
                request=self.request,
                selection=iterations[-1].selection,
                current_snapshot=self.request.baseline,
                lineage=(
                    self.request.ref,
                    iterations[-1].selection.ref,
                    self.request.baseline.ref,
                    *iterations[-1].selection.selected,
                ),
            )
            if self.handoff != canonical_handoff:
                raise ValueError("application handoff is not the exact result projection")
            if iterations[-1].selection.disposition == "none-accepted":
                raise ValueError("improvement cannot be claimed without an accepted candidate")
        elif self.handoff is not None:
            raise ValueError("no-improvement results cannot expose an application handoff")
        elif iterations[-1].selection.disposition != "none-accepted":
            raise ValueError("accepted selections cannot be downgraded to no improvement")
        stop_reason = _text(self.stop_reason, "stop reason")
        from .policy import improvement_stop_reason

        expected_stop_reason = improvement_stop_reason(
            self.request,
            iterations,
            resource_units=self.settled_state.resource_usage.get("units", 0.0),
        )
        if stop_reason != expected_stop_reason:
            raise ValueError("improvement result stop reason is not the exact policy projection")
        object.__setattr__(self, "stop_reason", stop_reason)
        usage = FrozenMap(self.budget_usage)
        if set(usage) != {"iterations", "experiments", "retries", "resource_units"}:
            raise ValueError("improvement result requires complete budget usage")
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            for value in usage.values()
        ):
            raise ValueError("improvement budget usage must be nonnegative numeric values")
        expected_experiments = sum(item.proposal.experiment_count for item in iterations)
        if usage["iterations"] != len(iterations) or usage["experiments"] != expected_experiments:
            raise ValueError("improvement iteration or experiment usage is not exact")
        if expected_experiments > self.request.budget.max_experiments:
            raise ValueError("improvement result exceeds its aggregate experiment budget")
        if set(self.settled_state.resource_usage) - {"units"}:
            raise ValueError("improvement result contains unauthorized resource dimensions")
        if usage["retries"] != self.settled_state.retry_count or usage[
            "resource_units"
        ] != self.settled_state.resource_usage.get("units", 0.0):
            raise ValueError("improvement retry or resource usage is not runtime derived")
        if (
            usage["retries"] > self.request.budget.max_retries
            or usage["resource_units"] > self.request.budget.max_resource_units
        ):
            raise ValueError("improvement result exceeds its retry or resource budget")
        object.__setattr__(self, "budget_usage", usage)
        expected = (
            self.request.ref,
            self.settled_state.ref,
            *(item.ref for item in iterations),
            *((self.handoff.ref,) if self.handoff is not None else ()),
        )
        if tuple(self.lineage) != expected:
            raise ValueError("improvement result lineage is incomplete")
        super().__post_init__()
