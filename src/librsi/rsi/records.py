"""Canonical records for explicit, governed self-change."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from ..application import ApplicationResult
from ..comparison import CandidateAssessment, CandidateReview, CandidateTrialBatch, RiskPolicy
from ..governance import ApplicationGovernanceAuthority
from ..improvement import ImprovementResult
from ..intent import EvaluationContract
from ..interventions import CandidateSnapshot
from ..records import (
    Evaluation,
    ExperimentSpec,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    register_record_type,
)
from ..runtime import Action, Run, RunBudget, RunState, RuntimeFailure

SELF_CHANGE_CLASSES = frozenset(
    {
        "reasoner",
        "experiment-planner",
        "search-policy",
        "aggregation-policy",
        "selection-policy",
        "resource-allocation",
        "host-machinery",
        "governance-policy",
    }
)
SELF_CHANGE_RISK_TIERS = frozenset({"moderate", "high", "critical"})
SELF_CHANGE_EVALUATION_STAGES = frozenset({"historical", "forward-shadow"})
SELF_CHANGE_GATE_DISPOSITIONS = frozenset({"passed", "rejected", "inconclusive"})
SELF_CHANGE_GOVERNANCE_DISPOSITIONS = frozenset({"accepted", "rejected", "governance-failed"})
RSI_RESULT_DISPOSITIONS = frozenset(
    {
        "activation-disabled",
        "governance-rejected",
        "governance-failed",
        "verified",
        "rolled-back",
        "application-failed",
        "rollback-failed",
    }
)


def _text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _failures(values: Sequence[RuntimeFailure]) -> tuple[RuntimeFailure, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError("operational failures must be a sequence")
    items = tuple(values)
    if any(type(item) is not RuntimeFailure for item in items):
        raise TypeError("operational failures must contain RuntimeFailure records")
    if len({item.ref for item in items}) != len(items):
        raise ValueError("operational failures must be unique")
    return items


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelfChangeRule(SemanticRecord):
    """One configured self-change class and its visible risk tier."""

    RECORD_TYPE: ClassVar[str] = "self_change_rule"

    change_class: str
    risk_tier: str

    def __post_init__(self) -> None:
        change_class = _text(self.change_class, "self-change class")
        if change_class not in SELF_CHANGE_CLASSES:
            raise ValueError(f"unsupported self-change class: {change_class}")
        object.__setattr__(self, "change_class", change_class)
        risk_tier = _text(self.risk_tier, "self-change risk tier")
        if risk_tier not in SELF_CHANGE_RISK_TIERS:
            raise ValueError(f"unsupported self-change risk tier: {risk_tier}")
        object.__setattr__(self, "risk_tier", risk_tier)
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelfChangeGovernancePolicy(SemanticRecord):
    """Fail-closed class configuration and evidence risk policy."""

    RECORD_TYPE: ClassVar[str] = "self_change_governance_policy"

    policy_id: str
    rules: tuple[SelfChangeRule, ...]
    risk_policy: RiskPolicy

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "governance policy id"))
        rules = tuple(self.rules)
        if not rules or any(type(item) is not SelfChangeRule for item in rules):
            raise TypeError("self-change governance requires typed class rules")
        if len({item.change_class for item in rules}) != len(rules):
            raise ValueError("self-change governance rules must have unique classes")
        if rules != tuple(sorted(rules, key=lambda item: item.change_class)):
            raise ValueError("self-change governance rules must use canonical class order")
        object.__setattr__(self, "rules", rules)
        if type(self.risk_policy) is not RiskPolicy:
            raise TypeError("self-change governance requires an exact RiskPolicy")
        expected = (*(item.ref for item in rules), self.risk_policy.ref)
        if tuple(self.lineage) != expected:
            raise ValueError("self-change governance policy lineage is incomplete")
        super().__post_init__()

    @classmethod
    def strict(
        cls,
        *,
        policy_id: str = "strict-self-change",
        risk_policy: RiskPolicy | None = None,
    ) -> SelfChangeGovernancePolicy:
        tiers = {
            "reasoner": "moderate",
            "experiment-planner": "high",
            "search-policy": "high",
            "aggregation-policy": "critical",
            "selection-policy": "critical",
            "resource-allocation": "high",
            "host-machinery": "critical",
            "governance-policy": "critical",
        }
        rules = tuple(
            SelfChangeRule(change_class=name, risk_tier=tiers[name]) for name in sorted(tiers)
        )
        risk = (
            RiskPolicy(policy_id=f"{policy_id}:evaluation", confidence_multiplier=1.0)
            if risk_policy is None
            else risk_policy
        )
        return cls(
            policy_id=policy_id,
            rules=rules,
            risk_policy=risk,
            lineage=(*(item.ref for item in rules), risk.ref),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class MetaTargetDeclaration(SemanticRecord):
    """Explicit declaration that an exact target snapshot affects future improvement."""

    RECORD_TYPE: ClassVar[str] = "meta_target_declaration"

    declaration_id: str
    target_snapshot: TargetSnapshot
    change_classes: tuple[str, ...]
    candidate_author_id: str
    rollback_snapshot: TargetSnapshot | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "declaration_id",
            _text(self.declaration_id, "meta-target declaration id"),
        )
        if type(self.target_snapshot) is not TargetSnapshot:
            raise TypeError("meta-target declarations require an exact TargetSnapshot")
        classes = tuple(_text(item, "self-change class") for item in self.change_classes)
        if not classes or any(item not in SELF_CHANGE_CLASSES for item in classes):
            raise ValueError("meta-target declarations require supported self-change classes")
        if len(set(classes)) != len(classes):
            raise ValueError("meta-target self-change classes must be unique")
        if classes != tuple(sorted(classes)):
            raise ValueError("meta-target self-change classes must use canonical order")
        object.__setattr__(self, "change_classes", classes)
        object.__setattr__(
            self,
            "candidate_author_id",
            _text(self.candidate_author_id, "candidate author id"),
        )
        if self.rollback_snapshot is not None and self.rollback_snapshot != self.target_snapshot:
            raise ValueError("meta-target rollback must restore the exact declared baseline")
        if tuple(self.lineage) != (self.target_snapshot.ref,):
            raise ValueError("meta-target declaration lineage is incomplete")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        declaration_id: str,
        target_snapshot: TargetSnapshot,
        change_classes: Sequence[str],
        candidate_author_id: str,
        rollback_supported: bool = True,
    ) -> MetaTargetDeclaration:
        if type(rollback_supported) is not bool:
            raise TypeError("rollback support must be a boolean")
        return cls(
            declaration_id=declaration_id,
            target_snapshot=target_snapshot,
            change_classes=tuple(sorted(change_classes)),
            candidate_author_id=candidate_author_id,
            rollback_snapshot=target_snapshot if rollback_supported else None,
            lineage=(target_snapshot.ref,),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RSIRequest(SemanticRecord):
    """One ordinary improvement result under explicit self-change governance."""

    RECORD_TYPE: ClassVar[str] = "rsi_request"

    rsi_id: str
    declaration: MetaTargetDeclaration
    improvement: ImprovementResult
    governance: SelfChangeGovernancePolicy
    requested_by: str
    activate: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rsi_id", _text(self.rsi_id, "RSI request id"))
        if type(self.declaration) is not MetaTargetDeclaration:
            raise TypeError("RSI requests require an explicit MetaTargetDeclaration")
        if type(self.improvement) is not ImprovementResult:
            raise TypeError("RSI requests require an ordinary ImprovementResult")
        if self.improvement.disposition != "improved" or self.improvement.handoff is None:
            raise ValueError("RSI requests require an accepted ordinary improvement")
        if len(self.improvement.handoff.selection.selected) != 1:
            raise ValueError("RSI activation requires exactly one selected candidate")
        if self.declaration.target_snapshot != self.improvement.request.baseline:
            raise ValueError("meta-target declaration does not match the improvement baseline")
        if type(self.governance) is not SelfChangeGovernancePolicy:
            raise TypeError("RSI requests require a SelfChangeGovernancePolicy")
        configured = {item.change_class for item in self.governance.rules}
        missing = set(self.declaration.change_classes) - configured
        if missing:
            raise ValueError(f"self-change classes are not governed: {sorted(missing)}")
        from .policy import SelfChangePolicy

        if self.improvement.request.governance_requirement != SelfChangePolicy.requirement(
            self.declaration,
            self.governance,
        ):
            raise ValueError(
                "self-change improvement is not identity-bound to its governance requirement"
            )
        object.__setattr__(self, "requested_by", _text(self.requested_by, "RSI requester id"))
        if type(self.activate) is not bool:
            raise TypeError("RSI activation must be a boolean")
        expected = (
            self.declaration.ref,
            self.improvement.ref,
            self.governance.ref,
            self.governance.risk_policy.ref,
            self.candidate.ref,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("RSI request lineage is incomplete")
        super().__post_init__()

    @property
    def candidate(self) -> CandidateSnapshot:
        handoff = self.improvement.handoff
        assert handoff is not None
        selected = handoff.selection.selected
        matches = tuple(
            item.batch.candidate
            for item in handoff.selection.assessments
            if item.candidate_ref == selected[0]
        )
        if len(matches) != 1:  # pragma: no cover - ImprovementResult invariant
            raise RuntimeError("selected RSI candidate disappeared")
        return matches[0]

    def canonical_run(self) -> Run:
        return Run(
            run_id=f"{self.rsi_id}:governance",
            intent=self.ref,
            target_snapshot=self.declaration.target_snapshot,
            budget=RunBudget(max_actions=3, max_failures=1, max_retries=0),
            lineage=(self.ref, self.declaration.ref, self.improvement.ref, self.governance.ref),
        )

    @classmethod
    def create(
        cls,
        *,
        rsi_id: str,
        declaration: MetaTargetDeclaration,
        improvement: ImprovementResult,
        governance: SelfChangeGovernancePolicy,
        requested_by: str,
        activate: bool = False,
    ) -> RSIRequest:
        if type(improvement) is not ImprovementResult or improvement.handoff is None:
            raise ValueError("RSI requests require an accepted ordinary improvement")
        selected = improvement.handoff.selection.selected
        if len(selected) != 1:
            raise ValueError("RSI activation requires exactly one selected candidate")
        candidate = next(
            item.batch.candidate
            for item in improvement.handoff.selection.assessments
            if item.candidate_ref == selected[0]
        )
        return cls(
            rsi_id=rsi_id,
            declaration=declaration,
            improvement=improvement,
            governance=governance,
            requested_by=requested_by,
            activate=activate,
            lineage=(
                declaration.ref,
                improvement.ref,
                governance.ref,
                governance.risk_policy.ref,
                candidate.ref,
            ),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelfChangeEvaluationCommand(SemanticRecord):
    """Bounded host input for historical or forward-shadow evaluation."""

    RECORD_TYPE: ClassVar[str] = "self_change_evaluation_command"

    request: RecordRef
    stage: str
    contract: EvaluationContract
    risk_policy: RiskPolicy
    candidate: CandidateSnapshot
    baseline: TargetSnapshot
    predecessor: RecordRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, RecordRef) or self.request.record_type != "rsi_request":
            raise TypeError("self-change evaluation commands require an RSIRequest reference")
        stage = _text(self.stage, "self-change evaluation stage")
        if stage not in SELF_CHANGE_EVALUATION_STAGES:
            raise ValueError(f"unsupported self-change evaluation stage: {stage}")
        object.__setattr__(self, "stage", stage)
        if type(self.contract) is not EvaluationContract:
            raise TypeError("self-change evaluation requires an exact EvaluationContract")
        if type(self.risk_policy) is not RiskPolicy:
            raise TypeError("self-change evaluation requires an exact RiskPolicy")
        if type(self.candidate) is not CandidateSnapshot:
            raise TypeError("self-change evaluation requires an exact CandidateSnapshot")
        if type(self.baseline) is not TargetSnapshot:
            raise TypeError("self-change evaluation requires an exact baseline")
        if stage == "historical" and self.predecessor is not None:
            raise ValueError("historical evaluation cannot have a predecessor")
        if stage == "forward-shadow" and (
            not isinstance(self.predecessor, RecordRef)
            or self.predecessor.record_type != "self_change_evaluation"
        ):
            raise ValueError("forward-shadow evaluation requires exact historical evidence")
        if self.candidate.request.intervention.baseline != self.baseline:
            raise ValueError("self-change candidate does not derive from the exact baseline")
        expected = (
            self.request,
            self.contract.ref,
            self.risk_policy.ref,
            self.candidate.ref,
            self.baseline.ref,
            *((self.predecessor,) if self.predecessor is not None else ()),
        )
        if tuple(self.lineage) != expected:
            raise ValueError("self-change evaluation command lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelfChangeReviewCommand(SemanticRecord):
    """Bounded independent-review input over the exact forward-shadow result."""

    RECORD_TYPE: ClassVar[str] = "self_change_review_command"

    request: RecordRef
    forward_evaluation: RecordRef
    candidate: CandidateSnapshot
    experiment: ExperimentSpec
    evaluation: Evaluation
    candidate_author_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, RecordRef) or self.request.record_type != "rsi_request":
            raise TypeError("self-change review commands require an RSIRequest reference")
        if (
            not isinstance(self.forward_evaluation, RecordRef)
            or self.forward_evaluation.record_type != "self_change_evaluation"
        ):
            raise TypeError("self-change review requires a forward evaluation reference")
        if type(self.candidate) is not CandidateSnapshot:
            raise TypeError("self-change review requires an exact CandidateSnapshot")
        if type(self.experiment) is not ExperimentSpec or type(self.evaluation) is not Evaluation:
            raise TypeError("self-change review requires exact experiment and evaluation records")
        if (
            self.experiment.candidate_snapshot != self.candidate.snapshot
            or self.evaluation.subject_refs != (self.experiment.ref,)
        ):
            raise ValueError("self-change review inputs do not cover the exact candidate")
        object.__setattr__(
            self,
            "candidate_author_id",
            _text(self.candidate_author_id, "candidate author id"),
        )
        expected = (
            self.request,
            self.forward_evaluation,
            self.candidate.ref,
            self.experiment.ref,
            self.evaluation.ref,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("self-change review command lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelfChangeEvaluation(SemanticRecord):
    """Contract-derived gate over one exact self-change trial batch."""

    RECORD_TYPE: ClassVar[str] = "self_change_evaluation"

    request: RecordRef
    stage: str
    action: Action
    batch: CandidateTrialBatch
    assessment: CandidateAssessment
    disposition: str
    reason: str

    def __post_init__(self) -> None:
        from .actions import evaluation_command_from_action

        command = evaluation_command_from_action(self.action)
        if self.request != command.request or self.stage != command.stage:
            raise ValueError("self-change evaluation does not answer its exact command")
        if type(self.batch) is not CandidateTrialBatch:
            raise TypeError("self-change evaluations require a CandidateTrialBatch")
        from ..comparison import ComparativeSelectionPolicy

        expected_assessment = ComparativeSelectionPolicy.assess(
            self.batch,
            risk_policy=command.risk_policy,
        )
        if self.assessment != expected_assessment:
            raise ValueError("self-change assessment is not contract-derived")
        expected_disposition = {
            "accepted": "passed",
            "rejected": "rejected",
            "inconclusive": "inconclusive",
        }[self.assessment.disposition]
        if self.disposition != expected_disposition:
            raise ValueError("self-change gate disposition is not assessment-derived")
        if self.disposition not in SELF_CHANGE_GATE_DISPOSITIONS:
            raise ValueError("unsupported self-change gate disposition")
        expected_reason = "; ".join(self.assessment.reasons)
        if self.reason != expected_reason:
            raise ValueError("self-change gate reason is not assessment-derived")
        expected = (self.request, self.action.ref, self.batch.ref, self.assessment.ref)
        if tuple(self.lineage) != expected:
            raise ValueError("self-change evaluation lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelfChangeReview(SemanticRecord):
    """Independent actor decision over the exact forward-shadow evaluation."""

    RECORD_TYPE: ClassVar[str] = "self_change_review"

    request: RecordRef
    forward_evaluation: RecordRef
    action: Action
    review: CandidateReview
    disposition: str
    reason: str

    def __post_init__(self) -> None:
        from .actions import review_command_from_action

        command = review_command_from_action(self.action)
        if (
            self.request != command.request
            or self.forward_evaluation != command.forward_evaluation
            or type(self.review) is not CandidateReview
            or self.review.candidate != command.candidate
            or self.review.experiment != command.experiment
            or self.review.evaluation != command.evaluation
        ):
            raise ValueError("self-change review does not answer its exact command")
        from ..reviews import ReviewPolicy

        ReviewPolicy.require_independent_actor(
            author_id=command.candidate_author_id,
            reviewer_id=self.review.reviewer_id,
            subject="self-change candidate author",
        )
        if self.disposition != self.review.disposition:
            raise ValueError("self-change review disposition is not reviewer-derived")
        expected_reason = "; ".join(self.review.findings)
        if self.reason != expected_reason:
            raise ValueError("self-change review reason is not reviewer-derived")
        expected = (
            self.request,
            self.forward_evaluation,
            self.action.ref,
            self.review.ref,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("self-change review lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelfChangeGovernanceResult(SemanticRecord):
    """Replay-derived terminal result for the stronger self-change gates."""

    RECORD_TYPE: ClassVar[str] = "self_change_governance_result"

    request: RSIRequest
    disposition: str
    settled_state: RunState
    historical: SelfChangeEvaluation | None = None
    forward_shadow: SelfChangeEvaluation | None = None
    independent_review: SelfChangeReview | None = None
    operational_failures: tuple[RuntimeFailure, ...] = ()

    def __post_init__(self) -> None:
        if type(self.request) is not RSIRequest or type(self.settled_state) is not RunState:
            raise TypeError("self-change governance results require exact request and state")
        from .replay import governance_projection_fields, replay_governance_state

        settled, projection = replay_governance_state(self.request, self.settled_state)
        if settled != self.settled_state:
            raise ValueError("self-change governance result state is not settled")
        supplied = (
            self.disposition,
            self.historical,
            self.forward_shadow,
            self.independent_review,
            _failures(self.operational_failures),
        )
        if supplied != governance_projection_fields(self.request, settled, projection):
            raise ValueError("self-change governance result is not runtime-derived")
        if self.disposition not in SELF_CHANGE_GOVERNANCE_DISPOSITIONS:
            raise ValueError("unsupported self-change governance disposition")
        object.__setattr__(self, "operational_failures", supplied[-1])
        expected = (
            self.request.ref,
            self.settled_state.ref,
            *((self.historical.ref,) if self.historical is not None else ()),
            *((self.forward_shadow.ref,) if self.forward_shadow is not None else ()),
            *((self.independent_review.ref,) if self.independent_review is not None else ()),
            *(item.ref for item in self.operational_failures),
        )
        if tuple(self.lineage) != expected:
            raise ValueError("self-change governance result lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class SelfChangeApproval(ApplicationGovernanceAuthority):
    """Identity-bound authority produced only after every configured gate passes."""

    RECORD_TYPE: ClassVar[str] = "self_change_approval"

    request: RSIRequest
    governance: SelfChangeGovernanceResult
    rollback_snapshot: TargetSnapshot
    risk_tier: str

    def __post_init__(self) -> None:
        if type(self.request) is not RSIRequest or not self.request.activate:
            raise ValueError("self-change approval requires an activation-enabled RSI request")
        if (
            type(self.governance) is not SelfChangeGovernanceResult
            or self.governance.request != self.request
            or self.governance.disposition != "accepted"
        ):
            raise ValueError("self-change approval requires exact accepted governance")
        if self.candidate != self.request.candidate:
            raise ValueError("self-change approval names another candidate")
        if self.requirement != self.request.improvement.request.governance_requirement:
            raise ValueError("self-change approval names another governance requirement")
        if self.current_snapshot != self.request.declaration.target_snapshot:
            raise ValueError("self-change approval is stale for the governed target")
        if (
            self.request.declaration.rollback_snapshot is None
            or self.rollback_snapshot != self.request.declaration.rollback_snapshot
        ):
            raise ValueError("self-change approval requires the exact rollback baseline")
        from .policy import SelfChangePolicy

        if self.risk_tier != SelfChangePolicy.risk_tier(self.request):
            raise ValueError("self-change approval risk tier is not policy-derived")
        expected = (
            self.request.ref,
            self.governance.ref,
            self.requirement.ref,
            self.candidate.ref,
            self.rollback_snapshot.ref,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("self-change approval lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RSIResult(SemanticRecord):
    """Consumable self-change outcome composed from governance and application."""

    RECORD_TYPE: ClassVar[str] = "rsi_result"

    request: RSIRequest
    disposition: str
    governance: SelfChangeGovernanceResult
    approval: SelfChangeApproval | None = None
    application: ApplicationResult | None = None
    authoritative_snapshot: TargetSnapshot | None = None
    operational_failures: tuple[RuntimeFailure, ...] = ()

    def __post_init__(self) -> None:
        if type(self.request) is not RSIRequest:
            raise TypeError("RSI results require an RSIRequest")
        if (
            type(self.governance) is not SelfChangeGovernanceResult
            or self.governance.request != self.request
        ):
            raise ValueError("RSI results require exact governance")
        from .policy import SelfChangePolicy

        expected = SelfChangePolicy.result_fields(
            self.request,
            self.governance,
            approval=self.approval,
            application=self.application,
        )
        supplied = (
            self.disposition,
            self.approval,
            self.application,
            self.authoritative_snapshot,
            _failures(self.operational_failures),
        )
        if supplied != expected:
            raise ValueError("RSI result is not the exact governance/application projection")
        if self.disposition not in RSI_RESULT_DISPOSITIONS:
            raise ValueError("unsupported RSI result disposition")
        object.__setattr__(self, "operational_failures", supplied[-1])
        expected_lineage = (
            self.request.ref,
            self.governance.ref,
            *((self.approval.ref,) if self.approval is not None else ()),
            *((self.application.ref,) if self.application is not None else ()),
            *(
                (self.authoritative_snapshot.ref,)
                if self.authoritative_snapshot is not None
                else ()
            ),
            *(item.ref for item in self.operational_failures),
        )
        if tuple(self.lineage) != expected_lineage:
            raise ValueError("RSI result lineage is incomplete")
        super().__post_init__()
