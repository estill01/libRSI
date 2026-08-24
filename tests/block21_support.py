from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from librsi import (
    CapabilityBinding,
    CapabilityRegistry,
    CapabilityRoute,
    Evidence,
    TargetAdmission,
    ValidationEvidenceBatch,
    make_validation_evidence_result,
    validation_evidence_request_from_action,
)
from librsi.runtime import Action, ActionResult, RuntimeFailure
from librsi.service import LibRSIService
from librsi.validation import make_validation_evidence_failure
from tests.block20_support import target_admission, validation_result


@dataclass
class AutomaticValidationExperimenter:
    api_key: str = "service-secret-must-not-project"
    calls: int = 0

    def experiment(self, action: Action) -> ActionResult:
        self.calls += 1
        return validation_result(action)


@dataclass
class FailingValidationExperimenter:
    calls: int = 0

    def experiment(self, action: Action) -> ActionResult:
        self.calls += 1
        return make_validation_evidence_failure(
            action=action,
            failure=RuntimeFailure(classification="execution", message="bounded failure"),
        )


@dataclass
class InconclusiveValidationExperimenter:
    calls: int = 0

    def experiment(self, action: Action) -> ActionResult:
        self.calls += 1
        request = validation_evidence_request_from_action(action)
        evidence = Evidence(
            evidence_type="null",
            data={"observation": self.calls},
            subject_refs=(request.validation.claim.ref,),
            source_refs=(request.ref,),
            target_snapshot=request.validation.target_snapshot,
            weight=0.0,
        )
        return make_validation_evidence_result(
            action=action,
            batch=ValidationEvidenceBatch.collected(
                request=request,
                evidence=(evidence,),
            ),
        )


def automatic_validation_admission():
    return target_admission(
        capabilities=(
            CapabilityBinding(
                action_kind="validation-evidence",
                family="experimenter",
                posture="automatic",
            ),
        )
    )


def automatic_validation_registry(provider: object) -> CapabilityRegistry:
    return CapabilityRegistry(
        routes=(CapabilityRoute("validation-evidence", "experimenter", "automatic"),),
        implementations=(provider,),
    )


def automatic_admission(admission: TargetAdmission) -> TargetAdmission:
    """Rebuild an external protocol fixture with exact automatic authority."""

    capabilities = tuple(
        CapabilityBinding(
            action_kind=binding.action_kind,
            family=binding.family,
            posture="automatic",
        )
        for binding in admission.capabilities
    )
    return TargetAdmission.create(
        admission_id=admission.admission_id,
        target_snapshot=admission.target_snapshot,
        objective=admission.objective,
        evaluation_contract=admission.evaluation_contract,
        capabilities=capabilities,
        evidence_baseline=admission.evidence_baseline,
        application_requirement=admission.application_requirement,
        resource_limits=admission.resource_limits,
    )


class ManagedImprovementProvider:
    """Expose the deterministic hypothesis-to-intervention cycle as a Reasoner."""

    def __init__(self, provider: object) -> None:
        self.provider = provider

    def reason(self, action: Action) -> ActionResult:
        method = getattr(self.provider, "improve_cycle", None)
        if not callable(method):
            raise TypeError("managed improvement provider requires improve_cycle")
        result = method(action)
        if type(result) is not ActionResult:
            raise TypeError("managed improvement provider returned an invalid result")
        return result


def service(path: Path, provider: object | None = None) -> LibRSIService:
    registry = None if provider is None else automatic_validation_registry(provider)
    return LibRSIService.local(path, registry=registry)
