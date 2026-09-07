from __future__ import annotations

from dataclasses import fields
from functools import lru_cache

from librsi import (
    FORWARD_SHADOW_ACTION_KIND,
    HISTORICAL_EVALUATION_ACTION_KIND,
    INDEPENDENT_REVIEW_ACTION_KIND,
    Action,
    ActionResult,
    CandidateReview,
    CapabilityRegistry,
    CapabilityRoute,
    MetaTargetDeclaration,
    RSIRequest,
    SelfChangeGovernancePolicy,
    deserialize_record,
    evaluation_command_from_action,
    make_evaluation_result,
    make_review_result,
    review_command_from_action,
    serialize_record,
)
from tests.block14_support import ComparisonContext, trial_batch
from tests.block15_support import DeterministicCycleProvider, improvement_request
from tests.block16_support import DeterministicApplicationTarget, application_registry


class DeterministicGovernanceProvider:
    def __init__(
        self,
        context: ComparisonContext,
        *,
        historical: str = "passed",
        forward_shadow: str = "passed",
        review: str = "accepted",
        reviewer_id: str = "independent-reviewer",
    ) -> None:
        self.context = context
        self.outcomes = {
            "historical": historical,
            "forward-shadow": forward_shadow,
        }
        self.review_disposition = review
        self.reviewer_id = reviewer_id
        self.experiment_actions: list[Action] = []
        self.review_actions: list[Action] = []

    def experiment(self, action: Action) -> ActionResult:
        self.experiment_actions.append(action)
        command = evaluation_command_from_action(action)
        outcome = self.outcomes[command.stage]
        rows = ((76.0, 16.0, 2.0),) * 3 if outcome == "passed" else ((72.0, 18.0, 2.0),) * 3
        invalid = (
            tuple((role, index) for role in ("baseline", "candidate") for index in range(3))
            if outcome == "inconclusive"
            else ()
        )
        batch = trial_batch(
            self.context,
            command.candidate,
            candidate_rows=rows,
            invalid=invalid,
            experiment_suffix=f":{command.stage}",
        )
        return make_evaluation_result(action=action, batch=batch)

    def review(self, action: Action) -> ActionResult:
        self.review_actions.append(action)
        command = review_command_from_action(action)
        review = CandidateReview(
            review_id=f"{command.request.root}:review",
            reviewer_id=self.reviewer_id,
            candidate=command.candidate,
            experiment=command.experiment,
            evaluation=command.evaluation,
            disposition=self.review_disposition,
            findings=(
                "independent evaluator accepts the exact shadow result"
                if self.review_disposition == "accepted"
                else "independent evaluator rejects the exact shadow result",
            ),
            lineage=(
                command.candidate.ref,
                command.experiment.ref,
                command.evaluation.ref,
            ),
        )
        return make_review_result(action=action, review=review)


def self_change_request(
    context: ComparisonContext,
    *,
    activate: bool = False,
    rollback_supported: bool = True,
    change_classes: tuple[str, ...] = ("selection-policy",),
    candidate_author_id: str = "candidate-author",
) -> RSIRequest:
    declaration = MetaTargetDeclaration.create(
        declaration_id="selector-self-change",
        target_snapshot=context.baseline_snapshot,
        change_classes=change_classes,
        candidate_author_id=candidate_author_id,
        rollback_supported=rollback_supported,
    )
    governance = SelfChangeGovernancePolicy.strict()
    from librsi import SelfChangePolicy

    requirement = SelfChangePolicy.requirement(declaration, governance)
    improvement = deserialize_record(
        _prepared_improvement(
            tuple(serialize_record(getattr(context, item.name)) for item in fields(context)),
            serialize_record(requirement),
        )
    )
    return RSIRequest.create(
        rsi_id="bounded-rsi",
        declaration=declaration,
        improvement=improvement,
        governance=governance,
        requested_by="system-owner",
        activate=activate,
    )


@lru_cache(maxsize=16)
def _prepared_improvement(context_records: tuple[str, ...], requirement_record: str) -> str:
    # Different workflow tests share this prerequisite, not the behavior under
    # test. Exact serialized inputs include metadata; immutable output bytes are
    # decoded afresh by each caller, so adversarial mutations cannot leak.
    from librsi import improve

    context = ComparisonContext(*(deserialize_record(item) for item in context_records))
    improvement = improve(
        improvement_request(context, governance_requirement=deserialize_record(requirement_record)),
        provider=DeterministicCycleProvider(context, (True,)),
        current_snapshot=context.baseline_snapshot,
    )
    return serialize_record(improvement)


def self_change_registry(
    governance: DeterministicGovernanceProvider | None,
    target: DeterministicApplicationTarget | None = None,
    *,
    governance_posture: str = "automatic",
    application_posture: str = "automatic",
) -> CapabilityRegistry:
    base = application_registry(
        target,
        apply_posture=application_posture,
        verify_posture=application_posture,
        rollback_posture=application_posture,
    )
    routes = (
        CapabilityRoute(
            HISTORICAL_EVALUATION_ACTION_KIND,
            "experimenter",
            governance_posture,
        ),
        CapabilityRoute(
            FORWARD_SHADOW_ACTION_KIND,
            "experimenter",
            governance_posture,
        ),
        CapabilityRoute(
            INDEPENDENT_REVIEW_ACTION_KIND,
            "reviewer",
            governance_posture,
        ),
        *base.routes,
    )
    implementations = tuple(item for item in (governance, target) if item is not None)
    return CapabilityRegistry(routes=routes, implementations=implementations)
