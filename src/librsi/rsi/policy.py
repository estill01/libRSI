"""Nonreplaceable activation, independence, currentness, and result policy."""

from __future__ import annotations

from ..application import ApplicationRequest, ApplicationResult
from ..governance import ApplicationGovernanceRequirement
from ..records import TargetSnapshot
from ..runtime import RunState, RuntimeFailure
from .records import (
    MetaTargetDeclaration,
    RSIRequest,
    RSIResult,
    SelfChangeApproval,
    SelfChangeGovernancePolicy,
    SelfChangeGovernanceResult,
)
from .replay import governance_projection_fields, replay_governance_state

_RISK_ORDER = {"moderate": 0, "high": 1, "critical": 2}


class SelfChangePolicy:
    """Own stronger self-change gates without replacing ordinary improvement."""

    @staticmethod
    def validate_request(request: RSIRequest) -> None:
        if type(request) is not RSIRequest:
            raise TypeError("self-change policy requires an RSIRequest")
        if request.declaration.target_snapshot != request.improvement.request.baseline:
            raise ValueError("self-change request does not retain the exact improvement baseline")
        if request.candidate.request.intervention.baseline != request.declaration.target_snapshot:
            raise ValueError("self-change candidate does not derive from the declared baseline")
        if request.activate and request.declaration.rollback_snapshot is None:
            raise ValueError("self-change activation requires exact rollback support")

    @staticmethod
    def risk_tier(request: RSIRequest) -> str:
        SelfChangePolicy.validate_request(request)
        by_class = {item.change_class: item.risk_tier for item in request.governance.rules}
        tiers = tuple(by_class[item] for item in request.declaration.change_classes)
        return max(tiers, key=_RISK_ORDER.__getitem__)

    @staticmethod
    def require_current(request: RSIRequest, current_snapshot: TargetSnapshot) -> None:
        if type(current_snapshot) is not TargetSnapshot:
            raise TypeError("self-change governance requires an explicit current snapshot")
        if current_snapshot != request.declaration.target_snapshot:
            raise ValueError("self-change target snapshot is stale")

    @staticmethod
    def governance_result(request: RSIRequest, state: RunState) -> SelfChangeGovernanceResult:
        settled, projection = replay_governance_state(request, state)
        disposition, historical, forward, review, failures = governance_projection_fields(
            request,
            settled,
            projection,
        )
        return SelfChangeGovernanceResult(
            request=request,
            disposition=disposition,
            settled_state=settled,
            historical=historical,
            forward_shadow=forward,
            independent_review=review,
            operational_failures=failures,
            lineage=(
                request.ref,
                settled.ref,
                *((historical.ref,) if historical is not None else ()),
                *((forward.ref,) if forward is not None else ()),
                *((review.ref,) if review is not None else ()),
                *(item.ref for item in failures),
            ),
        )

    @staticmethod
    def approval(
        request: RSIRequest,
        governance: SelfChangeGovernanceResult,
    ) -> SelfChangeApproval:
        SelfChangePolicy.validate_request(request)
        if not request.activate:
            raise ValueError("activation-disabled RSI requests cannot produce approval")
        if governance.request != request or governance.disposition != "accepted":
            raise ValueError("self-change activation requires accepted governance")
        rollback = request.declaration.rollback_snapshot
        if rollback is None:  # pragma: no cover - validate_request invariant
            raise RuntimeError("accepted activation lost rollback support")
        requirement = request.improvement.request.governance_requirement
        if type(requirement) is not ApplicationGovernanceRequirement:
            raise RuntimeError("accepted self-change lost its governance requirement")
        return SelfChangeApproval(
            requirement=requirement,
            request=request,
            governance=governance,
            candidate=request.candidate,
            current_snapshot=request.declaration.target_snapshot,
            rollback_snapshot=rollback,
            risk_tier=SelfChangePolicy.risk_tier(request),
            lineage=(
                request.ref,
                governance.ref,
                requirement.ref,
                request.candidate.ref,
                rollback.ref,
            ),
        )

    @staticmethod
    def application_request(
        approval: SelfChangeApproval,
        *,
        current_snapshot: TargetSnapshot,
    ) -> ApplicationRequest:
        if type(approval) is not SelfChangeApproval:
            raise TypeError("self-change application requires a SelfChangeApproval")
        SelfChangePolicy.require_current(approval.request, current_snapshot)
        return ApplicationRequest.create(
            application_id=f"{approval.request.rsi_id}:activation",
            improvement=approval.request.improvement,
            current_snapshot=current_snapshot,
            apply=True,
            governance_authority=approval,
        )

    @staticmethod
    def result_fields(
        request: RSIRequest,
        governance: SelfChangeGovernanceResult,
        *,
        approval: SelfChangeApproval | None,
        application: ApplicationResult | None,
    ) -> tuple[
        str,
        SelfChangeApproval | None,
        ApplicationResult | None,
        TargetSnapshot | None,
        tuple[RuntimeFailure, ...],
    ]:
        if governance.request != request:
            raise ValueError("RSI governance belongs to another request")
        expected: tuple[
            str,
            SelfChangeApproval | None,
            ApplicationResult | None,
            TargetSnapshot | None,
            tuple[RuntimeFailure, ...],
        ]
        if governance.disposition == "governance-failed":
            expected = (
                "governance-failed",
                None,
                None,
                request.declaration.target_snapshot,
                governance.operational_failures,
            )
        elif governance.disposition == "rejected":
            expected = (
                "governance-rejected",
                None,
                None,
                request.declaration.target_snapshot,
                governance.operational_failures,
            )
        elif not request.activate:
            expected = (
                "activation-disabled",
                None,
                None,
                request.declaration.target_snapshot,
                governance.operational_failures,
            )
        else:
            canonical_approval = SelfChangePolicy.approval(request, governance)
            if approval != canonical_approval or type(application) is not ApplicationResult:
                raise ValueError("activated RSI requires exact approval and application result")
            application_request = SelfChangePolicy.application_request(
                canonical_approval,
                current_snapshot=request.declaration.target_snapshot,
            )
            if application.request != application_request:
                raise ValueError("application result does not retain self-change approval")
            expected = (
                application.disposition,
                canonical_approval,
                application,
                application.authoritative_snapshot,
                (*governance.operational_failures, *application.operational_failures),
            )
        if expected[0] not in {
            "governance-failed",
            "governance-rejected",
            "activation-disabled",
            "verified",
            "rolled-back",
            "application-failed",
            "rollback-failed",
        }:
            raise ValueError(f"unsupported application projection for RSI: {expected[0]}")
        return expected

    @staticmethod
    def result(
        request: RSIRequest,
        governance: SelfChangeGovernanceResult,
        *,
        approval: SelfChangeApproval | None = None,
        application: ApplicationResult | None = None,
    ) -> RSIResult:
        disposition, expected_approval, expected_application, snapshot, failures = (
            SelfChangePolicy.result_fields(
                request,
                governance,
                approval=approval,
                application=application,
            )
        )
        return RSIResult(
            request=request,
            disposition=disposition,
            governance=governance,
            approval=expected_approval,
            application=expected_application,
            authoritative_snapshot=snapshot,
            operational_failures=failures,
            lineage=(
                request.ref,
                governance.ref,
                *((expected_approval.ref,) if expected_approval is not None else ()),
                *((expected_application.ref,) if expected_application is not None else ()),
                *((snapshot.ref,) if snapshot is not None else ()),
                *(item.ref for item in failures),
            ),
        )

    @staticmethod
    def requirement(
        declaration: MetaTargetDeclaration,
        governance: SelfChangeGovernancePolicy,
    ) -> ApplicationGovernanceRequirement:
        if type(declaration) is not MetaTargetDeclaration:
            raise TypeError("self-change requirements require a MetaTargetDeclaration")
        if type(governance) is not SelfChangeGovernancePolicy:
            raise TypeError("self-change requirements require a governance policy")
        configured = {item.change_class for item in governance.rules}
        missing = set(declaration.change_classes) - configured
        if missing:
            raise ValueError(f"self-change classes are not governed: {sorted(missing)}")
        return ApplicationGovernanceRequirement(
            requirement_id=f"{declaration.declaration_id}:application-governance",
            authority_record_type="self_change_approval",
            target_snapshot=declaration.target_snapshot,
            governing_refs=(declaration.ref, governance.ref),
            lineage=(declaration.target_snapshot.ref, declaration.ref, governance.ref),
        )
