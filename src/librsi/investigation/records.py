"""Canonical records for bounded, evidence-driven investigation workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, cast

from ..epistemics import EVIDENCE_RELATIONSHIPS, EpistemicPolicy
from ..identity import FrozenMap
from ..records import (
    BeliefState,
    Evidence,
    EvidenceRef,
    ExperimentSpec,
    Hypothesis,
    Question,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    register_record_type,
)
from ..runtime import ActionResult, Run, RunBudget

INVESTIGATION_MODES = frozenset({"sequential", "parallel"})
INVESTIGATION_BRANCH_STATUSES = frozenset({"active", "supported", "rejected", "retired"})
INVESTIGATION_RETIREMENT_REASONS = frozenset(
    {
        "evidence-unavailable",
        "experiment-budget",
        "redesign-budget",
        "runtime-failure",
        "no-action",
    }
)
INVESTIGATION_BATCH_DISPOSITIONS = frozenset({"collected", "unavailable"})
INVESTIGATION_DISPOSITIONS = frozenset(
    {"answered", "partially-answered", "inconclusive", "exhausted"}
)
INVESTIGATION_STOP_REASONS = frozenset(
    {
        "sufficient",
        "experiment-budget",
        "no-viable-hypotheses",
        "evidence-unavailable",
        "runtime-failure",
    }
)


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _nonnegative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _positive_int(value: int, label: str) -> int:
    result = _nonnegative_int(value, label)
    if result == 0:
        raise ValueError(f"{label} must be positive")
    return result


def _refs(value: Sequence[RecordRef], label: str) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of RecordRef values")
    result = tuple(value)
    if any(not isinstance(item, RecordRef) for item in result):
        raise TypeError(f"{label} must contain RecordRef values")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must be unique")
    return result


def _evidence_refs(
    value: Sequence[EvidenceRef | RecordRef],
    label: str,
) -> tuple[EvidenceRef, ...]:
    refs = _refs(value, label)
    evidence_refs: list[EvidenceRef] = []
    for item in refs:
        if isinstance(item, EvidenceRef):
            evidence_refs.append(item)
        elif item.record_type == "evidence":
            evidence_refs.append(EvidenceRef(item.root))
        else:
            raise TypeError(f"{label} must contain EvidenceRef values")
    return tuple(sorted(evidence_refs, key=lambda item: item.root))


def _initial_belief(
    hypothesis: Hypothesis,
    target_snapshot: TargetSnapshot | None,
) -> BeliefState:
    return BeliefState(
        subject_ref=hypothesis.ref,
        status="proposed",
        confidence=0.5,
        target_snapshot=target_snapshot,
    )


def _canonical_belief(
    hypothesis: Hypothesis,
    evidence: Sequence[Evidence],
    target_snapshot: TargetSnapshot | None,
) -> BeliefState:
    items = tuple(sorted(evidence, key=lambda item: item.root))
    if not items:
        return _initial_belief(hypothesis, target_snapshot)
    return EpistemicPolicy().aggregate(
        subject=hypothesis,
        evidence=items,
        prior=_initial_belief(hypothesis, target_snapshot),
        current_snapshot=target_snapshot,
    )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InvestigationRequest(SemanticRecord):
    """One exact question, search posture, and bounded epistemic budget."""

    RECORD_TYPE: ClassVar[str] = "investigation_request"

    investigation_id: str
    question: Question
    target_snapshot: TargetSnapshot | None = None
    initial_hypotheses: tuple[Hypothesis, ...] = ()
    portfolio_mode: str = "parallel"
    max_hypotheses: int = 4
    max_experiments: int = 6
    max_redesigns_per_hypothesis: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "investigation_id",
            _require_text(self.investigation_id, "investigation id"),
        )
        if not isinstance(self.question, Question):
            raise TypeError("investigation requests require a Question")
        if self.question.target is None:
            if self.target_snapshot is not None:
                raise ValueError("unbound questions cannot use a target snapshot")
        elif not isinstance(self.target_snapshot, TargetSnapshot):
            raise ValueError("target-bound investigations require a current TargetSnapshot")
        elif self.target_snapshot.target != self.question.target:
            raise ValueError("investigation target snapshot does not match the question")

        mode = _require_text(self.portfolio_mode, "investigation portfolio mode")
        if mode not in INVESTIGATION_MODES:
            raise ValueError(f"unsupported investigation portfolio mode: {mode}")
        object.__setattr__(self, "portfolio_mode", mode)
        maximum = _positive_int(self.max_hypotheses, "maximum hypotheses")
        if maximum < 2:
            raise ValueError("investigations require room for competing hypotheses")
        object.__setattr__(self, "max_hypotheses", maximum)
        object.__setattr__(
            self,
            "max_experiments",
            _positive_int(self.max_experiments, "maximum experiments"),
        )
        object.__setattr__(
            self,
            "max_redesigns_per_hypothesis",
            _nonnegative_int(
                self.max_redesigns_per_hypothesis,
                "maximum redesigns per hypothesis",
            ),
        )

        hypotheses = tuple(self.initial_hypotheses)
        if any(not isinstance(item, Hypothesis) for item in hypotheses):
            raise TypeError("initial investigation hypotheses must be Hypothesis records")
        if hypotheses and len(hypotheses) < 2:
            raise ValueError("initial investigations require competing hypotheses")
        if len(hypotheses) > maximum:
            raise ValueError("initial hypotheses exceed the declared hypothesis budget")
        if len({item.ref for item in hypotheses}) != len(hypotheses):
            raise ValueError("initial investigation hypotheses must be unique")
        for hypothesis in hypotheses:
            if hypothesis.target != self.question.target:
                raise ValueError("initial hypothesis target does not match the question")
            if self.question.ref not in hypothesis.source_refs:
                raise ValueError("initial hypotheses must cite the exact question")
            if not hypothesis.predictions:
                raise ValueError("investigation hypotheses require falsifiable predictions")
            if hypothesis.status != "proposed":
                raise ValueError("initial hypotheses must remain unvalidated proposals")
        object.__setattr__(self, "initial_hypotheses", hypotheses)

        expected_lineage = (
            self.question.ref,
            *(() if self.target_snapshot is None else (self.target_snapshot.ref,)),
            *(item.ref for item in hypotheses),
        )
        if _refs(self.lineage, "investigation request lineage") != expected_lineage:
            raise ValueError(
                "investigation request lineage must retain its question, snapshot, and seeds"
            )
        super().__post_init__()

    @classmethod
    def for_question(
        cls,
        *,
        investigation_id: str,
        question: Question,
        target_snapshot: TargetSnapshot | None = None,
        initial_hypotheses: Sequence[Hypothesis] = (),
        portfolio_mode: str = "parallel",
        max_hypotheses: int = 4,
        max_experiments: int = 6,
        max_redesigns_per_hypothesis: int = 1,
        metadata: Mapping[str, Any] | None = None,
    ) -> InvestigationRequest:
        if not isinstance(question, Question):
            raise TypeError("investigation requests require a Question")
        hypotheses = tuple(initial_hypotheses)
        lineage = (
            question.ref,
            *(() if target_snapshot is None else (target_snapshot.ref,)),
            *(item.ref for item in hypotheses),
        )
        return cls(
            investigation_id=investigation_id,
            question=question,
            target_snapshot=target_snapshot,
            initial_hypotheses=hypotheses,
            portfolio_mode=portfolio_mode,
            max_hypotheses=max_hypotheses,
            max_experiments=max_experiments,
            max_redesigns_per_hypothesis=max_redesigns_per_hypothesis,
            lineage=lineage,
            metadata=FrozenMap(metadata),
        )

    def canonical_run(self) -> Run:
        generation_actions = 0 if self.initial_hypotheses else 1
        maximum_actions = generation_actions + (2 * self.max_experiments)
        return Run(
            run_id=self.investigation_id,
            intent=self.question.ref,
            target_snapshot=self.target_snapshot,
            budget=RunBudget(
                max_actions=maximum_actions,
                max_failures=maximum_actions,
                max_retries=0,
            ),
            lineage=(self.ref,),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InvestigationBranch(SemanticRecord):
    """One hypothesis lane with canonical belief, experiments, and evidence origin."""

    RECORD_TYPE: ClassVar[str] = "investigation_branch"

    investigation: InvestigationRequest
    branch_id: str
    hypothesis: Hypothesis
    belief: BeliefState
    experiments: tuple[ExperimentSpec, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    reused_evidence_refs: tuple[EvidenceRef, ...] = ()
    gathered_evidence_refs: tuple[EvidenceRef, ...] = ()
    status: str = "active"
    retired_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.investigation, InvestigationRequest):
            raise TypeError("investigation branches require their exact request")
        object.__setattr__(self, "branch_id", _require_text(self.branch_id, "branch id"))
        if not isinstance(self.hypothesis, Hypothesis):
            raise TypeError("investigation branches require a Hypothesis")
        if self.hypothesis.target != self.investigation.question.target:
            raise ValueError("investigation branch hypothesis target has drifted")
        if self.investigation.question.ref not in self.hypothesis.source_refs:
            raise ValueError("investigation branch hypothesis does not cite the question")
        if not self.hypothesis.predictions:
            raise ValueError("investigation branch hypothesis is not falsifiable")
        if not isinstance(self.belief, BeliefState):
            raise TypeError("investigation branches require a BeliefState")

        experiments = tuple(self.experiments)
        if any(not isinstance(item, ExperimentSpec) for item in experiments):
            raise TypeError("investigation branch experiments must be ExperimentSpec records")
        if len({item.ref for item in experiments}) != len(experiments):
            raise ValueError("investigation branch experiments must be unique")
        for experiment in experiments:
            if experiment.kind != "investigation":
                raise ValueError("investigation branches require investigation experiments")
            if experiment.target_snapshot != self.investigation.target_snapshot:
                raise ValueError("investigation experiment currentness has drifted")
            if self.hypothesis.ref not in experiment.lineage:
                raise ValueError("investigation experiment does not cite its hypothesis")
        object.__setattr__(self, "experiments", experiments)

        raw_evidence = tuple(self.evidence)
        if any(not isinstance(item, Evidence) for item in raw_evidence):
            raise TypeError("investigation branch evidence must contain Evidence records")
        evidence = tuple(sorted(raw_evidence, key=lambda item: item.root))
        if len({item.ref for item in evidence}) != len(evidence):
            raise ValueError("investigation branch evidence must be unique")
        refs = {EvidenceRef.from_evidence(item) for item in evidence}
        reused = _evidence_refs(
            self.reused_evidence_refs,
            "investigation reused evidence references",
        )
        gathered = _evidence_refs(
            self.gathered_evidence_refs,
            "investigation gathered evidence references",
        )
        if set(reused) & set(gathered) or set((*reused, *gathered)) != refs:
            raise ValueError("investigation evidence origins must exactly partition evidence")
        experiment_refs = {item.ref for item in experiments}
        for item in evidence:
            reference = EvidenceRef.from_evidence(item)
            if item.subject_refs != (self.hypothesis.ref,):
                raise ValueError("investigation evidence leaked between hypotheses")
            if not item.source_refs:
                raise ValueError("investigation evidence requires exact provenance")
            if reference in set(gathered) and (
                len(item.source_refs) != 1 or item.source_refs[0] not in experiment_refs
            ):
                raise ValueError("investigation evidence must cite one exact experiment")
            if item.target_snapshot != self.investigation.target_snapshot:
                raise ValueError("investigation evidence currentness has drifted")
            if item.evidence_type not in EVIDENCE_RELATIONSHIPS:
                raise ValueError("investigation evidence relationship is unsupported")
            if item.weight is None:
                raise ValueError("investigation evidence requires an explicit weight")
        object.__setattr__(self, "evidence", evidence)

        expected_belief = _canonical_belief(
            self.hypothesis,
            evidence,
            self.investigation.target_snapshot,
        )
        if self.belief != expected_belief:
            raise ValueError("investigation branch belief is not canonically evidence-derived")

        object.__setattr__(self, "reused_evidence_refs", reused)
        object.__setattr__(self, "gathered_evidence_refs", gathered)

        status = _require_text(self.status, "investigation branch status")
        if status not in INVESTIGATION_BRANCH_STATUSES:
            raise ValueError(f"unsupported investigation branch status: {status}")
        expected_status = (
            "supported"
            if self.belief.status == "supported"
            else "rejected"
            if self.belief.status == "rejected"
            else "retired"
            if self.retired_reason is not None
            else "active"
        )
        if status != expected_status:
            raise ValueError("investigation branch status is unsupported by its evidence")
        object.__setattr__(self, "status", status)
        if self.retired_reason is not None:
            if status != "retired":
                raise ValueError(
                    "nonretired investigation branches cannot carry a retirement reason"
                )
            raw_reason = self.retired_reason
            reason = _require_text(raw_reason, "branch retirement reason")
            if reason not in INVESTIGATION_RETIREMENT_REASONS:
                raise ValueError(f"unsupported branch retirement reason: {reason}")
            object.__setattr__(self, "retired_reason", reason)

        expected_lineage = (
            self.investigation.ref,
            self.hypothesis.ref,
            self.belief.ref,
            *(item.ref for item in experiments),
            *(item.ref for item in evidence),
        )
        if _refs(self.lineage, "investigation branch lineage") != expected_lineage:
            raise ValueError("investigation branch lineage is incomplete")
        super().__post_init__()

    @property
    def redesign_count(self) -> int:
        return max(0, len(self.experiments) - 1)


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InvestigationFrontier(SemanticRecord):
    """Complete ordered branch roster and the one branch selected for work."""

    RECORD_TYPE: ClassVar[str] = "investigation_frontier"

    investigation: InvestigationRequest
    branches: tuple[InvestigationBranch, ...]
    selected_branch_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.investigation, InvestigationRequest):
            raise TypeError("investigation frontiers require an InvestigationRequest")
        branches = tuple(self.branches)
        if any(not isinstance(item, InvestigationBranch) for item in branches):
            raise TypeError("investigation frontiers require InvestigationBranch records")
        if any(item.investigation != self.investigation for item in branches):
            raise ValueError("investigation frontier branches belong to another request")
        if len({item.branch_id for item in branches}) != len(branches):
            raise ValueError("investigation frontier branch ids must be unique")
        if len({item.ref for item in branches}) != len(branches):
            raise ValueError("investigation frontier branches must be unique")
        if len({item.hypothesis.ref for item in branches}) != len(branches):
            raise ValueError("investigation frontier hypotheses must be unique")
        if len(branches) > self.investigation.max_hypotheses:
            raise ValueError("investigation frontier exceeds its hypothesis budget")
        if branches and len(branches) < 2:
            raise ValueError("investigation frontiers require competing hypothesis branches")
        seeds = self.investigation.initial_hypotheses
        if branches and seeds and tuple(item.hypothesis for item in branches) != seeds:
            raise ValueError("investigation frontier does not contain its complete seed roster")
        if not branches and seeds:
            raise ValueError("seeded investigations cannot use a generation frontier")
        object.__setattr__(self, "branches", branches)

        selected = self.selected_branch_id
        if not branches:
            if selected is not None:
                raise ValueError("an empty investigation frontier cannot select a branch")
        else:
            if type(selected) is not str or not selected:
                raise ValueError("a populated investigation frontier must select one branch")
            branch = next((item for item in branches if item.branch_id == selected), None)
            if branch is None:
                raise ValueError("investigation frontier selection is outside its branch roster")
            if branch.status != "active":
                raise ValueError("investigation frontier must select an active branch")

        expected_lineage = (self.investigation.ref, *(item.ref for item in branches))
        if _refs(self.lineage, "investigation frontier lineage") != expected_lineage:
            raise ValueError("investigation frontier lineage is incomplete")
        super().__post_init__()

    @classmethod
    def for_hypothesis_generation(
        cls,
        investigation: InvestigationRequest,
    ) -> InvestigationFrontier:
        if not isinstance(investigation, InvestigationRequest):
            raise TypeError("hypothesis generation requires an InvestigationRequest")
        return cls(investigation=investigation, branches=(), lineage=(investigation.ref,))

    @classmethod
    def for_branch(
        cls,
        *,
        investigation: InvestigationRequest,
        branches: Sequence[InvestigationBranch],
        selected_branch_id: str,
    ) -> InvestigationFrontier:
        items = tuple(branches)
        return cls(
            investigation=investigation,
            branches=items,
            selected_branch_id=selected_branch_id,
            lineage=(investigation.ref, *(item.ref for item in items)),
        )

    @property
    def selected_branch(self) -> InvestigationBranch | None:
        selected = self.selected_branch_id
        if selected is None:
            return None
        return next(item for item in self.branches if item.branch_id == selected)


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InvestigationExperimentRequest(SemanticRecord):
    """Exact experiment request bound to the complete current branch frontier."""

    RECORD_TYPE: ClassVar[str] = "investigation_experiment_request"

    frontier: InvestigationFrontier
    experiment: ExperimentSpec
    sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.frontier, InvestigationFrontier):
            raise TypeError("investigation experiment requests require an exact frontier")
        branch = self.frontier.selected_branch
        if branch is None:
            raise ValueError("investigation experiment requests require a selected branch")
        if not isinstance(self.experiment, ExperimentSpec):
            raise TypeError("investigation experiment requests require an ExperimentSpec")
        if not branch.experiments or branch.experiments[-1] != self.experiment:
            raise ValueError("investigation experiment request is not for the branch frontier")
        object.__setattr__(
            self,
            "sequence",
            _positive_int(self.sequence, "investigation experiment sequence"),
        )
        expected_lineage = (
            self.frontier.ref,
            *self.frontier.lineage,
            branch.hypothesis.ref,
            self.experiment.ref,
        )
        if _refs(self.lineage, "investigation experiment request lineage") != expected_lineage:
            raise ValueError("investigation experiment request lineage is incomplete")
        super().__post_init__()

    @classmethod
    def for_branch(
        cls,
        *,
        branches: Sequence[InvestigationBranch],
        branch: InvestigationBranch,
        sequence: int,
    ) -> InvestigationExperimentRequest:
        if not isinstance(branch, InvestigationBranch) or not branch.experiments:
            raise TypeError("investigation experiment requests require a designed branch")
        frontier = InvestigationFrontier.for_branch(
            investigation=branch.investigation,
            branches=branches,
            selected_branch_id=branch.branch_id,
        )
        return cls.for_frontier(frontier=frontier, sequence=sequence)

    @classmethod
    def for_frontier(
        cls,
        *,
        frontier: InvestigationFrontier,
        sequence: int,
    ) -> InvestigationExperimentRequest:
        if not isinstance(frontier, InvestigationFrontier):
            raise TypeError("investigation experiment requests require an exact frontier")
        branch = frontier.selected_branch
        if branch is None or not branch.experiments:
            raise TypeError("investigation experiment requests require a designed branch")
        experiment = branch.experiments[-1]
        return cls(
            frontier=frontier,
            experiment=experiment,
            sequence=sequence,
            lineage=(
                frontier.ref,
                *frontier.lineage,
                branch.hypothesis.ref,
                experiment.ref,
            ),
        )

    @property
    def investigation(self) -> InvestigationRequest:
        return self.frontier.investigation

    @property
    def branch(self) -> InvestigationBranch:
        branch = self.frontier.selected_branch
        if branch is None:  # pragma: no cover - constructor invariant
            raise RuntimeError("investigation experiment request lost its selected branch")
        return branch


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InvestigationEvidenceBatch(SemanticRecord):
    """Evidence for one exact experiment frontier, or explicit unavailability."""

    RECORD_TYPE: ClassVar[str] = "investigation_evidence_batch"

    request: InvestigationExperimentRequest
    disposition: str
    evidence: tuple[Evidence, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, InvestigationExperimentRequest):
            raise TypeError("investigation evidence batches require their exact request")
        disposition = _require_text(self.disposition, "investigation evidence disposition")
        if disposition not in INVESTIGATION_BATCH_DISPOSITIONS:
            raise ValueError(f"unsupported investigation evidence disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        raw = tuple(self.evidence)
        if any(not isinstance(item, Evidence) for item in raw):
            raise TypeError("investigation evidence batches must contain Evidence records")
        evidence = tuple(sorted(raw, key=lambda item: item.root))
        if len({item.ref for item in evidence}) != len(evidence):
            raise ValueError("investigation evidence batches must contain unique evidence")
        branch = self.request.branch
        for item in evidence:
            if item.subject_refs != (branch.hypothesis.ref,):
                raise ValueError("investigation evidence leaked between hypotheses")
            if item.source_refs != (self.request.experiment.ref,):
                raise ValueError("investigation evidence does not cite the exact experiment")
            if item.target_snapshot != self.request.investigation.target_snapshot:
                raise ValueError("investigation evidence is stale or target-mismatched")
            if item.evidence_type not in EVIDENCE_RELATIONSHIPS:
                raise ValueError("investigation evidence relationship is unsupported")
            if item.weight is None:
                raise ValueError("investigation evidence requires an explicit weight")
            _canonical_belief(
                branch.hypothesis,
                (item,),
                self.request.investigation.target_snapshot,
            )
        object.__setattr__(self, "evidence", evidence)
        if disposition == "collected":
            if not evidence:
                raise ValueError("collected investigation batches cannot be empty")
            if self.reason is not None:
                raise ValueError("collected investigation batches cannot contain a reason")
        else:
            if evidence:
                raise ValueError("unavailable investigation batches cannot contain evidence")
            object.__setattr__(
                self,
                "reason",
                _require_text(
                    cast(str, self.reason),
                    "unavailable investigation reason",
                ),
            )
        expected_lineage = (
            self.request.ref,
            *self.request.lineage,
            *(item.ref for item in evidence),
        )
        if _refs(self.lineage, "investigation evidence batch lineage") != expected_lineage:
            raise ValueError("investigation evidence batch lineage is incomplete")
        super().__post_init__()

    @classmethod
    def collected(
        cls,
        *,
        request: InvestigationExperimentRequest,
        evidence: Sequence[Evidence],
    ) -> InvestigationEvidenceBatch:
        items = tuple(sorted(evidence, key=lambda item: item.root))
        return cls(
            request=request,
            disposition="collected",
            evidence=items,
            lineage=(request.ref, *request.lineage, *(item.ref for item in items)),
        )

    @classmethod
    def unavailable(
        cls,
        *,
        request: InvestigationExperimentRequest,
        reason: str,
    ) -> InvestigationEvidenceBatch:
        return cls(
            request=request,
            disposition="unavailable",
            reason=reason,
            lineage=(request.ref, *request.lineage),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InvestigationFinding(SemanticRecord):
    """A supported hypothesis projected without narrative synthesis."""

    RECORD_TYPE: ClassVar[str] = "investigation_finding"

    branch: InvestigationBranch
    statement: str
    evidence_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.branch, InvestigationBranch):
            raise TypeError("investigation findings require an InvestigationBranch")
        if self.branch.status != "supported":
            raise ValueError("investigation findings require a supported branch")
        statement = _require_text(self.statement, "investigation finding statement")
        if statement != self.branch.hypothesis.statement:
            raise ValueError("investigation findings cannot synthesize a new conclusion")
        object.__setattr__(self, "statement", statement)
        expected_refs = tuple(EvidenceRef.from_evidence(item) for item in self.branch.evidence)
        if _evidence_refs(self.evidence_refs, "investigation finding evidence") != expected_refs:
            raise ValueError("investigation finding must cite the exact branch evidence")
        if not expected_refs:
            raise ValueError("investigation findings require supporting evidence")
        expected_lineage = (
            self.branch.ref,
            self.branch.hypothesis.ref,
            self.branch.belief.ref,
            *expected_refs,
        )
        if _refs(self.lineage, "investigation finding lineage") != expected_lineage:
            raise ValueError("investigation finding lineage is incomplete")
        super().__post_init__()

    @classmethod
    def from_branch(cls, branch: InvestigationBranch) -> InvestigationFinding:
        if not isinstance(branch, InvestigationBranch):
            raise TypeError("investigation findings require an InvestigationBranch")
        refs = tuple(EvidenceRef.from_evidence(item) for item in branch.evidence)
        return cls(
            branch=branch,
            statement=branch.hypothesis.statement,
            evidence_refs=refs,
            lineage=(branch.ref, branch.hypothesis.ref, branch.belief.ref, *refs),
        )


def investigation_unresolved(branches: Sequence[InvestigationBranch]) -> tuple[str, ...]:
    items = tuple(branches)
    if not items:
        return ("hypothesis generation did not complete",)
    unresolved = tuple(
        f"{branch.hypothesis.statement}: {branch.retired_reason}"
        for branch in items
        if branch.status == "retired" and branch.retired_reason is not None
    )
    if not any(branch.status == "supported" for branch in items) and all(
        branch.status == "rejected" for branch in items
    ):
        return ("all proposed hypotheses were contradicted",)
    return unresolved


def _investigation_stop_reason(
    branches: Sequence[InvestigationBranch],
    failure_result: ActionResult | None,
) -> str:
    if failure_result is not None:
        return "runtime-failure"
    items = tuple(branches)
    if any(item.status == "supported" for item in items):
        return "sufficient"
    reasons = {item.retired_reason for item in items if item.retired_reason is not None}
    if "experiment-budget" in reasons:
        return "experiment-budget"
    if "evidence-unavailable" in reasons:
        return "evidence-unavailable"
    return "no-viable-hypotheses"


@register_record_type
@dataclass(frozen=True, kw_only=True)
class InvestigationResult(SemanticRecord):
    """Evidence-bound answer and explicit unresolved alternatives for one question."""

    RECORD_TYPE: ClassVar[str] = "investigation_result"

    investigation: InvestigationRequest
    run: RecordRef
    disposition: str
    stop_reason: str
    branches: tuple[InvestigationBranch, ...]
    findings: tuple[InvestigationFinding, ...]
    evidence: tuple[Evidence, ...]
    unresolved: tuple[str, ...] = ()
    failure_result: ActionResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.investigation, InvestigationRequest):
            raise TypeError("investigation results require an InvestigationRequest")
        expected_run = self.investigation.canonical_run().ref
        if not isinstance(self.run, RecordRef) or self.run != expected_run:
            raise ValueError("investigation result does not cite the canonical Run")
        failure_result = self.failure_result
        failure_lineage: tuple[RecordRef, ...] = ()
        if failure_result is not None:
            if not isinstance(failure_result, ActionResult):
                raise TypeError("investigation runtime failure must be an ActionResult")
            failure = failure_result.failure
            if (
                failure_result.disposition == "succeeded"
                or failure is None
                or failure_result.action.run != expected_run
                or failure_result.action.kind
                not in {"investigation-reason", "investigation-experiment"}
            ):
                raise ValueError(
                    "investigation runtime failure must be an exact failed workflow result"
                )
            failure_lineage = (failure_result.ref, failure.ref)
        object.__setattr__(self, "failure_result", failure_result)
        branches = tuple(self.branches)
        if len(branches) < 2 and failure_result is None:
            raise ValueError("investigation results require competing hypothesis branches")
        if any(not isinstance(item, InvestigationBranch) for item in branches):
            raise TypeError("investigation results require InvestigationBranch records")
        if any(item.investigation != self.investigation for item in branches):
            raise ValueError("investigation result branches belong to another request")
        if len({item.branch_id for item in branches}) != len(branches):
            raise ValueError("investigation result branch ids must be unique")
        if any(item.status == "active" for item in branches):
            raise ValueError("investigation results cannot retain active branches")
        object.__setattr__(self, "branches", branches)

        if failure_result is not None:
            from .actions import (
                _investigation_reasoning_context,
                investigation_experiment_request_from_action,
            )
            from .policy import InvestigationPolicy

            if failure_result.action.kind == "investigation-reason":
                failure_investigation, failure_frontier, _, _ = _investigation_reasoning_context(
                    failure_result.action
                )
            else:
                experiment_request = investigation_experiment_request_from_action(
                    failure_result.action
                )
                failure_investigation = experiment_request.investigation
                failure_frontier = experiment_request.frontier
            if failure_investigation != self.investigation:
                raise ValueError("investigation runtime failure belongs to another request")
            expected_branches = InvestigationPolicy().settle(
                self.investigation,
                failure_frontier.branches,
                reason="runtime-failure",
            )
            if branches != expected_branches:
                raise ValueError(
                    "investigation runtime failure does not settle its complete exact frontier"
                )

        stop_reason = _require_text(self.stop_reason, "investigation stop reason")
        if stop_reason not in INVESTIGATION_STOP_REASONS:
            raise ValueError(f"unsupported investigation stop reason: {stop_reason}")
        expected_stop_reason = _investigation_stop_reason(branches, failure_result)
        if stop_reason != expected_stop_reason:
            raise ValueError("investigation stop reason is unsupported by its exact state")
        object.__setattr__(self, "stop_reason", stop_reason)

        expected_findings = tuple(
            InvestigationFinding.from_branch(branch)
            for branch in branches
            if branch.status == "supported"
        )
        findings = tuple(self.findings)
        if findings != expected_findings:
            raise ValueError("investigation findings are not the exact supported branches")
        object.__setattr__(self, "findings", findings)

        expected_evidence = tuple(
            item
            for _, item in sorted(
                {item.root: item for branch in branches for item in branch.evidence}.items()
            )
        )
        evidence = tuple(self.evidence)
        if evidence != expected_evidence:
            raise ValueError("investigation result evidence does not match its branches")
        object.__setattr__(self, "evidence", evidence)

        expected_disposition = (
            "partially-answered"
            if findings and any(branch.status == "retired" for branch in branches)
            else "answered"
            if findings
            else "exhausted"
            if stop_reason == "experiment-budget"
            else "inconclusive"
        )
        disposition = _require_text(self.disposition, "investigation disposition")
        if disposition not in INVESTIGATION_DISPOSITIONS:
            raise ValueError(f"unsupported investigation disposition: {disposition}")
        if disposition != expected_disposition:
            raise ValueError("investigation disposition is unsupported by its branches")
        object.__setattr__(self, "disposition", disposition)

        expected_unresolved = investigation_unresolved(branches)
        unresolved = tuple(
            _require_text(item, "investigation unresolved item") for item in self.unresolved
        )
        if unresolved != expected_unresolved:
            raise ValueError("investigation unresolved items have drifted from its branches")
        object.__setattr__(self, "unresolved", unresolved)

        expected_lineage = (
            self.investigation.ref,
            expected_run,
            *(branch.ref for branch in branches),
            *(finding.ref for finding in findings),
            *(item.ref for item in evidence),
            *failure_lineage,
        )
        if _refs(self.lineage, "investigation result lineage") != expected_lineage:
            raise ValueError("investigation result lineage is incomplete")
        super().__post_init__()
