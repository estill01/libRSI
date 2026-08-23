from __future__ import annotations

from librsi import (
    APPLY_CANDIDATE_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
    Action,
    ActionResult,
    CandidateSnapshot,
    CapabilityRegistry,
    CapabilityRoute,
    RuntimeFailure,
    TargetSnapshot,
    application_command_from_action,
    make_application_failure,
    make_application_success,
    make_rollback_success,
    make_verification_result,
    rollback_input_from_action,
    verification_input_from_action,
)
from tests.block14_support import ComparisonContext, comparison_context, trial_batch


class DeterministicApplicationTarget:
    def __init__(
        self,
        baseline: TargetSnapshot,
        *,
        verification: str = "verified",
        fail_application: bool = False,
        fail_rollback: bool = False,
        context: ComparisonContext | None = None,
        actual_label: str = "actual",
    ) -> None:
        self.snapshot = baseline
        self.context = (
            comparison_context(target_kind=baseline.target.kind) if context is None else context
        )
        if self.context.baseline_snapshot != baseline:
            raise ValueError("application target context does not match its exact baseline")
        self.verification = verification
        self.fail_application = fail_application
        self.fail_rollback = fail_rollback
        self.actual_label = actual_label
        self.apply_calls: list[Action] = []
        self.verify_calls: list[Action] = []

    def apply(self, action: Action) -> ActionResult:
        self.apply_calls.append(action)
        if action.kind == APPLY_CANDIDATE_ACTION_KIND:
            command = application_command_from_action(action)
            if self.fail_application:
                return make_application_failure(
                    action=action,
                    failure=RuntimeFailure(
                        classification="execution",
                        message="synthetic application failed",
                    ),
                )
            candidate = command.candidate
            self.snapshot = TargetSnapshot(
                target=candidate.snapshot.target,
                state={**candidate.snapshot.state, "host_applied": self.actual_label},
                revision=f"{self.actual_label}-{candidate.snapshot.revision}",
                components=candidate.snapshot.components,
                lineage=(command.prior_snapshot.ref, candidate.ref),
            )
            return make_application_success(
                action=action,
                produced_snapshot=self.snapshot,
            )
        if action.kind == ROLLBACK_APPLICATION_ACTION_KIND:
            application, _ = rollback_input_from_action(action)
            if self.fail_rollback:
                return make_application_failure(
                    action=action,
                    failure=RuntimeFailure(
                        classification="execution",
                        message="synthetic rollback failed",
                    ),
                )
            self.snapshot = application.prior_snapshot
            return make_rollback_success(
                action=action,
                restored_snapshot=self.snapshot,
            )
        raise AssertionError("unexpected applier action")

    def verify(self, action: Action) -> ActionResult:
        self.verify_calls.append(action)
        application = verification_input_from_action(action)
        if self.verification == "unavailable":
            failure = RuntimeFailure(
                classification="execution",
                message="synthetic verifier infrastructure failure",
            )
            return make_verification_result(
                action=action,
                observed_snapshot=self.snapshot,
                operational_failure=failure,
            )
        command = application_command_from_action(application.action)
        actual_candidate = CandidateSnapshot.prepared(
            request=command.candidate.request,
            snapshot=self.snapshot,
            artifacts=command.candidate.artifacts,
        )
        rows = (
            ((76.0, 16.0, 2.0),) * 3
            if self.verification == "verified"
            else ((72.0, 18.0, 2.0),) * 3
        )
        return make_verification_result(
            action=action,
            observed_snapshot=self.snapshot,
            batch=trial_batch(self.context, actual_candidate, candidate_rows=rows),
        )


def application_registry(
    target: DeterministicApplicationTarget | None = None,
    *,
    apply_posture: str = "automatic",
    verify_posture: str = "automatic",
    rollback_posture: str = "automatic",
) -> CapabilityRegistry:
    routes = (
        CapabilityRoute(
            APPLY_CANDIDATE_ACTION_KIND,
            "applier",
            apply_posture,
        ),
        CapabilityRoute(
            VERIFY_APPLICATION_ACTION_KIND,
            "verifier",
            verify_posture,
        ),
        CapabilityRoute(
            ROLLBACK_APPLICATION_ACTION_KIND,
            "applier",
            rollback_posture,
        ),
    )
    return CapabilityRegistry(
        routes=routes,
        implementations=() if target is None else (target,),
    )
