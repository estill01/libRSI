"""Canonical records for authorized application, verification, and rollback."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from ..comparison import CandidateAssessment, RiskPolicy
from ..governance import ApplicationGovernanceAuthority
from ..improvement import ApplicationHandoff, ImprovementResult
from ..intent import EvaluationContract
from ..interventions import CandidateSnapshot
from ..records import (
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    register_record_type,
    registered_record_class,
)
from ..runtime import Action, Run, RunBudget, RunState, RuntimeFailure

APPLY_CANDIDATE_ACTION_KIND = "apply-selected-candidate"
VERIFY_APPLICATION_ACTION_KIND = "verify-applied-target"
ROLLBACK_APPLICATION_ACTION_KIND = "rollback-applied-target"
APPLICATION_ACTION_KINDS = frozenset(
    {
        APPLY_CANDIDATE_ACTION_KIND,
        VERIFY_APPLICATION_ACTION_KIND,
        ROLLBACK_APPLICATION_ACTION_KIND,
    }
)
APPLICATION_VERIFICATION_DISPOSITIONS = frozenset({"verified", "rejected", "unavailable"})
APPLICATION_RESULT_DISPOSITIONS = frozenset(
    {"application-disabled", "verified", "rolled-back", "application-failed", "rollback-failed"}
)


def _text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _failures(
    values: Sequence[RuntimeFailure],
) -> tuple[RuntimeFailure, ...]:
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
class ApplicationRequest(SemanticRecord):
    """Explicit request to retain or authoritatively apply one improvement result."""

    RECORD_TYPE: ClassVar[str] = "application_request"

    application_id: str
    improvement: ImprovementResult
    current_snapshot: TargetSnapshot
    apply: bool = False
    governance_authority: ApplicationGovernanceAuthority | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "application_id",
            _text(self.application_id, "application id"),
        )
        if type(self.improvement) is not ImprovementResult:
            raise TypeError("application requests require an ImprovementResult")
        if self.improvement.disposition != "improved" or self.improvement.handoff is None:
            raise ValueError("application requires an improved result with an explicit handoff")
        if type(self.current_snapshot) is not TargetSnapshot:
            raise TypeError("application requests require an exact current TargetSnapshot")
        if self.current_snapshot != self.improvement.handoff.current_snapshot:
            raise ValueError("application request is stale for the improvement handoff")
        if type(self.apply) is not bool:
            raise TypeError("apply must be a boolean")
        if self.apply and len(self.improvement.handoff.selection.selected) != 1:
            raise ValueError("authoritative application requires exactly one selected candidate")
        requirement = self.handoff.governance_requirement
        if not self.apply and self.governance_authority is not None:
            raise ValueError("disabled application cannot carry governance authority")
        if requirement is None and self.governance_authority is not None:
            raise ValueError("ordinary application cannot claim unconfigured governance")
        if self.apply and requirement is not None:
            authority = self.governance_authority
            if not isinstance(authority, ApplicationGovernanceAuthority):
                raise ValueError(
                    "governed application requires an exact matching governance authority"
                )
            try:
                authority_class = registered_record_class(requirement.authority_record_type)
            except ValueError as error:
                raise ValueError(
                    "application governance authority is not a canonical record"
                ) from error
            if type(authority) is not authority_class:
                raise ValueError("application governance authority is not a canonical record")
            if (
                authority.requirement != requirement
                or authority.candidate != self.candidate
                or authority.current_snapshot != self.current_snapshot
            ):
                raise ValueError(
                    "application governance authority does not match the exact handoff"
                )
        expected = (
            self.improvement.ref,
            self.improvement.handoff.ref,
            self.current_snapshot.ref,
            *((self.governance_authority.ref,) if self.governance_authority is not None else ()),
            *self.improvement.handoff.selection.selected,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("application request lineage is incomplete")
        super().__post_init__()

    def identity_data(self) -> dict[str, object]:
        data = super().identity_data()
        if self.governance_authority is None:
            data.pop("governance_authority")
        return data

    @property
    def handoff(self) -> ApplicationHandoff:
        handoff = self.improvement.handoff
        assert isinstance(handoff, ApplicationHandoff)
        return handoff

    @property
    def candidate(self) -> CandidateSnapshot | None:
        selected = self.handoff.selection.selected
        if len(selected) != 1:
            return None
        matches = tuple(
            assessment.batch.candidate
            for assessment in self.handoff.selection.assessments
            if assessment.candidate_ref == selected[0]
        )
        if len(matches) != 1:  # pragma: no cover - SelectionDecision invariant
            raise RuntimeError("selected application candidate disappeared")
        return matches[0]

    def canonical_run(self) -> Run:
        return Run(
            run_id=f"{self.application_id}:application",
            intent=self.ref,
            target_snapshot=self.current_snapshot,
            target_transition_authority=self.ref,
            budget=RunBudget(max_actions=3, max_failures=3, max_retries=0),
            lineage=(
                self.ref,
                self.improvement.ref,
                self.handoff.ref,
                *(
                    (self.governance_authority.ref,)
                    if self.governance_authority is not None
                    else ()
                ),
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        application_id: str,
        improvement: ImprovementResult,
        current_snapshot: TargetSnapshot,
        apply: bool = False,
        governance_authority: ApplicationGovernanceAuthority | None = None,
    ) -> ApplicationRequest:
        if type(improvement) is not ImprovementResult or improvement.handoff is None:
            raise ValueError("application requires an improved result with an explicit handoff")
        return cls(
            application_id=application_id,
            improvement=improvement,
            current_snapshot=current_snapshot,
            apply=apply,
            governance_authority=governance_authority,
            lineage=(
                improvement.ref,
                improvement.handoff.ref,
                current_snapshot.ref,
                *((governance_authority.ref,) if governance_authority is not None else ()),
                *improvement.handoff.selection.selected,
            ),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ApplicationCommand(SemanticRecord):
    """Portable, bounded host input for one selected-candidate application."""

    RECORD_TYPE: ClassVar[str] = "application_command"

    application_id: str
    request: RecordRef
    improvement: RecordRef
    handoff: RecordRef
    contract: EvaluationContract
    risk_policy: RiskPolicy
    candidate: CandidateSnapshot
    prior_snapshot: TargetSnapshot
    governance_authority: RecordRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "application_id",
            _text(self.application_id, "application id"),
        )
        expected_types = (
            (self.request, "application_request"),
            (self.improvement, "improvement_result"),
            (self.handoff, "application_handoff"),
        )
        if any(
            not isinstance(ref, RecordRef) or ref.record_type != record_type
            for ref, record_type in expected_types
        ):
            raise TypeError("application command references have the wrong record type")
        if type(self.candidate) is not CandidateSnapshot:
            raise TypeError("application commands require an exact CandidateSnapshot")
        if type(self.contract) is not EvaluationContract:
            raise TypeError("application commands require the exact EvaluationContract")
        if type(self.risk_policy) is not RiskPolicy:
            raise TypeError("application commands require the exact RiskPolicy")
        if type(self.prior_snapshot) is not TargetSnapshot:
            raise TypeError("application commands require an exact prior TargetSnapshot")
        if self.governance_authority is not None and not isinstance(
            self.governance_authority, RecordRef
        ):
            raise TypeError("application command governance authority must be a RecordRef")
        expected = (
            self.request,
            self.improvement,
            self.handoff,
            self.contract.ref,
            self.risk_policy.ref,
            self.candidate.ref,
            self.prior_snapshot.ref,
            *((self.governance_authority,) if self.governance_authority is not None else ()),
        )
        if tuple(self.lineage) != expected:
            raise ValueError("application command lineage is incomplete")
        super().__post_init__()

    def identity_data(self) -> dict[str, object]:
        data = super().identity_data()
        if self.governance_authority is None:
            data.pop("governance_authority")
        return data

    @classmethod
    def from_request(cls, request: ApplicationRequest) -> ApplicationCommand:
        if type(request) is not ApplicationRequest or not request.apply:
            raise ValueError("application commands require an enabled ApplicationRequest")
        candidate = request.candidate
        if candidate is None:  # pragma: no cover - ApplicationRequest invariant
            raise RuntimeError("enabled application lost its selected candidate")
        return cls(
            application_id=request.application_id,
            request=request.ref,
            improvement=request.improvement.ref,
            handoff=request.handoff.ref,
            contract=request.improvement.request.contract,
            risk_policy=request.improvement.request.risk_policy,
            candidate=candidate,
            prior_snapshot=request.current_snapshot,
            governance_authority=(
                request.governance_authority.ref
                if request.governance_authority is not None
                else None
            ),
            lineage=(
                request.ref,
                request.improvement.ref,
                request.handoff.ref,
                request.improvement.request.contract.ref,
                request.improvement.request.risk_policy.ref,
                candidate.ref,
                request.current_snapshot.ref,
                *(
                    (request.governance_authority.ref,)
                    if request.governance_authority is not None
                    else ()
                ),
            ),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ApplicationReceipt(SemanticRecord):
    """Applier-reported actual target state, distinct from the proposed candidate."""

    RECORD_TYPE: ClassVar[str] = "application_receipt"

    request: RecordRef
    action: Action
    candidate: CandidateSnapshot
    prior_snapshot: TargetSnapshot
    produced_snapshot: TargetSnapshot

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request, RecordRef)
            or self.request.record_type != "application_request"
        ):
            raise TypeError("application receipts require an ApplicationRequest reference")
        if type(self.produced_snapshot) is not TargetSnapshot:
            raise TypeError("application receipts require the actual produced TargetSnapshot")
        if self.produced_snapshot.target != self.prior_snapshot.target:
            raise ValueError("application produced a snapshot for another target")
        from .actions import application_command_from_action

        command = application_command_from_action(self.action)
        if (
            command.request != self.request
            or command.candidate != self.candidate
            or command.prior_snapshot != self.prior_snapshot
        ):
            raise ValueError("application receipt does not answer the exact command")
        expected = (
            self.request,
            self.action.ref,
            self.candidate.ref,
            self.prior_snapshot.ref,
            self.produced_snapshot.ref,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("application receipt lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ApplicationVerification(SemanticRecord):
    """Verifier report over the exact state actually produced by application."""

    RECORD_TYPE: ClassVar[str] = "application_verification"

    request: RecordRef
    application: ApplicationReceipt
    action: Action
    observed_snapshot: TargetSnapshot
    disposition: str
    reason: str
    assessment: CandidateAssessment | None = None
    operational_failure: RuntimeFailure | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request, RecordRef)
            or self.request.record_type != "application_request"
        ):
            raise TypeError("application verification requires an ApplicationRequest reference")
        if (
            type(self.application) is not ApplicationReceipt
            or self.application.request != self.request
        ):
            raise ValueError("application verification requires the exact application receipt")
        if self.observed_snapshot != self.application.produced_snapshot:
            raise ValueError("verification must observe the exact produced target snapshot")
        from .actions import application_command_from_action, make_verify_action

        command = application_command_from_action(self.application.action)
        if self.operational_failure is not None:
            if type(self.operational_failure) is not RuntimeFailure:
                raise ValueError("unavailable verification requires an operational failure")
            expected_disposition = "unavailable"
            expected_reason = self.operational_failure.message
            if self.assessment is not None:
                raise ValueError("unavailable verification cannot contain an assessment")
        else:
            if type(self.assessment) is not CandidateAssessment:
                raise ValueError("conclusive verification requires a candidate assessment")
            if (
                self.assessment.batch.contract != command.contract
                or self.assessment.risk_policy != command.risk_policy
                or self.assessment.batch.candidate.request != command.candidate.request
                or self.assessment.batch.candidate.snapshot != self.observed_snapshot
            ):
                raise ValueError(
                    "verification assessment does not evaluate the exact applied target"
                )
            expected_disposition = (
                "verified" if self.assessment.disposition == "accepted" else "rejected"
            )
            expected_reason = "; ".join(self.assessment.reasons)
        disposition = _text(self.disposition, "verification disposition")
        if disposition not in APPLICATION_VERIFICATION_DISPOSITIONS:
            raise ValueError(f"unsupported application verification disposition: {disposition}")
        if disposition != expected_disposition:
            raise ValueError("verification disposition is not assessment-derived")
        object.__setattr__(self, "disposition", disposition)
        reason = _text(self.reason, "verification reason")
        if reason != expected_reason:
            raise ValueError("verification reason is not assessment-derived")
        object.__setattr__(self, "reason", reason)

        if self.action != make_verify_action(self.application):
            raise ValueError("application verification does not cite the canonical verify action")
        expected = (
            self.request,
            self.application.ref,
            self.action.ref,
            self.observed_snapshot.ref,
            *((self.assessment.ref,) if self.assessment is not None else ()),
            *((self.operational_failure.ref,) if self.operational_failure is not None else ()),
        )
        if tuple(self.lineage) != expected:
            raise ValueError("application verification lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class RollbackReceipt(SemanticRecord):
    """Applier-reported exact restoration of the pre-application target state."""

    RECORD_TYPE: ClassVar[str] = "rollback_receipt"

    request: RecordRef
    application: ApplicationReceipt
    verification: ApplicationVerification
    action: Action
    restored_snapshot: TargetSnapshot

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request, RecordRef)
            or self.request.record_type != "application_request"
        ):
            raise TypeError("rollback receipts require an ApplicationRequest reference")
        if (
            type(self.application) is not ApplicationReceipt
            or self.application.request != self.request
        ):
            raise ValueError("rollback receipt requires the exact application receipt")
        if (
            type(self.verification) is not ApplicationVerification
            or self.verification.application != self.application
            or self.verification.disposition == "verified"
        ):
            raise ValueError("rollback requires an exact nonverified application report")
        if self.restored_snapshot != self.application.prior_snapshot:
            raise ValueError("rollback must restore the exact prior target snapshot")
        from .actions import make_rollback_action

        if self.action != make_rollback_action(self.application, self.verification):
            raise ValueError("rollback receipt does not cite the canonical rollback action")
        expected = (
            self.request,
            self.application.ref,
            self.verification.ref,
            self.action.ref,
            self.restored_snapshot.ref,
        )
        if tuple(self.lineage) != expected:
            raise ValueError("rollback receipt lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class ApplicationResult(SemanticRecord):
    """Terminal authoritative application posture with operational failures separated."""

    RECORD_TYPE: ClassVar[str] = "application_result"

    request: ApplicationRequest
    disposition: str
    settled_state: RunState
    handoff: ApplicationHandoff
    application: ApplicationReceipt | None = None
    verification: ApplicationVerification | None = None
    rollback: RollbackReceipt | None = None
    operational_failures: tuple[RuntimeFailure, ...] = ()
    authoritative_snapshot: TargetSnapshot | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not ApplicationRequest:
            raise TypeError("application results require an ApplicationRequest")
        disposition = _text(self.disposition, "application result disposition")
        if disposition not in APPLICATION_RESULT_DISPOSITIONS:
            raise ValueError(f"unsupported application result disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        if type(self.settled_state) is not RunState:
            raise TypeError("application results require their exact settled RunState")
        if self.handoff != self.request.handoff:
            raise ValueError("application result handoff differs from the improvement selection")
        failures = _failures(self.operational_failures)
        object.__setattr__(self, "operational_failures", failures)
        from .replay import application_projection, replay_application_state

        settled, projection = replay_application_state(self.request, self.settled_state)
        if settled != self.settled_state:
            raise ValueError("application result state is not an exact settled frontier")
        expected = application_projection(self.request, settled, projection)
        supplied = (
            disposition,
            self.application,
            self.verification,
            self.rollback,
            failures,
            self.authoritative_snapshot,
        )
        if supplied != expected:
            raise ValueError("application result is not the exact runtime-derived projection")
        expected_lineage = (
            self.request.ref,
            self.settled_state.ref,
            self.handoff.ref,
            *((self.application.ref,) if self.application is not None else ()),
            *((self.verification.ref,) if self.verification is not None else ()),
            *((self.rollback.ref,) if self.rollback is not None else ()),
            *(item.ref for item in failures),
            *(
                (self.authoritative_snapshot.ref,)
                if self.authoritative_snapshot is not None
                else ()
            ),
        )
        if tuple(self.lineage) != expected_lineage:
            raise ValueError("application result lineage is incomplete")
        super().__post_init__()
