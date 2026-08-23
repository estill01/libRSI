from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from librsi import (
    APPLY_CANDIDATE_ACTION_KIND,
    FORWARD_SHADOW_ACTION_KIND,
    HISTORICAL_EVALUATION_ACTION_KIND,
    IMPROVEMENT_ACTION_KIND,
    INDEPENDENT_REVIEW_ACTION_KIND,
    INVESTIGATION_EXPERIMENT_ACTION_KIND,
    INVESTIGATION_REASONING_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
    ApplicationGovernanceRequirement,
    CapabilityBinding,
    Claim,
    Evidence,
    ExternalAgentController,
    InvestigationRequest,
    Question,
    TargetAdmission,
    ValidationEvidenceBatch,
    ValidationRequest,
    WorkflowRequest,
    make_validation_evidence_result,
    validation_evidence_request_from_action,
)
from librsi.runtime import Action, ActionResult
from tests.block13_support import IntentContext, intent_context
from tests.block14_support import comparison_context
from tests.block15_support import hypotheses, improvement_request
from tests.block17_support import self_change_request


@dataclass(frozen=True)
class ExternalWorkflowCase:
    command: str
    request: WorkflowRequest
    admission: TargetAdmission
    expected_action: str


def governance_requirement(context: IntentContext) -> ApplicationGovernanceRequirement:
    return ApplicationGovernanceRequirement(
        requirement_id="external-application-authority",
        authority_record_type="external_application_authority",
        target_snapshot=context.snapshot,
        governing_refs=(context.contract.ref,),
        lineage=(context.snapshot.ref, context.contract.ref),
    )


def target_admission(
    context: IntentContext | None = None,
    *,
    capabilities: tuple[CapabilityBinding, ...] | None = None,
) -> TargetAdmission:
    context = intent_context() if context is None else context
    routes = (
        (
            CapabilityBinding(
                action_kind="validation-evidence",
                family="experimenter",
                posture="external",
            ),
        )
        if capabilities is None
        else capabilities
    )
    return TargetAdmission.create(
        admission_id="fermenter-admission",
        target_snapshot=context.snapshot,
        objective=context.objective,
        evaluation_contract=context.contract,
        capabilities=routes,
        application_requirement=governance_requirement(context),
        resource_limits={
            "max_actions": 100,
            "max_failures": 100,
            "max_retries": 10,
            "units": 100,
        },
    )


def validation_request(context: IntentContext | None = None) -> ValidationRequest:
    context = intent_context() if context is None else context
    return ValidationRequest.for_claim(
        validation_id="external-validation",
        claim=Claim(
            statement="The admitted fermenter remains within its yield envelope",
            kind="behavioral",
            target=context.target,
        ),
        target_snapshot=context.snapshot,
        max_evidence_actions=1,
    )


def validation_result(action: Action) -> ActionResult:
    request = validation_evidence_request_from_action(action)
    evidence = Evidence(
        evidence_type="support",
        data={"yield_pct": 73.5},
        subject_refs=(request.validation.claim.ref,),
        source_refs=(request.ref,),
        target_snapshot=request.validation.target_snapshot,
        weight=1.0,
    )
    return make_validation_evidence_result(
        action=action,
        batch=ValidationEvidenceBatch.collected(request=request, evidence=(evidence,)),
    )


def controller(path: Path) -> ExternalAgentController:
    return ExternalAgentController.local(path)


def workflow_cases() -> tuple[ExternalWorkflowCase, ...]:
    validation = validation_request()
    validation_case = ExternalWorkflowCase(
        "validate",
        validation,
        target_admission(),
        "validation-evidence",
    )
    context = comparison_context()
    requirement = ApplicationGovernanceRequirement(
        requirement_id="external-application-authority",
        authority_record_type="external_application_authority",
        target_snapshot=context.baseline_snapshot,
        governing_refs=(context.contract.ref,),
        lineage=(context.baseline_snapshot.ref, context.contract.ref),
    )
    question = Question(
        prompt="Which mechanism changes the exact yield objective?",
        target=context.target,
        lineage=(context.baseline_snapshot.ref,),
    )
    investigation = InvestigationRequest.for_question(
        investigation_id="external-investigation",
        question=question,
        target_snapshot=context.baseline_snapshot,
        initial_hypotheses=hypotheses(question),
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    improvement = improvement_request(context, governance_requirement=requirement)
    rsi = self_change_request(context)
    routes = {
        "investigate": (
            CapabilityBinding(
                action_kind=INVESTIGATION_REASONING_ACTION_KIND,
                family="reasoner",
                posture="external",
            ),
            CapabilityBinding(
                action_kind=INVESTIGATION_EXPERIMENT_ACTION_KIND,
                family="experimenter",
                posture="external",
            ),
        ),
        "improve": (
            CapabilityBinding(
                action_kind=IMPROVEMENT_ACTION_KIND,
                family="reasoner",
                posture="external",
            ),
        ),
        "rsi": tuple(
            CapabilityBinding(action_kind=kind, family=family, posture="external")
            for kind, family in (
                (HISTORICAL_EVALUATION_ACTION_KIND, "experimenter"),
                (FORWARD_SHADOW_ACTION_KIND, "experimenter"),
                (INDEPENDENT_REVIEW_ACTION_KIND, "reviewer"),
                (APPLY_CANDIDATE_ACTION_KIND, "applier"),
                (VERIFY_APPLICATION_ACTION_KIND, "verifier"),
                (ROLLBACK_APPLICATION_ACTION_KIND, "applier"),
            )
        ),
    }
    requests = (
        ("investigate", investigation, requirement, INVESTIGATION_REASONING_ACTION_KIND),
        ("improve", improvement, requirement, IMPROVEMENT_ACTION_KIND),
        (
            "rsi",
            rsi,
            rsi.improvement.request.governance_requirement,
            HISTORICAL_EVALUATION_ACTION_KIND,
        ),
    )
    cases = [validation_case]
    for command, request, application_requirement, expected_action in requests:
        assert application_requirement is not None
        cases.append(
            ExternalWorkflowCase(
                command,
                request,
                TargetAdmission.create(
                    admission_id=f"{command}-admission",
                    target_snapshot=context.baseline_snapshot,
                    objective=context.contract.objectives[0],
                    evaluation_contract=context.contract,
                    capabilities=routes[command],
                    application_requirement=application_requirement,
                    resource_limits={
                        "max_actions": 100,
                        "max_failures": 100,
                        "max_retries": 10,
                        "units": 100,
                    },
                ),
                expected_action,
            )
        )
    return tuple(cases)
